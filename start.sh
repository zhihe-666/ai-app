#!/usr/bin/env bash
# AI 中控台 — 一键启动脚本
# 用法：./start.sh
# 前置：macOS/Linux + Python 3.10+ + Node 18+ + npm

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}=== AI 中控台 启动脚本 ===${NC}"

# ---- 1. 环境检查 ----
echo -e "${YELLOW}[1/6] 检查环境...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3，请安装 Python 3.10+${NC}"
    exit 1
fi
if ! command -v node &> /dev/null; then
    echo -e "${RED}错误: 未找到 node，请安装 Node 18+ (https://nodejs.org)${NC}"
    exit 1
fi
if ! command -v npm &> /dev/null; then
    echo -e "${RED}错误: 未找到 npm，请安装 Node 18+${NC}"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")")
NODE_VER=$(node -v)
echo -e "  Python: $PY_VER"
echo -e "  Node: $NODE_VER"

# ---- 2. 后端 venv + 依赖 ----
echo -e "${YELLOW}[2/6] 准备后端环境...${NC}"
cd backend

if [ ! -d "venv" ]; then
    echo -e "  创建虚拟环境..."
    python3 -m venv venv
fi

# 激活 venv
source venv/bin/activate

echo -e "  安装后端依赖（首次较慢）..."
pip install --quiet --upgrade pip 2>/dev/null || true
pip install --quiet -r requirements.txt 2>&1 | tail -3 || {
    echo -e "${YELLOW}  默认源较慢，尝试国内镜像...${NC}"
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet 2>&1 | tail -3
}

cd "$SCRIPT_DIR"

# ---- 3. 前端依赖 + build ----
echo -e "${YELLOW}[3/6] 准备前端环境...${NC}"
cd frontend

if [ ! -d "node_modules" ]; then
    echo -e "  安装前端依赖（首次较慢）..."
    npm install --silent 2>&1 | tail -3 || {
        echo -e "${YELLOW}  默认源较慢，尝试国内镜像...${NC}"
        npm install --registry=https://registry.npmmirror.com 2>&1 | tail -3
    }
fi

if [ ! -d "dist" ]; then
    echo -e "  构建前端..."
    npm run build 2>&1 | tail -3
fi

cd "$SCRIPT_DIR"

# ---- 4. 飞书 lark-cli 配置 ----
echo -e "${YELLOW}[4/6] 检查飞书配置...${NC}"
LARK_CONFIG_DIR="${LARK_CONFIG_DIR:-$HOME/.dewuclaw/lark-cli-config}"

if [ -d "lark-config" ]; then
    # 项目自带 lark-config，复制到用户目录
    if [ ! -d "$LARK_CONFIG_DIR" ]; then
        echo -e "  复制飞书配置到 $LARK_CONFIG_DIR ..."
        mkdir -p "$HOME/.dewuclaw"
        cp -r lark-config "$LARK_CONFIG_DIR"
    fi
fi

# 检查 lark-cli 是否安装
if ! command -v lark-cli &> /dev/null; then
    echo -e "${YELLOW}  安装 lark-cli (npm 全局)...${NC}"
    npm install -g lark-cli 2>&1 | tail -2 || echo -e "${YELLOW}  lark-cli 安装失败，飞书功能不可用${NC}"
fi

# 设置环境变量
export LARK_CONFIG_DIR
echo -e "  LARK_CONFIG_DIR=$LARK_CONFIG_DIR"

# ---- 5. 默认配置 ----
echo -e "${YELLOW}[5/6] 加载默认配置...${NC}"
if [ -f "backend/.env" ]; then
    echo -e "  使用 backend/.env 默认配置 (LLM + Git Token)"
    set -a
    source backend/.env
    set +a
else
    echo -e "${YELLOW}  未找到 backend/.env，请在前端配置 LLM/Git Token${NC}"
fi

# ---- 6. 启动后端 ----
echo -e "${YELLOW}[6/6] 启动后端...${NC}"
cd backend
source venv/bin/activate

echo -e "${GREEN}=== 启动完成 ===${NC}"
echo -e "  访问地址: ${GREEN}http://localhost:5000${NC}"
echo -e "  内网访问: ${GREEN}http://$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I | awk '{print $1}'):5000${NC}"
echo -e "  停止服务: Ctrl+C"
echo -e ""

exec python run.py
