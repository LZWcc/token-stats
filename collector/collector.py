#!/usr/bin/env python3
"""token-stats collector：增量解析本机 Claude Code / Codex 日志，逐请求写入 usage.db，导出日数据。

只读日志；只用标准库，兼容 Python 3.9。规则见 PROJECT.md 第 5–7 节。
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime

# Asia/Shanghai 自 1991 年起无夏令时，固定 +8，避免依赖系统 tzdata
TZ_OFFSET_SEC = 8 * 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
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
  path   TEXT PRIMARY KEY,
  size   INTEGER NOT NULL,
  mtime  INTEGER NOT NULL,
  offset INTEGER NOT NULL,
  state  TEXT    NOT NULL
);
"""

# 同一请求多次出现时：时间取最早的一次（fork 会话复制的事件时间戳被改写过）；
# token 数取 output 最大的一次（第三方模型流式响应的中间行 output 还没写全）。与读取顺序无关。
# SQLite 的 UPDATE SET 中列名引用的都是旧值。
UPSERT = """
INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)
ON CONFLICT (agent, request_key) DO UPDATE SET
  ts          = min(ts, excluded.ts),
  model       = CASE WHEN excluded.ts < ts THEN excluded.model ELSE model END,
  input       = CASE WHEN excluded.output > output THEN excluded.input ELSE input END,
  cache_write = CASE WHEN excluded.output > output THEN excluded.cache_write ELSE cache_write END,
  cache_read  = CASE WHEN excluded.output > output THEN excluded.cache_read ELSE cache_read END,
  output      = max(output, excluded.output)
WHERE excluded.ts < ts OR excluded.output > output
"""

FIELDS = ('input', 'cache_write', 'cache_read', 'output')
CODEX_TOTAL_KEYS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                    'output_tokens', 'reasoning_output_tokens', 'total_tokens')


def to_ms(ts):
    # 日志时间戳形如 2026-10-20T03:12:45.123Z；3.9 的 fromisoformat 不认 Z
    return int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() * 1000)


def parse_claude(o, state, path):
    """一行 Claude Code 日志 → (request_key, ts, model, input, cache_write, cache_read, output) 或 None。"""
    msg = o.get('message')
    if not isinstance(msg, dict) or not isinstance(msg.get('usage'), dict) or not msg.get('id'):
        return None
    u = msg['usage']
    return ('%s:%s' % (msg['id'], o.get('requestId') or ''), to_ms(o['timestamp']), msg.get('model') or 'unknown',
            u.get('input_tokens') or 0, u.get('cache_creation_input_tokens') or 0,
            u.get('cache_read_input_tokens') or 0, u.get('output_tokens') or 0)


def codex_usage(u):
    cached = u.get('cached_input_tokens') or 0
    write = u.get('cache_write_input_tokens') or 0
    # 原始 input 含缓存读和缓存写；output 已含 reasoning
    return ((u.get('input_tokens') or 0) - cached - write, write, cached, u.get('output_tokens') or 0)


def parse_codex(o, state, path):
    """一行 Codex 日志 → 同上。state 跨行（跨增量读取）保存 model / rec。"""
    t = o.get('type')
    pl = o.get('payload')
    if not isinstance(pl, dict):
        return None
    if t == 'turn_context':
        state['model'] = pl.get('model')
    elif t == 'token_usage_record':
        # 新格式：一行一个请求；出现后同文件的 token_count 只是重复汇报
        state['rec'] = True
        return (pl['response_id'], to_ms(o['timestamp']), state.get('model') or 'unknown') + codex_usage(pl['usage'])
    elif pl.get('type') == 'token_count' and not state.get('rec') and isinstance(pl.get('info'), dict):
        # 老格式：以累计用量本身为主键。累计值不变的重复事件、fork 会话整段复制的父会话事件
        # （时间戳被改写、累计值不变）主键都相同，只记一行
        info = pl['info']
        tot = info['total_token_usage']
        key = 'total:' + ','.join(str(tot.get(k) or 0) for k in CODEX_TOTAL_KEYS)
        return (key, to_ms(o['timestamp']), state.get('model') or 'unknown') + codex_usage(info['last_token_usage'])
    return None


def iter_files(agent, roots):
    exts = ('.jsonl', '.jsonl.zst') if agent == 'codex' else ('.jsonl',)
    for root in roots:
        for dp, _, fs in os.walk(root):
            for f in sorted(fs):
                if f.endswith(exts):
                    yield os.path.join(dp, f)


def read_new(path, offset, zstd):
    """返回 (待解析的字节, 新 offset)。未压缩文件只消费到最后一个换行，半行留到下次。"""
    if path.endswith('.zst'):
        data = subprocess.run([zstd, '-dc', path], check=True, stdout=subprocess.PIPE).stdout
        return data, os.path.getsize(path)
    with open(path, 'rb') as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b'\n') + 1
    return data[:end], offset + end


