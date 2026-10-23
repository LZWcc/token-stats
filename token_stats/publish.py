"""可选发布：把日数据和卡片推送到用户 GitHub 仓库的 token-stats/ 子目录，子目录以外的文件不碰。见 PROJECT.md 第 2 节“发布”。"""
import os
import shutil
import subprocess

from .config import PATHS

SUBDIR = 'token-stats'
CARDS = (('heatmap', 'Token 用量'), ('stats', 'Token 统计'), ('models-donut', '模型占比'), ('models-bar', '模型排行'))
# 自动提交的作者不关联任何 GitHub 账号，不计入用户的贡献图；用 -c 传入，不改用户的 git 配置。
# 关闭签名：用户全局开启 commit.gpgsign 时，会用他的密钥给这个作者签名。克隆空仓库时分支名用 main（与 GitHub 默认一致）
GIT_OPTS = ['-c', 'user.name=token-stats', '-c', 'user.email=token-stats@localhost', '-c', 'commit.gpgsign=false',
            '-c', 'init.defaultBranch=main']
ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0')  # 认证失败时直接报错，不卡在等待输入
# gh 的完整路径：launchd、ssh 等环境的 PATH 里可能没有 Homebrew 目录
GH = shutil.which('gh') or next((p for p in ('/opt/homebrew/bin/gh', '/usr/local/bin/gh') if os.path.exists(p)), None)
if GH:
    # 追加 gh 作为 github.com 的备用凭据助手：git 先试用户已有的（如钥匙串，ssh 会话里不可用），拿不到再用 gh 的登录。
    # 只对本程序执行的 git 命令生效，不改用户的 git 配置
    GIT_OPTS += ['-c', 'credential.https://github.com.helper=!"%s" auth git-credential' % GH]


def error_line(r):
    """git 报错中最有用的一行：优先 fatal: / error:（前面可能有凭据助手的无关报错，如钥匙串不可用时的 -25308）。"""
    lines = (r.stderr or r.stdout).strip().splitlines()
    return next((l for l in lines if l.startswith(('fatal:', 'error:'))), lines[0] if lines else '')


def run(cwd, *args, check=True):
    r = subprocess.run(['git'] + GIT_OPTS + list(args), cwd=cwd, env=ENV,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if check and r.returncode != 0:
        raise RuntimeError('git %s 失败：%s' % (args[0], error_line(r)))
    return r


def url(repo):
    return 'https://github.com/%s.git' % repo


def clone(repo):
    """确保 publish/ 是该仓库的克隆（配置换了仓库时重新克隆），返回目录。"""
    d = PATHS['publish']
    if os.path.isdir(os.path.join(d, '.git')) and run(d, 'remote', 'get-url', 'origin', check=False).stdout.strip() == url(repo):
        return d
    if os.path.exists(d):
        shutil.rmtree(d)
    run(None, 'clone', '-q', url(repo), d)
    return d


def branch(d):
    return run(d, 'symbolic-ref', '--short', 'HEAD').stdout.strip()


def mirror(src, dst, ext):
    """把 src 中的 *ext 文件复制到 dst，并删除 dst 中多余的文件（dst 由本程序独占管理）。"""
    os.makedirs(dst, exist_ok=True)
    want = [f for f in os.listdir(src) if f.endswith(ext)] if os.path.isdir(src) else []
    for f in os.listdir(dst):
        if f not in want:
            os.remove(os.path.join(dst, f))
    for f in want:
        shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))


def publish(repo, daily_dir, cards_dir, today):
    """与远端同步 → 镜像复制 → 有变化才提交 → 推送。返回说明，失败时抛出 RuntimeError，下次 sync 重试。"""
    d = clone(repo)
    b = branch(d)
    run(d, 'fetch', '-q', 'origin')
    remote = run(d, 'rev-parse', '--verify', '-q', 'origin/' + b, check=False).returncode == 0
    if remote:
        # 以远端为准，保留用户在网页上对其他文件的修改。子目录完全由本地数据生成，所以不用 rebase：
        # 上次没推上去的提交丢弃后由下面重新生成，远端对子目录的改动被覆盖，不会冲突
        run(d, 'reset', '-q', '--hard', 'origin/' + b)
    mirror(daily_dir, os.path.join(d, SUBDIR, 'data', 'daily'), '.json')
    mirror(cards_dir, os.path.join(d, SUBDIR, 'cards'), '.svg')
    run(d, 'add', '-A', SUBDIR)
    changed = run(d, 'diff', '--cached', '--quiet', check=False).returncode != 0
    if changed:
        run(d, 'commit', '-q', '-m', 'update %s' % today)
    ahead = int(run(d, 'rev-list', '--count', 'origin/%s..HEAD' % b if remote else 'HEAD', check=False).stdout.strip() or 0)
    if ahead:
        run(d, 'push', '-q', 'origin', 'HEAD')
    return '%s · %s' % ('已提交 update %s' % today if changed else '无变化',
                        '已推送 %d 个提交' % ahead if ahead else '远端已是最新')


def snippet(repo, b):
    """README 片段：每张卡片一个 <picture>，按访客主题切换亮暗。"""
    base = 'https://raw.githubusercontent.com/%s/%s/%s/cards/' % (repo, b, SUBDIR)
    return '\n'.join('<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="%s%s-dark.svg">\n'
                     '  <img alt="%s" src="%s%s.svg">\n</picture>' % (base, name, alt, base, name) for name, alt in CARDS)


def create(repo):
    """用 gh 新建公开仓库，克隆后提交并推送 README 作为第一个提交（只在新建时生成一次）。"""
    r = subprocess.run([GH, 'repo', 'create', repo, '--public'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if r.returncode != 0:
        raise RuntimeError('gh repo create 失败：%s' % (r.stderr or r.stdout).strip())
    d = clone(repo)
    b = branch(d)
    s = snippet(repo, b)
    with open(os.path.join(d, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('# Token 用量\n\n%s\n\n## 在 README 中引用\n\n```html\n%s\n```\n\n'
                '日数据在 `%s/data/daily/`，每天一个 JSON 文件。token-stats 只更新 `%s/` 子目录；'
                '本文件只在新建仓库时生成一次，之后可以随意修改。\n' % (s, s, SUBDIR, SUBDIR))
    run(d, 'add', 'README.md')
    run(d, 'commit', '-q', '-m', 'init')
    run(d, 'push', '-q', 'origin', 'HEAD')


def status(repo):
    """供 doctor（不 fetch）：返回 (连接错误或 None, 是否已克隆, 远端最新提交的毫秒时间戳或 None, 未推送的提交数)。"""
    r = run(None, 'ls-remote', '-q', '--heads', url(repo), check=False)
    err = None if r.returncode == 0 else error_line(r)
    d = PATHS['publish']
    if not os.path.isdir(os.path.join(d, '.git')):
        return err, False, None, 0
    b = branch(d)
    last = run(d, 'log', '-1', '--format=%ct', 'origin/' + b, check=False).stdout.strip()
    ahead = run(d, 'rev-list', '--count', 'origin/%s..HEAD' % b if last else 'HEAD', check=False).stdout.strip()
    return err, True, int(last) * 1000 if last else None, int(ahead or 0)
