"""发布到 GitHub 仓库的 token-stats/ 子目录（PROJECT.md 第 2 节“发布”）。用本地裸仓库代替 GitHub。"""
import os
import shutil
import subprocess
import unittest
from unittest import mock

from token_stats import publish
from tests.helpers import TempDirTest

REPO = 'alice/token-stats-data'
GIT = ['git', '-c', 'user.name=alice', '-c', 'user.email=alice@example.com']
real_run = subprocess.run


@unittest.skipUnless(shutil.which('git'), '没有 git')
class PublishTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.bare = self.path('remote.git')
        for name, value in (('url', lambda repo: self.bare), ('GH', 'fake-gh')):
            p = mock.patch.object(publish, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(publish.PATHS, {'publish': self.path('clone')})
        p.start()
        self.addCleanup(p.stop)
        self.daily, self.cards = self.path('daily'), self.path('cards')
        for d, names in ((self.daily, ['2026-01-0%d.json' % i for i in range(1, 4)]), (self.cards, ['a.svg', 'a-dark.svg'])):
            os.makedirs(d)
            for n in names:
                self.write(os.path.join(d, n), n)
        with open(os.path.join(self.cards, 'preview.html'), 'w') as f:   # 不推送
            f.write('preview')
        # 假 gh：repo create 时建一个本地裸仓库
        fake = lambda cmd, **kw: real_run(['git', 'init', '-q', '--bare', self.bare], **kw) if cmd[0] == 'fake-gh' else real_run(cmd, **kw)
        with mock.patch.object(publish.subprocess, 'run', fake):
            publish.create(REPO)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text + '\n')

    def bare_git(self, *args):
        return real_run(['git', '--git-dir', self.bare] + list(args), stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()

    def files(self):
        return sorted(self.bare_git('ls-tree', '-r', '--name-only', 'HEAD').splitlines())

    def publish(self):
        return publish.publish(REPO, self.daily, self.cards, '2026-01-03')

    def other_clone(self):
        """模拟用户在别处（如网页）改了仓库。"""
        d = self.path('other')
        if not os.path.exists(d):
            real_run(['git', 'clone', '-q', self.bare, d], check=True)
        else:
            real_run(['git', '-C', d, 'pull', '-q'], check=True)
        return d

    def push_other(self, d, msg):
        real_run(GIT + ['-C', d, 'add', '-A'], check=True)
        real_run(GIT + ['-C', d, 'commit', '-qm', msg], check=True)
        real_run(['git', '-C', d, 'push', '-q'], check=True)

    def test_create_readme_branch_author(self):
        self.assertEqual(self.bare_git('branch', '--format=%(refname:short)'), 'main')
        self.assertEqual(self.files(), ['README.md'])
        readme = self.bare_git('show', 'HEAD:README.md')
        self.assertIn('https://raw.githubusercontent.com/%s/main/token-stats/cards/heatmap.svg' % REPO, readme)

    def test_publish_nochange_and_author(self):
        self.assertEqual(self.publish(), '已提交 update 2026-01-03 · 已推送 1 个提交')
        self.assertEqual(self.files(), ['README.md', 'token-stats/cards/a-dark.svg', 'token-stats/cards/a.svg'] +
                         ['token-stats/data/daily/2026-01-0%d.json' % i for i in range(1, 4)])
        self.assertEqual(self.publish(), '无变化 · 远端已是最新')
        authors = set(self.bare_git('log', '--format=%an <%ae>|%cn <%ce>').splitlines())
        self.assertEqual(authors, {'token-stats <token-stats@localhost>|token-stats <token-stats@localhost>'})

    def test_mirror_removes_stale_files(self):
        self.publish()
        os.remove(os.path.join(self.daily, '2026-01-01.json'))
        self.publish()
        self.assertNotIn('token-stats/data/daily/2026-01-01.json', self.files())

    def test_keeps_outside_changes_and_overwrites_subdir(self):
        self.publish()
        d = self.other_clone()
        with open(os.path.join(d, 'README.md'), 'a', encoding='utf-8') as f:
            f.write('用户加的一行\n')
        self.write(os.path.join(d, 'notes.txt'), '用户的文件')
        self.write(os.path.join(d, 'token-stats', 'data', 'daily', '2026-01-02.json'), 'remote edit')
        self.push_other(d, 'user edits')
        self.write(os.path.join(self.daily, '2026-01-03.json'), 'local change')
        self.assertTrue(self.publish().startswith('已提交'))
        self.assertTrue(self.bare_git('show', 'HEAD:README.md').endswith('用户加的一行'))
        self.assertEqual(self.bare_git('show', 'HEAD:notes.txt'), '用户的文件')
        self.assertEqual(self.bare_git('show', 'HEAD:token-stats/data/daily/2026-01-02.json'), '2026-01-02.json')  # 被本地数据覆盖

    def test_remote_unavailable_then_recovers(self):
        self.publish()
        os.rename(self.bare, self.bare + '.off')
        self.write(os.path.join(self.daily, '2026-01-04.json'), 'new day')
        with self.assertRaises(RuntimeError) as cm:
            self.publish()
        self.assertIn('fatal:', str(cm.exception))
        self.assertIsNotNone(publish.status(REPO)[0])
        os.rename(self.bare + '.off', self.bare)
        self.assertTrue(self.publish().endswith('已推送 1 个提交'))
        err, cloned, last, ahead = publish.status(REPO)
        self.assertEqual((err, cloned, ahead), (None, True, 0))
        self.assertIn('token-stats/data/daily/2026-01-04.json', self.files())


class ErrorLineTest(unittest.TestCase):
    def test_prefers_fatal_line(self):
        r = subprocess.CompletedProcess([], 128, '', 'failed to get: -25308\nfatal: repository not found\nhint: x\n')
        self.assertEqual(publish.error_line(r), 'fatal: repository not found')
        r = subprocess.CompletedProcess([], 1, '', 'something odd\nmore\n')
        self.assertEqual(publish.error_line(r), 'something odd')


if __name__ == '__main__':
    unittest.main()
