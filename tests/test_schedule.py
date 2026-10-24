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
    def install(self, kind):
        calls = []

        def fake_run(cmd, **kw):
            calls.append((cmd, kw.get('input')))
            return subprocess.CompletedProcess(cmd, 1 if cmd == ['crontab', '-l'] else 0, '', '')

        with mock.patch.object(schedule, 'kind', lambda: kind), mock.patch.object(schedule, '_run', fake_run), \
                mock.patch.object(schedule, '_plist', lambda: self.path('agents', 'x.plist')), \
                mock.patch.object(schedule, '_systemd_dir', lambda: self.path('systemd')), \
                mock.patch.object(schedule, 'DATA_DIR', self.tmp), \
                mock.patch.dict(schedule.PATHS, {'log': self.path('run.log')}):
            schedule.install()
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


if __name__ == '__main__':
    unittest.main()
