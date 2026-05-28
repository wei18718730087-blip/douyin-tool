#!/usr/bin/env bash
set -e

REPO="https://github.com/YOUR_USERNAME/douyin-tool.git"
INSTALL_DIR="$HOME/.douyin-tool"
BIN_DIR="$HOME/.local/bin"
CLI_NAME="douyin-tool"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 检查 Python
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        error "未找到 Python，请先安装 Python 3.10+"
    fi
    VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    MAJOR=$(echo "$VERSION" | cut -d. -f1)
    MINOR=$(echo "$VERSION" | cut -d. -f2)
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
        error "Python 版本过低: $VERSION，需要 3.10+"
    fi
    info "Python $VERSION"
}

# 安装
install() {
    info "安装 $CLI_NAME ..."

    # 创建目录
    mkdir -p "$INSTALL_DIR" "$BIN_DIR"

    # 下载代码
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "更新已有安装..."
        cd "$INSTALL_DIR" && git pull -q 2>/dev/null || true
    else
        info "下载代码..."
        git clone --depth 1 "$REPO" "$INSTALL_DIR" 2>/dev/null || {
            # 如果 git clone 失败，尝试直接下载
            error "下载失败，请检查网络连接"
        }
    fi

    cd "$INSTALL_DIR"

    # 创建 venv
    if [ ! -d ".venv" ]; then
        info "创建虚拟环境..."
        $PYTHON -m venv .venv
    fi

    # 安装依赖
    info "安装依赖..."
    .venv/bin/pip install -e . -q 2>/dev/null || {
        .venv/bin/pip install httpx fastapi uvicorn click jieba pydantic pydantic-settings playwright jinja2 -q
    }

    # 安装 Playwright 浏览器
    info "安装 Playwright 浏览器..."
    .venv/bin/playwright install chromium 2>/dev/null || true

    # 创建 wrapper
    cat > "$BIN_DIR/$CLI_NAME" << EOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/cli.py" "\$@"
EOF
    chmod +x "$BIN_DIR/$CLI_NAME"

    # 检查 PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        warn "$BIN_DIR 不在 PATH 中"
        # 自动添加到 shell profile
        SHELL_NAME=$(basename "$SHELL")
        if [ "$SHELL_NAME" = "zsh" ]; then
            PROFILE="$HOME/.zshrc"
        elif [ "$SHELL_NAME" = "bash" ]; then
            PROFILE="$HOME/.bashrc"
        else
            PROFILE="$HOME/.profile"
        fi
        if ! grep -q ".local/bin" "$PROFILE" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$PROFILE"
            info "已添加 PATH 到 $PROFILE"
        fi
        export PATH="$BIN_DIR:$PATH"
    fi

    info "安装完成!"
    echo ""
    echo "使用方式:"
    echo "  $CLI_NAME -h              查看帮助"
    echo "  $CLI_NAME info <链接>      获取视频信息"
    echo "  $CLI_NAME download <链接>  下载无水印视频"
    echo "  $CLI_NAME comments <链接>  抓取评论"
    echo ""
}

# 卸载
uninstall() {
    info "卸载 $CLI_NAME ..."
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_DIR/$CLI_NAME"
    info "已卸载"
}

case "${1:-install}" in
    install) check_python; install ;;
    uninstall) uninstall ;;
    *) echo "用法: $0 [install|uninstall]"; exit 1 ;;
esac
