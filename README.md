# token-stats

汇总多台机器上 Claude Code 与 Codex 的 token 用量，生成可以贴在 GitHub 主页上的 SVG 卡片。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/overview-dark.svg">
  <img alt="Token 概览" src="https://raw.githubusercontent.com/LZWcc/token-stats-data/main/token-stats/cards/overview.svg">
</picture>

- **一台主机，服务器零安装**：其他机器经 ssh 拉取，服务器上不安装、不留下任何文件。
- **逐请求账本，永久保存**：本地 SQLite 记录每一次请求，跨机器去重；Claude Code 的日志 30 天后会被清理，入库后的数据不受影响。可以导入 CC Switch 中更早的历史。
- **只依赖 Python 标准库，数据只进你自己的仓库**：有 Python ≥ 3.9 就能运行；卡片发布到你自己的公开 GitHub 仓库，不经过任何第三方服务。

## 卡片

上面是作者自己的 `overview`，每天更新。共 9 张，每张都有亮色、暗色两份，随访客的 GitHub 主题切换：

| 卡片 | 尺寸 | 内容 |
|---|---|---|
| `overview` | 宽 | 模型占比环形图 + 近半年热力图 + 近 7 / 30 天、活跃天数、连续使用 |
| `heatmap` | 宽 | 最近一年的每日用量热力图 |
| `stats` | 宽 | 总量、近 7 / 30 天、活跃天数、连续使用、最常用模型 |
| `monthly` | 宽 | 最近 12 个月的月度用量，按 Claude Code / Codex 堆叠 |
| `models-donut` | 窄 | 模型占比环形图 |
| `models-bar` | 窄 | 模型排行，按厂商上色 |
| `heatmap-half` | 窄 | 近半年热力图 |
| `agents` | 窄 | Claude Code 与 Codex 的用量对比 |
| `badge` | 徽章 | shields.io 风格的 `AI tokens │ 总量` |

两张窄卡片并排正好等于一张宽卡片的宽度。每张卡片的样子和 README 片段见 [docs/cards.md](docs/cards.md)。

## 快速开始

1. 安装。macOS / Linux：

   ```bash
   curl -fsSL https://raw.githubusercontent.com/LZWcc/token-stats/main/install.sh | sh
   ```

   Windows（PowerShell）：

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/LZWcc/token-stats/main/install.ps1 | iex"
   ```

   需要 Python ≥ 3.9：macOS 运行 `xcode-select --install`，Linux 发行版通常自带，Windows 从 [python.org](https://www.python.org/downloads/) 安装。Codex 的压缩日志（`.jsonl.zst`）需要 `zstd`，没有时只跳过这些文件。启动脚本装在 `~/.local/bin/`（Windows：`%LOCALAPPDATA%\token-stats\bin\`），不在 PATH 中时安装脚本只提示，不修改你的 shell 配置。

2. 试用：`token-stats` 只统计本机，不写入数据目录，在当前目录的 `token-stats-cards/` 生成卡片并打开预览页（`--no-open` 不打开）。

3. 配置：`token-stats init` 依次询问本机名、要加入的服务器（从 `~/.ssh/config` 中选，只读不改）、时区和口径、发布仓库，检测到 CC Switch 时询问是否导入，最后做首次采集。重新运行可以修改配置，各项默认沿用原值。

4. 之后运行 `token-stats sync` 更新：只读取新增的日志，重复运行不会重复计数。`token-stats doctor` 检查各机器的连接和发布状态。

## 至少每 30 天 sync 一次

Claude Code 默认清理 30 天前的会话日志，所以每台机器至少每 30 天要被 `sync` 一次，否则日志会在入库前被删掉。超过 7 天没有成功采集时，`sync` 和 `doctor` 会提醒。

也可以在 `init` 最后安装定时任务，每天 12:00 运行：macOS 用 launchd（另在每次登录时运行，睡眠或关机错过的会补上）；Linux 用 systemd 用户定时器（开机后补跑，要在退出登录后也运行需开启 `loginctl enable-linger`），没有 systemd 时用 crontab；Windows 用任务计划程序。crontab 和任务计划程序错过了不补跑。输出写入数据目录的 `run.log`（systemd 用 `journalctl --user -u token-stats` 查看）。

## 多台机器

- **ssh 能连上的服务器**：需要免密登录和 Python ≥ 3.9。`sync` 把解析程序经 ssh 发过去执行，只传回结果，服务器上不写任何文件。
- **连不上的机器**（如家里的 Windows 电脑）：在那台机器上也装一份自己采集，再用 `token-stats merge <它的 usage.db> --as <名字>` 合并，可以重复执行。那份 usage.db 放在网盘同步文件夹里的话，可以在 `init` 中设为自动合并，每次 `sync` 时合并。
- 同一请求出现在多台机器的日志里时（如复制过日志目录），只计一次。

## 发布到 GitHub

卡片要放在**公开**仓库里，主页 README 才能引用。推荐单独建一个（如 `token-stats-data`）：在 `init` 中输入仓库名，仓库不存在时可以用 [gh](https://cli.github.com/) 直接新建，没有 gh 就先在网页上建好。

- 每次 `sync` 把日数据和卡片推送到仓库的 `token-stats/` 子目录，有变化才提交。只管理这个子目录，仓库里的其他文件不动；子目录由本地数据生成，不要手动修改。
- 自动提交的作者是 `token-stats <token-stats@localhost>`，不计入你的贡献图。
- 使用本机已有的 git 登录，装了 gh 时以 gh 的登录作为备用。不保存任何令牌，不修改你的 git 配置。
- 不要推送到 token-stats 源码仓库或它的 fork。

`init` 最后会打印每张卡片的 README 片段，挑想要的贴进你的主页 README（token-stats 不会改你的主页仓库）。例如：

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/overview-dark.svg">
  <img alt="Token 概览" src="https://raw.githubusercontent.com/<owner>/<repo>/main/token-stats/cards/overview.svg">
</picture>
```