def collect(conn, agent, roots, stats, zstd):
    parse = parse_codex if agent == 'codex' else parse_claude
    # 先用子串粗筛，只对可能有用的行做 json 解析
    needles = (b'turn_context', b'token_usage_record', b'token_count') if agent == 'codex' else (b'"usage"',)
    for path in iter_files(agent, roots):
        st = os.stat(path)
        row = conn.execute('SELECT size, mtime, offset, state FROM files WHERE path = ?', (path,)).fetchone()
        if row and row[0] == st.st_size and row[1] == st.st_mtime_ns:
            stats['files_unchanged'] += 1
            continue
        if path.endswith('.zst') and not zstd:
            stats['zst_skipped_no_zstd'] += 1
            continue
        if row and not path.endswith('.zst') and st.st_size > row[0]:
            offset, state = row[2], json.loads(row[3])
        else:
            offset, state = 0, {}
        data, new_offset = read_new(path, offset, zstd)
        rows = []
        for line in data.splitlines():
            if not any(n in line for n in needles):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                stats['bad_json'] += 1
                continue
            r = parse(o, state, path)
            # 四项全为 0 的行（如 Claude 的 <synthetic> 消息）不记
            if r and any(r[3:]):
                rows.append((agent,) + r + ('log',))
        with conn:
            before = conn.total_changes
            conn.executemany(UPSERT, rows)
            stats['rows_written'] += conn.total_changes - before
            conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?)',
                         (path, st.st_size, st.st_mtime_ns, new_offset, json.dumps(state)))
        stats['files_read'] += 1
        stats['rows_parsed'] += len(rows)


def export(conn, machine, out_dir, stats):
    days = {}
    q = """SELECT agent, date(ts / 1000 + ?, 'unixepoch') AS d, model, source,
                  sum(input), sum(cache_write), sum(cache_read), sum(output)
           FROM requests GROUP BY agent, d, model, source ORDER BY agent, d, model"""
    for agent, d, model, source, *vals in conn.execute(q, (TZ_OFFSET_SEC,)):
        days.setdefault((agent, d), {}).setdefault(source, {})[model] = dict(zip(FIELDS, vals))
    for (agent, d), by_source in days.items():
        # 某天有 CC Switch 数据就只用它（那时的日志已被清理、不完整），否则用日志
        source = 'cc-switch' if 'cc-switch' in by_source else 'log'
        models = by_source[source]
        obj = {'machine': machine, 'agent': agent, 'date': d}
        for k in FIELDS:
            obj[k] = sum(m[k] for m in models.values())
        obj['source'] = source
        obj['models'] = models
        text = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
        p = os.path.join(out_dir, machine, agent, d + '.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                if f.read() == text:
                    stats['export_unchanged'] += 1
                    continue
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        stats['export_written'] += 1


def main():
    home = os.path.expanduser('~')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--machine', required=True, help='公开 id，如 laptop / server-1')
    ap.add_argument('--db', required=True, help='usage.db 路径')
    ap.add_argument('--out', required=True, help='导出目录，即仓库的 data/daily')
    ap.add_argument('--claude-dir', action='append',
                    help='Claude Code projects 目录，可重复；默认 ~/.claude/projects 和 ~/.config/claude/projects')
    ap.add_argument('--codex-home', default=os.path.join(home, '.codex'), help='默认 ~/.codex')
    args = ap.parse_args()

    claude_dirs = args.claude_dir or [os.path.join(home, '.claude', 'projects'),
                                      os.path.join(home, '.config', 'claude', 'projects')]
    codex_dirs = [os.path.join(args.codex_home, d) for d in ('sessions', 'archived_sessions')]
    # launchd / 非交互 shell 的 PATH 里通常没有 Homebrew
    zstd = shutil.which('zstd') or next((p for p in ('/opt/homebrew/bin/zstd', '/usr/local/bin/zstd')
                                         if os.path.exists(p)), None)

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    for agent, roots in (('claude-code', claude_dirs), ('codex', codex_dirs)):
        stats = dict.fromkeys(('files_read', 'files_unchanged', 'rows_parsed', 'rows_written',
                               'bad_json', 'zst_skipped_no_zstd'), 0)
        collect(conn, agent, [r for r in roots if os.path.isdir(r)], stats, zstd)
        print(agent, ' '.join('%s=%d' % kv for kv in stats.items() if kv[1]) or '无日志')
    stats = {'export_written': 0, 'export_unchanged': 0}
    export(conn, args.machine, args.out, stats)
    print('export', ' '.join('%s=%d' % kv for kv in stats.items()))
    conn.close()


if __name__ == '__main__':
    main()
