"""卡片渲染（PROJECT.md 第 9 节）。"""
import json
import os
import re
import unittest
from datetime import date
from xml.dom import minidom

from token_stats import render
from tests.helpers import TempDirTest

LIGHT = render.THEMES['light']
ANTHROPIC, OPENAI = '#d97757', '#10a37f'


def legend(svg):
    """环形图图例：[(名字, 颜色)]。"""
    return [(name, color) for color, name in re.findall(r'<rect [^>]*fill="(#\w+)"/>\s*<text [^>]*>([^<]*)</text>', svg)]


class HelpersTest(unittest.TestCase):
    def test_human(self):
        self.assertEqual([render.human(n) for n in (999, 1500, 2000000, 1.23e9, 3e12)], ['999', '1.5K', '2M', '1.2B', '3T'])

    def test_fit(self):
        self.assertEqual(render.fit('short', 100, 12), 'short')
        for name in ('x' * 200, '模型' * 50):
            s = render.fit(name, 100, 12)
            self.assertTrue(s.endswith('…'))
            self.assertLessEqual(render.text_w(s, 12), 100)

    def test_vendor(self):
        names = ['openrouter/anthropic/claude-x', 'gpt-5', 'o3-mini', 'codex-auto-review', 'gemini-3', 'deepseek-v3', 'mimo']
        self.assertEqual([render.vendor(LIGHT, n)[0] for n in names],
                         ['Anthropic', 'OpenAI', 'OpenAI', 'OpenAI', 'Google', 'DeepSeek', '其他厂商'])


class DonutColorTest(unittest.TestCase):
    def test_brand_colors_and_displaced_series(self):
        s = LIGHT['series']   # 薄荷、薰衣草、奶油黄、天空蓝、蜜桃
        svg = render.donut(LIGHT, {'claude-a': 9, 'gpt-a': 8, 'gpt-b': 7, 'mimo': 6, 'kimi': 5, 'x': 1}, 200)
        # 两家各自用量最高的模型用品牌色；让出薄荷（≈ OpenAI 绿）和蜜桃（≈ Anthropic 橙）
        self.assertEqual(legend(svg), [('claude-a', ANTHROPIC), ('gpt-a', OPENAI), ('gpt-b', s[1]), ('mimo', s[2]),
                                       ('kimi', s[3]), ('其他 1 个模型', LIGHT['other'])])

    def test_same_vendor_top_two(self):
        s = LIGHT['series']
        svg = render.donut(LIGHT, {'claude-a': 9, 'claude-b': 8, 'mimo': 7, 'gemini': 6, 'kimi': 5}, 200)
        self.assertEqual(legend(svg), [('claude-a', ANTHROPIC), ('claude-b', s[0]), ('mimo', s[1]), ('gemini', s[2]),
                                       ('kimi', s[3])])


class RenderCardsTest(TempDirTest):
    def render(self, days):
        d = self.path('daily')
        os.makedirs(d)
        for day in days:
            with open(os.path.join(d, day['date'] + '.json'), 'w', encoding='utf-8') as f:
                json.dump(day, f, ensure_ascii=False)
        out = self.path('cards')
        render.render_cards(d, out, 'all', date(2026, 3, 1))
        svgs = {}
        for f in sorted(os.listdir(out)):
            if f.endswith('.svg'):
                with open(os.path.join(out, f), encoding='utf-8') as fh:
                    svgs[f] = fh.read()
        self.assertEqual(len(svgs), 14)
        self.assertTrue(os.path.exists(os.path.join(out, 'preview.html')))
        for name, svg in svgs.items():
            minidom.parseString(svg.encode('utf-8'))   # 都是合法的 XML
        return svgs

    def test_no_data(self):
        svgs = self.render([])
        for name in ('models-donut', 'models-donut-dark', 'models-bar', 'models-bar-dark', 'monthly', 'monthly-dark',
                     'agents', 'agents-dark'):
            self.assertIn('暂无数据', svgs[name + '.svg'])
        self.assertIn('>0</text>', svgs['badge.svg'])

    def test_cjk_long_and_special_names(self):
        v = lambda n: {'input': n, 'cache_write': 0, 'cache_read': 0, 'output': 0}
        models = {'中文模型名' * 10: v(5), 'a' * 300: v(4), 'x<&>"y': v(3), 'claude-x': v(2)}
        svgs = self.render([{'date': '2026-02-28', 'input': 14, 'cache_write': 0, 'cache_read': 0, 'output': 0,
                             'agents': {'claude-code': v(14)}, 'models': models}])
        self.assertIn('…', svgs['models-bar.svg'])
        self.assertNotIn('a' * 300, svgs['models-bar.svg'])


