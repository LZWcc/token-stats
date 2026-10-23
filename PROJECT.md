# token-stats 项目规格（唯一规格来源）

> 本仓库公开。本文件和所有提交内容都不得包含真实机器名、IP、端口、ssh 别名或配置、代理、用户名、本地路径。文档中的 `laptop` / `server-1` / `server-2` 只是示例标签。

## 1. 项目目标

开源的 AI Coding Token 用量统计工具：

- 汇总一个人多台机器上 Claude Code 与 Codex 的 token 用量，按模型统计（通过 Claude Code / Codex 调用的第三方模型同样计入）。
- 先统计、再安装：零配置一条命令就能看到本机统计和卡片；需要长期使用时，一个向导完成多机器、定时、发布的配置。
- 生成一组静态 SVG 卡片（热力图、模型占比环形图、模型排行柱状图、统计卡片），发布到用户自己的 GitHub 仓库，供主页 README 引用。
- 数据只进用户自己的仓库，不上传任何第三方服务。

与现有项目的区别（2026-10 调研）：tokscale 需要把数据上传到它的服务；token-history 每台机器都要安装并依赖 ccusage，按天快照、超过 7 天只增不减。本项目：只在一台主机上安装，服务器零安装；逐请求账本永久保存、跨机器去重；只依赖 Python 标准库；支持导入 CC Switch 历史。

## 2. 用户使用流程（M3 实现，命令名为草案）

```bash
uvx token-stats              # 或 pipx run token-stats：只统计本机，打印汇总，生成全部卡片和预览页
token-stats init             # 向导：选择要加入的服务器（读取 ~/.ssh/config 中的主机，只读不改）、
                             #       发布到哪个 GitHub 仓库、是否导入 CC Switch、安装定时任务、首次运行、
                             #       打印可直接贴进 README 的 Markdown
token-stats sync             # 拉取 → 入库 → 导出 JSON → 渲染 → 推送（定时任务调用的就是它）
token-stats doctor           # 每台机器能否连上、上次成功时间、行数等（只在本地显示）
```

## 3. 架构：主机拉取

```
主机（用户自己的电脑，唯一安装 token-stats 的机器，定时运行 sync）
  ├─ 本机日志 ───────────────────────────────┐
  ├─ ssh 服务器A  python3 -（stdin 传入解析脚本）──┤→ 中央 usage.db（逐请求，带 machine 列）
  ├─ ssh 服务器B  python3 -  …                 ──┤
  └─ CC Switch 快照（可选，一次性导入）─────────┘
        ↓ 导出（所有机器合计，不含机器信息）
  data/daily/<YYYY-MM-DD>.json
        ↓ 渲染
  output/*.svg  → git push 到用户自己的 GitHub 仓库 → 主页 README 引用
```

- **服务器零安装、零写入**：主机通过 ssh 把解析脚本从 stdin 发给远端 `python3 -`，同时发去该机器各日志文件的读取进度；远端只解析新增部分，把新请求和新进度逐行打印回来。远端不写任何文件，日志只读。远端只需要 sshd、python3 ≥ 3.9。
- **服务器不需要 git 和 GitHub 凭据**：入库、导出、渲染、推送都在主机上完成，推送用主机上已有的 git 登录。
- 每小时只传回新增请求（每条几十字节），不复制日志。
- ssh 一律加 `-o BatchMode=yes -o ConnectTimeout=15 -o RemoteCommand=none -o RequestTTY=no`：不交互、不卡住，并覆盖用户 ssh 配置中的 RemoteCommand / RequestTTY。不修改任何 ssh 配置。
- 本机总是扫描，机器名固定为 `local`（与 CC Switch 导入一致，保证按机器选来源时对得上）；远端用 `--remote <ssh 主机名>` 指定，可重复，主机名同时作为本地记录的机器名。
- 按机器隔离失败：某台连不上不影响其他机器，`doctor` 显示每台的上次成功时间。
- 同一时间只允许一个进程写 usage.db：collector 和 CC Switch 导入启动时都对 `usage.db.lock` 加锁，已被占用就提示后退出。
- 主机关机期间不采集。Claude Code 默认只保留 30 天日志，主机至少每 30 天要运行一次 sync，否则服务器上更早的日志会在入库前被清理。
- 不需要 GitHub Action：主机自己渲染并推送；“最近一年”窗口随主机每天的运行自然滚动。

