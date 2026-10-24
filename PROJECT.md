# token-stats 项目规格（唯一规格来源）

> 本仓库公开。本文件和所有提交内容都不得包含真实机器名、IP、端口、ssh 别名或配置、代理、本机用户名（作为路径或登录名）、本地路径；GitHub 账号除外（源码仓库地址、安装命令中会出现）。文档中的 `laptop` / `server-1` / `server-2` 只是示例标签。

## 1. 项目目标

开源的 AI Coding Token 用量统计工具：

- 汇总一个人多台机器上 Claude Code 与 Codex 的 token 用量，按模型统计（通过 Claude Code / Codex 调用的第三方模型同样计入）。
- 先统计、再安装：零配置一条命令就能看到本机统计和卡片；需要长期使用时，一个向导完成多机器、定时、发布的配置。
- 生成一组静态 SVG 卡片（热力图、模型占比环形图、模型排行柱状图、统计卡片），发布到用户自己的 GitHub 仓库，供主页 README 引用。
- 数据只进用户自己的仓库，不上传任何第三方服务。

与现有项目的区别（2026-10 调研）：tokscale 需要把数据上传到它的服务；token-history 每台机器都要安装并依赖 ccusage，按天快照、超过 7 天只增不减。本项目：只在一台主机上安装，服务器零安装；逐请求账本永久保存、跨机器去重；只依赖 Python 标准库；支持导入 CC Switch 历史。

## 2. 命令行与配置（M3）

### 命令

| 命令 | 作用 |
|---|---|
| `token-stats` | 先统计：零配置，只扫本机，用临时库（不写任何文件到数据目录），终端打印汇总，生成卡片到当前目录的 `token-stats-cards/` 并打开预览页 |
| `token-stats init` | 向导：本机起名 → 从 `~/.ssh/config` 列出主机供勾选（只读不改）→ 逐台检查免密连接和远端 Python 版本 → 检测到 CC Switch 时询问是否导入（先做只读快照）→ 询问发布仓库（可选，见“发布”）→ 写配置 → 首次全量采集 → 询问是否安装定时任务（可选，默认否） |
| `token-stats sync` | 采集本机和各远端 → 自动合并配置里的其他库 → 导出 → 渲染 → 配置了发布仓库时推送（见“发布”）。定时任务调用的就是它 |
| `token-stats doctor` | 每台机器：能否连上、远端 Python 版本、上次成功时间、上次错误、行数；定时任务是否已安装；zstd 是否可用；发布仓库是否已克隆、能否连上、上次推送时间、未推送的提交数 |
| `token-stats merge <usage.db> --as <名字>` | 把另一台机器（如连不上的 Windows）自己的 usage.db 合并进来，机器名改为指定名字；只合并请求，不合并对方的读取进度；可重复执行，靠主键去重 |
| `token-stats import-cc-switch` | 导入 CC Switch 历史（init 中也会询问），规则见第 8 节 |
| `token-stats rename <旧名> <新名>` | 改机器名：同时更新 requests / files / machines 三张表，否则改名后读取进度对不上、会把所有文件重读一遍 |
| `token-stats uninstall` | 卸载（v0.1.1 起），见下方“安装”中的“卸载” |

### 配置文件

`~/.config/token-stats/config.json`（Windows：`%APPDATA%\token-stats\config.json`），JSON 格式（Python 3.9 没有内置 TOML 解析）：

```json
{
  "machine": "mac",
  "remotes": [
    { "ssh": "server-a", "name": "server-1", "python": "python3" }
  ],
  "merge": [
    { "path": "~/OneDrive/token-stats/win-pc.db", "name": "win-pc" }
  ],
  "timezone": "Asia/Shanghai",
  "metric": "all",
  "publish": "alice/token-stats-data"
}
```

- `machine`：本机名，默认 `local`。collector 与 CC Switch 导入都用它，保证按机器选来源时对得上。
- `remotes`：经 ssh 拉取的远端。`ssh` 是 `~/.ssh/config` 里的主机名；`name` 是记录用的机器名，默认等于 `ssh`；`python` 是远端的 Python 命令，默认 `python3`（Windows 远端通常是 `python`）。
- `merge`：每次 `sync` 自动合并的其他库，适合放在网盘同步文件夹里：那台机器自己运行 token-stats，把 usage.db 同步过来。
- `timezone`：划分日期用，默认取系统时区。
- `metric`：卡片口径，`all`（默认）或 `effective`。
- `publish`：发布仓库 `owner/name`，默认不发布（见“发布”）。
- 机器名只存在本地 usage.db 中，不进入公开数据，可以随意起。一台机器的名字确定后不要直接改配置，用 `rename`。

