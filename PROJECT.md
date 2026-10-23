# token-stats 项目规格（唯一规格来源）

> 本仓库将公开。本文件和所有提交内容都不得包含服务器真实机器名、IP、端口、ssh 别名或配置、代理、用户名、本地路径。这些只记在不提交的 `LOCAL.md` 中。

## 1. 项目目标

个人 AI Coding Token 用量统计工具：汇总多台机器上 Claude Code 与 Codex 的 token 用量，按模型统计（通过 Claude Code / Codex 调用的第三方模型同样计入），生成类似 GitHub 贡献图的 SVG，由 GitHub Action 自动渲染并发布到 GitHub 主页（类似贪吃蛇贡献图）。

## 2. 机器

| 公开 id | 类型 | Agent | 说明 |
|---------|------|-------|------|
| laptop | macOS 笔记本 | codex、claude-code（少量） | 另有 CC Switch 数据库，含约半年本机历史用量（阶段三导入） |
| server-1 | Linux 服务器 | claude-code | |
| server-2 | Linux 服务器 | claude-code | |

公开 id 与真实机器的对应关系只在 `LOCAL.md` 中。每台机器在本机配置里写自己的公开 id。

## 3. 架构

```
每台机器（本机定时运行）
  collector.py：增量读取本机日志 → 逐请求写入本机 usage.db（以请求 id 去重）
             → 导出 data/daily/<公开 id>/… → git commit + push 到 GitHub 公开仓库
GitHub Action（data/ 有推送时运行 + 每天定时运行）
  渲染 SVG → 提交到 output 分支 → 主页 README 引用
```

- 采集在各机器本地完成，原始日志不离开本机。每台机器只写自己的 `data/daily/<公开 id>/` 目录，推送互不冲突。
- 每台机器的 `usage.db` 是本机的唯一事实来源：一个请求只记一行，之后日志被清理也不影响。行永不删除。
- 不依赖某一台机器开机：每台都独立采集和推送。
- Claude Code 默认只保留 30 天日志，所以 collector 至少每天运行一次（建议每小时运行一次）。

### 阶段

1. ✅ 项目初始化 + 日志探查：把日志复制到本地 archive/，用 ccusage 拿到各机器的基准总量
2. ✅ collector.py：日志解析 + SQLite + 导出。在 laptop 上对 archive/ 副本运行，与 ccusage@20.0.41 逐日对账
3. ✅ CC Switch 历史导入（laptop）
4. SVG 渲染（Node，本地可运行）
5. 发布：建立公开仓库（使用干净的初始提交，不带开发期历史）、各机器部署 collector 和定时任务、配置推送凭据、GitHub Action、主页 README；各机器首次部署完成后删除本地 archive/

## 4. 目录结构

仓库内：

```
collector/collector.py                         采集器（Python 标准库，三台机器通用）
collector/import_cc_switch.py                  CC Switch 历史一次性导入（仅 laptop）
scripts/                                       渲染等 Node 脚本
data/daily/<公开 id>/<agent>/<YYYY-MM-DD>.json 日数据（进 git，渲染阶段唯一输入）
output/                                        本地生成的 SVG（线上由 Action 发布到 output 分支）
.github/workflows/                             GitHub Action
config.yaml                                    时区、渲染选项
LOCAL.md                                       本地连接细节与机器对应关系（不提交）
```

各机器本地（不在仓库中，具体路径在阶段五确定）：本机配置（公开 id、仓库 clone 位置）、`usage.db`、推送凭据。

开发期：本地 `archive/`（阶段一复制的日志副本，不提交）。部署时可用它为各机器生成初始 usage.db，以免部署前被 30 天保留期清理的日志丢失；各机器首次部署完成后删除。

## 5. usage.db 表结构（草案，阶段二实现时定稿）

```sql
-- 逐请求用量，一个请求一行
CREATE TABLE requests (
  agent       TEXT    NOT NULL,   -- 'claude-code' | 'codex'
  request_key TEXT    NOT NULL,   -- 去重主键，见第 6 节
  ts          INTEGER NOT NULL,   -- 请求时间，Unix 毫秒（UTC）
  model       TEXT    NOT NULL,   -- 原始模型名
  input       INTEGER NOT NULL,   -- 未缓存输入
  cache_write INTEGER NOT NULL,
  cache_read  INTEGER NOT NULL,
  output      INTEGER NOT NULL,   -- 含 reasoning
  source      TEXT    NOT NULL,   -- 'log' | 'cc-switch'
  PRIMARY KEY (agent, request_key)
);
-- 增量读取进度，一个日志文件一行
CREATE TABLE files (
  path   TEXT PRIMARY KEY,
  size   INTEGER NOT NULL,
  mtime  INTEGER NOT NULL,       -- 纳秒
  offset INTEGER NOT NULL,       -- 已解析到的字节位置
  state  TEXT    NOT NULL        -- 续读所需的解析状态（JSON），如 Codex 当前模型名
);
```

