"""配置文件、数据目录与时区。见 PROJECT.md 第 2 节。"""
import json
import os
from datetime import datetime

if os.name == 'nt':
    CONFIG_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'token-stats')
    DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'token-stats')
else:
    CONFIG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'token-stats')
    DATA_DIR = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), 'token-stats')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
PATHS = {
    'db': os.path.join(DATA_DIR, 'usage.db'),
    'daily': os.path.join(DATA_DIR, 'daily'),
    'cards': os.path.join(DATA_DIR, 'cards'),
    'backups': os.path.join(DATA_DIR, 'backups'),
    'log': os.path.join(DATA_DIR, 'run.log'),
    'publish': os.path.join(DATA_DIR, 'publish'),
}
DEFAULTS = {'machine': 'local', 'remotes': [], 'merge': [], 'timezone': None, 'metric': 'all', 'publish': None}


def load():
    """读取配置并补全默认值；没有配置文件时返回 None。"""
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, encoding='utf-8') as f:
        cfg = dict(DEFAULTS, **json.load(f))
    for r in cfg['remotes']:
        r.setdefault('name', r['ssh'])
        r.setdefault('python', 'python3')
    return cfg


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write('\n')


def get_tz(name):
    """配置的时区。返回 None 表示用系统本地时间：没配置，或本机没有时区数据（Windows 上标准库不带 tzdata）。"""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except (ImportError, KeyError, ValueError) as e:   # ZoneInfoNotFoundError 是 KeyError 的子类
        print('提示：无法加载时区 %s（%s），改用系统本地时间' % (name, e))
        return None


def local_day(ts_ms, tz):
    """毫秒时间戳 → 该时区的日期。tz 为 None 时用系统本地时间，夏令时由操作系统处理。"""
    return datetime.fromtimestamp(ts_ms / 1000, tz).date()


def today(tz):
    return datetime.now(tz).date()


def noon_ms(day, tz):
    """'YYYY-MM-DD' 当天 12:00（该时区）的毫秒时间戳。"""
    y, m, d = map(int, day.split('-'))
    return int(datetime(y, m, d, 12, tzinfo=tz).timestamp() * 1000)
