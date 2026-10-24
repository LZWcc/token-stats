"""定时任务：记录的 Python 路径与四种平台生成的内容（用假的系统命令，不会真的安装）。"""
import os
import plistlib
import subprocess
import sys
import unittest
from unittest import mock

from token_stats import schedule
from tests.helpers import TempDirTest


class CommandTest(unittest.TestCase):
    def python_for(self, exe, platform):
        with mock.patch.object(sys, 'executable', exe), mock.patch.object(sys, 'platform', platform):
            return schedule.command()[0]

    def test_macos_developer_python_uses_forwarder(self):
        for exe in ('/Applications/Xcode.app/Contents/Developer/usr/bin/python3',
                    '/Library/Developer/CommandLineTools/usr/bin/python3'):
            self.assertEqual(self.python_for(exe, 'darwin'), '/usr/bin/python3')

    def test_other_python_unchanged(self):
        exe = '/opt/homebrew/opt/python@3.14/bin/python3.14'
        self.assertEqual(self.python_for(exe, 'darwin'), exe)
        exe = '/x/Contents/Developer/python3'
        self.assertEqual(self.python_for(exe, 'linux'), exe)


class InstallTest(TempDirTest):
    def install(self, kind, fn=None, crontab=None):
        """用假的系统命令运行 fn（默认 schedule.install）；crontab 为 crontab -l 的输出，None 表示没有 crontab。"""
        calls = []

        def fake_run(cmd, **kw):
            calls.append((cmd, kw.get('input')))
            if cmd == ['crontab', '-l']:
                return subprocess.CompletedProcess(cmd, 1 if crontab is None else 0, crontab or '', '')
            return subprocess.CompletedProcess(cmd, 0, '', '')

        with mock.patch.object(schedule, 'kind', lambda: kind), mock.patch.object(schedule, '_run', fake_run), \
                mock.patch.object(schedule, '_plist', lambda: self.path('agents', 'x.plist')), \
                mock.patch.object(schedule, '_systemd_dir', lambda: self.path('systemd')), \
                mock.patch.object(schedule, 'DATA_DIR', self.tmp), \
                mock.patch.dict(schedule.PATHS, {'log': self.path('run.log')}):
            (fn or schedule.install)()
        return calls

    def test_launchd(self):
        if not hasattr(os, 'getuid'):
            self.skipTest('launchd 只在 Unix 上')
        self.install('launchd')
        with open(self.path('agents', 'x.plist'), 'rb') as f:
            d = plistlib.load(f)
        self.assertEqual(d['StartCalendarInterval'], {'Hour': 12, 'Minute': 0})
        self.assertTrue(d['RunAtLoad'])
        self.assertNotIn('StartInterval', d)

    def test_systemd(self):
        self.install('systemd')
        with open(self.path('systemd', 'token-stats.timer')) as f:
            timer = f.read()
        self.assertIn('OnCalendar=*-*-* 12:00:00', timer)
        self.assertIn('Persistent=true', timer)

    def test_cron(self):
        calls = self.install('cron')
        line = [inp for cmd, inp in calls if cmd == ['crontab', '-']][0]
        self.assertTrue(line.startswith('0 12 * * * '))
        self.assertTrue(line.strip().endswith(schedule.CRON_MARK))

    def test_schtasks(self):
        calls = self.install('schtasks')
        cmd = [c for c, _ in calls if c[0] == 'schtasks'][0]
        self.assertEqual(cmd[cmd.index('/SC') + 1:cmd.index('/SC') + 4], ['DAILY', '/ST', '12:00'])
        with open(self.path('sync.cmd'), 'rb') as f:
            data = f.read()
        self.assertTrue(data.startswith(b'@echo off\r\n'))
        self.assertNotIn(b'\r\r\n', data)

    def test_uninstall_launchd(self):
        if not hasattr(os, 'getuid'):
            self.skipTest('launchd 只在 Unix 上')
        self.install('launchd')
        calls = self.install('launchd', schedule.uninstall)
        self.assertEqual(calls[0][0][:2], ['launchctl', 'bootout'])
        self.assertFalse(os.path.exists(self.path('agents', 'x.plist')))
        self.assertEqual(self.install('launchd', schedule.uninstall), [])   # 没装时什么也不做

    def test_uninstall_systemd(self):
        self.install('systemd')
        calls = [c for c, _ in self.install('systemd', schedule.uninstall)]
        self.assertIn(['systemctl', '--user', 'disable', '--now', 'token-stats.timer'], calls)
        self.assertEqual(os.listdir(self.path('systemd')), [])
        self.assertEqual(self.install('systemd', schedule.uninstall), [])

    def test_uninstall_cron(self):
        calls = self.install('cron', schedule.uninstall, crontab='0 1 * * * other\n0 12 * * * x %s\n' % schedule.CRON_MARK)
        self.assertEqual([inp for c, inp in calls if c == ['crontab', '-']], ['0 1 * * * other\n'])   # 其他行保留
        calls = self.install('cron', schedule.uninstall, crontab='0 1 * * * other\n')
        self.assertEqual(calls, [(['crontab', '-l'], None)])

    def test_uninstall_schtasks(self):
        self.install('schtasks')
        calls = [c for c, _ in self.install('schtasks', schedule.uninstall)]
        self.assertIn(['schtasks', '/Delete', '/F', '/TN', 'token-stats'], calls)
        self.assertFalse(os.path.exists(self.path('sync.cmd')))


if __name__ == '__main__':
    unittest.main()
