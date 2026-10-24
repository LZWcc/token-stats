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
        self.assertEqual(len(svgs), 8)
        self.assertTrue(os.path.exists(os.path.join(out, 'preview.html')))
        for name, svg in svgs.items():
            minidom.parseString(svg.encode('utf-8'))   # 都是合法的 XML
        return svgs

    def test_no_data(self):
        svgs = self.render([])
        for name in ('models-donut', 'models-donut-dark', 'models-bar', 'models-bar-dark'):
            self.assertIn('暂无数据', svgs[name + '.svg'])

    def test_cjk_long_and_special_names(self):
        v = lambda n: {'input': n, 'cache_write': 0, 'cache_read': 0, 'output': 0}
        models = {'中文模型名' * 10: v(5), 'a' * 300: v(4), 'x<&>"y': v(3), 'claude-x': v(2)}
        svgs = self.render([{'date': '2026-02-28', 'input': 14, 'cache_write': 0, 'cache_read': 0, 'output': 0,
                             'agents': {'claude-code': v(14)}, 'models': models}])
        self.assertIn('…', svgs['models-bar.svg'])
        self.assertNotIn('a' * 300, svgs['models-bar.svg'])


if __name__ == '__main__':
    unittest.main()