## 4. 里程碑

旧架构（每台机器各自采集、各自推送）下已完成：阶段一日志探查、阶段二解析与对账、阶段三 CC Switch 导入、阶段四单张热力图。解析规则、CC Switch 规则、对账结论沿用（第 6、8 节）。

| 里程碑 | 内容 | 完成标准 |
|---|---|---|
| ✅ **M1 主机拉取架构** | 中央 usage.db（machine 列、跨机器去重）；ssh 远程解析并回传；导出改为每天一个文件 | 三台真实机器实测，各机器 × agent 与 ccusage 对账一致；重复运行不新增行、不重写文件；远端不留任何文件 |
| ✅ **M2 卡片** | 渲染改为 Python；热力图、模型占比环形图、模型排行柱状图、统计卡片，亮暗两色；预览页 | 预览页四张卡片正确，数字与 usage.db 一致 |
| **M3 命令行工具** | `token-stats`（一次性统计）、`init`、`sync`、`doctor`；配置文件；定时任务安装 | 在一台干净的机器上，几条命令完成从安装到出图 |
| **M4 发布** | `sync` 推送 data 和卡片；生成 README 片段 | 主页显示卡片，每小时自动更新 |
| **M5 开源打包** | 中英文 README、LICENSE、合成日志测试、PyPI | 他人照 README 可装好 |

M1 实测结果（2026-10-23，主机 laptop + 两台服务器经 ssh）：
- 代码：`collector/scan.py`（扫描与解析，同一份源码既在主机本地调用，也经 ssh 发给远端 `python3 -I -B -` 执行）、`collector/collector.py`（中央 usage.db、调度、导出）、`collector/import_cc_switch.py`。
- 用日志副本模拟三台机器写入同一个库并导入 CC Switch：各机器 × agent 与 ccusage 对账结果与第 6 节相同；合计 JSON 等于按机器选来源后之和，不含机器信息；第二、三次运行不新增行、不改写文件。
- 传输等价：同一批日志直接调用 scan() 与经 `python3 -` 执行，产出的 52524 个事件逐个相同；带读取进度再跑，570 个文件全部跳过。发给远端的程序连同进度约 140 KB。
- 真实机器：ssh 实测结果与日志副本在重叠日期（服务器 09-28 ~ 10-22、laptop 全部日期）逐日、逐模型完全一致。首次全量约 52 秒，之后每次约 6.5 秒（主要是 ssh 连接）。
- 远端无写入：扫描后在两台服务器上查找此后新增或修改的文件，只有 ssh 登录本身产生的系统日志（journal、btmp，以及系统登录时刷新的信息缓存），没有 .pyc 或任何本项目的文件。
- 新发现：server-1 上也有 Codex 日志（07-16 ~ 07-26，1824 次请求），旧架构只采集了它的 Claude Code；新架构默认每台机器两种 agent 都扫，自动补上，与 laptop 的 Codex 无主键冲突。

M1 期间代码沿用 `collector/`，包结构在 M3 定稿。开发期本地 `archive/`（阶段一的日志副本，不提交）在 M1 实测通过后删除。

## 5. usage.db（主机上唯一的一份）

```sql
-- 逐请求用量，一个请求一行
CREATE TABLE requests (
  machine     TEXT    NOT NULL,   -- 机器名（本地叫法，如 ssh 主机别名；'local' 为主机本身），不公开
  agent       TEXT    NOT NULL,   -- 'claude-code' | 'codex'
  request_key TEXT    NOT NULL,   -- 去重主键，见第 6 节
  ts          INTEGER NOT NULL,   -- 请求时间，Unix 毫秒（UTC）
  model       TEXT    NOT NULL,   -- 原始模型名
  input       INTEGER NOT NULL,   -- 未缓存输入
  cache_write INTEGER NOT NULL,
  cache_read  INTEGER NOT NULL,
  output      INTEGER NOT NULL,   -- 含 reasoning
  source      TEXT    NOT NULL,   -- 'log' | 'cc-switch'
  PRIMARY KEY (agent, request_key)   -- 不含 machine：同一请求出现在多台机器的日志里也只记一行
);
-- 增量读取进度，一个日志文件一行
CREATE TABLE files (
  machine TEXT    NOT NULL,
  path    TEXT    NOT NULL,       -- 该机器上的路径，只存本地
  size    INTEGER NOT NULL,
  mtime   INTEGER NOT NULL,       -- 纳秒
  offset  INTEGER NOT NULL,       -- 已解析到的字节位置
  state   TEXT    NOT NULL,       -- 续读所需的解析状态（JSON），如 Codex 当前模型名
  PRIMARY KEY (machine, path)
);
-- 每台机器的采集状态，供 doctor 使用
CREATE TABLE machines (
  machine    TEXT PRIMARY KEY,
  last_ok    INTEGER,             -- 上次成功的时间，Unix 毫秒
  last_error TEXT
);
```