GitHub 对图片有缓存，推送后可能要几分钟才更新。

**公开的内容**：每天合计的四项 token 数（输入、输出、缓存写入、缓存读取）、按 agent 和按模型的拆分（含模型名）、卡片。日数据在仓库的 `token-stats/data/daily/`，每天一个 JSON 文件；`token-stats/data/summary.json` 是汇总好的总量、近 7 / 30 天、连续天数、各模型和各工具的合计、逐日总量，与卡片上的数字一致，个人网站要显示用量时直接读它就行。

**不公开**：机器名和数量、IP、端口、ssh 配置、本机用户名、本地路径；日志原文、prompt、代码、项目路径、会话 id；`usage.db`；任何凭据。

## 导入 CC Switch 历史

[CC Switch](https://github.com/farion1231/cc-switch) 记录的 Claude Code 用量可能比本机日志更早。`init` 检测到时会询问，也可以单独运行 `token-stats import-cc-switch`。先复制一份快照再导入，不改动原库。

**只能导入一次**：CC Switch 之后会把逐请求记录汇总成日汇总并删除明细，再次导入会重复计数，所以库中已有 CC Switch 数据时拒绝导入。只导入 Claude Code：Codex 的日志不会被自动清理，比 CC Switch 中的记录更完整。

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

`~/.config/token-stats/config.json`（Windows：`%APPDATA%\token-stats\config.json`），由 `init` 生成，也可以手动编辑：

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
| `remotes` | 经 ssh 拉取的服务器：`ssh` 为 `~/.ssh/config` 中的主机名，`name` 为记录用的名字（默认同 `ssh`），`python` 为远端的 Python 命令（默认 `python3`，Windows 远端通常是 `python`） |
| `merge` | 每次 `sync` 自动合并的其他 usage.db |
| `timezone` | 划分日期的时区，默认系统时区（Windows 上没有时区数据，用系统本地时区） |
| `metric` | 卡片口径：`all`（默认，四项全加）或 `effective`（不含缓存读取；缓存读取通常占 90% 以上） |
| `publish` | 发布仓库 `owner/name`，不填则只在本地生成卡片 |

数据目录 `~/.local/share/token-stats/`（Windows：`%LOCALAPPDATA%\token-stats\`）：`usage.db`（逐请求账本）、`daily/`、`cards/`（含预览页 `preview.html` 和汇总数据 `summary.json`）、`backups/`（每日备份，保留 7 份）、`publish/`（发布仓库的本地克隆）、`run.log`，程序本身在 `app/`。

## 升级与卸载

- **升级**：重新运行安装命令。只替换程序（数据目录下的 `app/`），配置和数据不变，定时任务不用重装。
- **升级 Python 后**：启动脚本和定时任务记录的是 Python 的绝对路径，Homebrew 和 Windows 上 python.org 版本的路径带版本号，要重新运行安装命令；装了定时任务的，再运行一次 `token-stats init`（各项回车沿用原值）。macOS 上安装脚本默认用系统自带的 `/usr/bin/python3`，不受影响。
- **卸载**：`token-stats uninstall`。确认后移除定时任务、程序和启动脚本；配置和数据单独询问，默认保留。**usage.db 中超过 30 天的 Claude Code 记录在日志中已经不存在，删除后无法恢复。** 发布仓库在 GitHub 上，需要自己删除。手动卸载见 [docs/uninstall.md](docs/uninstall.md)。

## 平台支持

- macOS、Linux：已在真实机器上使用，包括作为主机和作为 ssh 远端。
- Windows：自动化测试和安装脚本在 GitHub Actions 上运行；本地运行、定时任务和作为 ssh 远端**尚未在 Windows 上实测**，欢迎反馈。

## 许可证

[MIT](LICENSE)