### 数据目录

`~/.local/share/token-stats/`（Windows：`%LOCALAPPDATA%\token-stats\`）：`usage.db`、`usage.db.lock`、`daily/`（导出的日数据）、`cards/`（卡片）、`publish/`（发布仓库的本地克隆，见“发布”）、`run.log`。

### 发布（M4）

可选。配置了 `publish` 时，`sync` 在渲染之后把日数据和卡片推送到用户自己的 GitHub 仓库，主页 README 引用其中的卡片；不配置就只在本地生成。

- 为什么需要一个仓库：数据来自用户机器上的日志，在线服务和 GitHub Actions 都读不到，只能在本机生成卡片，再放到公开的地方供 README 引用。推荐单独建一个仓库（如 `token-stats-data`），也可以用已有仓库（如主页仓库）。不推到 token-stats 源码仓库或它的 fork：数据提交会和代码混在一起，升级时与上游长期分叉。
- 仓库必须公开，否则主页无法显示其中的图片。公开内容见第 10 节。
- 只管理目标仓库中的 `token-stats/` 子目录，子目录以外的文件一概不碰：

```
<仓库>/
  README.md                         ← 只在 init 新建仓库时生成一次（展示卡片并附 README 片段），之后不再改动；已有仓库不碰
  token-stats/
    data/daily/<YYYY-MM-DD>.json    ← 第 7 节的日数据
    cards/*.svg                     ← 第 9 节的卡片，亮暗各一份；preview.html 不推送
```

- 本地克隆在数据目录的 `publish/`。`sync` 照常导出到 `daily/`、渲染到 `cards/`，再镜像复制到 `publish/token-stats/`（删除多余文件，如改时区后不再对应数据的日期文件），导出与渲染逻辑不变。`publish/` 损坏时删掉重新克隆即可，不影响数据。
- 推送步骤：`git fetch` → 本地重置到远端（`git reset --hard origin/<分支>`，保留用户在网页上对其他文件的修改）→ 镜像复制 → `git add -A token-stats` → 有变化才提交 → `git push`。子目录完全由本地数据生成，所以不用 rebase：上次没推上去的提交丢弃后会重新生成，远端对子目录的改动会被覆盖，不会出现冲突卡住发布。提交说明 `update <YYYY-MM-DD>`（配置时区的当天）。任何一步失败只打印错误，不影响采集和导出，下次 `sync` 重试；`doctor` 显示连接状态和未推送的提交数。`publish/` 由程序独占，不要在里面手动修改。
- 提交作者固定为 `token-stats <token-stats@localhost>`（通过 `git -c user.name=… -c user.email=…` 传入，不修改用户的 git 配置）。这个邮箱不关联任何 GitHub 账号，自动提交不计入用户的贡献图；否则每天一次的提交会让贡献图天天变绿。
- 凭据：用主机上已有的登录，token-stats 不保存任何令牌，也不修改 git 配置。https 克隆，先用用户已有的 git 凭据助手（macOS 上通常是钥匙串）；装了 gh 时，token-stats 执行的 git 命令另用 `-c` 追加 gh 作为 github.com 的备用凭据助手（`gh auth git-credential`，gh 用完整路径）。原因：钥匙串只在本机登录会话中可用，ssh 远程会话里取不到凭据（实测报 “User interaction is not allowed”），追加 gh 后本机终端、ssh、定时任务都能推送，也不需要用户运行会修改 `~/.gitconfig` 的 `gh auth setup-git`。都取不到凭据时推送失败并打印错误。
- `init` 在口径之后询问“发布到哪个 GitHub 仓库（owner/name），直接回车跳过”：
  - 仓库不存在且装了 gh：说明公开内容后询问，同意则 `gh repo create <owner/name> --public`，并推送生成的 README 作为第一个提交。
  - 仓库不存在且没有 gh：提示先在网页上建一个公开仓库，再重新运行 `init`。
  - 仓库已存在：直接克隆，不碰 README 和子目录以外的文件。
  - 最后打印 README 片段。
- README 片段：每张卡片一个 `<picture>`，按访客主题切换亮暗，图片地址为 `https://raw.githubusercontent.com/<owner>/<repo>/<默认分支>/token-stats/cards/<名字>{,-dark}.svg`。用户自己决定贴哪几张、贴到哪里，程序不修改用户的主页仓库。GitHub 对图片有缓存，推送后可能要几分钟才更新。
- 试用模式（不带子命令的 `token-stats`）永不推送。

### 跨平台

- 本机（主机）支持 macOS、Linux、Windows。文件锁按平台实现（Unix 用 fcntl，Windows 用 msvcrt）。
- 时区：有 zoneinfo 和系统时区数据时按配置的时区划分日期；Windows 上没有系统时区数据（标准库不带 tzdata），退回系统本地时区。
- 推荐手动运行 `sync`。定时任务可选（`init` 中询问，默认不装），每天 12:00 运行（白天主机大概率开着）：
  - macOS：launchd `StartCalendarInterval` + `RunAtLoad`。睡眠中错过的在唤醒后补跑（launchd 文档明确的行为），关机错过的由下次登录时的 `RunAtLoad` 补上；一天最多运行两次，`sync` 是增量的，不会重复计数。不用 `StartInterval`：它从加载时计时，睡眠期间是否计时文档没有写明。
  - Linux：systemd 用户定时器（`Persistent=true`，错过的在开机后补跑）；没有 systemd 时用 crontab（不补跑）。
  - Windows：任务计划程序（schtasks，不补跑）。
- 不装定时任务时手动运行 `sync`。唯一的硬约束：每台机器至少每 30 天被 `sync` 一次，否则 Claude Code 日志会在入库前被 30 天保留期清理（超过 7 天未成功采集时 `sync` 和 `doctor` 会提醒）。要以后再装定时任务，重新运行 `init`，各项默认沿用原值。
- macOS 上程序位于 `~/Documents` 等受隐私保护（TCC）的目录时，launchd 启动的后台进程可能无权读取，因此要装定时任务时程序应放在数据目录下的 `app/`（与安装脚本的位置一致）。
- Windows 相关部分（本地运行、任务计划程序、作为 ssh 远端）**尚未在 Windows 上实测**；自动化测试和安装脚本在 GitHub Actions 的 Windows 上运行（M5）。

### 包结构

Python 包 `token_stats/`（`python3 -m token_stats`）；M5 起用安装脚本装好后直接运行 `token-stats`（见下方“安装”）：

| 模块 | 作用 |
|---|---|
| `scan.py` | 读日志、解析请求（第 6 节）；同一份源码既在主机本地调用，也经 ssh 发给远端执行，所以只用标准库、不 import 本包其他模块、不写文件 |
| `store.py` | 表结构、去重写入、导出日数据、合并、改名、备份、跨平台文件锁 |
| `remote.py` | 经 ssh 在远端执行 scan.py、检查远端 Python 版本 |
| `ccswitch.py` | CC Switch 只读快照与导入（第 8 节） |
| `render.py` | 四张卡片（第 9 节） |
| `config.py` | 配置文件、数据目录、时区 |
| `schedule.py` | 定时任务的安装与状态 |
| `cli.py` | 各命令 |

### 安装（M5）

只提供安装脚本，不上 PyPI，不需要 pip / uvx / pipx。只依赖标准库，装好即可运行：

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/LZWcc/token-stats/main/install.sh | sh
```

```powershell
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/LZWcc/token-stats/main/install.ps1 | iex"
```

- 源码仓库：`LZWcc/token-stats`。
- 与 Codex 的安装脚本不同，下载的不是独立程序，用户机器上需要 Python ≥ 3.9：macOS 由 Xcode 命令行工具提供 `/usr/bin/python3`，Linux 发行版通常自带，Windows 需自行安装。不用 PyInstaller 打包独立程序（每个平台要单独构建，体积大）。
- 安装脚本：
  1. 找 Python ≥ 3.9：macOS 优先系统自带的 `/usr/bin/python3`，其次 PATH 中的 `python3`；Linux 用 PATH 中的 `python3`；Windows 用 `python`。不满足就提示安装方法后退出。
  2. 从 GitHub 下载**最新 Release** 的源码包（再下载 GitHub 为该 tag 自动生成的归档，不需要构建步骤），解压后只取其中的 `token_stats/`，整个替换程序目录：数据目录下的 `app/`（先复制到 `app.new/` 再替换，下载或解压失败时旧的 `app/` 不变）。只装发布过的版本，不装 `main` 上未发布的代码。版本号：`install.sh` 由 `releases/latest` 的重定向得到，用 GET 而不是 HEAD（实测 HTTP/2 下对 GitHub 发 HEAD 会出错或卡住）；`install.ps1` 用 GitHub API `releases/latest` 的 `tag_name`（Windows PowerShell 5.1 与 PowerShell 7 读取重定向地址的方式不同）。环境变量 `TOKEN_STATS_ARCHIVE` 可指定源码包的地址或本地路径，只用于测试。
  3. 生成启动脚本：macOS / Linux 为 `~/.local/bin/token-stats`，Windows 为 `%LOCALAPPDATA%\token-stats\bin\token-stats.cmd`，内容是设置 `PYTHONPATH` 为程序目录后，用第 1 步找到的 Python 的**绝对路径**执行 `-m token_stats` 并传入全部参数。定时任务记录的也是这个 Python；Homebrew 等带版本号的路径在升级 Python 后会失效，所以 macOS 优先 `/usr/bin/python3`。
  4. 启动脚本所在目录不在 PATH 中时，只打印需要添加的那一行，不修改 `~/.zshrc`、`~/.bashrc` 或系统 PATH 等用户配置。
  5. 打印安装的版本。
- 升级：重新运行安装命令。只替换 `app/`，不动配置和 usage.db；定时任务指向的程序目录不变，不用重装。
- 卸载：`token-stats uninstall`（v0.1.1 起）。确认后移除定时任务（`schedule.uninstall()`，与安装对称，没装时什么也不做）；程序位于数据目录的 `app/`（安装脚本装的）时删除 `app/` 和启动脚本，从源码目录等其他位置运行时不删程序文件；另行询问是否同时删除配置和数据目录，默认保留（usage.db 删除后无法恢复）；移除定时任务失败时什么都不删；不碰 GitHub 上的发布仓库。README 另附手动卸载命令。
- Windows 上 `uninstall` 不能直接删除正在运行的启动脚本：cmd 执行完一行才回文件读下一行，Python 退出后文件已不在会报错。改为启动独立的 cmd 进程，约 2 秒后（启动脚本退出后）删除 `bin\`（删除数据时删除整个数据目录）；`app\` 立即删除（模块已读入内存）。CI 实测过的其他写法都不行：行尾加 `& exit /b` 时退出码变为 0；加 `& call exit /b %%errorlevel%%` 时退出码正确，但删除自身后 `call` 报 “The system cannot find the path specified.”、退出码变为 1。由 CI 的 Windows 安装测试验证：启动脚本传回退出码、卸载后不报错、`bin\` 和 `app\` 被删除。
- 现有代码不依赖安装位置：定时任务按包所在目录设置 `PYTHONPATH`，远端扫描从包目录读取 `scan.py` 源码。
- Windows 的安装脚本只在 GitHub Actions 的 Windows 上用本地源码包测试过，尚未在真实 Windows 上从 GitHub 安装。

### M3 同时修复与补充

1. 时区从配置读取（默认系统时区），导出时在 Python 中逐行按时区换算日期（正确处理夏令时；SQLite 只支持固定偏移）。CC Switch 汇总行记在配置时区的当天 12:00。
2. 导出时删除不再对应任何数据的日期文件（例如改时区后），只清理自己管理的目录。
3. 没有任何数据时渲染不崩溃，卡片显示“暂无数据”（M2 版本会除以零）。
4. 文字宽度按 `unicodedata.east_asian_width` 估算（中文按 1 em、拉丁字符按 0.6 em），替换 M2 中遇到 GBK 外字符会崩溃的写法；截断同样按此估算。
5. 文件锁跨平台（Unix 用 fcntl，Windows 用 msvcrt）。
6. 远端 Python 命令可配置（见配置文件 `python` 字段）。
7. `sync` 与 `doctor` 检查每台机器上次成功的时间，超过 7 天醒目提示（主机长期不运行时，服务器上的日志会在入库前被清理）。
8. `sync` 每天自动备份 usage.db 一份到数据目录的 `backups/`，保留最近 7 份（usage.db 是唯一事实来源）。
9. 更新本地 `LOCAL.md`：新架构下机器名不公开，“公开 id 对应真实机器”的说明已过时。

## 3. 架构：主机拉取

```
主机（用户自己的电脑，唯一安装 token-stats 的机器，手动或定时运行 sync）
  ├─ 本机日志 ───────────────────────────────┐
  ├─ ssh 服务器A  python3 -（stdin 传入解析脚本）──┤→ 中央 usage.db（逐请求，带 machine 列）
  ├─ ssh 服务器B  python3 -  …                 ──┤
  └─ CC Switch 快照（可选，一次性导入）─────────┘
        ↓ 导出（所有机器合计，不含机器信息）
  daily/<YYYY-MM-DD>.json（数据目录）
        ↓ 渲染
  cards/*.svg  →（可选）复制到发布仓库的 token-stats/ 子目录，git push → 主页 README 引用
```

- **服务器零安装、零写入**：主机通过 ssh 把解析脚本从 stdin 发给远端 `python3 -`，同时发去该机器各日志文件的读取进度；远端只解析新增部分，把新请求和新进度逐行打印回来。远端不写任何文件，日志只读。远端只需要 sshd、python3 ≥ 3.9。
- **服务器不需要 git 和 GitHub 凭据**：入库、导出、渲染、推送都在主机上完成，推送用主机上已有的 git 登录。
- 每次只传回新增请求（每条几十字节），不复制日志。
- ssh 一律加 `-o BatchMode=yes -o ConnectTimeout=15 -o RemoteCommand=none -o RequestTTY=no`：不交互、不卡住，并覆盖用户 ssh 配置中的 RemoteCommand / RequestTTY。不修改任何 ssh 配置。
- 本机总是扫描，机器名取配置的 `machine`（默认 `local`，与 CC Switch 导入共用，保证按机器选来源时对得上）；远端由配置的 `remotes` 指定，记录用的机器名为 `name`（默认等于 ssh 主机名）。
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
| ✅ **M3 命令行工具** | 第 2 节的全部命令、配置文件、数据目录、跨平台、定时任务；包结构改为 `token_stats/` | 用全新的临时家目录模拟首次安装，`init` 到出图全程跑通；在本机 `sync` 的结果与 M2 一致；`merge` 重复执行不重复计数；`rename` 后不重读文件 |
| ✅ **M4 发布** | 可选发布（第 2 节“发布”）：`sync` 把日数据和卡片推送到用户仓库的 `token-stats/` 子目录；`init` 询问仓库，可用 gh 新建；README 片段；自动提交不计入贡献图 | 用本地裸仓库测试：首次推送、无变化不提交、推送失败后补推、多余文件被删除、子目录以外的文件不变、提交作者正确；真实仓库推送后卡片在 GitHub 上正常显示 |
| ✅ **M5 开源打包** | LICENSE、自动化测试与 GitHub Actions、安装脚本（第 2 节“安装”）、中文 README、公开源码仓库并发布 Release（见下方“M5 计划”） | 他人照 README 用一条命令装好，直接运行 `token-stats`；三个平台的 CI 通过 |

M1 实测结果（2026-10-23，主机 laptop + 两台服务器经 ssh）：
- 代码（当时位于 `collector/`，M3 移入 `token_stats/`）：scan.py（扫描与解析，同一份源码既在主机本地调用，也经 ssh 发给远端 `python3 -I -B -` 执行）、中央 usage.db 与调度、CC Switch 导入。
- 用日志副本模拟三台机器写入同一个库并导入 CC Switch：各机器 × agent 与 ccusage 对账结果与第 6 节相同；合计 JSON 等于按机器选来源后之和，不含机器信息；第二、三次运行不新增行、不改写文件。
- 传输等价：同一批日志直接调用 scan() 与经 `python3 -` 执行，产出的 52524 个事件逐个相同；带读取进度再跑，570 个文件全部跳过。发给远端的程序连同进度约 140 KB。
- 真实机器：ssh 实测结果与日志副本在重叠日期（服务器 09-28 ~ 10-22、laptop 全部日期）逐日、逐模型完全一致。首次全量约 52 秒，之后每次约 6.5 秒（主要是 ssh 连接）。
- 远端无写入：扫描后在两台服务器上查找此后新增或修改的文件，只有 ssh 登录本身产生的系统日志（journal、btmp，以及系统登录时刷新的信息缓存），没有 .pyc 或任何本项目的文件。
- 新发现：server-1 上也有 Codex 日志（07-16 ~ 07-26，1824 次请求），旧架构只采集了它的 Claude Code；新架构默认每台机器两种 agent 都扫，自动补上，与 laptop 的 Codex 无主键冲突。

M3 实测结果（2026-10-23，Mac 上用临时家目录模拟首次安装，日志与 CC Switch 用符号链接指向真实目录，远端为两台真实服务器）：
- 试用模式（`token-stats`）：空家目录下不崩溃、卡片显示“暂无数据”；读真实日志约 8 秒，不创建配置和数据目录。
- `init` 全流程约 44 秒：两台远端连接与 Python 版本检查通过，导入 CC Switch，首次采集、导出、渲染、备份。与 M2 的结果相比，10-22 及以前的 170 个日数据文件逐字节一致；CC Switch 原库校验和与目录列表不变。
- 实时 CC Switch 已把 09-21 的逐请求记录汇总成日汇总行（快照时 160 汇总行 + 8 逐请求，现在 163 + 0），四项总量不变——印证了“只能导入一次”的保护。
- 第二次 `sync` 只读新增日志、当天不重复备份；`rename` 后读取进度对得上，不重读文件；自动合并与手动 `merge` 重复执行写入 0 行，合并后的日数据与原库一致。
- 改时区为 America/New_York：122 个日期文件变化、多余的日期文件被删除；改回后与改之前逐字节一致。美东夏令时切换前后的日期换算正确。
- 过期提醒、备份只保留 7 份、同时运行两个 `sync` 时第二个被拒，均符合预期；中文和 GBK 外字符的截断不再崩溃。
- 未实测：定时任务的实际安装（会装进真实的 launchd，留到正式部署）、systemd / crontab 安装、Windows 上的全部功能。

M4 实测结果（2026-10-24，主机 laptop）：
- 本地裸仓库测试（`gh repo create` 替换为 `git init --bare`）：`init` 时仓库不存在 → 新建并推送 README → 首次 `sync` 推送卡片；推送 171 个日数据文件；再次运行无变化、不提交；删除日数据文件后远端同步删除；远端改动子目录以外的文件（README、新文件）被保留；远端不可用时只报错、不影响采集，`doctor` 显示连接失败，恢复后下次推送成功；远端改动子目录内的文件时被本地数据覆盖、不冲突；提交作者和提交者都是 `token-stats <token-stats@localhost>`；空仓库克隆后分支为 `main`（克隆空仓库时本地分支跟随远端 HEAD，当时本机裸仓库的 HEAD 因 Xcode 自带的 git 配置为 main；CI 中默认是 master，测试改为显式 `--initial-branch=main` 模拟 GitHub）；用户的 `~/.gitconfig` 不变。
- 最初推送前用 `git pull --rebase`：远端改动子目录内的文件时会冲突，之后每次发布都失败，因此改为 fetch 后重置到远端（第 2 节“发布”）。
- 凭据：ssh 会话里钥匙串不可用（-25308），追加 gh 作为备用凭据助手后，经 ssh、精简 PATH 的推送演练（`push --dry-run`）成功。
- 真实仓库：主机上用正式数据运行 `init`，用 gh 新建公开仓库并首次推送 README、8 张卡片、172 个日数据文件；默认分支 `main`；卡片的 raw 地址返回 `image/svg+xml`；推送内容中没有机器名、用户名和本地路径；`doctor` 正常。
- 未实测：没有 gh 时的流程（提示先在网页上建仓库）、推到已有内容的仓库（如主页仓库）、定时任务中推送。

M5 计划：
1. 基础文件：`LICENSE`（MIT，版权人 LZWcc）；`.gitignore` 加 `__pycache__/`。
2. 自动化测试：`tests/`，只用标准库 `unittest`，用 `python3 -m unittest` 运行；合成日志按第 6 节规则构造，不含任何真实数据。覆盖：解析；跨机器去重、同一请求多次出现时的取舍；增量读取（文件变大、变小、`.zst`）；CC Switch 导入（合成 sqlite 库）与只导入一次的保护；导出的时区、夏令时、删除多余的日期文件；渲染时没有数据、中文和超长模型名；`merge`、`rename`；发布（本地裸仓库，覆盖 M4 实测的各项）。不覆盖 ssh 远端和定时任务的实际安装。
3. GitHub Actions：每次推送在 macOS、Linux、Windows 上用 Python 3.9 和最新版运行测试；另在三个平台上用当前提交打出的源码包（`TOKEN_STATS_ARCHIVE`）运行安装脚本，再用启动脚本运行一次试用。这是 Windows 目前唯一的验证途径，但覆盖不到定时任务和 ssh 远端。
4. 安装脚本：`install.sh`、`install.ps1`（第 2 节“安装”），在 Mac 的临时家目录中测试（`TOKEN_STATS_ARCHIVE` 指向本地打包的源码包）。
5. README：先只写中文 `README.md`；英文版以后再补（`README.en.md`）。内容：是什么；卡片示例（引用作者的数据仓库）；安装、试用、`init`；多台机器（服务器需要免密 ssh、Python ≥ 3.9）；发布与 README 片段；合并其他机器、导入 CC Switch；配置说明；公开哪些内容；Claude Code 30 天日志保留期与“至少每 30 天 `sync` 一次”；可选的定时任务；升级与卸载；升级 Python 后重新运行安装命令，装了定时任务的再运行一次 `init`（启动脚本和定时任务记录的都是 Python 的绝对路径，Homebrew 和 Windows 上 python.org 版本的路径带版本号）。
6. 公开发布（每一步先征得作者同意）：创建公开仓库 `LZWcc/token-stats`，只推送 `main`，不推送旧架构的 `dev` 分支；打 tag `v0.1.0`，用 `gh release create` 发布 Release。`PROJECT.md`、`CLAUDE.md`、`AGENTS.md` 随仓库公开；提交作者为作者本人的 GitHub 身份。
7. 实测：在临时家目录中用 `curl … | sh` 从 GitHub 安装并跑通；再用安装脚本替换作者手动复制的 `app/`，配置和 usage.db 不动。

M5 实测结果（2026-10-24）：
- 测试：43 个 unittest（合成日志），macOS、Linux、Windows × Python 3.9 / 最新版全部通过；Windows 上跳过 launchd 和时区两项（没有时区数据）。CI 暴露并修复：测试中的裸仓库默认分支依赖本机 git（Xcode 自带的 git 配置为 main，CI 中为 master；克隆空仓库时本地分支跟随远端 HEAD）；Windows 上子进程文本默认按本地代码页编解码（测试与 `publish.py`、`schedule.py` 改为显式指定编码）。
- 测试中发现并修复的产品问题：加锁失败时未关闭锁文件；Windows 上输出重定向（如定时任务写 run.log）时打印中文报错（`main()` 中把标准输出和标准错误改为 UTF-8，CI 中确认）；Windows 的 `sync.cmd` 换行变成 `\r\r\n`、未按 OEM 代码页写入。
- 安装脚本：Mac 临时家目录中用 `/bin/sh` 与 dash、C / en_US.UTF-8 / zh_CN.UTF-8 测试首次安装、升级（只替换 `app/`，配置和 usage.db 不变）、源码包地址错误时旧 `app/` 不变、路径含空格和单引号、`XDG_DATA_HOME`、尚未发布时的报错。发现并修复：HTTP/2 下对 GitHub 发 HEAD 请求会出错或卡住，改用 GET；macOS 的 `/bin/sh`（bash 3.2）在 UTF-8 语言环境下把紧跟变量的全角标点读进变量名，`set -u` 下脚本中止、退出码却为 0，提示被截断（变量加花括号；CI 的 macOS 安装测试改用 UTF-8 语言环境）。`install.ps1` 只在 CI 的 Windows 上测试。
- 发布：公开源码仓库 `LZWcc/token-stats`（只推送 main），tag `v0.1.0`，用 `gh release create` 发布 Release；`releases/latest` 的重定向和 API 的 `tag_name` 都是 v0.1.0。
- 实测安装：临时家目录中用 `curl … | sh` 从 GitHub 安装 v0.1.0，`app/` 与 tag 中的源码一致，启动脚本运行试用正常；主机上用安装脚本替换手动复制的 `app/`，前后配置和 usage.db 的校验和不变，`doctor` 正常，`sync` 采集、导出并推送到数据仓库成功。
- 未实测：真实 Windows 上的全部功能（包括从 GitHub 安装）、systemd / crontab 定时任务的实际安装、没有 gh 时的发布流程、推到已有内容的仓库。

M5 之后的补充：v0.1.1 新增 `token-stats uninstall`（第 2 节“安装”中的“卸载”）。

代码位于 `token_stats/`（第 2 节）。开发期本地 `archive/`（阶段一的日志副本）已于 2026-10-23 删除。

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

`token-stats import-cc-switch`（`init` 中也会询问）：只读打开 CC Switch 原库，用 SQLite 备份接口复制一份快照，再从快照导入，不改动原库；导入主机的 usage.db，machine = 配置的本机名，source = `'cc-switch'`。一个 usage.db 只应从一份快照导入一次：CC Switch 之后可能把逐请求记录汇总成日汇总行并删除明细，用新快照再导入会重复计数。导入脚本会检查：库中已有 cc-switch 数据就拒绝导入，不提供强制选项。

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

`token-stats sync` 渲染到数据目录的 `cards/`（试用模式渲染到当前目录的 `token-stats-cards/`）：四张静态 SVG，每张亮色、暗色各一份（`-dark` 后缀），外加本地预览页 `preview.html`（两种背景并排）。没有数据时卡片显示“暂无数据”。README 用 `<picture>` 按访客主题切换。

口径 metric：默认 all = 四项全加，与 Codex、ccusage 的“总 token”一致；effective = input + cache_write + output，不含缓存读取。缓存读取通常占 90% 以上，两者相差一个数量级；统计卡片底部注明当前口径。由配置文件的 `metric` 指定。

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
- 环形图：段间 2 px 背景间隙，从 12 点方向顺时针，最多 6 段（前 5 名 + 其他）。Claude、GPT 系列各自用量最高的模型用 Anthropic / OpenAI 的厂商色（同排行图），并让出相近的分类色（橙让蜜桃、绿让薄荷）；其余模型按名次依次取剩下的分类色。厂商色与其余颜色的相邻关系随数据变化，只保证正常视力可区分，未按分类色的 ΔE 标准验证。
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

- 公开（推送到用户仓库的 `token-stats/` 子目录）：每天合计的四项 token 数、按 agent 和按模型的拆分（含模型名）、SVG 卡片。自动提交的作者是 `token-stats <token-stats@localhost>`，不含用户的姓名和邮箱。
- 不公开：机器名和数量、IP、端口、ssh 配置、代理、本机用户名（作为路径或登录名）、本地路径；日志原文、prompt、代码、项目路径、会话 id；`usage.db`；任何凭据。
- GitHub 账号例外：源码仓库地址、安装命令、README 中的示例卡片地址会出现作者的 GitHub 账号。源码仓库的提交作者为作者本人的 GitHub 身份。
- `.gitignore` 至少包含：`archive/`、`output/`、`LOCAL.md`、`*.db`、`.env`、`__pycache__/`。

## 11. 运行环境

- 主机和远端：Python ≥ 3.9，只用标准库（含 sqlite3 模块）。主机另需 ssh 客户端和能推送到用户仓库的 git；用安装脚本安装时另需 curl（Windows 为 PowerShell）。
- 不需要 Node：渲染已改写为 Python（`token_stats/render.py`），Node 脚本与 package.json、config.yaml 已删除。口径、时区都在配置文件中。
- 对账基准（仅开发期）：`npx ccusage@20.0.41 {claude|codex} daily --json -z Asia/Shanghai -O`。用 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 指定日志目录，`-O` 表示用缓存的价格，不联网拉价格表。

阶段一的 ccusage 基准总量（2026-10-23 的日志副本，server-1 当时仍在增长）：

| 机器 / agent | Input | Output | Cache Create | Cache Read |
|---|---|---|---|---|
| laptop / codex | 183,497,679 | 16,602,135 | 2,970,333 | 3,472,335,879 |
| laptop / claude-code | 41,493 | 14,084 | 0 | 272,256 |
| server-1 / claude-code | 16,060 | 8,856,913 | 27,209,962 | 2,214,368,493 |
| server-2 / claude-code | 5,998 | 4,233,665 | 7,296,608 | 724,336,745 |
