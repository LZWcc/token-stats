# token-stats

汇总你多台机器上 Claude Code 与 Codex 的 token 用量，按模型统计，生成可以贴在 GitHub 主页上的 SVG 卡片。

- **只在一台主机上安装**：其他机器（服务器）经 ssh 拉取，服务器上不安装、不留下任何文件。
- **只依赖 Python 标准库**：有 Python ≥ 3.9 就能运行，不需要 pip、Node 或 ccusage。
- **逐请求账本永久保存**：本地 SQLite 记录每一次请求，跨机器去重；Claude Code 的日志 30 天后会被清理，入库后的数据不受影响。
- **数据只进你自己的仓库**：卡片发布到你自己的公开 GitHub 仓库，不上传任何第三方服务。
- 通过 Claude Code / Codex 调用的第三方模型同样计入；可以导入 CC Switch 中更早的 Claude Code 历史。

## 卡片示例

作者自己的数据（每天更新）。共 9 张，每张都有亮色、暗色两份，随访客的 GitHub 主题切换；挑喜欢的贴进主页 README（片段见下方“发布到 GitHub”）。

**概览** `overview`：模型占比、近半年热力图和几项统计合在一张里，只想放一张图时用它。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/overview-dark.svg">
  <img alt="Token 概览" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/overview.svg">
</picture>

**热力图** `heatmap`（最近一年）与 **统计** `stats`（总量、近 7 / 30 天、活跃天数、连续使用、最常用模型）：

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap-dark.svg">
  <img alt="Token 用量" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap.svg">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/stats-dark.svg">
  <img alt="Token 统计" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/stats.svg">
</picture>

**月度用量** `monthly`：最近 12 个月，按 Claude Code / Codex 堆叠。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/monthly-dark.svg">
  <img alt="月度用量" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/monthly.svg">
</picture>

**模型占比** `models-donut` 与 **模型排行** `models-bar`（按厂商上色）：窄卡片，两张并排正好等于一张宽卡片的宽度。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-donut-dark.svg">
  <img alt="模型占比" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-donut.svg">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-bar-dark.svg">
  <img alt="模型排行" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/models-bar.svg">
</picture>

**近半年热力图** `heatmap-half` 与 **工具对比** `agents`：窄卡片，两张等高，可以并排。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap-half-dark.svg">
  <img alt="近半年用量" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/heatmap-half.svg">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/agents-dark.svg">
  <img alt="工具对比" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/agents.svg">
</picture>

**徽章** `badge`：shields.io 风格，可以和其他徽章放在一起。

<img alt="AI tokens" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/badge.svg">

## 安装

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/LZWcc/token-stats/main/install.sh | sh
```

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/LZWcc/token-stats/main/install.ps1 | iex"
```

