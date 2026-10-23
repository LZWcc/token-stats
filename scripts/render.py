#!/usr/bin/env python3
"""token-stats 卡片渲染：从 data/daily 生成四张静态 SVG 卡片（亮色、暗色各一份）和本地预览页。

热力图统计最近一年；模型占比环形图、模型排行条形图、统计卡片统计全部时间。
配色按 dataviz 规范在 GitHub 亮 / 暗背景下验证过，见 PROJECT.md 第 9 节。只用标准库，兼容 Python 3.9。
"""
import argparse
import glob
import json
import os
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

# 与 collector 一致的固定 +8；M3 改为读配置
TZ = timezone(timedelta(hours=8))

THEMES = {
    'light': {'text': '#1f2328', 'muted': '#59636e', 'border': '#d1d9e0',
              'series': ['#46b68c', '#c0a2f5', '#ccb352', '#5dc0f6', '#dc855d'], 'other': '#c3c2b7',
              'heat': ['#ebeef0', '#b3eacb', '#7ad3b0', '#3ab19b', '#128984']},
    'dark': {'text': '#f0f6fc', 'muted': '#9198a1', 'border': '#3d444d',
             'series': ['#3aac83', '#a183d4', '#ac942f', '#3aa0d4', '#d17c54'], 'other': '#52514e',
             'heat': ['#1b2129', '#024d4a', '#037465', '#2f9e7f', '#64cc9d']},
}
# 排行图按厂商上色：模型名去掉中转商前缀（最后一个 / 之后）后按前缀识别。只给 4 家用接近品牌原色的颜色，
# 其余归入“其他厂商”——品牌色多了必然撞色（蓝色系尤其多），见 PROJECT.md 第 9 节
VENDORS = (('Anthropic', ('claude',), '#d97757'), ('OpenAI', ('gpt', 'codex', 'o1', 'o3', 'o4'), '#10a37f'),
           ('Google', ('gemini',), '#7faefd'), ('DeepSeek', ('deepseek',), '#4d6bfe'))
FONT = "system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif"
PAD = 16
STEP, CELL = 13, 10                     # 热力图格子步长、边长
WIDE = PAD + 28 + 53 * STEP - 3 + PAD   # 宽卡片：热力图、统计
NARROW = (WIDE - PAD) // 2              # 窄卡片：环形图、排行，两张并排加间距等于宽卡片
TOP_N_DONUT, TOP_N_BAR = 5, 8
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def human(n):
    for unit, suffix in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if n >= unit:
            return ('%.1f' % (n / unit)).rstrip('0').rstrip('.') + suffix
    return str(n)


def fit(name, px, size):
    """按字号估算宽度（拉丁字符约 0.6em），放不下就截断加省略号。SVG 无法在生成时测量文字。"""
    n = int(px / (size * 0.6))
    return name if len(name) <= n else name[:n - 1] + '…'


def card(w, h, t, title, body):
    return ''.join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="%s">\n'
        % (w, h, w, h, FONT),
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="6" fill="none" stroke="%s"/>\n' % (w - 1, h - 1, t['border']),
        '<text x="%d" y="30" font-size="14" font-weight="600" fill="%s">%s</text>\n' % (PAD, t['text'], title),
        body, '</svg>\n'])


def subtitle(t, s):
    return '<tspan dx="10" font-size="12" font-weight="400" fill="%s">%s</tspan>' % (t['muted'], s)