def day(date, **agents):
    """一天的日数据：agents 为 {agent: 输入 token 数}，模型用同名占位。"""
    v = lambda n: {'input': n, 'cache_write': 0, 'cache_read': 0, 'output': 0}
    total = sum(agents.values())
    return {'date': date, 'input': total, 'cache_write': 0, 'cache_read': 0, 'output': 0,
            'agents': {a: v(n) for a, n in agents.items()}, 'models': {a + '-model': v(n) for a, n in agents.items()}}


class NewCardsTest(unittest.TestCase):
    TODAY = date(2026, 3, 15)

    def test_nice(self):
        self.assertEqual([render.nice(v) for v in (1, 3, 3.3e9, 4.5e6, 7000, 1e3)], [1, 4, 4e9, 5e6, 1e4, 1e3])

    def agent_days(self, days):
        return {d['date']: {a: x['input'] for a, x in d['agents'].items()} for d in days}

    def test_monthly(self):
        days = [day('2025-03-31', codex=999),               # 12 个月之前，不计入
                day('2025-04-01', codex=10), day('2026-02-10', codex=30, **{'claude-code': 20}), day('2026-03-14', codex=5)]
        svg = render.monthly(LIGHT, self.agent_days(days), self.TODAY)
        minidom.parseString(svg.encode('utf-8'))
        self.assertIn('最近 12 个月 · 65', svg)
        self.assertNotIn('999', svg)
        self.assertIn('>Apr</text>', svg)                    # 窗口从去年 4 月开始，最后一列是本月
        self.assertIn('>本月</text>', svg)
        self.assertNotIn('>Mar</text>', svg)
        self.assertIn('>50</text>', svg)                     # 峰值月份（2 月）和本月才标数值
        self.assertIn('>5</text>', svg)
        self.assertNotIn('>10</text>', svg)
        self.assertEqual(svg.count('y="17" width="10"'), 2)  # 两个 agent 有图例
        self.assertIn(ANTHROPIC, svg)
        self.assertIn(OPENAI, svg)

    def test_monthly_single_agent_has_no_legend(self):
        svg = render.monthly(LIGHT, self.agent_days([day('2026-03-01', codex=5)]), self.TODAY)
        self.assertNotIn('y="17" width="10"', svg)

    def test_tools(self):
        days = [day('2026-01-01', codex=300), day('2026-03-10', codex=100, **{'claude-code': 100}), day('2026-03-11', other=0)]
        svg = render.tools(LIGHT, self.agent_days(days), self.TODAY, 274)
        minidom.parseString(svg.encode('utf-8'))
        self.assertIn('全部时间 · 500', svg)
        # Codex 在前（用量大）；近 30 天只算 2 月 14 日以后
        self.assertLess(svg.index('>Codex<'), svg.index('>Claude Code<'))
        self.assertIn('近 30 天 100 · 活跃 2 天', svg)
        self.assertIn('首次使用 2026-01-01', svg)
        self.assertIn('80.0%', svg)
        self.assertIn('20.0%', svg)
        self.assertNotIn('>other<', svg)                     # 用量为 0 的 agent 不列出

    def test_badge(self):
        svg = render.badge(7.6e9)
        minidom.parseString(svg.encode('utf-8'))
        self.assertIn('>AI tokens<', svg)
        self.assertIn('>7.6B<', svg)
        self.assertIn(render.BADGE[1], svg)


if __name__ == '__main__':
    unittest.main()
