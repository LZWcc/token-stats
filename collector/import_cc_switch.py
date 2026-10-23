#!/usr/bin/env python3
"""把 CC Switch 中 Claude Code 的历史用量一次性导入 usage.db（仅 laptop）。

只读打开 CC Switch 数据库，应传入快照而不是原库。规则见 PROJECT.md 第 8 节。
导入后运行一次 collector.py 重新导出日数据。
"""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from collector import SCHEMA, TZ_OFFSET_SEC, UPSERT


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True, help='usage.db 路径')
    ap.add_argument('--cc-switch', required=True, help='CC Switch 数据库快照路径')
    args = ap.parse_args()

    src = sqlite3.connect(Path(args.cc_switch).resolve().as_uri() + '?mode=ro', uri=True)
    rows = []
    # 早期数据只剩日汇总：一条汇总行记一行，主键取汇总表主键，时间记在当天北京时间 12:00
    for d, provider, model, req_model, pricing, i, cw, cr, o in src.execute(
            """SELECT date, provider_id, model, request_model, pricing_model,
                      input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens
               FROM usage_daily_rollups WHERE app_type = 'claude'"""):
        day = datetime.strptime(d, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()
        ts = int(day - TZ_OFFSET_SEC + 12 * 3600) * 1000
        key = 'rollup:' + json.dumps([d, provider, model, req_model, pricing], ensure_ascii=False)
        rows.append(('claude-code', key, ts, model, i, cw, cr, o, 'cc-switch'))
    n_rollup = len(rows)
    # 尚未汇总的逐请求记录（created_at 为秒）
    for rid, created, model, i, cw, cr, o in src.execute(
            """SELECT request_id, created_at, model, input_tokens, cache_creation_tokens,
                      cache_read_tokens, output_tokens
               FROM proxy_request_logs WHERE app_type = 'claude'"""):
        rows.append(('claude-code', 'cc-switch:' + rid, created * 1000, model,
                     i or 0, cw or 0, cr or 0, o or 0, 'cc-switch'))
    src.close()
    kept = [r for r in rows if any(r[4:8])]

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    with conn:
        before = conn.total_changes
        conn.executemany(UPSERT, kept)
        written = conn.total_changes - before
    print('rollup=%d proxy=%d zero_skipped=%d rows_written=%d'
          % (n_rollup, len(rows) - n_rollup, len(rows) - len(kept), written))
    conn.close()


if __name__ == '__main__':
    main()