需要 Python ≥ 3.9：macOS 由 Xcode 命令行工具提供（`xcode-select --install`），Linux 发行版通常自带，Windows 从 [python.org](https://www.python.org/downloads/) 安装。Codex 的压缩日志（`.jsonl.zst`）需要 `zstd` 命令，没有时只跳过这些文件。

安装脚本下载最新的 Release，放到数据目录下的 `app/`（macOS / Linux：`~/.local/share/token-stats/app/`，Windows：`%LOCALAPPDATA%\token-stats\app\`），并生成启动脚本 `token-stats`（macOS / Linux：`~/.local/bin/`，Windows：`%LOCALAPPDATA%\token-stats\bin\`）。启动脚本所在目录不在 PATH 中时，安装脚本只打印需要添加的那一行，不修改你的 shell 配置或系统设置。

## 先试用

```bash
token-stats
```

零配置：只扫描本机的日志，用临时数据库，不写入数据目录。终端打印汇总，在当前目录的 `token-stats-cards/` 生成卡片并打开预览页（`--no-open` 不打开）。

## 开始使用

```bash
token-stats init
```

向导依次询问：

1. 本机的名字（只记在本地，不公开）。
2. 要加入的服务器：从 `~/.ssh/config` 列出主机供选择（只读不改），逐台检查免密连接和远端 Python 版本。
3. 自动合并的其他 usage.db（见下方“多台机器”），可跳过。
4. 时区（划分日期用，默认系统时区）和卡片口径。
5. 发布到哪个 GitHub 仓库（见下方“发布”），可跳过。
6. 检测到 CC Switch 时，是否导入其中 Claude Code 的历史。
7. 首次全量采集（日志多时需要一两分钟）。
8. 是否安装定时任务（默认不装）。

之后运行 `token-stats sync` 更新：采集本机和各服务器的新日志 → 合并 → 导出日数据 → 渲染卡片 → 发布。只读取新增的日志，重复运行不会重复计数。随时可以运行 `token-stats doctor` 检查各机器的连接和状态。

重新运行 `init` 可以修改配置，各项默认沿用原值。

## 多台机器

**服务器（ssh 可以连上的机器）**：要求能免密 ssh 登录（`~/.ssh/config` 中的主机），并有 Python ≥ 3.9。服务器上不需要安装 token-stats：`sync` 时把解析程序经 ssh 发过去执行，只把结果传回，远端不写任何文件。

**连不上的机器**（如家里的 Windows 电脑）：在那台机器上也装一份 token-stats 自己采集，再把它的 `usage.db` 合并到主机：

```bash
token-stats merge /path/to/other.db --as win-pc
```

`merge` 可以重复执行，同一请求不会重复计数。如果那台机器的 `usage.db` 放在网盘同步文件夹里，可以在 `init` 中把它加为“自动合并”，之后每次 `sync` 自动合并。

同一请求出现在多台机器的日志中时（例如复制过日志目录），只计一次。

## 发布到 GitHub

卡片需要放在一个**公开**的 GitHub 仓库里，主页 README 才能引用。推荐单独建一个仓库（如 `token-stats-data`），`init` 中输入仓库名即可：

- 仓库不存在且装了 [gh](https://cli.github.com/)：确认后用 gh 新建公开仓库。
- 仓库不存在且没有 gh：先在网页上新建一个公开仓库，再重新运行 `init`。
- 仓库已存在：直接使用，不碰其中的其他文件。

之后每次 `sync` 把日数据和卡片推送到仓库的 `token-stats/` 子目录，有变化才提交。token-stats 只管理这个子目录，仓库里的其他文件一概不动；子目录完全由本地数据生成，不要在其中手动修改。

- **不计入贡献图**：自动提交的作者是 `token-stats <token-stats@localhost>`，不关联任何 GitHub 账号，每天的提交不会让你的贡献图变绿。
- **凭据**：使用本机已有的 git 登录；装了 gh 时还会用 gh 的登录作为备用（在 ssh 会话和定时任务中，macOS 钥匙串可能不可用）。token-stats 不保存任何令牌，也不修改你的 git 配置。
- 不要推送到 token-stats 源码仓库或它的 fork：数据提交会和代码混在一起。

`init` 最后会打印 README 片段，贴到你的主页仓库 `README.md` 中想要的位置（token-stats 不会修改你的主页仓库）。每张卡片一段，例如：

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/heatmap-dark.svg">
  <img alt="Token 用量" src="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/heatmap.svg">
</picture>
```

卡片名：宽卡片 `overview`、`heatmap`、`stats`、`monthly`；窄卡片 `models-donut` 与 `models-bar`、`heatmap-half` 与 `agents`（两张并排正好等于一张宽卡片的宽度）；徽章 `badge`（颜色不随主题变化，可以直接用 `<img>`）。GitHub 对图片有缓存，推送后可能要几分钟才更新。

### 公开哪些内容

- **公开**：每天合计的四项 token 数（输入、输出、缓存写入、缓存读取）、按 agent 和按模型的拆分（含模型名）、SVG 卡片。
- **不公开**：机器名和数量、IP、端口、ssh 配置、本机用户名、本地路径；日志原文、prompt、代码、项目路径、会话 id；`usage.db`；任何凭据。

日数据在仓库的 `token-stats/data/daily/`，每天一个 JSON 文件。

## 导入 CC Switch 历史

[CC Switch](https://github.com/farion1231/cc-switch) 记录过的 Claude Code 用量可能比本机日志更早（日志 30 天后被清理）。`init` 检测到时会询问，也可以单独运行：

```bash
token-stats import-cc-switch
```

只读打开 CC Switch 的数据库并复制一份快照再导入，不改动原库。**只能导入一次**：CC Switch 之后会把逐请求记录汇总成日汇总并删除明细，再次导入会重复计数，所以库中已有 CC Switch 数据时拒绝导入。只导入 Claude Code：Codex 的日志不会被自动清理，比 CC Switch 中的记录更完整准确。

## 至少每 30 天 sync 一次

Claude Code 默认清理 30 天前的会话日志。每台机器至少每 30 天要被 `sync` 一次，否则日志会在入库前被删掉；入库后的数据永久保存。超过 7 天没有成功采集的机器，`sync` 和 `doctor` 会提醒。

## 定时任务（可选）

推荐手动运行 `sync`。也可以在 `init` 中安装定时任务，每天 12:00 运行：

| 平台 | 方式 | 错过时 |
|---|---|---|
| macOS | launchd，另在每次登录时运行 | 睡眠中错过的在唤醒后补跑，关机错过的在下次登录时补上 |
| Linux | systemd 用户定时器；没有 systemd 时用 crontab | systemd 在开机后补跑；crontab 不补跑 |
| Windows | 任务计划程序 | 不补跑 |

输出写入数据目录的 `run.log`（systemd 用 `journalctl --user -u token-stats` 查看）。Linux 上没有开启 linger 时，退出登录后 systemd 用户定时器不会运行（`loginctl enable-linger`）。`sync` 是增量的，一天运行多次也不会重复计数。

## 命令

| 命令 | 作用 |
|---|---|
| `token-stats` | 试用：只统计本机，不写入数据目录，在当前目录生成卡片 |
| `token-stats init` | 配置向导 |
| `token-stats sync` | 采集 → 合并 → 导出 → 渲染 → 发布（定时任务运行的就是它） |
| `token-stats doctor` | 检查配置、各机器的连接与状态、定时任务、zstd、发布仓库 |
| `token-stats merge <usage.db> --as <名字>` | 合并另一台机器自己的 usage.db，可重复执行 |
| `token-stats import-cc-switch` | 导入 CC Switch 中 Claude Code 的历史（只能一次） |
| `token-stats rename <旧名> <新名>` | 修改机器名（不要直接改配置文件里的名字，否则会把日志重读一遍） |
| `token-stats uninstall` | 卸载（见下方“升级与卸载”） |

## 配置

配置文件 `~/.config/token-stats/config.json`（Windows：`%APPDATA%\token-stats\config.json`），由 `init` 生成，也可以手动编辑：

```json
{
  "machine": "laptop",
  "remotes": [
    { "ssh": "my-server", "name": "server-1", "python": "python3" }
  ],
  "merge": [
    { "path": "~/OneDrive/token-stats/win-pc.db", "name": "win-pc" }
  ],
  "timezone": "Asia/Shanghai",
  "metric": "all",
  "publish": "your-name/token-stats-data"
}
```

| 字段 | 含义 |
|---|---|
| `machine` | 本机名，只记在本地 |
| `remotes` | 经 ssh 拉取的服务器：`ssh` 是 `~/.ssh/config` 中的主机名，`name` 是记录用的机器名（默认同 `ssh`），`python` 是远端的 Python 命令（默认 `python3`，Windows 远端通常是 `python`） |
| `merge` | 每次 `sync` 自动合并的其他 usage.db |
| `timezone` | 划分日期用的时区，默认系统时区。Windows 上没有时区数据，使用系统本地时区 |
| `metric` | 卡片口径：`all`（默认）= 四项全加，与 Codex、ccusage 显示的总 token 一致；`effective` = 不含缓存读取。缓存读取通常占 90% 以上，两者相差一个数量级 |
| `publish` | 发布仓库 `owner/name`，不填则只在本地生成卡片 |

数据目录 `~/.local/share/token-stats/`（Windows：`%LOCALAPPDATA%\token-stats\`）：`usage.db`（逐请求账本）、`daily/`（日数据）、`cards/`（卡片和预览页 `preview.html`）、`backups/`（usage.db 的每日备份，保留 7 份）、`publish/`（发布仓库的本地克隆）、`run.log`。

## 升级与卸载

**升级**：重新运行安装命令。只替换 `app/`，配置和 usage.db 不变，定时任务不用重装。

**升级 Python 后**：启动脚本和定时任务记录的都是 Python 的绝对路径。Homebrew 和 Windows 上 python.org 版本的路径带版本号，升级 Python 后会失效，需要重新运行安装命令；装了定时任务的，再运行一次 `token-stats init`（各项直接回车沿用原值）。macOS 上安装脚本优先使用系统自带的 `/usr/bin/python3`，不受影响。

**卸载**：

```bash
token-stats uninstall
```

确认后移除定时任务，删除程序（`app/`）和启动脚本；再单独询问是否同时删除配置和数据，默认保留。**usage.db 中保存着全部历史，其中超过 30 天的 Claude Code 记录在日志中已经不存在，删除后无法恢复。** 发布仓库在 GitHub 上，需要自己删除。`uninstall` 从 v0.1.1 起提供，更早的版本先重新运行安装命令升级。

<details>
<summary>手动卸载（例如程序已经删除、只剩定时任务）</summary>

1. 移除定时任务（没装可以跳过）：

   ```bash
   # macOS
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.token-stats.sync.plist
   rm ~/Library/LaunchAgents/com.token-stats.sync.plist

   # Linux（systemd）
   systemctl --user disable --now token-stats.timer
   rm ~/.config/systemd/user/token-stats.service ~/.config/systemd/user/token-stats.timer
   systemctl --user daemon-reload

   # Linux（crontab）
   crontab -l | grep -v '# token-stats sync$' | crontab -
   ```

   ```powershell
   # Windows
   schtasks /Delete /TN token-stats /F
   ```

2. 删除程序和启动脚本：

   ```bash
   rm -rf ~/.local/share/token-stats/app ~/.local/bin/token-stats
   ```

   ```powershell
   Remove-Item -Recurse "$env:LOCALAPPDATA\token-stats\app", "$env:LOCALAPPDATA\token-stats\bin"
   ```

3. 配置和数据是否删除由你决定。**usage.db 中保存着全部历史，其中超过 30 天的 Claude Code 记录在日志中已经不存在，删除后无法恢复。** 要彻底删除：macOS / Linux 删除 `~/.config/token-stats` 和 `~/.local/share/token-stats`；Windows 删除 `%APPDATA%\token-stats` 和 `%LOCALAPPDATA%\token-stats`。发布仓库在 GitHub 上，需要自己删除。

</details>

## 平台支持

- macOS、Linux：已在真实机器上使用，包括作为主机和作为 ssh 远端。
- Windows：自动化测试和安装脚本在 GitHub Actions 上运行；本地运行、定时任务和作为 ssh 远端**尚未在 Windows 上实测**，欢迎反馈。

## 许可证

[MIT](LICENSE)