def heatmap(t, days, today):
    # 53 列，每列从周日开始，最后一列截止到今天
    start = today - timedelta(days=(today.weekday() + 1) % 7 + 52 * 7)
    cells = []
    d = start
    while d <= today:
        cells.append(days.get(d.isoformat(), 0))
        d += timedelta(days=1)
    nonzero = sorted(v for v in cells if v > 0)
    # 0 单独一档，非零日按四分位分 4 档（与 GitHub 相同）
    qs = [nonzero[int((len(nonzero) - 1) * p)] for p in (0.25, 0.5, 0.75)] if nonzero else []
    level = lambda v: 0 if v == 0 else 1 + sum(v > q for q in qs)
    left, top = PAD + 28, 62
    out = []
    prev = None
    labels = []
    for col in range((len(cells) + 6) // 7):
        m = (start + timedelta(days=col * 7)).month
        if m != prev:
            labels.append((col, m))
        prev = m
    # 与下一个标签相距不足 3 列的丢掉，避免重叠
    for i, (col, m) in enumerate(labels):
        if i + 1 < len(labels) and labels[i + 1][0] - col < 3:
            continue
        out.append('<text x="%d" y="%d" font-size="10" fill="%s">%s</text>' % (left + col * STEP, top - 8, t['muted'], MONTHS[m - 1]))
    for row, name in ((1, 'Mon'), (3, 'Wed'), (5, 'Fri')):
        out.append('<text x="%d" y="%d" font-size="10" text-anchor="end" fill="%s">%s</text>'
                   % (left - 6, top + row * STEP + 9, t['muted'], name))
    for i, v in enumerate(cells):
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"/>'
                   % (left + i // 7 * STEP, top + i % 7 * STEP, CELL, CELL, t['heat'][level(v)]))
    # 色阶图例：右下角“少 □□□□□ 多”
    ly = top + 7 * STEP + 10
    lx = WIDE - PAD - 14 - 5 * STEP
    out.append('<text x="%d" y="%d" font-size="10" text-anchor="end" fill="%s">少</text>' % (lx - 4, ly + 9, t['muted']))
    for i, c in enumerate(t['heat']):
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"/>' % (lx + i * STEP, ly, CELL, CELL, c))
    out.append('<text x="%d" y="%d" font-size="10" fill="%s">多</text>' % (lx + 5 * STEP + 1, ly + 9, t['muted']))
    title = 'Token 用量' + subtitle(t, '过去一年 %s · 活跃 %d 天' % (human(sum(nonzero)), len(nonzero)))
    return card(WIDE, ly + CELL + PAD, t, title, '\n'.join(out) + '\n')


def ranked(models, n):
    """前 n 名 + “其他”（其余合计，只有超过 n 个模型时才有）。"""
    items = sorted(models.items(), key=lambda kv: -kv[1])
    top = items[:n]
    rest = sum(v for _, v in items[n:])
    return top, rest, len(items)


def donut(t, models, height):
    top, rest, count = ranked(models, TOP_N_DONUT)
    segs = [(name, v, t['series'][i]) for i, (name, v) in enumerate(top)]
    if rest:
        segs.append(('其他 %d 个模型' % (count - TOP_N_DONUT), rest, t['other']))
    total = sum(v for _, v, _ in segs)
    cx, cy, r, width = PAD + 66, 52 + (height - 52 - PAD) // 2, 52, 18
    circ = 2 * 3.141592653589793 * r
    out = []
    offset = 0.0
    for name, v, color in segs:
        length = circ * v / total
        # 段与段之间留 2px 背景间隙；从 12 点方向顺时针
        out.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d" '
                   'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" transform="rotate(-90 %d %d)"/>'
                   % (cx, cy, r, color, width, max(length - 2, 0.5), circ, -offset, cx, cy))
        offset += length
    out.append('<text x="%d" y="%d" font-size="18" font-weight="600" text-anchor="middle" fill="%s">%s</text>'
               % (cx, cy + 4, t['text'], human(total)))
    out.append('<text x="%d" y="%d" font-size="10" text-anchor="middle" fill="%s">tokens</text>' % (cx, cy + 18, t['muted']))
    lx = PAD + 66 + r + width // 2 + 22
    row = (height - 52 - PAD) / len(segs)
    for i, (name, v, color) in enumerate(segs):
        y = 52 + i * row + (row - 26) / 2
        out.append('<rect x="%d" y="%.1f" width="10" height="10" rx="2" fill="%s"/>' % (lx, y, color))
        out.append('<text x="%d" y="%.1f" font-size="12" fill="%s">%s</text>'
                   % (lx + 16, y + 9, t['text'], escape(fit(name, NARROW - PAD - lx - 16, 12))))
        out.append('<text x="%d" y="%.1f" font-size="11" fill="%s">%s · %.1f%%</text>'
                   % (lx + 16, y + 23, t['muted'], human(v), 100.0 * v / total))
    return card(NARROW, height, t, '模型占比' + subtitle(t, '全部时间'), '\n'.join(out) + '\n')


def vendor(t, model):
    base = model.lower().rsplit('/', 1)[-1]
    for name, prefixes, color in VENDORS:
        if base.startswith(prefixes):
            return name, color
    return '其他厂商', t['other']


def bars(t, models, height):
    top, _, count = ranked(models, TOP_N_BAR)
    name_w, value_w, legend_h = 118, 44, 22
    x0 = PAD + name_w + 8
    max_w = NARROW - PAD - value_w - x0
    row = (height - 52 - PAD - legend_h) / TOP_N_BAR
    out = []
    seen = []
    for i, (name, v) in enumerate(top):
        vname, color = vendor(t, name)
        if vname not in seen:
            seen.append(vname)
        y = 52 + i * row + (row - 10) / 2
        w = max(max_w * v / top[0][1], 2)
        r = min(4, w / 2)
        # 起点（基线）为直角，数值端 4px 圆角
        out.append('<path d="M%d %.1f h%.1f a%.1f %.1f 0 0 1 %.1f %.1f v%.1f a%.1f %.1f 0 0 1 %.1f %.1f h%.1f z" fill="%s"/>'
                   % (x0, y, w - r, r, r, r, r, 10 - 2 * r, r, r, -r, r, -(w - r), color))
        out.append('<text x="%d" y="%.1f" font-size="11" fill="%s">%s</text>'
                   % (PAD, y + 9, t['text'], escape(fit(name, name_w, 11))))
        out.append('<text x="%.1f" y="%.1f" font-size="11" fill="%s">%s</text>' % (x0 + w + 6, y + 9, t['muted'], human(v)))
    # 厂商图例：只列前 n 名里出现的厂商，按出现顺序
    x, y = PAD, height - PAD - 10
    for vname in seen:
        color = vendor(t, next(n for n, _ in top if vendor(t, n)[0] == vname))[1]
        out.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s"/>' % (x, y, color))
        out.append('<text x="%d" y="%d" font-size="11" fill="%s">%s</text>' % (x + 14, y + 9, t['muted'], vname))
        x += 14 + len(vname.encode('gbk')) * 6 + 14   # 估算宽度：汉字按 2 个拉丁字符计
    note = '全部时间' + (' · 前 %d / 共 %d 个' % (TOP_N_BAR, count) if count > TOP_N_BAR else '')
    return card(NARROW, height, t, '模型排行' + subtitle(t, note), '\n'.join(out) + '\n')


def streaks(days, today):
    active = sorted(d for d, v in days.items() if v > 0)
    longest = run = 0
    prev = None
    for d in active:
        cur = datetime.strptime(d, '%Y-%m-%d').date()
        run = run + 1 if prev and cur - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = cur
    # 当前连续：截止到今天；今天还没用过时截止到昨天，不算中断
    current = 0
    d = today if days.get(today.isoformat(), 0) > 0 else today - timedelta(days=1)
    while days.get(d.isoformat(), 0) > 0:
        current += 1
        d -= timedelta(days=1)
    return current, longest


def stats(t, days, models, today, metric):
    recent = lambda n: sum(days.get((today - timedelta(days=i)).isoformat(), 0) for i in range(n))
    current, longest = streaks(days, today)
    top = max(models.items(), key=lambda kv: kv[1])[0] if models else '—'
    tiles = [('总量', human(sum(days.values())), ''), ('近 7 天', human(recent(7)), ''), ('近 30 天', human(recent(30)), ''),
             ('活跃天数', '%d 天' % sum(v > 0 for v in days.values()), ''),
             ('连续使用', '%d 天' % current, '最长 %d 天' % longest), ('最常用模型', None, top)]
    col_w = (WIDE - 2 * PAD) // 3
    out = []
    for i, (label, value, extra) in enumerate(tiles):
        x, y = PAD + i % 3 * col_w, 58 + i // 3 * 58
        out.append('<text x="%d" y="%d" font-size="12" fill="%s">%s</text>' % (x, y, t['muted'], label))
        if value is None:   # 模型名较长，用小一号字
            out.append('<text x="%d" y="%d" font-size="15" font-weight="600" fill="%s">%s</text>'
                       % (x, y + 24, t['text'], escape(fit(extra, col_w - 12, 15))))
            continue
        out.append('<text x="%d" y="%d" font-size="20" font-weight="600" fill="%s">%s%s</text>'
                   % (x, y + 26, t['text'], value, subtitle(t, extra) if extra else ''))
    basis = '输入 + 缓存读取 + 缓存写入 + 输出' if metric == 'all' else '输入 + 缓存写入 + 输出，不含缓存读取'
    h = 58 + 2 * 58 + 6
    out.append('<text x="%d" y="%d" font-size="10" fill="%s">口径：%s</text>' % (PAD, h - PAD, t['muted'], basis))
    return card(WIDE, h, t, 'Token 统计', '\n'.join(out) + '\n')


PREVIEW = """<!doctype html>
<meta charset="utf-8">
<title>token-stats 预览</title>
<style>
  body { margin: 0; font: 13px -apple-system, sans-serif; }
  section { padding: 24px; display: grid; grid-template-columns: repeat(2, max-content); gap: 16px; }
  section img.wide { grid-column: span 2; }
  .light { background: #ffffff; } .dark { background: #0d1117; }
</style>
<section class="light">%s</section>
<section class="dark">%s</section>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data', default='data/daily', help='日数据目录（collector 的 --out）')
    ap.add_argument('--out', default='output', help='输出目录')
    ap.add_argument('--metric', choices=('all', 'effective'), default='all',
                    help='all = 四项全加（默认，与 Codex、ccusage 的“总 token”一致）；effective = 不含缓存读取')
    args = ap.parse_args()

    value = lambda x: x['input'] + x['cache_write'] + x['output'] + (x['cache_read'] if args.metric == 'all' else 0)
    days, models = {}, {}
    for p in glob.glob(os.path.join(args.data, '*.json')):
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        days[d['date']] = value(d)
        for m, v in d['models'].items():
            models[m] = models.get(m, 0) + value(v)
    models = {m: v for m, v in models.items() if v > 0}
    today = datetime.now(TZ).date()

    os.makedirs(args.out, exist_ok=True)
    pair_h = 52 + TOP_N_BAR * 23 + 22 + PAD   # 环形图与排行等高，便于并排；22 为排行图的厂商图例
    names = ('heatmap', 'stats', 'models-donut', 'models-bar')
    for theme, t in THEMES.items():
        svgs = (heatmap(t, days, today), stats(t, days, models, today, args.metric), donut(t, models, pair_h), bars(t, models, pair_h))
        for name, svg in zip(names, svgs):
            with open(os.path.join(args.out, name + ('-dark' if theme == 'dark' else '') + '.svg'), 'w', encoding='utf-8') as f:
                f.write(svg)
    imgs = lambda suffix: ''.join('<img%s src="%s%s.svg">' % (' class="wide"' if n in ('heatmap', 'stats') else '', n, suffix) for n in names)
    with open(os.path.join(args.out, 'preview.html'), 'w', encoding='utf-8') as f:
        f.write(PREVIEW % (imgs(''), imgs('-dark')))
    print('%d 天、%d 个模型 → %s/{%s}{,-dark}.svg 与 preview.html' % (len(days), len(models), args.out, ','.join(names)))


if __name__ == '__main__':
    main()
