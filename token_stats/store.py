"""中央 usage.db：表结构、写入与去重、导出日数据、合并、改名、备份、文件锁。规则见 PROJECT.md 第 5、7 节。"""
import glob
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from .config import local_day

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
  machine     TEXT    NOT NULL,
  agent       TEXT    NOT NULL,
  request_key TEXT    NOT NULL,
  ts          INTEGER NOT NULL,
  model       TEXT    NOT NULL,
  input       INTEGER NOT NULL,
  cache_write INTEGER NOT NULL,
  cache_read  INTEGER NOT NULL,
  output      INTEGER NOT NULL,
  source      TEXT    NOT NULL,
  PRIMARY KEY (agent, request_key)
);
CREATE TABLE IF NOT EXISTS files (
  machine TEXT    NOT NULL,
  path    TEXT    NOT NULL,
  size    INTEGER NOT NULL,
  mtime   INTEGER NOT NULL,
  offset  INTEGER NOT NULL,
  state   TEXT    NOT NULL,
  PRIMARY KEY (machine, path)
);
CREATE TABLE IF NOT EXISTS machines (
  machine    TEXT PRIMARY KEY,
  last_ok    INTEGER,
  last_error TEXT
);
"""

# 主键不含 machine：同一请求出现在多台机器的日志里也只记一行。
# 同一请求多次出现时：时间取最早的一次（fork 会话复制的事件时间戳被改写过），machine、model 跟随最早那次；
# token 数取 output 最大的一次（第三方模型流式响应的中间行 output 还没写全）。与读取顺序无关。
# SQLite 的 UPDATE SET 中列名引用的都是旧值。
UPSERT = """
INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?)
ON CONFLICT (agent, request_key) DO UPDATE SET
  ts          = min(ts, excluded.ts),
  machine     = CASE WHEN excluded.ts < ts THEN excluded.machine ELSE machine END,
  model       = CASE WHEN excluded.ts < ts THEN excluded.model ELSE model END,
  input       = CASE WHEN excluded.output > output THEN excluded.input ELSE input END,
  cache_write = CASE WHEN excluded.output > output THEN excluded.cache_write ELSE cache_write END,
  cache_read  = CASE WHEN excluded.output > output THEN excluded.cache_read ELSE cache_read END,
  output      = max(output, excluded.output)
