"""命令行端到端：子进程运行 python -m token_stats，家目录相关的环境变量全部指向临时目录。"""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from token_stats import cli, config, schedule, store
from tests.helpers import TempDirTest, claude_line, write_lines

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CliTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.home = self.path('home')
        self.cwd = self.path('cwd')
        os.makedirs(self.home)
        os.makedirs(self.cwd)
        env = {k: v for k, v in os.environ.items() if not k.startswith('XDG_')}
        env.update(HOME=self.home, USERPROFILE=self.home, APPDATA=self.path('home', 'AppData', 'Roaming'),
                   LOCALAPPDATA=self.path('home', 'AppData', 'Local'), PYTHONPATH=ROOT, PYTHONIOENCODING='utf-8')
        self.env = env

    def ts(self, *args, stdin=''):
        r = subprocess.run([sys.executable, '-B', '-m', 'token_stats'] + list(args), input=stdin, cwd=self.cwd, env=self.env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8')
        return r.returncode, r.stdout

    def data_dir(self):
        if os.name == 'nt':
            return self.path('home', 'AppData', 'Local', 'token-stats')
        return self.path('home', '.local', 'share', 'token-stats')

    def config_path(self):
        if os.name == 'nt':
            return self.path('home', 'AppData', 'Roaming', 'token-stats', 'config.json')
        return self.path('home', '.config', 'token-stats', 'config.json')

    def add_log(self, n):
        write_lines(self.path('home', '.claude', 'projects', 'p', 's.jsonl'),
                    [claude_line('m%d' % i, 'r%d' % i, '2026-01-02T03:04:05Z') for i in range(n)], mode='a')

    def test_trial_empty_home(self):
        rc, out = self.ts('--no-open')
        self.assertEqual(rc, 0, out)
        self.assertIn('还没有任何用量数据', out)
        self.assertTrue(os.path.exists(os.path.join(self.cwd, 'token-stats-cards', 'preview.html')))
        self.assertFalse(os.path.exists(self.data_dir()))       # 试用不写数据目录
        self.assertFalse(os.path.exists(self.config_path()))

    def test_trial_with_logs(self):
        self.add_log(2)
        rc, out = self.ts('--no-open')
        self.assertEqual(rc, 0, out)
        self.assertIn('请求 2', out)

    def test_redirected_output_is_utf8(self):
        # 输出重定向到文件时（如定时任务写 run.log）Python 用本地编码，Windows 上常为 cp1252，不能因中文崩溃
        env = {k: v for k, v in self.env.items() if k not in ('PYTHONIOENCODING', 'PYTHONUTF8')}
        out = self.path('out.txt')
        with open(out, 'wb') as f:
            r = subprocess.run([sys.executable, '-B', '-m', 'token_stats', '--no-open'], stdin=subprocess.DEVNULL,
                               cwd=self.cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        with open(out, 'rb') as f:
            data = f.read()
        self.assertEqual(r.returncode, 0, data)
        self.assertIn('还没有任何用量数据'.encode('utf-8'), data)

    def test_init_sync_doctor_merge_rename(self):
        self.add_log(2)
        # 本机名 box；没有 ssh 主机；其余直接回车：不合并、系统时区、口径 all、不发布、不装定时任务
        rc, out = self.ts('init', stdin='box\n' + '\n' * 10)
        self.assertEqual(rc, 0, out)
        with open(self.config_path(), encoding='utf-8') as f:
            cfg = json.load(f)
        self.assertEqual((cfg['machine'], cfg['remotes'], cfg['publish']), ('box', [], None))
        self.assertTrue(os.path.exists(os.path.join(self.data_dir(), 'daily', '2026-01-02.json')))

        self.add_log(1)                                           # 追加 1 个新请求（m0 与已有的重复，入库时去重）
        rc, out = self.ts('sync')
        self.assertEqual(rc, 0, out)
        self.assertIn('box：读取文件 1 · 请求 1\n', out)          # m0 已存在：读到 1 个请求，写入 0 行（为 0 的项不显示）
        rc, out = self.ts('sync')
        self.assertIn('box：未变文件 1', out)

        rc, out = self.ts('doctor')
        self.assertEqual(rc, 0, out)
        self.assertIn('结果：正常', out)

        other = self.path('other.db')
        conn = store.connect(other)
        store.apply(conn, 'x', [['row', 'codex', 'k1', 1000, 'gpt', 1, 0, 0, 1], ['file', '/f', 1, 1, 1, '{}'], ['stats', {}]])
        conn.close()
        rc, out = self.ts('merge', other, '--as', 'win')
        self.assertIn('1 行 · 写入 1', out)
        rc, out = self.ts('merge', other, '--as', 'win')
        self.assertIn('1 行 · 写入 0', out)

        rc, out = self.ts('rename', 'box', 'box2')
        self.assertEqual(rc, 0, out)
        with open(self.config_path(), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['machine'], 'box2')
        rc, out = self.ts('rename', 'box2', 'win')                # 新名字已被使用
        self.assertNotEqual(rc, 0)
        self.assertIn('已在使用', out)


class UninstallTest(TempDirTest):
    """uninstall：在本进程中运行，数据目录、配置目录、启动脚本都指向临时目录，定时任务用假的。"""
    def setUp(self):
        super().setUp()
        self.data, self.conf = self.path('data'), self.path('conf')
        self.app, self.bin = os.path.join(self.data, 'app'), self.path('bin')
        self.launcher = os.path.join(self.bin, 'token-stats')
        for p in (os.path.join(self.app, 'token_stats', '__init__.py'), self.launcher,
                  os.path.join(self.data, 'usage.db'), os.path.join(self.conf, 'config.json')):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w').close()
        self.removed, self.later = [], []

    def run_uninstall(self, answers, pkg_parent=None, fail=False):
        def fake_uninstall():
            if fail:
                raise RuntimeError('schtasks 失败')
            self.removed.append('schedule')
            return '定时任务：未安装'
        out = io.StringIO()
        with mock.patch.object(config, 'DATA_DIR', self.data), mock.patch.object(config, 'CONFIG_DIR', self.conf), \
                mock.patch.object(config, 'load', lambda: {'publish': 'alice/data'}), \
                mock.patch.object(schedule, 'uninstall', fake_uninstall), \
                mock.patch.object(schedule, 'PKG_PARENT', pkg_parent or self.app), \
                mock.patch.object(cli, 'launcher', lambda: self.launcher), \
                mock.patch.object(cli, 'remove_later', self.later.extend), \
                mock.patch('builtins.input', side_effect=answers), contextlib.redirect_stdout(out):
            rc = cli.cmd_uninstall(None)   # 不经过 main()：它会重设标准输出的编码，StringIO 不支持
        return rc, out.getvalue()

    def test_removes_program_keeps_data(self):
        rc, out = self.run_uninstall(['y', ''])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.removed, ['schedule'])
        self.assertFalse(os.path.exists(self.app))
        if os.name == 'nt':
            self.assertEqual(self.later, [self.bin])               # 正在运行的启动脚本稍后由独立进程删除
        else:
            self.assertFalse(os.path.exists(self.launcher))
        self.assertTrue(os.path.exists(os.path.join(self.data, 'usage.db')))
        self.assertTrue(os.path.exists(os.path.join(self.conf, 'config.json')))
        self.assertIn('alice/data', out)                          # 提醒自己删除发布仓库

    def test_purge(self):
        rc, out = self.run_uninstall(['y', 'y'])
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(self.conf))
        if os.name == 'nt':
            self.assertEqual(self.later, [self.data])              # 数据目录稍后整个删除
        else:
            self.assertFalse(os.path.exists(self.data))

    def test_running_from_source_keeps_program(self):
        rc, out = self.run_uninstall(['y', ''], pkg_parent=self.path('src'))
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.exists(self.app))
        self.assertTrue(os.path.exists(self.launcher))
        self.assertIn('不删除程序文件', out)

    def test_cancel(self):
        rc, out = self.run_uninstall([''])
        self.assertEqual((rc, self.removed), (0, []))
        self.assertTrue(os.path.exists(self.app))
        self.assertIn('已取消', out)

    def test_schedule_failure_deletes_nothing(self):
        rc, out = self.run_uninstall(['y', 'y'], fail=True)
        self.assertEqual(rc, 1)
        self.assertTrue(os.path.exists(self.app))
        self.assertTrue(os.path.exists(os.path.join(self.data, 'usage.db')))
        self.assertIn('schtasks 失败', out)


if __name__ == '__main__':
    unittest.main()
