"""CC Switch 一次性导入（PROJECT.md 第 8 节）。"""
import hashlib
import sqlite3
import unittest

from token_stats import ccswitch, config, store
from tests.helpers import TempDirTest, zone


class ImportTest(TempDirTest):
    def make_db(self):
        p = self.path('cc-switch.db')
        c = sqlite3.connect(p)
        c.executescript("""
            CREATE TABLE usage_daily_rollups (date TEXT, app_type TEXT, provider_id TEXT, model TEXT, request_model TEXT,
              pricing_model TEXT, input_tokens INT, cache_creation_tokens INT, cache_read_tokens INT, output_tokens INT);
            CREATE TABLE proxy_request_logs (request_id TEXT, app_type TEXT, created_at INT, model TEXT, input_tokens INT,
              cache_creation_tokens INT, cache_read_tokens INT, output_tokens INT);
            INSERT INTO usage_daily_rollups VALUES ('2026-01-05', 'claude', 'p1', 'claude-x', 'req', 'price', 1, 2, 3, 4);
            INSERT INTO usage_daily_rollups VALUES ('2026-01-05', 'claude', 'p2', 'claude-y', 'req', 'price', 0, 0, 0, 0);
            INSERT INTO usage_daily_rollups VALUES ('2026-01-05', 'codex', 'p1', 'gpt-x', 'req', 'price', 9, 9, 9, 9);
            INSERT INTO proxy_request_logs VALUES ('r1', 'claude', 1767600000, 'claude-x', 5, 0, 1, 2);
            INSERT INTO proxy_request_logs VALUES ('r2', 'claude', 1767600001, 'claude-x', NULL, NULL, NULL, NULL);
            INSERT INTO proxy_request_logs VALUES ('r3', 'codex', 1767600002, 'gpt-x', 9, 9, 9, 9);
        """)
        c.commit()
        c.close()
        return p

    def test_import_once_claude_only(self):
        p = self.make_db()
        with open(p, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        tz = zone('Asia/Shanghai')
        conn = store.connect(':memory:')
        r = ccswitch.import_history(conn, p, 'mac', tz)
        self.assertEqual(r, {'rollup': 2, 'proxy': 2, 'zero_skipped': 2, 'rows_written': 2})
        rows = conn.execute('SELECT machine, agent, request_key, ts, model, input, cache_write, cache_read, output, source '
                            'FROM requests ORDER BY request_key').fetchall()
        self.assertEqual(rows[0], ('mac', 'claude-code', 'cc-switch:r1', 1767600000000, 'claude-x', 5, 0, 1, 2, 'cc-switch'))
        self.assertEqual(rows[1][2], 'rollup:["2026-01-05", "p1", "claude-x", "req", "price"]')
        self.assertEqual(rows[1][3], config.noon_ms('2026-01-05', tz))   # 汇总行记在当天 12:00
        self.assertTrue(ccswitch.imported(conn))
        with self.assertRaises(ValueError):                              # 只能导入一次
            ccswitch.import_history(conn, p, 'mac', tz)
        with open(p, 'rb') as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest)   # 原库不变


if __name__ == '__main__':
    unittest.main()
