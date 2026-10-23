"""CC Switch 中 Claude Code 历史的一次性导入。只读打开 CC Switch 数据库，先做快照再导入，不碰原库。规则见 PROJECT.md 第 8 节。"""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .config import noon_ms
from .store import UPSERT

DEFAULT_PATH = os.path.expanduser('~/.cc-switch/cc-switch.db')


def snapshot(src_path, dest):
    """用 SQLite 备份接口从只读连接复制一份一致的快照。"""
    src = sqlite3.connect(Path(src_path).resolve().as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def imported(conn):
    return conn.execute("SELECT 1 FROM requests WHERE source = 'cc-switch' LIMIT 1").fetchone() is not None


def import_history(conn, src_path, machine, tz):
    if imported(conn):
        raise ValueError('usage.db 中已有 CC Switch 数据，拒绝再次导入：不同时间的快照里，同一批请求可能先是逐请求记录、'
                         '后被汇总成日汇总行，主键不同，会重复计数（见 PROJECT.md 第 8 节）')
    rows = []
    with tempfile.TemporaryDirectory() as d:
        snap = os.path.join(d, 'cc-switch.db')
        snapshot(src_path, snap)
        src = sqlite3.connect(snap)
        try:
            # 早期数据只剩日汇总：一条汇总行记一行，主键取汇总表主键，时间记在当天 12:00
            for day, provider, model, req_model, pricing, i, cw, cr, o in src.execute(
                    """SELECT date, provider_id, model, request_model, pricing_model,
                              input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens
                       FROM usage_daily_rollups WHERE app_type = 'claude'"""):
                key = 'rollup:' + json.dumps([day, provider, model, req_model, pricing], ensure_ascii=False)
                rows.append((machine, 'claude-code', key, noon_ms(day, tz), model, i, cw, cr, o, 'cc-switch'))
            n_rollup = len(rows)
            # 尚未汇总的逐请求记录（created_at 为秒）
            for rid, created, model, i, cw, cr, o in src.execute(
                    """SELECT request_id, created_at, model, input_tokens, cache_creation_tokens,
                              cache_read_tokens, output_tokens
                       FROM proxy_request_logs WHERE app_type = 'claude'"""):
                rows.append((machine, 'claude-code', 'cc-switch:' + rid, created * 1000, model,
                             i or 0, cw or 0, cr or 0, o or 0, 'cc-switch'))
        finally:
            src.close()
    kept = [r for r in rows if any(r[5:9])]
    with conn:
        before = conn.total_changes
        conn.executemany(UPSERT, kept)
        written = conn.total_changes - before
    return {'rollup': n_rollup, 'proxy': len(rows) - n_rollup, 'zero_skipped': len(rows) - len(kept), 'rows_written': written}
