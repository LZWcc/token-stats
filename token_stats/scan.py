"""日志扫描：增量解析 Claude Code / Codex 日志，产出逐请求记录和各文件的读取进度。

主机上由 collector.py 直接调用；扫描远端时，本文件源码原样经 ssh 发给远端 `python3 -` 执行（见 remote()）。
所以只能用标准库、不能 import 本项目的其他文件、不能写任何文件。兼容 Python 3.9。规则见 PROJECT.md 第 5、6 节。
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

CODEX_TOTAL_KEYS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                    'output_tokens', 'reasoning_output_tokens', 'total_tokens')


def to_ms(ts):
    # 日志时间戳形如 2026-10-20T03:12:45.123Z；3.9 的 fromisoformat 不认 Z
    return int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() * 1000)


def parse_claude(o, state):
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


def parse_codex(o, state):
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


# agent → (解析函数, 粗筛子串：只对含这些子串的行做 json 解析, 文件扩展名)
AGENTS = {
    'claude-code': (parse_claude, (b'"usage"',), ('.jsonl',)),
    'codex': (parse_codex, (b'turn_context', b'token_usage_record', b'token_count'), ('.jsonl', '.jsonl.zst')),
}


def find_zstd():
    # launchd / 非交互 shell 的 PATH 里通常没有 Homebrew
    return shutil.which('zstd') or next((p for p in ('/opt/homebrew/bin/zstd', '/usr/local/bin/zstd')
                                         if os.path.exists(p)), None)


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


def scan(roots, known):
    """roots：{agent: [目录]}；known：{path: [size, mtime, offset, state]}，即上次的读取进度。

    逐个产出事件：
      ['row', agent, request_key, ts, model, input, cache_write, cache_read, output]
      ['file', path, size, mtime, offset, state]   在该文件的 row 之后产出
      ['stats', {...}]                             最后产出
    """
    zstd = find_zstd()
    stats = dict.fromkeys(('files_read', 'files_unchanged', 'rows', 'bad_json', 'zst_skipped', 'vanished'), 0)
    for agent, dirs in roots.items():
        parse, needles, exts = AGENTS[agent]
        for root in dirs:
            for dp, _, fs in os.walk(root):
                for f in sorted(fs):
                    if not f.endswith(exts):
                        continue
                    path = os.path.join(dp, f)
                    zst = path.endswith('.zst')
                    try:
                        st = os.stat(path)
                        prev = known.get(path)
                        if prev and prev[0] == st.st_size and prev[1] == st.st_mtime_ns:
                            stats['files_unchanged'] += 1
                            continue
                        if zst and not zstd:
                            stats['zst_skipped'] += 1
                            continue
                        if prev and not zst and st.st_size > prev[0]:
                            offset, state = prev[2], json.loads(prev[3])
                        else:
                            offset, state = 0, {}
                        data, new_offset = read_new(path, offset, zstd)
                    except FileNotFoundError:
                        # 扫描途中被 Claude Code 按保留期清理
                        stats['vanished'] += 1
                        continue
                    for line in data.splitlines():
                        if not any(n in line for n in needles):
                            continue
                        try:
                            o = json.loads(line)
                        except ValueError:
                            stats['bad_json'] += 1
                            continue
                        r = parse(o, state)
                        # 四项全为 0 的行（如 Claude 的 <synthetic> 消息）不记
                        if r and any(r[3:]):
                            stats['rows'] += 1
                            yield ['row', agent] + list(r)
                    stats['files_read'] += 1
                    yield ['file', path, st.st_size, st.st_mtime_ns, new_offset, json.dumps(state)]
    yield ['stats', stats]


def remote(params):
    """在远端执行：目录按远端家目录展开，事件逐行以 JSON 写到 stdout。"""
    roots = {agent: [os.path.expanduser(d) for d in dirs] for agent, dirs in params['roots'].items()}
    for ev in scan(roots, params['known']):
        sys.stdout.write(json.dumps(ev) + '\n')
