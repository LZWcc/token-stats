"""命令行入口：token-stats [init | sync | doctor | merge | import-cc-switch | rename]。见 PROJECT.md 第 2 节。"""
import argparse
import os
import sqlite3
import subprocess
import tempfile
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from . import ccswitch, config, remote, render, scan, schedule, store

STALE_DAYS = 7
LABELS = {'files_read': '读取文件', 'files_unchanged': '未变文件', 'rows': '请求', 'rows_written': '写入',
          'bad_json': '无法解析的行', 'zst_skipped': '缺少 zstd 而跳过的 .zst', 'vanished': '扫描中被删除的文件',
          'export_written': '写入', 'export_unchanged': '未变', 'export_removed': '删除'}


def fmt(stats):
    return ' · '.join('%s %d' % (LABELS.get(k, k), v) for k, v in stats.items() if v) or '无日志'


def ask(prompt, default=''):
    try:
        v = input('%s%s：' % (prompt, '（默认 %s）' % default if default else '')).strip()
    except EOFError:
        v = ''
    return v or default


def ask_yes(prompt, default):
    v = ask('%s [%s]' % (prompt, 'Y/n' if default else 'y/N')).lower()
    return default if not v else v in ('y', 'yes', '是')


def require_config():
    cfg = config.load()
    if not cfg:
        raise SystemExit('还没有配置：先运行 token-stats init')
    return cfg


def local_roots():
    return {a: [os.path.abspath(os.path.expanduser(d)) for d in ds] for a, ds in remote.log_roots().items()}


