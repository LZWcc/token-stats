#!/usr/bin/env python3
"""token-stats 主机端：扫描本机和各远端（ssh）的日志，逐请求写入中央 usage.db，导出每天的合计数据。

远端零安装、零写入：scan.py 的源码经 ssh 发给远端 `python3 -` 执行，只回传新增请求和读取进度。
只用标准库，兼容 Python 3.9。规则见 PROJECT.md 第 3、5、7 节。
"""
import argparse
import fcntl
import json
import os
import sqlite3
import subprocess
import time

import scan

# Asia/Shanghai 自 1991 年起无夏令时，固定 +8，避免依赖系统 tzdata
TZ_OFFSET_SEC = 8 * 3600
# 本机（主机自己）的机器名，collector 与 CC Switch 导入共用，保证按机器选来源时对得上
LOCAL = 'local'

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

# 不交互、不卡住；覆盖用户 ssh 配置里可能有的 RemoteCommand / RequestTTY。不改任何 ssh 配置
SSH_OPTS = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'RemoteCommand=none',
            '-o', 'RequestTTY=no', '-o', 'Compression=yes']


def lock(db):
    """防止两个进程同时写同一个 usage.db。锁文件放在库旁边，进程退出时自动释放；返回值需保持引用。"""
    f = open(db + '.lock', 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('已有另一个 token-stats 进程在使用 %s，本次退出' % db)
    return f


def log_roots(claude_dirs=None, codex_home='~/.codex'):
    return {'claude-code': claude_dirs or ['~/.claude/projects', '~/.config/claude/projects'],
            'codex': [os.path.join(codex_home, 'sessions'), os.path.join(codex_home, 'archived_sessions')]}


def known_files(conn, machine):
    q = 'SELECT path, size, mtime, offset, state FROM files WHERE machine = ?'
    return {p: [size, mtime, offset, state] for p, size, mtime, offset, state in conn.execute(q, (machine,))}


def remote_program(roots, known):
    """发给远端 `python3 -` 的程序：scan.py 源码 + 一行调用。参数以 JSON 字符串字面量嵌入。"""
    with open(scan.__file__, encoding='utf-8') as f:
        source = f.read()
    return source + '\nremote(json.loads(%r))\n' % json.dumps({'roots': roots, 'known': known})


def remote_events(host, roots, known):
    # -B 不写 .pyc（以管理员身份运行时可能写进系统库目录），-I 忽略远端环境变量和用户 site-packages
    p = subprocess.Popen(['ssh'] + SSH_OPTS + [host, 'python3', '-I', '-B', '-'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # 远端 python 先读完整个 stdin 才开始执行，所以先写完再读输出不会互相阻塞
    p.stdin.write(remote_program(roots, known).encode('utf-8'))
    p.stdin.close()
    for line in p.stdout:
        yield json.loads(line)
    err = p.stderr.read().decode('utf-8', 'replace').strip()
    if p.wait() != 0:
        raise RuntimeError('ssh %s 退出码 %d：%s' % (host, p.returncode, err.splitlines()[-1] if err else ''))


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


def export(conn, out_dir, stats):
    q = """SELECT machine, agent, date(ts / 1000 + ?, 'unixepoch') AS d, source, model,
                  sum(input), sum(cache_write), sum(cache_read), sum(output)
           FROM requests GROUP BY machine, agent, d, source, model"""
    groups = {}
    for machine, agent, d, source, model, *vals in conn.execute(q, (TZ_OFFSET_SEC,)):
        groups.setdefault((machine, agent, d), {}).setdefault(source, []).append((model, vals))
    days = {}
    for (machine, agent, d), by_source in groups.items():
        # 先按机器选来源：这台机器这个 agent 这天有 CC Switch 数据就只用它（那时的日志已被清理、不完整）
        day = days.setdefault(d, {'agents': {}, 'models': {}})
        for model, vals in by_source.get('cc-switch') or by_source['log']:
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True, help='usage.db 路径')
    ap.add_argument('--out', required=True, help='导出目录，即仓库的 data/daily')
    ap.add_argument('--remote', action='append', default=[], metavar='HOST',
                    help='另外经 ssh 扫描远端日志，可重复；HOST 为 ssh 主机名，也作为本地记录的机器名')
    ap.add_argument('--claude-dir', action='append',
                    help='本机 Claude Code projects 目录，可重复；默认 ~/.claude/projects 和 ~/.config/claude/projects')
    ap.add_argument('--codex-home', default='~/.codex', help='本机 Codex 目录，默认 ~/.codex')
    args = ap.parse_args()

    held = lock(args.db)  # 保持锁文件句柄直到进程退出
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    # 本机总是扫描；远端由 --remote 指定
    roots = log_roots(args.claude_dir, args.codex_home)
    roots = {a: [os.path.abspath(os.path.expanduser(d)) for d in ds] for a, ds in roots.items()}
    jobs = [(LOCAL, lambda known: scan.scan(roots, known))]
    for host in args.remote:
        jobs.append((host, lambda known, host=host: remote_events(host, log_roots(), known)))

    # 按机器隔离失败：一台连不上不影响其他机器
    for machine, events in jobs:
        try:
            stats = apply(conn, machine, events(known_files(conn, machine)))
        except (OSError, RuntimeError, ValueError) as e:
            with conn:
                conn.execute('INSERT INTO machines (machine, last_error) VALUES (?, ?) '
                             'ON CONFLICT (machine) DO UPDATE SET last_error = excluded.last_error', (machine, str(e)))
            print(machine, '失败：', e)
            continue
        with conn:
            conn.execute('INSERT OR REPLACE INTO machines VALUES (?, ?, NULL)', (machine, int(time.time() * 1000)))
        print(machine, ' '.join('%s=%d' % kv for kv in stats.items() if kv[1]) or '无日志')
    stats = {'export_written': 0, 'export_unchanged': 0}
    export(conn, args.out, stats)
    print('export', ' '.join('%s=%d' % kv for kv in stats.items()))
    conn.close()


if __name__ == '__main__':
    main()
