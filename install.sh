#!/bin/sh
# token-stats 安装脚本（macOS / Linux）：
#   curl -fsSL https://raw.githubusercontent.com/LZWcc/token-stats/main/install.sh | sh
# 把最新 Release 装到数据目录下的 app/，生成启动脚本 ~/.local/bin/token-stats。
# 重新运行即升级：只替换 app/，不动配置和 usage.db。
# 环境变量 TOKEN_STATS_ARCHIVE 可指定源码包（.tar.gz）的地址或本地路径，只用于测试。
set -eu

REPO=LZWcc/token-stats

say() { printf '%s\n' "$*"; }
die() { printf '错误：%s\n' "$*" >&2; exit 1; }

# 单引号转义，写入启动脚本的路径可以含空格
q() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

ok_python() {
    "$1" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1
}

# macOS 优先自带的 /usr/bin/python3：Homebrew 等的路径带版本号，升级 Python 后会失效
find_python() {
    if [ "$(uname -s)" = Darwin ] && ok_python /usr/bin/python3; then
        echo /usr/bin/python3
        return
    fi
    p=$(command -v python3 2>/dev/null) || return 1
    ok_python "$p" || return 1
    echo "$p"
}

main() {
    py=$(find_python) || {
        if [ "$(uname -s)" = Darwin ]; then
            die '需要 Python 3.9 或更高版本：运行 xcode-select --install 安装命令行工具（自带 /usr/bin/python3）后重试'
        fi
        die '需要 Python 3.9 或更高版本：用系统的包管理器安装 python3 后重试'
    }

    if [ -n "${TOKEN_STATS_ARCHIVE:-}" ]; then
        url=$TOKEN_STATS_ARCHIVE
    else
        # releases/latest 重定向到 releases/tag/<版本>；用 GET 而不是 HEAD（-I）：实测 HTTP/2 下对 GitHub 发 HEAD 会出错或卡住
        latest=$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest") ||
            die '无法获取最新版本（网络不通或尚未发布）'
        tag=${latest##*/tag/}
        [ "$tag" != "$latest" ] || die '无法获取最新版本（尚未发布）'
        url="https://github.com/$REPO/archive/refs/tags/$tag.tar.gz"
    fi

    data=${XDG_DATA_HOME:-$HOME/.local/share}/token-stats   # 与 token_stats/config.py 的数据目录一致
    app=$data/app
    bin=$HOME/.local/bin

    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    say "下载 $url"
    if [ -f "$url" ]; then
        cp "$url" "$tmp/src.tar.gz"
    else
        curl -fsSL "$url" -o "$tmp/src.tar.gz" || die "下载失败：$url"
    fi
    tar -xzf "$tmp/src.tar.gz" -C "$tmp"
    set -- "$tmp"/*/token_stats
    [ -d "$1" ] || die '源码包中没有 token_stats/'

    # 先放到 app.new/，完整复制后再替换 app/
    mkdir -p "$data" "$bin"
    rm -rf "$data/app.new"
    mkdir "$data/app.new"
    cp -R "$1" "$data/app.new/"
    rm -rf "$app"
    mv "$data/app.new" "$app"

    cat > "$bin/token-stats" <<LAUNCHER
#!/bin/sh
PYTHONPATH=$(q "$app")
export PYTHONPATH
exec $(q "$py") -m token_stats "\$@"
LAUNCHER
    chmod +x "$bin/token-stats"

    ver=$("$py" -c 'import sys; sys.path.insert(0, sys.argv[1]); import token_stats; print(token_stats.__version__)' "$app")
    say "已安装 token-stats $ver"
    say "  程序：$app"
    say "  启动脚本：$bin/token-stats（Python：${py}）"

    case ":$PATH:" in
        *":$bin:"*) ;;
        *)
            case ${SHELL:-} in
                */zsh) rc='~/.zshrc' ;;
                */bash) rc='~/.bashrc' ;;
                *) rc='shell 的配置文件' ;;
            esac
            say ''
            say "$bin 不在 PATH 中。把下面这一行加到 ${rc}，然后重新打开终端："
            say '  export PATH="$HOME/.local/bin:$PATH"'
            ;;
    esac
    say ''
    say '下一步：运行 token-stats 试用（只统计本机，不写入数据目录），或运行 token-stats init 开始配置'
}

main "$@"