去重规则：

- **跨机器**：主键不含 machine。request_key 全局唯一（Claude 的消息 id + 请求 id、Codex 的 response_id），所以多台机器日志重叠（例如同步了 `~/.claude`）时也只记一次。
- **同一请求多次出现**（UPSERT，SQLite ≥ 3.24）：时间取最早的一次（fork 会话复制的事件时间戳被改写过），machine 和 model 跟随最早那次；token 数取 output 最大的一次（第三方模型流式响应的中间行 output 还没写全）。结果与读取顺序无关。
- **增量**：文件大小和 mtime 都没变就跳过；未压缩文件变大时从 offset 继续读，只消费到最后一个换行；其他情况（变小、压缩、改名）整个文件重读，靠主键去重。
- 四项全为 0 的行不记（如 Claude 的 `<synthetic>` 消息）。行永不删除：日志被清理后数据仍在。usage.db 是唯一事实来源，应当备份。

## 6. 日志解析规则

阶段一已用原始日志核对过语义。实现细节以和 ccusage@20.0.41 逐日对账一致为准，对账发现的差异要在本节记录。

### Claude Code（`~/.claude/projects/**/*.jsonl`，存在时也读 `~/.config/claude/projects`）

- 读取带 `message.usage` 的行。request_key = `message.id + ':' + requestId`（少数行没有 requestId，按空串处理）。同一请求会写多行：Anthropic 模型各行 usage 相同；经代理调用的第三方模型只有最后一行带完整 output，按第 5 节规则取 output 最大的一行。
- input = input_tokens；cache_write = cache_creation_input_tokens；cache_read = cache_read_input_tokens；output = output_tokens；model = message.model；ts = timestamp。

### Codex（`~/.codex/sessions/**` 和 `~/.codex/archived_sessions/**`，`.jsonl` 和 `.jsonl.zst`）

- 新格式：顶层 `type` 为 `token_usage_record` 的行，一行一个请求。request_key = `payload.response_id`，取 `payload.usage`。文件中一旦出现 token_usage_record，其后的 token_count 只是重复汇报，不再计入。
- 老格式：只有 `event_msg` / `token_count` 事件，取 `info.last_token_usage`（与累计值之差在 99.98% 的事件上相等，其余是累计值归零）；`info` 为 null 的跳过。request_key = `total:` + `info.total_token_usage` 的 6 个字段值，不含会话 id。理由：fork 会话会把父会话的 token_count 整段复制过来，时间戳改成 fork 时刻、累计值不变；累计值不变的重复事件也很常见。以累计值为主键，两者都只记一行。
- 模型名：同一文件中前面最近一条 `turn_context.model`，原样保存；前面没有 turn_context 的记为 `unknown`（实测这类行四项全为 0，不入库）。auto-review 子会话的模型名是 `codex-auto-review`，日志中没有更多信息；ccusage 会把它改记到别的模型，我们不改名。
- input = input_tokens − cached_input_tokens − cache_write_input_tokens（原始 input 同时包含缓存读和缓存写）；cache_read = cached_input_tokens；cache_write = cache_write_input_tokens；output = output_tokens（已含 reasoning，reasoning_output_tokens 不再加）。
- 新格式按 token_usage_record 求和，会比 token_count 的累计值略大，多出 compaction 等请求。以 token_usage_record 为准，ccusage 也是这样处理。
- `.zst` 文件用 `zstd -dc` 解压读取。先在 PATH 中找 zstd，再找 Homebrew 的默认路径；找不到时跳过 .zst 文件且不记进度，下次重试。
- ts = 该行的 `timestamp`。

### 对账结果（2026-10-23 的日志副本，ccusage@20.0.41）

