"""在主机上安装每小时运行一次 `token-stats sync` 的定时任务。见 PROJECT.md 第 2 节。

macOS 用 launchd；Linux 用 systemd 用户定时器，没有时用 crontab；Windows 用任务计划程序（尚未在 Windows 上实测）。
"""
import os
import plistlib
import shutil
import subprocess
import sys

from .config import DATA_DIR, PATHS

NAME = 'token-stats'
LABEL = 'com.token-stats.sync'
# 不要求安装进 site-packages：把包所在目录放进 PYTHONPATH，直接从源码目录运行也行
PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRON_MARK = '# token-stats sync'


def command():
    return [sys.executable, '-m', 'token_stats', 'sync']


def _run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, **kw)


def _check(r, what):
    if r.returncode != 0:
        raise RuntimeError('%s 失败：%s' % (what, r.stderr.strip()))


def kind():
    if sys.platform == 'darwin':
        return 'launchd'
    if os.name == 'nt':
        return 'schtasks'
    if shutil.which('systemctl') and _run(['systemctl', '--user', 'show-environment']).returncode == 0:
        return 'systemd'
    return 'cron'


def _plist():
    return os.path.expanduser('~/Library/LaunchAgents/%s.plist' % LABEL)


def _systemd_dir():
    return os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'systemd', 'user')


def install():
    """安装并启用，返回说明。已安装时覆盖为当前的 Python 路径与包位置。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    k = kind()
    if k == 'launchd':
        p = _plist()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            plistlib.dump({'Label': LABEL, 'ProgramArguments': command(), 'EnvironmentVariables': {'PYTHONPATH': PKG_PARENT},
                           'StartInterval': 3600, 'StandardOutPath': PATHS['log'], 'StandardErrorPath': PATHS['log']}, f)
        domain = 'gui/%d' % os.getuid()
        _run(['launchctl', 'bootout', domain, p])   # 先卸下旧的；没加载过时报错可忽略
        _check(_run(['launchctl', 'bootstrap', domain, p]), 'launchctl bootstrap')
        return 'launchd：%s，每小时运行一次，输出写入 %s' % (p, PATHS['log'])
    if k == 'systemd':
        d = _systemd_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, NAME + '.service'), 'w') as f:
            f.write('[Unit]\nDescription=token-stats sync\n\n[Service]\nType=oneshot\nEnvironment="PYTHONPATH=%s"\nExecStart=%s\n'
                    % (PKG_PARENT, ' '.join('"%s"' % c for c in command())))
        with open(os.path.join(d, NAME + '.timer'), 'w') as f:
            f.write('[Unit]\nDescription=token-stats sync, hourly\n\n[Timer]\nOnCalendar=hourly\nRandomizedDelaySec=300\n'
                    'Persistent=true\n\n[Install]\nWantedBy=timers.target\n')
        _check(_run(['systemctl', '--user', 'daemon-reload']), 'systemctl daemon-reload')
        _check(_run(['systemctl', '--user', 'enable', '--now', NAME + '.timer']), 'systemctl enable')
        return ('systemd 用户定时器：%s/%s.timer，每小时运行一次，日志用 journalctl --user -u %s 查看。'
                '注意：没有开启 linger 时，退出登录后不会运行（loginctl enable-linger）' % (d, NAME, NAME))
    if k == 'cron':
        line = '17 * * * * PYTHONPATH="%s" "%s" -m token_stats sync >> "%s" 2>&1 %s' % (PKG_PARENT, sys.executable, PATHS['log'], CRON_MARK)
        cur = _run(['crontab', '-l'])
        lines = [x for x in (cur.stdout.splitlines() if cur.returncode == 0 else []) if not x.endswith(CRON_MARK)]
        _check(_run(['crontab', '-'], input='\n'.join(lines + [line]) + '\n'), 'crontab')
        return 'crontab：每小时第 17 分钟运行，输出写入 %s' % PATHS['log']
    wrapper = os.path.join(DATA_DIR, 'sync.cmd')
    with open(wrapper, 'w') as f:
        f.write('@echo off\r\nset "PYTHONPATH=%s"\r\n"%s" -m token_stats sync >> "%s" 2>&1\r\n' % (PKG_PARENT, sys.executable, PATHS['log']))
    _check(_run(['schtasks', '/Create', '/F', '/SC', 'HOURLY', '/TN', NAME, '/TR', '"%s"' % wrapper]), 'schtasks')
    return '任务计划程序：%s，每小时运行一次（尚未在 Windows 上实测）' % NAME


def status():
    """返回 (是否已安装, 说明)。"""
    k = kind()
    if k == 'launchd':
        return _run(['launchctl', 'print', 'gui/%d/%s' % (os.getuid(), LABEL)]).returncode == 0, 'launchd %s' % LABEL
    if k == 'systemd':
        return _run(['systemctl', '--user', 'is-active', NAME + '.timer']).stdout.strip() == 'active', 'systemd 用户定时器 %s.timer' % NAME
    if k == 'cron':
        cur = _run(['crontab', '-l'])
        return cur.returncode == 0 and CRON_MARK in cur.stdout, 'crontab'
    return _run(['schtasks', '/Query', '/TN', NAME]).returncode == 0, '任务计划程序 %s' % NAME