WHERE excluded.ts < ts OR excluded.output > output
"""

FIELDS = ('input', 'cache_write', 'cache_read', 'output')
BACKUPS_KEPT = 7


def lock(db):
    """防止两个进程同时写同一个 usage.db。锁文件放在库旁边，进程退出时自动释放；返回值需保持引用。"""
    os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    f = open(db + '.lock', 'a+')
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit('已有另一个 token-stats 进程在使用 %s，本次退出' % db)
    return f


def connect(db):
    if db != ':memory:':
        os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    return conn


def known_files(conn, machine):
    q = 'SELECT path, size, mtime, offset, state FROM files WHERE machine = ?'
    return {p: [size, mtime, offset, state] for p, size, mtime, offset, state in conn.execute(q, (machine,))}


def apply(conn, machine, events):
    """把扫描事件写入 usage.db：一个文件的行和它的新进度在同一个事务里提交。"""
    stats = {'rows_written': 0}
    rows = []
    for ev in events:
        if ev[0] == 'row':
            rows.append((machine,) + tuple(ev[1:]) + ('log',))
        elif ev[0] == 'file':
            with conn:
                before = conn.total_changes
                conn.executemany(UPSERT, rows)
                stats['rows_written'] += conn.total_changes - before
                conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)', (machine,) + tuple(ev[1:]))
            rows = []
        elif ev[0] == 'stats':
            stats.update(ev[1])
    return stats


def set_status(conn, machine, error=None):
    """记录一台机器这次采集的结果：成功更新 last_ok 并清空错误，失败只记错误。"""
    with conn:
        if error is None:
            conn.execute('INSERT OR REPLACE INTO machines VALUES (?, ?, NULL)', (machine, int(time.time() * 1000)))
        else:
            conn.execute('INSERT INTO machines (machine, last_error) VALUES (?, ?) '
                         'ON CONFLICT (machine) DO UPDATE SET last_error = excluded.last_error', (machine, error))


def export(conn, out_dir, tz):
    """从 usage.db 重算每天的合计，写 <out_dir>/<YYYY-MM-DD>.json；内容没变的不重写，不再有数据的日期文件删除。"""
    stats = {'export_written': 0, 'export_unchanged': 0, 'export_removed': 0}
    groups = {}
    q = 'SELECT machine, agent, ts, source, model, input, cache_write, cache_read, output FROM requests'
    for machine, agent, ts, source, model, *vals in conn.execute(q):
        # 在 Python 里按时区逐行换算日期，才能正确处理夏令时（SQLite 只支持固定偏移）
        d = local_day(ts, tz).isoformat()
        m = groups.setdefault((machine, agent, d), {}).setdefault(source, {}).setdefault(model, [0, 0, 0, 0])
        for i, v in enumerate(vals):
            m[i] += v
    days = {}
    for (machine, agent, d), by_source in groups.items():
        # 先按机器选来源：这台机器这个 agent 这天有 CC Switch 数据就只用它（那时的日志已被清理、不完整）
        day = days.setdefault(d, {'agents': {}, 'models': {}})
        for model, vals in (by_source.get('cc-switch') or by_source['log']).items():
            for part, name in (('agents', agent), ('models', model)):
                m = day[part].setdefault(name, dict.fromkeys(FIELDS, 0))
                for k, v in zip(FIELDS, vals):
                    m[k] += v
    os.makedirs(out_dir, exist_ok=True)
    for d, day in days.items():
        obj = {'date': d}
        for k in FIELDS:
            obj[k] = sum(a[k] for a in day['agents'].values())
        obj['agents'] = dict(sorted(day['agents'].items()))
        obj['models'] = dict(sorted(day['models'].items()))
        text = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
        p = os.path.join(out_dir, d + '.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                if f.read() == text:
                    stats['export_unchanged'] += 1
                    continue
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        stats['export_written'] += 1
    # 例如改时区后，有的日期不再有数据：只删本目录下日期命名的文件
    for f in os.listdir(out_dir):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f) and f[:-5] not in days:
            os.remove(os.path.join(out_dir, f))
            stats['export_removed'] += 1
    return stats


def merge_db(conn, path, name):
    """把另一台机器自己的 usage.db 合并进来：只取请求，机器名一律记为 name；靠主键去重，可重复执行。"""
    src = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = [(name,) + r for r in src.execute(
            'SELECT agent, request_key, ts, model, input, cache_write, cache_read, output, source FROM requests')]
    finally:
        src.close()
    with conn:
        before = conn.total_changes
        conn.executemany(UPSERT, rows)
        return conn.total_changes - before, len(rows)


def rename(conn, old, new):
    """改机器名：三张表一起改，读取进度才对得上。新名字已被使用时拒绝，避免两台机器的进度混在一起。"""
    tables = ('requests', 'files', 'machines')
    for t in tables:
        if conn.execute('SELECT 1 FROM %s WHERE machine = ? LIMIT 1' % t, (new,)).fetchone():
            raise ValueError('机器名 %s 已在使用' % new)
    counts = {}
    with conn:
        for t in tables:
            counts[t] = conn.execute('UPDATE %s SET machine = ? WHERE machine = ?' % t, (new, old)).rowcount
    return counts


def backup(conn, backups_dir, day):
    """每天备份一份 usage.db，保留最近 BACKUPS_KEPT 份；当天已备份过就跳过。返回新备份的路径或 None。"""
    path = os.path.join(backups_dir, 'usage-%s.db' % day)
    if os.path.exists(path):
        return None
    os.makedirs(backups_dir, exist_ok=True)
    dst = sqlite3.connect(path)
    try:
        conn.backup(dst)
    finally:
        dst.close()
    for old in sorted(glob.glob(os.path.join(backups_dir, 'usage-*.db')))[:-BACKUPS_KEPT]:
        os.remove(old)
    return path