| 机器 / agent | 结果 |
|---|---|
| laptop / codex | 148 天四项总量完全相等；除下面两处，逐日、逐模型一致 |
| laptop / claude-code | 完全一致 |
| server-1 / claude-code | 33 天完全一致 |
| server-2 / claude-code | 12 天完全一致 |

已知差异：
- `codex-auto-review`：ccusage 改记到其他模型。对账时要求每天其余模型的缺口之和恰好等于我们的 codex-auto-review，26 天全部成立。
- 跨零点的请求：新格式记录在北京时间 09-25 23:59:58，ccusage 记到 09-26，看来用的是 2 秒后紧随的 token_count 的时间。我们用记录自身的时间。只影响恰好跨过零点的个别请求。

### 与其他工具的统计为何不同（2026-10-23 核查，口径均为四项全加）

- **Claude Code `/stats`（`~/.claude/stats-cache.json`）偏大约 2.4 倍**：一次 API 回复按内容块（thinking / text / tool_use）拆成多行写入日志，每行都带这次调用的完整 usage。`/stats` 逐行相加：某台服务器 12 天里 12 天的日值与“逐行相加”完全相等，与“按请求去重”一天都对不上；该机 2983 个请求中 2404 个写了 2–8 行，多行 usage 全部相同、都在同一文件。本项目与 ccusage 一样按 message.id + requestId 去重。
- **`stats-cache.json` 保留了日志已被清理的天数**：另一台服务器上有 44 天只存在于其中（逐行计 10.42B），更早还有只按模型累计、不分日期的部分。它只有每天每模型一个总数、且是逐行重复计数的，无法还原为逐请求数据。**决定：不导入**，只统计能逐请求核实的数据（估算修正后约 5.7B 的历史因此缺失）。
- **Codex 账号页（chatgpt.com/profile）比本地日志多约 0.4B**：本机 Codex 自己的会话表（`~/.codex/state_5.sqlite` 的 `threads.tokens_used`）合计 3.87B，与本项目的 3.73B 基本一致，没有漏掉会话文件；`thread_history_1.sqlite` 是从日志派生的投影，不是独立来源。差额应是账号级用量中不在这些机器日志里的部分（网页 / 云端任务、其他设备等），本地无法核实。
- **CC Switch 偏大**：Codex 的 input 已含缓存又另计 cache_read，且未去掉 fork 会话的重复（见第 8 节）。

## 7. 导出的日数据格式

`data/daily/<YYYY-MM-DD>.json`，所有机器合计，不含任何机器信息：

```json
{ "date": "YYYY-MM-DD",
  "input": 0, "cache_write": 0, "cache_read": 0, "output": 0,
  "agents": { "claude-code": { "input": 0, "cache_write": 0, "cache_read": 0, "output": 0 } },
  "models": { "<模型名>":    { "input": 0, "cache_write": 0, "cache_read": 0, "output": 0 } } }
```

- 日期按配置的时区划分（默认 Asia/Shanghai）。每次导出都从 usage.db 重算所有日期，内容没变的文件不重写。
- 顶层四项等于各 agent 之和，也等于各模型之和。模型名原样保留，不合并、不改名。
- 来源选择**先按机器、再合计**：某台机器的某个 agent 某天有 CC Switch 数据时，这台机器这个 agent 这天只用 CC Switch，否则用日志。不影响同一天其他机器的数据。

## 8. CC Switch 导入（可选，一次性）

只读打开 CC Switch 数据库快照（`sqlite3 -readonly 原库 ".backup 快照"`），不碰原库；导入主机的 usage.db，machine = 'local'，source = `'cc-switch'`。一个 usage.db 只应从一份快照导入一次：CC Switch 之后可能把逐请求记录汇总成日汇总行并删除明细，用新快照再导入会重复计数。导入脚本会检查：库中已有 cc-switch 数据就拒绝导入，不提供强制选项。

CC Switch 中的数据（2026-10-23 快照）：
- `usage_daily_rollups`：较早的逐请求记录被汇总成"日期 × 应用 × 供应商 × 模型 × 请求模型 × 计价模型"的日汇总，明细已删除。
- `proxy_request_logs`：尚未汇总的逐请求记录（created_at 为秒），与汇总表日期不重叠。其中 codex 行是 CC Switch 从 Codex 会话日志同步来的（data_source = codex_session），claude 行是代理请求。