def ago(ms):
    if not ms:
        return '从未'
    hours = (time.time() * 1000 - ms) / 3600000
    when = datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M')
    return '%s（%s前）' % (when, '%d 天' % (hours // 24) if hours >= 24 else '%d 小时' % hours if hours >= 1 else '不到 1 小时')


def print_summary(daily_dir, metric, today):
    days, models, agents = render.load(daily_dir, metric)
    if not days:
        print('还没有任何用量数据')
        return
    h = render.human
    recent = lambda n: sum(days.get((today - timedelta(days=i)).isoformat(), 0) for i in range(n))
    total = sum(days.values())
    print('总量 %s（%s）· 近 7 天 %s · 近 30 天 %s · 活跃 %d 天 · %s ~ %s' % (
        h(total), '四项全加' if metric == 'all' else '不含缓存读取', h(recent(7)), h(recent(30)),
        sum(v > 0 for v in days.values()), min(days), max(days)))
    print('按 agent：' + ' · '.join('%s %s' % (a, h(v)) for a, v in sorted(agents.items(), key=lambda kv: -kv[1])))
    top = sorted(models.items(), key=lambda kv: -kv[1])[:5]
    print('前 5 个模型：' + ' · '.join('%s %s（%.1f%%）' % (m, h(v), 100.0 * v / total) for m, v in top))


def stale(conn, cfg):
    """配置里的机器中，超过 STALE_DAYS 天没有成功采集（或从未成功）的。"""
    names = [cfg['machine']] + [r['name'] for r in cfg['remotes']] + [m['name'] for m in cfg['merge']]
    last = dict(conn.execute('SELECT machine, last_ok FROM machines'))
    limit = time.time() * 1000 - STALE_DAYS * 86400000
    return [(n, last.get(n)) for n in names if not last.get(n) or last[n] < limit]


def collect(conn, cfg):
    """采集本机和各远端、合并配置里的其他库；按机器隔离失败，返回失败的机器名。"""
    roots = local_roots()
    jobs = [(cfg['machine'], lambda known: scan.scan(roots, known))]
    for r in cfg['remotes']:
        jobs.append((r['name'], lambda known, r=r: remote.remote_events(r['ssh'], r['python'], remote.log_roots(), known)))
    failed = []
    for machine, events in jobs:
        try:
            stats = store.apply(conn, machine, events(store.known_files(conn, machine)))
        except (OSError, RuntimeError, ValueError) as e:
            store.set_status(conn, machine, str(e))
            print('%s 失败：%s' % (machine, e))
            failed.append(machine)
            continue
        store.set_status(conn, machine)
        print('%s：%s' % (machine, fmt(stats)))
    for m in cfg['merge']:
        try:
            written, total = store.merge_db(conn, os.path.expanduser(m['path']), m['name'])
        except (sqlite3.Error, OSError) as e:   # 例如网盘还没同步完
            store.set_status(conn, m['name'], str(e))
            print('%s 合并失败：%s' % (m['name'], e))
            failed.append(m['name'])
            continue
        store.set_status(conn, m['name'])
        print('%s：合并 %d 行 · 写入 %d' % (m['name'], total, written))
    return failed


def run_sync(conn, cfg):
    tz = config.get_tz(cfg['timezone'])
    today = config.today(tz)
    failed = collect(conn, cfg)
    print('导出：%s' % fmt(store.export(conn, config.PATHS['daily'], tz)))
    preview = render.render_cards(config.PATHS['daily'], config.PATHS['cards'], cfg['metric'], today)
    if store.backup(conn, config.PATHS['backups'], today):
        print('已备份 usage.db 到 %s' % config.PATHS['backups'])
    for name, last in stale(conn, cfg):
        print('⚠ %s 已超过 %d 天没有成功采集（上次成功：%s）。服务器上的 Claude Code 日志只保留 30 天，请尽快检查'
              % (name, STALE_DAYS, ago(last)))
    print('卡片：%s' % preview)
    return 1 if failed else 0


def cmd_try(args):
    print('只统计本机，不写入数据目录。要长期统计、加入其他机器：token-stats init\n')
    conn = store.connect(':memory:')
    print('本机：%s' % fmt(store.apply(conn, 'local', scan.scan(local_roots(), {}))))
    tz = config.get_tz(None)
    today = config.today(tz)
    with tempfile.TemporaryDirectory() as d:
        store.export(conn, d, tz)
        print_summary(d, 'all', today)
        preview = render.render_cards(d, os.path.abspath('token-stats-cards'), 'all', today)
    print('卡片：%s' % preview)
    if not args.no_open:
        webbrowser.open(Path(preview).as_uri())
    return 0


def cmd_sync(args):
    cfg = require_config()
    held = store.lock(config.PATHS['db'])  # 保持锁文件句柄直到进程退出
    print('== token-stats sync %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    return run_sync(store.connect(config.PATHS['db']), cfg)


def cmd_doctor(args):
    cfg = config.load()
    print('配置文件：%s%s' % (config.CONFIG_PATH, '' if cfg else '（不存在，先运行 token-stats init）'))
    if not cfg:
        return 1
    problems = 0
    db = config.PATHS['db']
    print('数据目录：%s' % config.DATA_DIR)
    zstd = scan.find_zstd()
    print('本机 zstd：%s' % (zstd or '未找到（Codex 的 .zst 压缩日志会被跳过）'))
    ok, desc = schedule.status()
    print('定时任务：%s' % ('已安装（%s）' % desc if ok else '未安装（可选，手动运行 sync 即可）'))
    conn = store.connect(db) if os.path.exists(db) else None
    status = {m: (o, e) for m, o, e in conn.execute('SELECT machine, last_ok, last_error FROM machines')} if conn else {}
    rows = dict(conn.execute('SELECT machine, count(*) FROM requests GROUP BY 1')) if conn else {}
    print('机器：')
    entries = [(cfg['machine'], '本机', None)] + [(r['name'], 'ssh %s' % r['ssh'], r) for r in cfg['remotes']] \
        + [(m['name'], '合并 %s' % m['path'], m) for m in cfg['merge']]
    for name, how, item in entries:
        last_ok, last_err = status.get(name, (None, None))
        check = ''
        if how.startswith('ssh'):
            try:
                v = remote.python_version(item['ssh'], item['python'])
                check = 'Python %d.%d%s' % (v[0], v[1], '' if v >= (3, 9) else '，需要 ≥ 3.9')
                problems += v < (3, 9)
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
                check = '连接失败：%s' % e
                problems += 1
        elif item:
            exists = os.path.exists(os.path.expanduser(item['path']))
            check = '文件存在' if exists else '文件不存在'
            problems += not exists
        print('  %-12s %-20s %7d 行  上次成功 %s  %s%s' % (name, how, rows.get(name, 0), ago(last_ok), check,
                                                    '\n%s上次错误：%s' % (' ' * 15, last_err) if last_err else ''))
    for name, last in stale(conn, cfg) if conn else []:
        print('⚠ %s 已超过 %d 天没有成功采集（上次成功：%s）' % (name, STALE_DAYS, ago(last)))
        problems += 1
    print('结果：%s' % ('有 %d 个问题' % problems if problems else '正常'))
    return 1 if problems else 0


def cmd_merge(args):
    db = config.PATHS['db']
    if os.path.exists(db) and os.path.exists(args.path) and os.path.samefile(db, args.path):
        raise SystemExit('不能把 usage.db 合并到它自己')
    held = store.lock(db)  # 保持锁文件句柄直到进程退出
    conn = store.connect(db)
    written, total = store.merge_db(conn, args.path, args.name)
    store.set_status(conn, args.name)
    print('已合并 %s（记为 %s）：%d 行 · 写入 %d。运行 token-stats sync 更新导出数据和卡片' % (args.path, args.name, total, written))
    return 0


def cmd_rename(args):
    held = store.lock(config.PATHS['db'])  # 保持锁文件句柄直到进程退出
    try:
        counts = store.rename(store.connect(config.PATHS['db']), args.old, args.new)
    except ValueError as e:
        raise SystemExit(str(e))
    cfg = config.load()
    if cfg:
        if cfg['machine'] == args.old:
            cfg['machine'] = args.new
        for item in cfg['remotes'] + cfg['merge']:
            if item['name'] == args.old:
                item['name'] = args.new
        config.save(cfg)
    print('已改名 %s → %s：请求 %d 行 · 读取进度 %d 个文件 · 状态 %d 条%s' % (
        args.old, args.new, counts['requests'], counts['files'], counts['machines'], '；配置已同步' if cfg else ''))
    return 0


def import_cc_switch(conn, cfg, path):
    try:
        r = ccswitch.import_history(conn, path, cfg['machine'], config.get_tz(cfg['timezone']))
    except sqlite3.Error as e:
        raise SystemExit('读取 CC Switch 数据库失败：%s' % e)
    print('CC Switch：汇总行 %d · 逐请求 %d · 跳过全零 %d · 写入 %d' % (r['rollup'], r['proxy'], r['zero_skipped'], r['rows_written']))


def cmd_import_cc_switch(args):
    cfg = require_config()
    held = store.lock(config.PATHS['db'])  # 保持锁文件句柄直到进程退出
    try:
        import_cc_switch(store.connect(config.PATHS['db']), cfg, args.path)
    except ValueError as e:
        raise SystemExit(str(e))
    print('运行 token-stats sync 更新导出数据和卡片')
    return 0


def ssh_hosts():
    """~/.ssh/config 中的 Host 名（只读），跳过带通配符的模式。"""
    p = os.path.expanduser('~/.ssh/config')
    hosts = []
    if os.path.exists(p):
        with open(p, encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0].lower() == 'host':
                    hosts += [h for h in parts[1:] if not any(c in h for c in '*?!') and h not in hosts]
    return hosts


def cmd_init(args):
    old = config.load()
    if old and not ask_yes('已有配置 %s，重新配置？' % config.CONFIG_PATH, False):
        return 0
    old = old or dict(config.DEFAULTS)
    cfg = dict(config.DEFAULTS, remotes=[], merge=[])
    db = config.PATHS['db']
    held = store.lock(db)  # 保持锁文件句柄直到进程退出；导入和首次采集都在这把锁下完成
    conn = store.connect(db)

    cfg['machine'] = ask('本机的名字（只记在本地，不公开）', old['machine'])
    if cfg['machine'] != old['machine'] and conn.execute('SELECT 1 FROM files WHERE machine = ? LIMIT 1', (old['machine'],)).fetchone():
        print('库中已有本机的读取进度（名字 %s），直接改名会对不上，已保留原名；要改名请用 token-stats rename' % old['machine'])
        cfg['machine'] = old['machine']

    hosts = ssh_hosts()
    prev = {r['ssh']: r for r in old['remotes']}
    if hosts:
        print('~/.ssh/config 中的主机：')
        for i, h in enumerate(hosts, 1):
            print('  %d. %s' % (i, h))
        default = ','.join(str(hosts.index(h) + 1) for h in prev if h in hosts)
        picked = [x.strip() for x in ask('要加入的服务器编号，逗号分隔，直接回车跳过', default).split(',') if x.strip()]
        for x in picked:
            if not x.isdigit() or not 1 <= int(x) <= len(hosts):
                print('  忽略无效编号：%s' % x)
                continue
            h = hosts[int(x) - 1]
            p = prev.get(h, {})
            item = {'ssh': h, 'name': ask('  %s 的名字（只记在本地）' % h, p.get('name', h)),
                    'python': ask('  %s 上的 Python 命令' % h, p.get('python', 'python3'))}
            try:
                v = remote.python_version(h, item['python'])
                print('  ✓ 已连接，Python %d.%d%s' % (v[0], v[1], '' if v >= (3, 9) else '（需要 ≥ 3.9，采集会失败）'))
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
                print('  ✗ 连接失败：%s（需要能免密登录）' % e)
                if not ask_yes('  仍然加入？', False):
                    continue
            cfg['remotes'].append(item)
    else:
        print('~/.ssh/config 中没有可选的主机，跳过远端；以后可以再运行 token-stats init')

    if old['merge'] and ask_yes('保留已有的 %d 个自动合并项？' % len(old['merge']), True):
        cfg['merge'] = old['merge']
    while True:
        path = ask('自动合并的其他 usage.db（例如网盘同步文件夹里另一台机器的库），直接回车跳过')
        if not path:
            break
        name = ask('  这台机器的名字')
        if name:
            cfg['merge'].append({'path': path, 'name': name})

    offset = datetime.now().astimezone().strftime('%z')
    tz = ask('时区（如 Asia/Shanghai），直接回车使用系统时区（当前 UTC%s:%s）' % (offset[:3], offset[3:]), old['timezone'] or '')
    cfg['timezone'] = tz if tz and config.get_tz(tz) else None
    metric = ask('卡片口径：all = 四项全加，effective = 不含缓存读取', old['metric'])
    cfg['metric'] = metric if metric in ('all', 'effective') else 'all'
    config.save(cfg)
    print('已保存配置：%s' % config.CONFIG_PATH)

    if os.path.exists(ccswitch.DEFAULT_PATH) and not ccswitch.imported(conn) \
            and ask_yes('检测到 CC Switch（%s），导入其中 Claude Code 的历史？' % ccswitch.DEFAULT_PATH, True):
        import_cc_switch(conn, cfg, ccswitch.DEFAULT_PATH)

    print('\n首次采集（日志多时需要一两分钟）…')
    rc = run_sync(conn, cfg)
    conn.close()
    held.close()

    if ask_yes('\n安装定时任务（%s），每天 %02d:%02d 自动运行 token-stats sync？不装也可以，'
               '但至少每 30 天手动运行一次 sync，否则 Claude Code 日志会在入库前被清理' % (schedule.kind(), schedule.HOUR, schedule.MINUTE), False):
        try:
            print(schedule.install())
        except (RuntimeError, OSError) as e:
            print('安装失败：%s' % e)
            rc = 1
    print('\n完成。数据目录：%s；随时可运行 token-stats doctor 检查状态' % config.DATA_DIR)
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(prog='token-stats', description='汇总多台机器上 Claude Code 与 Codex 的 token 用量，生成 GitHub 主页卡片。'
                                 '不带子命令时只统计本机、不写入数据目录。')
    ap.add_argument('--no-open', action='store_true', help='不带子命令时：生成卡片后不自动打开预览页')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('init', help='向导：本机名、远端、自动合并、时区、口径、CC Switch、首次采集、定时任务')
    sub.add_parser('sync', help='采集 → 合并 → 导出 → 渲染（定时任务调用）')
    sub.add_parser('doctor', help='检查配置、各机器连接与状态、定时任务')
    p = sub.add_parser('merge', help='合并另一台机器自己的 usage.db，可重复执行')
    p.add_argument('path')
    p.add_argument('--as', dest='name', required=True, help='记为哪台机器')
    p = sub.add_parser('import-cc-switch', help='导入 CC Switch 中 Claude Code 的历史（只能导入一次）')
    p.add_argument('--from', dest='path', default=ccswitch.DEFAULT_PATH, help='CC Switch 数据库，默认 %(default)s')
    p = sub.add_parser('rename', help='改机器名（三张表与配置一起改）')
    p.add_argument('old')
    p.add_argument('new')
    args = ap.parse_args(argv)
    return {None: cmd_try, 'init': cmd_init, 'sync': cmd_sync, 'doctor': cmd_doctor, 'merge': cmd_merge,
            'import-cc-switch': cmd_import_cc_switch, 'rename': cmd_rename}[args.cmd](args)
