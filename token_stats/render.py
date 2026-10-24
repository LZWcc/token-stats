"""卡片渲染：从日数据生成九张静态 SVG 卡片（亮色、暗色各一份）和本地预览页。

热力图统计最近一年，半年热力图统计最近 26 周，月度用量统计最近 12 个月；概览左上模型占比（全部时间）、右上近半年热力图、
底部一行统计；
模型占比环形图、模型排行条形图、统计卡片、工具对比、徽章统计全部时间。
配色按 dataviz 规范在 GitHub 亮 / 暗背景下验证过，见 PROJECT.md 第 9 节。只用标准库，兼容 Python 3.9。
"""
import glob
import json
import math
import os
import unicodedata
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

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
# 环形图里这两家用量最高的模型用品牌色，并让出与品牌色相近的分类色（橙 ≈ 蜜桃、绿 ≈ 薄荷）：厂商 → 让出的 series 下标
DONUT_BRANDS = {'Anthropic': 4, 'OpenAI': 0}
# agent 的颜色取对应厂商的颜色（与排行图一致），颜色跟着工具走；未知的 agent 用“其他”的灰色
AGENT_NAMES = {'claude-code': ('Claude Code', 'Anthropic'), 'codex': ('Codex', 'OpenAI')}
# 徽章：左灰右绿、白字，对比度 7.5 和 5.7（≥ 4.5），亮暗两份相同
BADGE = ('#555555', '#037465')
# Verdana 11px 下 ASCII 32–126 的字宽（macOS 上用 AppKit 实测），用来按 shields.io 的算法算徽章宽度；其他字符按 11px 计
VERDANA = (3.87, 4.33, 5.05, 9.00, 6.99, 11.84, 7.99, 2.95, 5.00, 5.00, 6.99, 9.00, 4.00, 5.00, 4.00, 5.00, 6.99, 6.99, 6.99, 6.99,
           6.99, 6.99, 6.99, 6.99, 6.99, 6.99, 5.00, 5.00, 9.00, 9.00, 9.00, 6.00, 11.00, 7.52, 7.54, 7.68, 8.48, 6.96, 6.32, 8.53,
           8.27, 4.63, 5.00, 7.62, 6.12, 9.27, 8.23, 8.66, 6.63, 8.66, 7.65, 7.52, 6.78, 8.05, 7.52, 10.88, 7.54, 6.77, 7.54, 5.00,
           5.00, 5.00, 9.00, 6.99, 6.99, 6.61, 6.85, 5.73, 6.85, 6.55, 3.87, 6.85, 6.96, 3.02, 3.79, 6.51, 3.02, 10.70, 6.96, 6.68,
           6.85, 6.85, 4.69, 5.73, 4.33, 6.96, 6.51, 9.00, 6.51, 6.51, 5.78, 6.98, 5.00, 6.98, 9.00)
FONT = "system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif"
PAD = 16
STEP, CELL = 13, 10                     # 热力图格子步长、边长
WIDE = PAD + 28 + 53 * STEP - 3 + PAD   # 宽卡片：热力图、统计
NARROW = (WIDE - PAD) // 2              # 窄卡片：环形图、排行，两张并排加间距等于宽卡片
TOP_N_DONUT, TOP_N_BAR = 5, 8
HALF_WEEKS, HALF_STEP, HALF_CELL = 26, 11, 9           # 半年热力图：26 周放进窄卡片，格子比全年的小一号
HALF_H = 62 + 7 * HALF_STEP + 10 + HALF_CELL + PAD      # 半年热力图的高度；工具对比、概览与它等高
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def human(n):
    for unit, suffix in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if n >= unit:
            return ('%.1f' % (n / unit)).rstrip('0').rstrip('.') + suffix
    return str(n)


def text_w(s, size):
    """估算文字宽度：中文等全角字符约 1 em，其余约 0.6 em。SVG 无法在生成时测量文字。"""
    return sum(1.0 if unicodedata.east_asian_width(ch) in 'WF' else 0.6 for ch in s) * size


def fit(name, px, size):
    """放不下就截断加省略号。"""
    if text_w(name, size) <= px:
        return name
    while name and text_w(name + '…', size) > px:
        name = name[:-1]
    return name + '…'


def no_data(t, x, y):
    return '<text x="%d" y="%d" font-size="12" text-anchor="middle" fill="%s">暂无数据</text>\n' % (x, y, t['muted'])


