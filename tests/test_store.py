"""usage.db：去重、读取进度、导出、合并、改名、备份、文件锁（PROJECT.md 第 5、7 节）。"""
import json
import os
import unittest
from datetime import datetime, timezone

from token_stats import store
from tests.helpers import TempDirTest, zone

FIELDS = ('input', 'cache_write', 'cache_read', 'output')


def ms(*args):
    """UTC 时间 → 毫秒时间戳。"""
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


def events(rows, path='/logs/a.jsonl'):
    """rows：[(agent, key, ts, model, i, cw, cr, o)] → 一个文件的扫描事件。"""
    return [['row'] + list(r) for r in rows] + [['file', path, 1, 1, 1, '{}'], ['stats', {}]]


def table(conn):
    return conn.execute('SELECT * FROM requests ORDER BY agent, request_key').fetchall()


class DedupTest(unittest.TestCase):
    def test_cross_machine_and_order_independent(self):
        late = ('claude-code', 'k', 2000, 'model-late', 1, 1, 1, 9)    # 后出现但 output 更全
        early = ('claude-code', 'k', 1000, 'model-early', 2, 2, 2, 3)  # 最早出现
        results = []
        for order in ((('a', late), ('b', early)), (('b', early), ('a', late))):
            conn = store.connect(':memory:')
            for machine, row in order:
                store.apply(conn, machine, events([row], '/%s.jsonl' % machine))
            results.append(table(conn))
        self.assertEqual(results[0], results[1])
        # 时间取最早，机器和模型跟随最早那次；token 数取 output 最大的一次
        self.assertEqual(results[0], [('b', 'claude-code', 'k', 1000, 'model-early', 1, 1, 1, 9, 'log')])

    def test_progress_and_rerun_writes_nothing(self):
        conn = store.connect(':memory:')
        evs = events([('codex', 'r1', 1000, 'm', 1, 0, 0, 1)])
        self.assertEqual(store.apply(conn, 'a', evs)['rows_written'], 1)
        self.assertEqual(store.known_files(conn, 'a'), {'/logs/a.jsonl': [1, 1, 1, '{}']})
        self.assertEqual(store.apply(conn, 'a', evs)['rows_written'], 0)


class ExportTest(TempDirTest):
    def export(self, rows, tz):
        conn = store.connect(':memory:')
        conn.executemany('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
        out = self.path('daily')
        stats = store.export(conn, out, tz)
        days = {}
        for f in sorted(os.listdir(out)):
            with open(os.path.join(out, f), encoding='utf-8') as fh:
                days[f] = json.load(fh) if f.endswith('.json') else fh.read()
        return days, stats, conn

    def test_totals_and_source_selection(self):
        t = ms(2026, 1, 5, 4)
        days, _, _ = self.export([
            ('a', 'claude-code', 'log1', t, 'claude-x', 1, 1, 1, 1, 'log'),
            ('a', 'claude-code', 'cc1', t, 'claude-x', 10, 10, 10, 10, 'cc-switch'),   # a 这天有 CC Switch：只用它
            ('b', 'claude-code', 'log2', t, 'claude-y', 2, 2, 2, 2, 'log'),           # b 不受影响
            ('a', 'codex', 'log3', t, 'gpt-x', 3, 0, 3, 3, 'log'),                     # a 的另一个 agent 不受影响
        ], None)
        d = days['2026-01-05.json']
        self.assertEqual(d['models'], {'claude-x': dict.fromkeys(FIELDS, 10), 'claude-y': dict.fromkeys(FIELDS, 2),
                                       'gpt-x': {'input': 3, 'cache_write': 0, 'cache_read': 3, 'output': 3}})
        for k in FIELDS:
            self.assertEqual(d[k], sum(a[k] for a in d['agents'].values()))
            self.assertEqual(d[k], sum(m[k] for m in d['models'].values()))

    def test_timezone_and_dst(self):
        sh, ny = zone('Asia/Shanghai'), zone('America/New_York')
        if not (sh and ny):
            self.skipTest('没有时区数据')
        row = lambda ts: [('a', 'codex', str(ts), ts, 'm', 1, 0, 0, 1, 'log')]
        days, _, _ = self.export(row(ms(2026, 1, 1, 16, 30)), sh)          # 北京时间 01-02 00:30
        self.assertEqual(list(days), ['2026-01-02.json'])
        days, _, _ = self.export(row(ms(2026, 3, 9, 4, 30)), ny)           # 夏令时开始后：纽约 03-09 00:30（固定 -5 会算成 03-08）
        self.assertEqual(list(days), ['2026-03-09.json'])

    def test_unchanged_not_rewritten_and_stale_removed(self):
        rows = [('a', 'codex', 'k', ms(2026, 1, 5, 4), 'm', 1, 0, 0, 1, 'log')]
        _, _, conn = self.export(rows, None)
        out = self.path('daily')
        before = os.stat(os.path.join(out, '2026-01-05.json')).st_mtime_ns
        for name, text in (('2020-01-01.json', '{}'), ('notes.txt', 'keep')):
            with open(os.path.join(out, name), 'w') as f:
                f.write(text)
        stats = store.export(conn, out, None)
        self.assertEqual(stats, {'export_written': 0, 'export_unchanged': 1, 'export_removed': 1})
        self.assertEqual(sorted(os.listdir(out)), ['2026-01-05.json', 'notes.txt'])
        self.assertEqual(os.stat(os.path.join(out, '2026-01-05.json')).st_mtime_ns, before)


class MergeRenameBackupLockTest(TempDirTest):
    def test_merge(self):
        src_path = self.path('other.db')
        src = store.connect(src_path)
        store.apply(src, 'win', events([('claude-code', 'k1', 1000, 'm', 1, 1, 1, 1), ('codex', 'k2', 2000, 'g', 1, 0, 0, 1)]))
        src.close()
        conn = store.connect(':memory:')
        self.assertEqual(store.merge_db(conn, src_path, 'pc'), (2, 2))
        self.assertEqual({r[0] for r in table(conn)}, {'pc'})                        # 机器名改为指定名字
        self.assertEqual(conn.execute('SELECT count(*) FROM files').fetchone()[0], 0)  # 不合并读取进度
        self.assertEqual(store.merge_db(conn, src_path, 'pc'), (0, 2))                # 可重复执行

    def test_rename(self):
        conn = store.connect(':memory:')
        store.apply(conn, 'old', events([('codex', 'k', 1, 'm', 1, 0, 0, 1)]))
        store.set_status(conn, 'old')
        store.apply(conn, 'other', events([('codex', 'k2', 1, 'm', 1, 0, 0, 1)], '/o.jsonl'))
        self.assertEqual(store.rename(conn, 'old', 'new'), {'requests': 1, 'files': 1, 'machines': 1})
        self.assertEqual(list(store.known_files(conn, 'new')), ['/logs/a.jsonl'])
        with self.assertRaises(ValueError):
            store.rename(conn, 'new', 'other')

    def test_backup_once_per_day_keeps_seven(self):
        conn = store.connect(':memory:')
        d = self.path('backups')
        for day in range(1, 10):
            self.assertIsNotNone(store.backup(conn, d, '2026-01-%02d' % day))
        self.assertIsNone(store.backup(conn, d, '2026-01-09'))
        self.assertEqual(sorted(os.listdir(d)), ['usage-2026-01-%02d.db' % day for day in range(3, 10)])

    def test_lock(self):
        db = self.path('usage.db')
        held = store.lock(db)
        with self.assertRaises(SystemExit):
            store.lock(db)
        held.close()
        store.lock(db).close()


if __name__ == '__main__':
    unittest.main()
