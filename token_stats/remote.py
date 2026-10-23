"""经 ssh 在远端执行 scan.py：远端零安装、零写入，只回传新增请求和读取进度。见 PROJECT.md 第 3 节。"""
import json
import os
import subprocess

from . import scan

# 不交互、不卡住；覆盖用户 ssh 配置里可能有的 RemoteCommand / RequestTTY。不改任何 ssh 配置
SSH_OPTS = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'RemoteCommand=none',
            '-o', 'RequestTTY=no', '-o', 'Compression=yes']


def log_roots(claude_dirs=None, codex_home='~/.codex'):
    """日志目录（未展开 ~，本机由调用方展开，远端由 scan.remote() 按远端家目录展开）。"""
    return {'claude-code': claude_dirs or ['~/.claude/projects', '~/.config/claude/projects'],
            'codex': [os.path.join(codex_home, 'sessions'), os.path.join(codex_home, 'archived_sessions')]}


def remote_program(roots, known):
    """发给远端 `python -` 的程序：scan.py 源码 + 一行调用。参数以 JSON 字符串字面量嵌入。"""
    with open(scan.__file__, encoding='utf-8') as f:
        source = f.read()
    return source + '\nremote(json.loads(%r))\n' % json.dumps({'roots': roots, 'known': known})


def _ssh(host, python):
    # -B 不写 .pyc（以管理员身份运行时可能写进系统库目录），-I 忽略远端环境变量和用户 site-packages
    return ['ssh'] + SSH_OPTS + [host, python, '-I', '-B', '-']


def remote_events(host, python, roots, known):
    p = subprocess.Popen(_ssh(host, python), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # 远端 python 先读完整个 stdin 才开始执行，所以先写完再读输出不会互相阻塞
    p.stdin.write(remote_program(roots, known).encode('utf-8'))
    p.stdin.close()
    for line in p.stdout:
        yield json.loads(line)
    err = p.stderr.read().decode('utf-8', 'replace').strip()
    if p.wait() != 0:
        raise RuntimeError('ssh %s 退出码 %d：%s' % (host, p.returncode, err.splitlines()[-1] if err else ''))


def python_version(host, python):
    """远端 Python 版本，形如 (3, 11)；连不上或没有该命令时抛 RuntimeError。"""
    r = subprocess.run(_ssh(host, python), input=b'import sys; print("%d %d" % sys.version_info[:2])',
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    err = r.stderr.decode('utf-8', 'replace').strip()
    if r.returncode != 0:
        raise RuntimeError('退出码 %d：%s' % (r.returncode, err.splitlines()[-1] if err else ''))
    return tuple(int(x) for x in r.stdout.split())