def card(w, h, t, title, body):
    return ''.join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="%s">\n'
        % (w, h, w, h, FONT),
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="6" fill="none" stroke="%s"/>\n' % (w - 1, h - 1, t['border']),
        '<text x="%d" y="30" font-size="14" font-weight="600" fill="%s">%s</text>\n' % (PAD, t['text'], title),
        body, '</svg>\n'])


def subtitle(t, s):
    return '<tspan dx="10" font-size="12" font-weight="400" fill="%s">%s</tspan>' % (t['muted'], s)


def heat_grid(t, days, today, weeks, step, cell, left, top, right):
    """热力图的格子、月份与星期标签、右下角色阶图例。返回 (SVG 片段列表, 底边 y, 非零日的用量)。"""
    # weeks 列，每列从周日开始，最后一列截止到今天
    start = today - timedelta(days=(today.weekday() + 1) % 7 + (weeks - 1) * 7)
    cells = []
    d = start
    while d <= today:
        cells.append(days.get(d.isoformat(), 0))
        d += timedelta(days=1)
    nonzero = sorted(v for v in cells if v > 0)
    # 0 单独一档，非零日按四分位分 4 档（与 GitHub 相同）
    qs = [nonzero[int((len(nonzero) - 1) * p)] for p in (0.25, 0.5, 0.75)] if nonzero else []
    level = lambda v: 0 if v == 0 else 1 + sum(v > q for q in qs)
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
        out.append('<text x="%d" y="%d" font-size="10" fill="%s">%s</text>' % (left + col * step, top - 8, t['muted'], MONTHS[m - 1]))
    for row, name in ((1, 'Mon'), (3, 'Wed'), (5, 'Fri')):
        out.append('<text x="%d" y="%d" font-size="10" text-anchor="end" fill="%s">%s</text>'
                   % (left - 6, top + row * step + cell - 1, t['muted'], name))
    for i, v in enumerate(cells):
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"/>'
                   % (left + i // 7 * step, top + i % 7 * step, cell, cell, t['heat'][level(v)]))
    # 色阶图例：右下角“少 □□□□□ 多”
    ly = top + 7 * step + 10
    lx = right - 14 - 5 * step
    out.append('<text x="%d" y="%d" font-size="10" text-anchor="end" fill="%s">少</text>' % (lx - 4, ly + cell - 1, t['muted']))
    for i, c in enumerate(t['heat']):
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"/>' % (lx + i * step, ly, cell, cell, c))
    out.append('<text x="%d" y="%d" font-size="10" fill="%s">多</text>' % (lx + 5 * step + 1, ly + cell - 1, t['muted']))
    return out, ly + cell, nonzero


def heatmap(t, days, today):
    out, bottom, nonzero = heat_grid(t, days, today, 53, STEP, CELL, PAD + 28, 62, WIDE - PAD)
    title = 'Token 用量' + subtitle(t, '过去一年 %s · 活跃 %d 天' % (human(sum(nonzero)), len(nonzero)))
    return card(WIDE, bottom + PAD, t, title, '\n'.join(out) + '\n')


def heatmap_half(t, days, today):
    out, bottom, nonzero = heat_grid(t, days, today, HALF_WEEKS, HALF_STEP, HALF_CELL, PAD + 28, 62, NARROW - PAD)
    title = 'Token 用量' + subtitle(t, '近半年 %s · 活跃 %d 天' % (human(sum(nonzero)), len(nonzero)))
    return card(NARROW, bottom + PAD, t, title, '\n'.join(out) + '\n')


def ranked(models, n):
    """前 n 名 + “其他”（其余合计，只有超过 n 个模型时才有）。"""
    items = sorted(models.items(), key=lambda kv: -kv[1])
    top = items[:n]
    rest = sum(v for _, v in items[n:])
    return top, rest, len(items)


def model_segments(t, models, n):
    """前 n 名 + “其他”：[(名字, 用量, 颜色)]。Claude、GPT 系列各自用量最高的模型用厂商色，并让出相近的分类色。"""
    top, rest, count = ranked(models, n)
    first = {}
    for name, _ in top:
        vname, color = vendor(t, name)
        if vname in DONUT_BRANDS:
            first.setdefault(vname, (name, color))
    picked = dict(first.values())
    pool = iter([c for i, c in enumerate(t['series']) if i not in {DONUT_BRANDS[v] for v in first}])
    segs = [(name, v, picked[name] if name in picked else next(pool)) for name, v in top]
    if rest:
        segs.append(('其他 %d 个模型' % (count - n), rest, t['other']))
    return segs


def donut(t, models, height):
    segs = model_segments(t, models, TOP_N_DONUT)
    total = sum(v for _, v, _ in segs)
    cx, cy, r, width = PAD + 66, 52 + (height - 52 - PAD) // 2, 52, 18
    if not segs:
        ring = '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d"/>\n' % (cx, cy, r, t['heat'][0], width)
        return card(NARROW, height, t, '模型占比' + subtitle(t, '全部时间'), ring + no_data(t, cx, cy + 4))
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
    if not top:
        return card(NARROW, height, t, '模型排行' + subtitle(t, '全部时间'), no_data(t, NARROW // 2, height // 2 + 10))
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
        out.append('<rect x="%.1f" y="%d" width="10" height="10" rx="2" fill="%s"/>' % (x, y, color))
        out.append('<text x="%.1f" y="%d" font-size="11" fill="%s">%s</text>' % (x + 14, y + 9, t['muted'], vname))
        x += 14 + text_w(vname, 11) + 14
    note = '全部时间' + (' · 前 %d / 共 %d 个' % (TOP_N_BAR, count) if count > TOP_N_BAR else '')
    return card(NARROW, height, t, '模型排行' + subtitle(t, note), '\n'.join(out) + '\n')


def badge_text_w(s):
    return round(sum(VERDANA[ord(c) - 32] if 32 <= ord(c) < 127 else 11 for c in s))


def agent_style(t, agent):
    name, vname = AGENT_NAMES.get(agent, (agent, None))
    return name, next((c for n, _, c in VENDORS if n == vname), t['other'])


def nice(v):
    """不小于 v 的整齐刻度上限（1、2、4、5 × 10^k），平分成两格后仍是整齐的数。"""
    k = 10 ** math.floor(math.log10(v))
    return next(m * k for m in (1, 2, 4, 5, 10) if m * k >= v)


def column(x, y, w, h, color):
    """柱子：基线端直角，数值端（顶部）4px 圆角。"""
    r = min(4, w / 2, h / 2)
    return ('<path d="M%.1f %.1f v%.1f a%.1f %.1f 0 0 1 %.1f %.1f h%.1f a%.1f %.1f 0 0 1 %.1f %.1f v%.1f z" fill="%s"/>'
            % (x, y + h, -(h - r), r, r, r, -r, w - 2 * r, r, r, r, r, h - r, color))


def monthly(t, agent_days, today):
    # 最近 12 个月（含本月），每月按 agent 堆叠；用量大的 agent 在下面
    months = [((today.year * 12 + today.month - 1 - i) // 12, (today.month - 1 - i) % 12 + 1) for i in range(11, -1, -1)]
    vals = {k: {} for k in months}
    for d, per in agent_days.items():
        key = (int(d[:4]), int(d[5:7]))
        if key in vals:
            for a, v in per.items():
                vals[key][a] = vals[key].get(a, 0) + v
    by_agent = {}
    for per in vals.values():
        for a, v in per.items():
            by_agent[a] = by_agent.get(a, 0) + v
    order = [a for a, v in sorted(by_agent.items(), key=lambda kv: -kv[1]) if v > 0]
    totals = [sum(vals[k].values()) for k in months]
    height = 210
    title = '月度用量' + subtitle(t, '最近 12 个月 · %s' % human(sum(totals)))
    if not order:
        return card(WIDE, height, t, title, no_data(t, WIDE // 2, height // 2 + 10))
    left, right, top, base = PAD + 36, WIDE - PAD, 58, 178
    slot, bw = (right - left) / 12, 24
    peak = nice(max(totals))
    out = []
    # 刻度：0、一半、上限；网格线为细实线，基线用边框色
    for i, v in enumerate((0, peak / 2, peak)):
        y = base - (base - top) * i / 2
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>'
                   % (left, y + 0.5, right, y + 0.5, t['border'] if i == 0 else t['heat'][0]))
        out.append('<text x="%d" y="%.1f" font-size="10" text-anchor="end" fill="%s">%s</text>' % (left - 6, y + 4, t['muted'], human(v)))
    hi = max(range(12), key=lambda i: totals[i])
    for i, k in enumerate(months):
        x = left + i * slot + (slot - bw) / 2
        y = base
        segs = [(a, vals[k][a]) for a in order if vals[k].get(a, 0) > 0]
        for j, (a, v) in enumerate(segs):
            h = (base - top) * v / peak
            last = j == len(segs) - 1
            # 段与段之间留 2px 背景间隙；只有最上面一段是圆角的数值端
            draw_h = max(h if last else h - 2, 1)
            if last:
                out.append(column(x, y - draw_h, bw, draw_h, agent_style(t, a)[1]))
            else:
                out.append('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" fill="%s"/>' % (x, y - draw_h, bw, draw_h, agent_style(t, a)[1]))
            y -= h
        # 只标峰值月份和本月
        if i in (hi, 11) and totals[i]:
            out.append('<text x="%.1f" y="%.1f" font-size="11" text-anchor="middle" fill="%s">%s</text>'
                       % (x + bw / 2, y - 6, t['text'], human(totals[i])))
        out.append('<text x="%.1f" y="%d" font-size="10" text-anchor="middle" fill="%s">%s</text>'
                   % (x + bw / 2, base + 16, t['muted'], '本月' if i == 11 else MONTHS[k[1] - 1]))
    if len(order) > 1:   # 两个及以上 agent 才有图例，右上角从右往左排
        x = right
        for a in reversed(order):
            name, color = agent_style(t, a)
            x -= text_w(name, 11)
            out.append('<text x="%.1f" y="26" font-size="11" fill="%s">%s</text>' % (x, t['muted'], escape(name)))
            out.append('<rect x="%.1f" y="17" width="10" height="10" rx="2" fill="%s"/>' % (x - 14, color))
            x -= 14 + 14
    return card(WIDE, height, t, title, '\n'.join(out) + '\n')


def tools(t, agent_days, today, height):
    totals, recent, active = {}, {}, {}
    since = (today - timedelta(days=29)).isoformat()
    for d in sorted(agent_days):
        for a, v in agent_days[d].items():
            if v <= 0:
                continue
            totals[a] = totals.get(a, 0) + v
            active[a] = active.get(a, 0) + 1
            if d >= since:
                recent[a] = recent.get(a, 0) + v
    order = sorted(totals, key=lambda a: -totals[a])
    total = sum(totals.values())
    title = '工具对比' + subtitle(t, '全部时间 · %s' % human(total))
    if not total:
        return card(NARROW, height, t, title, no_data(t, NARROW // 2, height // 2 + 10))
    height = max(height, 76 + len(order) * 36 + PAD)   # 工具多时加高
    out = []
    # 占比条：段间 2px 间隙，左端（基线）直角，右端 4px 圆角
    x, span = PAD, NARROW - 2 * PAD
    for j, a in enumerate(order):
        w = span * totals[a] / total
        last = j == len(order) - 1
        draw_w = max(w if last else w - 2, 1)
        color = agent_style(t, a)[1]
        if last:
            r = min(4, draw_w / 2)
            out.append('<path d="M%.1f 48 h%.1f a%.1f %.1f 0 0 1 %.1f %.1f v%.1f a%.1f %.1f 0 0 1 %.1f %.1f h%.1f z" fill="%s"/>'
                       % (x, draw_w - r, r, r, r, r, 10 - 2 * r, r, r, -r, r, -(draw_w - r), color))
        else:
            out.append('<rect x="%.1f" y="48" width="%.1f" height="10" fill="%s"/>' % (x, draw_w, color))
        x += w
    row = (height - 76 - PAD) / max(len(order), 2)   # 各工具在占比条下方均匀分布
    for i, a in enumerate(order):
        name, color = agent_style(t, a)
        y = 76 + i * row
        out.append('<rect x="%d" y="%.1f" width="10" height="10" rx="2" fill="%s"/>' % (PAD, y, color))
        out.append('<text x="%d" y="%.1f" font-size="12" font-weight="600" fill="%s">%s</text>'
                   % (PAD + 16, y + 9, t['text'], escape(fit(name, 150, 12))))
        out.append('<text x="%d" y="%.1f" font-size="12" text-anchor="end" fill="%s">%s%s</text>'
                   % (NARROW - PAD, y + 9, t['text'], human(totals[a]), subtitle(t, '%.1f%%' % (100.0 * totals[a] / total))))
        out.append('<text x="%d" y="%.1f" font-size="11" fill="%s">近 30 天 %s · 活跃 %d 天</text>'
                   % (PAD + 16, y + 27, t['muted'], human(recent.get(a, 0)), active[a]))
    return card(NARROW, height, t, title, '\n'.join(out) + '\n')


def badge(total, label='AI tokens'):
    """shields.io 默认 flat 样式的徽章，结构照 img.shields.io 生成的 SVG：渐变、文字阴影、Verdana、textLength。
    每段宽度 = 文字宽度取整 + 10（与 shields 相同）。颜色不随主题变化。"""
    value = human(total)
    tl, tv = badge_text_w(label), badge_text_w(value)
    lw, vw = tl + 10, tv + 10
    w = lw + vw

    def text(x, s, tw):
        return ('<g transform="scale(.1)"><g aria-hidden="true" fill="#010101">'
                '<text x="%d" y="150" fill-opacity=".8" filter="url(#blur)" textLength="%d">%s</text>'
                '<text x="%d" y="150" fill-opacity=".3" textLength="%d">%s</text></g>'
                '<text x="%d" y="140" textLength="%d">%s</text></g>' % (x, tw * 10, s, x, tw * 10, s, x, tw * 10, s))
    return ''.join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="20" role="img" aria-label="%s: %s"><title>%s: %s</title>'
        % (w, escape(label), value, escape(label), value),
        '<filter id="blur"><feGaussianBlur stdDeviation="16"/></filter>',
        '<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>',
        '<clipPath id="r"><rect width="%d" height="20" rx="3"/></clipPath>' % w,
        '<g clip-path="url(#r)"><rect width="%d" height="20" fill="%s"/><rect x="%d" width="%d" height="20" fill="%s"/>'
        '<rect width="%d" height="20" fill="url(#s)"/></g>' % (lw, BADGE[0], lw, vw, BADGE[1], w),
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">',
        # 与 shields 相同：左段文字中心右移 1px，右段左移 1px
        text(lw * 5 + 10, escape(label), tl), text(lw * 10 + vw * 5 - 10, value, tv),
        '</g></svg>\n'])


def hbar(x, y, w, h, color):
    """横条：左端（基线）直角，右端（数值端）4px 圆角。"""
    r = min(4, w / 2, h / 2)
    return ('<path d="M%.1f %.1f h%.1f a%.1f %.1f 0 0 1 %.1f %.1f v%.1f a%.1f %.1f 0 0 1 %.1f %.1f h%.1f z" fill="%s"/>'
            % (x, y, w - r, r, r, r, r, h - 2 * r, r, r, -r, r, -(w - r), color))


def overview(t, days, models, today):
    """概览：左上模型占比环形图（全部时间），右上近半年热力图，底部一行统计（不重复环形图中心的总量）。"""
    left = WIDE - PAD - (HALF_WEEKS * HALF_STEP - (HALF_STEP - HALF_CELL))
    out, bottom, nonzero = heat_grid(t, days, today, HALF_WEEKS, HALF_STEP, HALF_CELL, left, 62, WIDE - PAD)
    zr = left - 28 - 24                       # 左侧区域的右边界，让出热力图的星期标签
    top, mid = 52, (52 + bottom) / 2
    segs = model_segments(t, models, TOP_N_DONUT)
    total = sum(v for _, v, _ in segs)
    if not segs:
        out.append(no_data(t, (PAD + zr) // 2, int(mid) + 4))
    else:
        # 环形图：与模型占比卡相同的配色和 2px 段间隙，中心为总量
        cx, r, width = PAD + 48, 38, 14
        circ = 2 * math.pi * r
        offset = 0.0
        for name, v, color in segs:
            length = circ * v / total
            out.append('<circle cx="%d" cy="%.1f" r="%d" fill="none" stroke="%s" stroke-width="%d" '
                       'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" transform="rotate(-90 %d %.1f)"/>'
                       % (cx, mid, r, color, width, max(length - 2, 0.5), circ, -offset, cx, mid))
            offset += length
        out.append('<text x="%d" y="%.1f" font-size="15" font-weight="600" text-anchor="middle" fill="%s">%s</text>'
                   % (cx, mid + 3, t['text'], human(total)))
        out.append('<text x="%d" y="%.1f" font-size="9" text-anchor="middle" fill="%s">tokens</text>' % (cx, mid + 15, t['muted']))
        # 图例：名字，token 数与百分比各占一列、右对齐
        lx, pct_w = cx + r + width // 2 + 20, 40
        row = (bottom - top) / len(segs)
        for i, (name, v, color) in enumerate(segs):
            y = top + i * row + (row - 10) / 2
            out.append('<rect x="%d" y="%.1f" width="10" height="10" rx="2" fill="%s"/>' % (lx, y, color))
            out.append('<text x="%d" y="%.1f" font-size="11" fill="%s">%s</text>'
                       % (lx + 16, y + 9, t['text'], escape(fit(name, zr - pct_w - 56 - lx - 16, 11))))
            for x, s in ((zr - pct_w, human(v)), (zr, '%.1f%%' % (100.0 * v / total))):
                out.append('<text x="%d" y="%.1f" font-size="11" text-anchor="end" fill="%s">%s</text>' % (x, y + 9, t['muted'], s))
    # 底部统计：与统计卡相同的算法；没有数据时环形图中心没有总量，才在这里显示
    recent = lambda n: sum(days.get((today - timedelta(days=i)).isoformat(), 0) for i in range(n))
    current, longest = streaks(days, today)
    tiles = ([] if segs else [('总量', human(sum(days.values())), '')]) + [
        ('近 7 天', human(recent(7)), ''), ('近 30 天', human(recent(30)), ''),
        ('活跃天数', '%d 天' % sum(v > 0 for v in days.values()), ''), ('连续使用', '%d 天' % current, '最长 %d 天' % longest)]
    y = bottom + 20
    out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>' % (PAD, y - 0.5, WIDE - PAD, y - 0.5, t['heat'][0]))
    col_w = (WIDE - 2 * PAD) / len(tiles)
    for i, (label, v, extra) in enumerate(tiles):
        x = PAD + i * col_w
        out.append('<text x="%.1f" y="%d" font-size="12" fill="%s">%s</text>' % (x, y + 22, t['muted'], label))
        out.append('<text x="%.1f" y="%d" font-size="18" font-weight="600" fill="%s">%s%s</text>'
                   % (x, y + 46, t['text'], v, subtitle(t, extra) if extra else ''))
    return card(WIDE, y + 46 + PAD, t, 'Token 用量', '\n'.join(out) + '\n')


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


def load(daily_dir, metric):
    """读取日数据：返回 (每天总量, 每个模型总量, 每个 agent 总量, 每天各 agent 的用量)，按口径 metric 计算。"""
    value = lambda x: x['input'] + x['cache_write'] + x['output'] + (x['cache_read'] if metric == 'all' else 0)
    days, models, agents, agent_days = {}, {}, {}, {}
    for p in glob.glob(os.path.join(daily_dir, '*.json')):
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        days[d['date']] = value(d)
        agent_days[d['date']] = {k: value(v) for k, v in d.get('agents', {}).items()}
        for part, acc in (('models', models), ('agents', agents)):
            for k, v in d.get(part, {}).items():
                acc[k] = acc.get(k, 0) + value(v)
    return days, {m: v for m, v in models.items() if v > 0}, agents, agent_days


def render_cards(daily_dir, out_dir, metric, today):
    """生成九张卡片（亮暗各一份）和 preview.html，返回预览页路径。"""
    days, models, _, agent_days = load(daily_dir, metric)
    os.makedirs(out_dir, exist_ok=True)
    pair_h = 52 + TOP_N_BAR * 23 + 22 + PAD   # 环形图与排行等高，便于并排；22 为排行图的厂商图例
    names = ('heatmap', 'stats', 'monthly', 'overview', 'models-donut', 'models-bar', 'heatmap-half', 'agents', 'badge')
    for theme, t in THEMES.items():
        svgs = (heatmap(t, days, today), stats(t, days, models, today, metric), monthly(t, agent_days, today),
                overview(t, days, models, today), donut(t, models, pair_h), bars(t, models, pair_h),
                heatmap_half(t, days, today), tools(t, agent_days, today, HALF_H), badge(sum(days.values())))
        for name, svg in zip(names, svgs):
            with open(os.path.join(out_dir, name + ('-dark' if theme == 'dark' else '') + '.svg'), 'w', encoding='utf-8') as f:
                f.write(svg)
    imgs = lambda suffix: ''.join('<img%s src="%s%s.svg">' % (' class="wide"' if n in ('heatmap', 'stats', 'monthly', 'overview') else '', n, suffix) for n in names)
    preview = os.path.join(out_dir, 'preview.html')
    with open(preview, 'w', encoding='utf-8') as f:
        f.write(PREVIEW % (imgs(''), imgs('-dark')))
    return preview