- 写入用 UPSERT（SQLite ≥ 3.24）。同一请求多次出现时：时间取最早的一次（fork 会话复制的事件时间戳被改写过）；token 数取 output 最大的一次（第三方模型流式响应的中间行 output 还没写全）。结果与读取顺序无关。
- 四项全为 0 的行不记（如 Claude 的 `<synthetic>` 消息）。
- 文件大小和 mtime 都没变就跳过。未压缩文件变大时，从 offset 处继续读，只消费到最后一个换行。其他情况（变小、压缩、改名）整个文件重读，靠主键去重。

## 6. 日志解析规则

阶段一已用原始日志核对过语义。实现细节以和 ccusage@20.0.41 逐日对账一致为准，对账发现的差异要在本节记录。

### Claude Code（`~/.claude/projects/**/*.jsonl`，存在时也读 `~/.config/claude/projects`）

- 读取带 `message.usage` 的行。request_key = `message.id + ':' + requestId`（少数行没有 requestId，按空串处理）。同一请求会写多行：Anthropic 模型各行 usage 相同；经代理调用的第三方模型只有最后一行带完整 output，按第 5 节规则取 output 最大的一行。
- input = input_tokens；cache_write = cache_creation_input_tokens；cache_read = cache_read_input_tokens；output = output_tokens；model = message.model；ts = timestamp。

### Codex（`~/.codex/sessions/**` 和 `~/.codex/archived_sessions/**`，`.jsonl` 和 `.jsonl.zst`）

- 新格式：顶层 `type` 为 `token_usage_record` 的行，一行一个请求。request_key = `payload.response_id`，取 `payload.usage`。文件中一旦出现 token_usage_record，其后的 token_count 只是重复汇报，不再计入。
- 老格式：只有 `event_msg` / `token_count` 事件，取 `info.last_token_usage`（与累计值之差在 99.98% 的事件上相等，其余是累计值归零）；`info` 为 null 的跳过。request_key = `total:` + `info.total_token_usage` 的 6 个字段值，不含会话 id。理由：fork 会话会把父会话的 token_count 整段复制过来，时间戳改成 fork 时刻、累计值不变；累计值不变的重复事件也很常见。以累计值为主键，两者都只记一行。
- 模型名：同一文件中前面最近一条 `turn_context.model`，原样保存；前面没有 turn_context 的记为 `unknown`（laptop 上这类行四项全为 0，不入库）。auto-review 子会话的模型名是 `codex-auto-review`，日志中没有更多信息；ccusage 会把它改记到别的模型（10 月为 gpt-5.6-luna，5 月为 gpt-5.4），我们不改名。
- input = input_tokens − cached_input_tokens − cache_write_input_tokens（原始 input 同时包含缓存读和缓存写）；cache_read = cached_input_tokens；cache_write = cache_write_input_tokens；output = output_tokens（已含 reasoning，reasoning_output_tokens 不再加）。
- 新格式按 token_usage_record 求和，会比 token_count 的累计值略大，多出 compaction 等请求。以 token_usage_record 为准，ccusage 也是这样处理。
- `.zst` 文件用 `zstd -dc` 解压读取（只有 laptop 上有）。collector 先在 PATH 中找 zstd，再找 Homebrew 的默认路径；找不到时跳过 .zst 文件且不记进度，下次重试。
- ts = 该行的 `timestamp`。

### 阶段二对账结果（2026-10-23 的 archive/ 副本，ccusage@20.0.41）

| 公开 id / agent | 结果 |
|---|---|
| laptop / codex | 148 天四项总量完全相等；除下面两处，逐日、逐模型一致 |
| laptop / claude-code | 完全一致 |
| server-1 / claude-code | 34 天完全一致 |
| server-2 / claude-code | 12 天完全一致 |

已知差异：
- `codex-auto-review`：ccusage 改记到其他模型。对账时要求每天其余模型的缺口之和恰好等于我们的 codex-auto-review，26 天全部成立。
- 跨零点的请求：新格式记录在北京时间 09-25 23:59:58，ccusage 记到 09-26，看来用的是 2 秒后紧随的 token_count 的时间。我们用记录自身的时间。只影响恰好跨过零点的个别请求。

## 7. 导出的日数据格式

`data/daily/<公开 id>/<agent>/<YYYY-MM-DD>.json`：

```json
{ "machine": "server-1", "agent": "claude-code", "date": "YYYY-MM-DD",
  "input": 0, "cache_write": 0, "cache_read": 0, "output": 0,
  "source": "log",
  "models": {
    "<模型名>": { "input": 0, "cache_write": 0, "cache_read": 0, "output": 0 }
  } }
```

- 日期按 Asia/Shanghai 划分。每次导出都从 usage.db 重算所有日期，内容没变的文件不重写。
- 顶层四项必须等于各模型之和。模型名原样保留，不合并、不改名。
- source：某个 agent 某天在 usage.db 中有 CC Switch 数据时只用 CC Switch，为 `"cc-switch"`；否则用日志，为 `"log"`。每天只有一种来源。

## 8. CC Switch 导入（阶段三）

