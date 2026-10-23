// 从 data/daily 渲染类 GitHub 贡献图 SVG（亮色、暗色各一张），规则见 PROJECT.md 第 9 节。
// 用法：node scripts/render.js [--data data/daily] [--out output]
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import YAML from 'yaml';

const { values: args } = parseArgs({
  options: {
    data: { type: 'string', default: 'data/daily' },
    out: { type: 'string', default: 'output' },
  },
});
const config = YAML.parse(readFileSync('config.yaml', 'utf8'));
const value = config.render?.metric === 'all'
  ? (d) => d.input + d.cache_write + d.cache_read + d.output
  : (d) => d.input + d.cache_write + d.output;

// 按日期合计所有机器、所有 agent
const totals = new Map();
for (const f of readdirSync(args.data, { recursive: true })) {
  if (!f.endsWith('.json')) continue;
  const d = JSON.parse(readFileSync(join(args.data, f), 'utf8'));
  totals.set(d.date, (totals.get(d.date) ?? 0) + value(d));
}

// 53 列，每列周日开始，最后一列截止到今天（按配置时区）
const DAY = 86400000;
const today = new Intl.DateTimeFormat('en-CA', { timeZone: config.timezone }).format(new Date());
const end = Date.parse(today + 'T00:00:00Z');
const start = end - (new Date(end).getUTCDay() + 52 * 7) * DAY;
const days = [];
for (let t = start; t <= end; t += DAY) {
  const date = new Date(t).toISOString().slice(0, 10);
  days.push({ date, v: totals.get(date) ?? 0 });
}

// 分档：0 单独一档，非零日按四分位分 4 档（与 GitHub 相同）
const nonzero = days.map((d) => d.v).filter((v) => v > 0).sort((a, b) => a - b);
const quartiles = [0.25, 0.5, 0.75].map((p) => nonzero[Math.floor((nonzero.length - 1) * p)]);
const level = (v) => (v === 0 ? 0 : 1 + quartiles.filter((q) => v > q).length);

const human = (n) => {
  for (const [unit, suffix] of [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']]) {
    if (n >= unit) return (n / unit).toFixed(1).replace(/\.0$/, '') + suffix;
  }
  return String(n);
};
const total = nonzero.reduce((a, b) => a + b, 0);
const peak = days.reduce((a, b) => (b.v > a.v ? b : a));
const stats = [`过去一年 ${human(total)}`, `活跃 ${nonzero.length} 天`];
if (peak.v > 0) stats.push(`峰值 ${human(peak.v)} (${peak.date.slice(5)})`);

const THEMES = {
  light: { text: '#1f2328', muted: '#59636e', cells: ['#eff2f5', '#aceebb', '#4ac26b', '#2da44e', '#116329'] },
  dark: { text: '#f0f6fc', muted: '#9198a1', cells: ['#151b23', '#033a16', '#196c2e', '#2ea043', '#56d364'] },
};
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const CELL = 10, STEP = 13, LEFT = 32, TOP = 44;
const COLS = Math.ceil(days.length / 7);
const W = LEFT + COLS * STEP + 8, H = TOP + 7 * STEP + 26;

// 月份标签放在该月第一次出现的列；与下一个标签相距不足 3 列的丢掉，避免重叠
const monthCols = [];
for (let col = 0; col < COLS; col++) {
  if (col === 0 || days[col * 7].date.slice(5, 7) !== days[(col - 1) * 7].date.slice(5, 7)) monthCols.push(col);
}
const labelCols = monthCols.filter((c, i) => i === monthCols.length - 1 || monthCols[i + 1] - c >= 3);

function render({ text, muted, cells }) {
  const out = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" ` +
      `font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif">`,
    `<text x="${LEFT}" y="18" font-size="14" font-weight="600" fill="${text}">Token 用量` +
      `<tspan dx="10" font-size="12" font-weight="400" fill="${muted}">${stats.join(' · ')}</tspan></text>`,
  ];
  for (const col of labelCols) {
    const month = MONTHS[Number(days[col * 7].date.slice(5, 7)) - 1];
    out.push(`<text x="${LEFT + col * STEP}" y="${TOP - 6}" font-size="10" fill="${muted}">${month}</text>`);
  }
  for (const [row, name] of [[1, 'Mon'], [3, 'Wed'], [5, 'Fri']]) {
    out.push(`<text x="${LEFT - 6}" y="${TOP + row * STEP + 9}" font-size="10" text-anchor="end" fill="${muted}">${name}</text>`);
  }
  days.forEach((d, i) => {
    const x = LEFT + Math.floor(i / 7) * STEP, y = TOP + (i % 7) * STEP;
    out.push(`<rect x="${x}" y="${y}" width="${CELL}" height="${CELL}" rx="2" fill="${cells[level(d.v)]}"/>`);
  });
  // 图例：右下角“少 □□□□□ 多”
  const ly = TOP + 7 * STEP + 8, lx = LEFT + COLS * STEP - 3 - 5 * STEP - 16;
  out.push(`<text x="${lx - 4}" y="${ly + 9}" font-size="10" text-anchor="end" fill="${muted}">少</text>`);
  cells.forEach((c, i) => out.push(`<rect x="${lx + i * STEP}" y="${ly}" width="${CELL}" height="${CELL}" rx="2" fill="${c}"/>`));
  out.push(`<text x="${lx + 5 * STEP + 1}" y="${ly + 9}" font-size="10" fill="${muted}">多</text>`);
  out.push('</svg>');
  return out.join('\n') + '\n';
}

mkdirSync(args.out, { recursive: true });
writeFileSync(join(args.out, 'token-stats.svg'), render(THEMES.light));
writeFileSync(join(args.out, 'token-stats-dark.svg'), render(THEMES.dark));
console.log(`${today} 截止的 ${days.length} 天，${stats.join(' · ')} → ${args.out}/token-stats{,-dark}.svg`);
