"""日志解析与增量读取（PROJECT.md 第 6 节）。"""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from token_stats import remote, scan
from tests.helpers import (TempDirTest, claude_line, codex_context, codex_count, codex_record, codex_usage,
                           write_lines)

TS = '2026-01-02T03:04:05.678Z'
TS_MS = scan.to_ms(TS)


def run_scan(roots, known=None):
    evs = list(scan.scan(roots, known or {}))
    rows = [e for e in evs if e[0] == 'row']
    files = {e[1]: e[2:] for e in evs if e[0] == 'file'}   # path → [size, mtime, offset, state]
    return rows, files, evs[-1][1]


class ClaudeTest(TempDirTest):
    def scan_lines(self, lines):
        write_lines(self.path('claude', 'p', 's.jsonl'), lines)
        return run_scan({'claude-code': [self.path('claude')]})

    def test_fields(self):
        rows, _, stats = self.scan_lines([claude_line('m1', 'r1', TS, 'claude-x', 1, 2, 3, 4)])
        self.assertEqual(rows, [['row', 'claude-code', 'm1:r1', TS_MS, 'claude-x', 1, 2, 3, 4]])
        self.assertEqual(stats['rows'], 1)

    def test_missing_request_id(self):
        rows, _, _ = self.scan_lines([claude_line('m2', None, TS)])
        self.assertEqual(rows[0][2], 'm2:')

    def test_skips_zero_and_non_usage_and_counts_bad_json(self):
        rows, _, stats = self.scan_lines([
            claude_line('m3', 'r3', TS, '<synthetic>', 0, 0, 0, 0),             # 四项全 0
            json.dumps({'type': 'user', 'message': {'content': 'usage'}}),       # 含 "usage" 子串但没有 usage 字段
            '{"usage": ',                                                         # 坏 JSON
            claude_line('m4', 'r4', TS)])
        self.assertEqual([r[2] for r in rows], ['m4:r4'])
        self.assertEqual(stats['bad_json'], 1)


class CodexTest(TempDirTest):
    def scan_lines(self, lines, name='rollout.jsonl'):
        write_lines(self.path('codex', name), lines)
        return run_scan({'codex': [self.path('codex')]})

    def test_old_format(self):
        total = codex_usage(100, 60, 10, 5)
        rows, _, _ = self.scan_lines([
            codex_count(TS, codex_usage(1, 0, 0, 1), codex_usage(1, 0, 0, 0)),   # turn_context 之前：模型记为 unknown
            codex_context(TS, 'gpt-test'),
            codex_count(TS, None, None),                                           # info 为 null
            codex_count(TS, total, total),
            codex_count(TS, total, total)])                                        # 累计值不变的重复事件
        self.assertEqual(rows[0][4], 'unknown')
        rest = rows[1:]
        self.assertEqual(len(rest), 2)
        key = 'total:100,60,10,5,0,105'
        # input 减去缓存读和缓存写；cache_read = cached；output 已含 reasoning
        self.assertEqual(rest[0], ['row', 'codex', key, TS_MS, 'gpt-test', 30, 10, 60, 5])
        self.assertEqual(rest[1][2], key)   # 主键相同，入库时只记一行

    def test_new_format_ignores_later_token_count(self):
        u = codex_usage(50, 20, 0, 7, reasoning=3)
        rows, _, _ = self.scan_lines([
            codex_context(TS, 'gpt-new'),
            codex_record(TS, 'resp_1', u),
            codex_count(TS, u, u)])
        self.assertEqual(rows, [['row', 'codex', 'resp_1', TS_MS, 'gpt-new', 30, 0, 20, 7]])

    def test_zst(self):
        zstd = scan.find_zstd()
        if not zstd:
            self.skipTest('没有 zstd')
        p = self.path('codex', 'r.jsonl')
        write_lines(p, [codex_context(TS, 'gpt-z'), codex_record(TS, 'resp_z', codex_usage(9, 0, 0, 1))])
        subprocess.run([zstd, '-q', '--rm', p, '-o', p + '.zst'], check=True)
        rows, files, _ = run_scan({'codex': [self.path('codex')]})
        self.assertEqual([r[2] for r in rows], ['resp_z'])
        self.assertEqual(list(files), [p + '.zst'])

    def test_zst_skipped_without_zstd(self):
        open(self.path('x.jsonl.zst'), 'wb').close()
        with mock.patch.object(scan, 'find_zstd', lambda: None):
            rows, files, stats = run_scan({'codex': [self.tmp]})
        self.assertEqual((rows, files, stats['zst_skipped']), ([], {}, 1))   # 不记进度，下次重试


class IncrementalTest(TempDirTest):
    def test_append_half_line_shrink_unchanged(self):
        p = self.path('claude', 's.jsonl')
        roots = {'claude-code': [self.path('claude')]}
        write_lines(p, [claude_line('a', '1', TS)])
        rows, known, _ = run_scan(roots)
        self.assertEqual(len(rows), 1)

        rows, known2, stats = run_scan(roots, known)                   # 没变：跳过
        self.assertEqual((rows, stats['files_unchanged']), ([], 1))

        write_lines(p, [claude_line('b', '2', TS)], mode='a')            # 变大：从断点续读
        rows, known, _ = run_scan(roots, known)
        self.assertEqual([r[2] for r in rows], ['b:2'])

        with open(p, 'a', encoding='utf-8') as f:                        # 半行：留到下次
            f.write(claude_line('c', '3', TS)[:20])
        rows, known_half, _ = run_scan(roots, known)
        self.assertEqual(rows, [])
        self.assertEqual(known_half[p][2], known[p][2])
        with open(p, 'a', encoding='utf-8', newline='\n') as f:
            f.write(claude_line('c', '3', TS)[20:] + '\n')
        rows, known, _ = run_scan(roots, known_half)
        self.assertEqual([r[2] for r in rows], ['c:3'])

        write_lines(p, [claude_line('d', '4', TS)])                      # 变小：整个重读
        rows, _, _ = run_scan(roots, known)
        self.assertEqual([r[2] for r in rows], ['d:4'])

    def test_codex_model_carries_across_reads(self):
        p = self.path('codex', 'r.jsonl')
        roots = {'codex': [self.path('codex')]}
        write_lines(p, [codex_context(TS, 'gpt-a'), codex_record(TS, 'r1', codex_usage(5, 0, 0, 1))])
        _, known, _ = run_scan(roots)
        write_lines(p, [codex_record(TS, 'r2', codex_usage(6, 0, 0, 1))], mode='a')
        rows, _, _ = run_scan(roots, known)
        self.assertEqual([(r[2], r[4]) for r in rows], [('r2', 'gpt-a')])


class RemoteProgramTest(TempDirTest):
    def test_same_events_as_local_scan(self):
        """发给 ssh 的程序在本机用 `python -` 执行，结果与直接调用 scan() 逐条相同。"""
        write_lines(self.path('claude', 's.jsonl'), [claude_line('m', 'r', TS), claude_line('n', 'q', TS)])
        write_lines(self.path('codex', 'r.jsonl'), [codex_context(TS, 'gpt'), codex_record(TS, 'x', codex_usage(3, 1, 0, 1))])
        roots = {'claude-code': [self.path('claude')], 'codex': [self.path('codex')]}
        r = subprocess.run([sys.executable, '-I', '-B', '-'], input=remote.remote_program(roots, {}),
                           stdout=subprocess.PIPE, universal_newlines=True, encoding='utf-8', check=True)
        remote_events = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual(remote_events, json.loads(json.dumps(list(scan.scan(roots, {})))))


if __name__ == '__main__':
    unittest.main()