用 `collector/import_cc_switch.py` 一次性导入 laptop 的 usage.db，source = `'cc-switch'`。只读打开 CC Switch 数据库，并且只对快照（`sqlite3 -readonly 原库 ".backup 快照"`）运行，不碰原库。导入后运行一次 collector 重新导出。

CC Switch 中的数据（2026-10-23 快照）：
- `usage_daily_rollups`：较早的逐请求记录被汇总成"日期 × 应用 × 供应商 × 模型 × 请求模型 × 计价模型"的日汇总，明细已删除。claude 为 04-06 ~ 09-10，codex 为 03-11 ~ 09-11。
- `proxy_request_logs`：尚未汇总的逐请求记录（created_at 为秒），与汇总表日期不重叠。其中 codex 行是 CC Switch 从 Codex 会话日志同步来的（data_source = codex_session），claude 行是代理请求。

导入规则：
- **只导入 claude**。Codex 日志覆盖了 CC Switch 的全部日期且更准确：CC Switch 未去掉 fork 会话的重复，部分天正好是日志的 2 倍，与日志完全一致的只有 37 / 118 天。
- laptop 的 Claude Code 日志已基本被 30 天保留期清理（09-08 日志只剩 14 次请求，CC Switch 记了 136 次），CC Switch 是这段历史的唯一来源。
- 汇总行一行记一行：request_key = `rollup:` + 汇总表主键各列（JSON），ts = 当天北京时间 12:00。逐请求行：request_key = `cc-switch:` + request_id。重复导入同一快照不会重复计数。
- 模型名取 `model` 列（实际调用的上游模型，与日志的 message.model 一致），不取 request_model / pricing_model。
- 四项直接对应：input_tokens → input，cache_creation_tokens → cache_write，cache_read_tokens → cache_read，output_tokens → output。claude 的 input 不含缓存：116 行有 cache_read 的汇总行中 83 行 input < cache_read。
- 四项全为 0 的行不记（失败请求等）。
- 来源选择见第 7 节：某天有 CC Switch 数据就只用 CC Switch。实际效果：laptop claude-code 在 09-21 及以前用 CC Switch，之后用日志。不需要配置切换日期。

验证结果（快照 2026-10-23）：导入 145 行，跳过全零 23 行，重复导入写入 0 行；导出的 cc-switch 部分四项总量等于 CC Switch 中 claude 的汇总表 + 逐请求表之和（128,288,898 / 4,487,412 / 390,435,116 / 3,047,745）；共 65 天；其他机器和 Codex 的导出文件不变；快照校验和不变。

## 9. 渲染口径

- 默认 metric = effective（input + cache_write + output），可选 all（四项全加）。
- 周、月、总计在渲染时从日数据计算，不单独存储。
- `npm run render`（`scripts/render.js [--data data/daily] [--out output]`）：所有机器、所有 agent 按日期合计，生成 `token-stats.svg`（亮色）和 `token-stats-dark.svg`（暗色），主页 README 用 `<picture>` 按访客主题切换。
- 静态 SVG，不含脚本和动画，背景透明。最近一年：53 列，每列从周日开始，最后一列截止到今天（config.yaml 的时区）。
- 颜色 5 档：0 单独一档，非零日按四分位数分 4 档（与 GitHub 相同），配色为 GitHub 绿色系。
- 顶部统计行：过去一年总量、活跃天数、峰值日。数字缩写为 K / M / B / T。

## 10. 公开与脱敏

- 可以公开：每天的四项 token 数、模型名、公开机器 id、渲染出的 SVG。
- 不得进入仓库、commit、Action 日志：服务器真实机器名、IP、端口、ssh 别名和配置、代理、用户名、本地路径；日志原文、prompt、代码、项目路径、会话 id；`usage.db`；推送凭据。
- 推送凭据只存在于各机器本地和 GitHub Secrets 中。workflow 中不得打印密钥。
- `.gitignore` 至少包含：`archive/`、`node_modules/`、`LOCAL.md`、`*.db`、`.env`。

## 11. 运行环境

- collector：Python ≥ 3.9，只用标准库（含 sqlite3 模块），三台机器都已有，无需安装。
- 渲染：Node 22（见 .nvmrc），在 laptop 和 GitHub Action 上运行。
- 对账基准：`npx ccusage@20.0.41 {claude|codex} daily --json -z Asia/Shanghai -O`。用 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 指定日志目录，`-O` 表示用缓存的价格，不联网拉价格表。

阶段一的 ccusage 基准总量（2026-10-23 的 archive/ 副本，server-1 当时仍在增长）：

| 公开 id / agent | Input | Output | Cache Create | Cache Read |
|---|---|---|---|---|
| laptop / codex | 183,497,679 | 16,602,135 | 2,970,333 | 3,472,335,879 |
| laptop / claude-code | 41,493 | 14,084 | 0 | 272,256 |
| server-1 / claude-code | 16,060 | 8,856,913 | 27,209,962 | 2,214,368,493 |
| server-2 / claude-code | 5,998 | 4,233,665 | 7,296,608 | 724,336,745 |