导入规则：
- **只导入 claude**。Codex 日志不会被自动清理，覆盖了 CC Switch 的全部日期且更准确：CC Switch 未去掉 fork 会话的重复，部分天正好是日志的 2 倍，与日志完全一致的只有 37 / 118 天。
- Claude Code 日志会被 30 天保留期清理，CC Switch 是更早历史的唯一来源（实测某天日志只剩 14 次请求，CC Switch 记了 136 次）。
- 汇总行一行记一行：request_key = `rollup:` + 汇总表主键各列（JSON），ts = 当天 12:00（配置的时区）。逐请求行：request_key = `cc-switch:` + request_id。
- 模型名取 `model` 列（实际调用的上游模型，与日志的 message.model 一致），不取 request_model / pricing_model。
- 四项直接对应：input_tokens → input，cache_creation_tokens → cache_write，cache_read_tokens → cache_read，output_tokens → output。claude 的 input 不含缓存：116 行有 cache_read 的汇总行中 83 行 input < cache_read。
- 四项全为 0 的行不记（失败请求等）。

验证结果（快照 2026-10-23）：导入 145 行，跳过全零 23 行，重复导入写入 0 行；导出的 cc-switch 部分四项总量等于 CC Switch 中 claude 的汇总表 + 逐请求表之和；其他数据不变；快照校验和不变。

## 9. 卡片

`python3 scripts/render.py [--data data/daily] [--out output] [--metric all|effective]`：生成四张静态 SVG，每张亮色、暗色各一份（`-dark` 后缀），外加本地预览页 `preview.html`（两种背景并排）。README 用 `<picture>` 按访客主题切换。

口径 metric：默认 all = 四项全加，与 Codex、ccusage 的“总 token”一致；effective = input + cache_write + output，不含缓存读取。缓存读取通常占 90% 以上，两者相差一个数量级；统计卡片底部注明当前口径。M3 起放进配置文件。

| 文件 | 内容 | 时间范围 | 尺寸 |
|---|---|---|---|
| `heatmap` | 每天用量热力图，标题行带过去一年总量和活跃天数，右下角色阶图例 | 最近一年（53 列，每列从周日开始，截止今天） | 宽 |
| `stats` | 总量、近 7 天、近 30 天、活跃天数、连续使用（附最长纪录）、最常用模型，底部注明口径 | 全部时间 | 宽 |
| `models-donut` | 模型占比环形图：前 5 名 + “其他”，中心为总量，图例写模型名、token 数、百分比 | 全部时间 | 窄 |
| `models-bar` | 模型排行横向条形图：前 8 名，最多的在最上面，数值写在条形末端；按厂商上色，底部厂商图例 | 全部时间 | 窄 |

宽卡片 746 px；窄卡片 365 px 且两张等高，并排加 16 px 间距正好等于宽卡片。

设计规则（按 dataviz 规范）：
- 静态 SVG，不含脚本，背景透明，1 px 细边框圆角卡片。GitHub README 中悬停无效，所以数值直接写在图上；仓库里的日数据 JSON 即表格形式的原始数据。
- 文字只用文字色（主色 / 次要色），不用数据色；数据色只用在色块、色段、条形上。
- 环形图：段间 2 px 背景间隙，从 12 点方向顺时针，最多 6 段（前 5 名 + 其他）。颜色按名次分配。
- 条形图：按厂商上色（颜色跟着厂商走，不随排名变化），底部图例只列前 8 名中出现的厂商；粗 10 px，基线端直角、数值端 4 px 圆角。
- 热力图：0 单独一档，非零日按四分位分 4 档（与 GitHub 相同）。
- 模型名放不下时按字号估算宽度截断加省略号（生成时无法测量文字）。
- 数字缩写为 K / M / B / T，保留 1 位小数。

配色（小清新：薄荷、薰衣草、奶油黄、天空蓝、蜜桃；用 dataviz 的验证脚本在 GitHub 背景上实测）：

