# 卡片

以下是作者自己的数据，每天更新。每张卡片都有亮色、暗色两份（`<名字>.svg` 和 `<名字>-dark.svg`），用 `<picture>` 按访客的 GitHub 主题切换：

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/<名字>-dark.svg">
  <img alt="Token 用量" src="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/<名字>.svg">
</picture>
```

`token-stats init` 最后会打印每张卡片填好仓库地址的片段。宽卡片 746 px；窄卡片 365 px，两张并排正好等于一张宽卡片。

## overview 概览

模型占比环形图（全部时间，中心为总量）、近半年热力图，底部一行是近 7 天、近 30 天、活跃天数、连续使用。只想放一张图时用它。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/overview-dark.svg">
  <img alt="Token 概览" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/overview.svg">
</picture>

## heatmap 热力图

最近一年的每日用量，标题行写着过去一年的总量和活跃天数。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap-dark.svg">
  <img alt="Token 用量" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap.svg">
</picture>

## stats 统计

总量、近 7 天、近 30 天、活跃天数、连续使用（附最长纪录）、最常用模型，底部注明口径。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/stats-dark.svg">
  <img alt="Token 统计" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/stats.svg">
</picture>

## monthly 月度用量

最近 12 个月，按 Claude Code / Codex 堆叠，标出峰值月份和本月。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/monthly-dark.svg">
  <img alt="月度用量" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/monthly.svg">
</picture>

## models-donut 模型占比、models-bar 模型排行

窄卡片，两张等高，可以并排。环形图为前 5 名 + 其他；排行图为前 8 名，按厂商上色。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-donut-dark.svg">
  <img alt="模型占比" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-donut.svg">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-bar-dark.svg">
  <img alt="模型排行" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-bar.svg">
</picture>

## heatmap-half 近半年热力图、agents 工具对比

窄卡片，两张等高，可以并排。工具对比列出 Claude Code 和 Codex 各自的总量、占比、近 30 天用量和活跃天数。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap-half-dark.svg">
  <img alt="近半年用量" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap-half.svg">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/agents-dark.svg">
  <img alt="工具对比" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/agents.svg">
</picture>

## badge 徽章

shields.io 默认样式，可以和其他项目的徽章放在一起。颜色不随主题变化，直接用 `<img>`：

<img alt="AI tokens" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/badge.svg">

```html
<img alt="AI tokens" src="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/badge.svg">
```
