# token-stats 安装脚本（Windows）：
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/LZWcc/token-stats/main/install.ps1 | iex"
# 把最新 Release 装到 %LOCALAPPDATA%\token-stats\app，生成启动脚本 %LOCALAPPDATA%\token-stats\bin\token-stats.cmd。
# 重新运行即升级：只替换 app\，不动配置和 usage.db。
# 环境变量 TOKEN_STATS_ARCHIVE 可指定源码包（.zip）的地址或本地路径，只用于测试。
# 本文件为无 BOM 的 UTF-8：按上面的 irm | iex 运行；Windows PowerShell 5.1 直接运行本地文件时会按本地编码读错中文。

function Install-TokenStats {
    # 写在函数内，不改变调用者会话的设置
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $repo = 'LZWcc/token-stats'

    # 取 sys.executable 作为绝对路径；PATH 中的 python 是应用商店占位程序时没有输出，按未安装处理
    $py = $null
    try { $py = & python -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2>$null } catch {}
    if (-not $py) {
        throw '需要 Python 3.9 或更高版本：从 https://www.python.org/downloads/ 安装（勾选 Add python.exe to PATH），重新打开 PowerShell 后重试'
    }
    $py = "$py".Trim()

    if ($env:TOKEN_STATS_ARCHIVE) {
        $url = $env:TOKEN_STATS_ARCHIVE
    } else {
        try {
            $tag = (Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/$repo/releases/latest").tag_name
        } catch {
            throw "无法获取最新版本（网络不通或尚未发布）：$_"
        }
        $url = "https://github.com/$repo/archive/refs/tags/$tag.zip"
    }

    $data = Join-Path $env:LOCALAPPDATA 'token-stats'   # 与 token_stats/config.py 的数据目录一致
    $app = Join-Path $data 'app'
    $bin = Join-Path $data 'bin'

    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('token-stats-' + [guid]::NewGuid())
    New-Item -ItemType Directory $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'src.zip'
        Write-Host "下载 $url"
        if (Test-Path -LiteralPath $url -PathType Leaf) {
            Copy-Item -LiteralPath $url $zip
        } else {
            Invoke-WebRequest -UseBasicParsing $url -OutFile $zip
        }
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp
        $src = Get-ChildItem -LiteralPath $tmp -Directory | ForEach-Object { Join-Path $_.FullName 'token_stats' } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Container } | Select-Object -First 1
        if (-not $src) { throw '源码包中没有 token_stats\' }

        # 先放到 app.new\，完整复制后再替换 app\
        New-Item -ItemType Directory -Force $data, $bin | Out-Null
        $new = Join-Path $data 'app.new'
        if (Test-Path -LiteralPath $new) { Remove-Item -LiteralPath $new -Recurse -Force }
        New-Item -ItemType Directory $new | Out-Null
        Copy-Item -LiteralPath $src $new -Recurse
        if (Test-Path -LiteralPath $app) { Remove-Item -LiteralPath $app -Recurse -Force }
        Rename-Item -LiteralPath $new 'app'
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }

    # cmd 按 OEM 代码页读取批处理文件；setlocal 使 PYTHONPATH 不留在调用者的 cmd 窗口中。
    # 运行 Python 与 exit /b 写在同一行：cmd 执行完一行才回文件读下一行，同一行已整体解析，
    # token-stats uninstall 删除正在运行的本文件后不会报“找不到批处理文件”。
    # exit /b 不带参数时退出码为 0（CI 实测），所以用 call 在执行时再展开一次 %errorlevel%（%% 在第一遍解析时变成 %）
    $cmd = Join-Path $bin 'token-stats.cmd'
    $text = "@echo off`r`nsetlocal`r`nset `"PYTHONPATH=$app`"`r`n`"$py`" -m token_stats %* & call exit /b %%errorlevel%%`r`n"
    Set-Content -LiteralPath $cmd -Value $text -Encoding Oem -NoNewline

    $ver = & $py -c "import sys; sys.path.insert(0, sys.argv[1]); import token_stats; print(token_stats.__version__)" $app
    if ($LASTEXITCODE) { throw '安装后无法导入 token_stats' }
    Write-Host "已安装 token-stats $ver"
    Write-Host "  程序：$app"
    Write-Host "  启动脚本：$cmd（Python：$py）"

    if (($env:Path -split ';') -notcontains $bin) {
        Write-Host ''
        Write-Host "$bin 不在 PATH 中。运行下面这一行把它加入用户 PATH，然后重新打开终端："
        Write-Host "  [Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'User') + ';$bin', 'User')"
    }
    Write-Host ''
    Write-Host '下一步：运行 token-stats 试用（只统计本机，不写入数据目录），或运行 token-stats init 开始配置'
}

Install-TokenStats