| 角色 | 亮色（背景 #ffffff） | 暗色（背景 #0d1117） |
|---|---|---|
| 分类 1–5 | `#46b68c` `#c0a2f5` `#ccb352` `#5dc0f6` `#dc855d` | `#3aac83` `#a183d4` `#ac942f` `#3aa0d4` `#d17c54` |
| 其他 | `#c3c2b7` | `#52514e` |
| 热力图 0–4 档 | `#ebeef0` `#b3eacb` `#7ad3b0` `#3ab19b` `#128984` | `#1b2129` `#024d4a` `#037465` `#2f9e7f` `#64cc9d` |
| 文字 / 次要文字 / 边框 | `#1f2328` / `#59636e` / `#d1d9e0` | `#f0f6fc` / `#9198a1` / `#3d444d` |

- 分类色：环形首尾相接，且“其他”夹在第 5 名和第 1 名之间，按这 7 对相邻关系验证。亮色最差色盲区分度 ΔE 8.0、正常视力 15.8；暗色 12.5、22.2（标准：色盲 ≥ 8、正常视力 ≥ 15）。明度带、色度下限均通过。亮色背景下分类色对比度低于 3:1，按规范要求图例中直接写出名称和数值。
- “其他”的灰色不能用中灰：与第 5 名在色盲模拟下几乎无法区分（暗色 ΔE 1.1），所以亮色用浅灰、暗色用深灰拉开明度。
- 厂商色（排行图，亮暗通用）：模型名去掉中转商前缀（最后一个 `/` 之后）后按前缀识别——`claude` → Anthropic `#d97757`；`gpt` / `codex` / `o1` / `o3` / `o4` → OpenAI `#10a37f`；`gemini` → Google `#7faefd`；`deepseek` → DeepSeek `#4d6bfe`；其余为“其他厂商”，用上表“其他”的灰色。色值是接近各家品牌色的近似值，不是官方色值。
  - 只给 4 家：品牌色多了必然撞色。实测近似品牌色时，Google、DeepSeek、智谱、通义、腾讯五家蓝色两两难分（正常视力 ΔE 最低 4.5），Claude 与小米的橙色 ΔE 7.8；在 ±0.18 明度、±20° 色相内调整也无法全部达标，且会面目全非（小米变成棕色）。
  - Google 原色 `#4285f4` 调亮为 `#7faefd`，否则在暗色背景下与 DeepSeek 分不清。
  - 验证（含“其他厂商”灰色，两两之间）：除 Anthropic ↔ OpenAI 色盲 ΔE 6.8（规范允许的 6–8 区间，每根条形都标了模型名并有厂商图例）外，正常视力均 ≥ 15、色盲均 ≥ 8。亮色背景下 Google、灰色对比度低于 3:1，同样靠标签和图例。
- 热力图：薄荷 → 青绿的相邻色相渐变，两种背景下明度单调，相邻档 ΔE 9–15。最浅一档代表“接近零”，有意接近背景色。

## 10. 公开与脱敏

- 公开（推送到用户仓库）：每天合计的四项 token 数、按 agent 和按模型的拆分、SVG 卡片。
- 不公开：机器名和数量、IP、端口、ssh 配置、代理、用户名、本地路径；日志原文、prompt、代码、项目路径、会话 id；`usage.db`；任何凭据。
- `.gitignore` 至少包含：`archive/`、`output/`、`LOCAL.md`、`*.db`、`.env`。

## 11. 运行环境

- 主机和远端：Python ≥ 3.9，只用标准库（含 sqlite3 模块）。主机另需 ssh 客户端和能推送到用户仓库的 git。
- 不需要 Node：渲染已在 M2 改写为 Python（`scripts/render.py`），Node 脚本与 package.json、config.yaml 已删除；口径用 `--metric` 指定，时区暂与 collector 一样固定 +8，M3 统一放进配置。
- 对账基准（仅开发期）：`npx ccusage@20.0.41 {claude|codex} daily --json -z Asia/Shanghai -O`。用 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 指定日志目录，`-O` 表示用缓存的价格，不联网拉价格表。

阶段一的 ccusage 基准总量（2026-10-23 的日志副本，server-1 当时仍在增长）：

| 机器 / agent | Input | Output | Cache Create | Cache Read |
|---|---|---|---|---|
| laptop / codex | 183,497,679 | 16,602,135 | 2,970,333 | 3,472,335,879 |
| laptop / claude-code | 41,493 | 14,084 | 0 | 272,256 |
| server-1 / claude-code | 16,060 | 8,856,913 | 27,209,962 | 2,214,368,493 |
| server-2 / claude-code | 5,998 | 4,233,665 | 7,296,608 | 724,336,745 |
