"""测试用的合成日志、临时目录与时区。所有数据都是手写的假数据，不含任何真实日志。"""
import json
import os
import shutil
import tempfile
import unittest


def claude_line(msg_id, req_id, ts, model='claude-test-1', i=10, cw=20, cr=30, o=40):
    """一行 Claude Code 日志：带 message.usage 的 assistant 消息。req_id 为 None 时不写 requestId。"""
    o_ = {'type': 'assistant', 'timestamp': ts,
          'message': {'id': msg_id, 'model': model, 'usage': {
              'input_tokens': i, 'cache_creation_input_tokens': cw, 'cache_read_input_tokens': cr, 'output_tokens': o}}}
    if req_id is not None:
        o_['requestId'] = req_id
    return json.dumps(o_)


def codex_usage(i, cached, write, o, reasoning=0):
    return {'input_tokens': i, 'cached_input_tokens': cached, 'cache_write_input_tokens': write,
            'output_tokens': o, 'reasoning_output_tokens': reasoning, 'total_tokens': i + o}


def codex_context(ts, model):
    return json.dumps({'timestamp': ts, 'type': 'turn_context', 'payload': {'model': model}})


def codex_record(ts, rid, usage):
    """新格式：一行一个请求。"""
    return json.dumps({'timestamp': ts, 'type': 'token_usage_record', 'payload': {'response_id': rid, 'usage': usage}})


def codex_count(ts, total, last):
    """老格式：token_count 事件；total 为 None 时 info 为 null。"""
    info = None if total is None else {'total_token_usage': total, 'last_token_usage': last}
    return json.dumps({'timestamp': ts, 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': info}})


def write_lines(path, lines, mode='w'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding='utf-8', newline='\n') as f:
        f.write(''.join(line + '\n' for line in lines))


def zone(name):
    """有时区数据时返回 ZoneInfo，否则 None（Windows 上的标准库不带 tzdata）。"""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except (ImportError, KeyError, ValueError):
        return None


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ts-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)
