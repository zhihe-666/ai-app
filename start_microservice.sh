#!/usr/bin/env bash
# 知识库微服务启动脚本（加载中控台 .env 共享配置）
#
# 用法：
#   ./start_microservice.sh                    # 默认微服务目录 ../ju
#   KB_SERVICE_DIR=/path/to/ju ./start_microservice.sh
#
# 前置：微服务目录有 .venv，且已装依赖（python-dotenv/chroma/ollama 等）
# 微服务会读环境变量 DEEPSEEK_API_KEY/GL_TOKEN 等（从中控台 .env 加载）

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 微服务目录（默认中控台同级 ../ju，可用环境变量覆盖）
KB_SERVICE_DIR="${KB_SERVICE_DIR:-$SCRIPT_DIR/../ju}"

if [ ! -d "$KB_SERVICE_DIR" ]; then
    echo -e "${RED}错误: 知识库微服务目录不存在: $KB_SERVICE_DIR${NC}"
    echo -e "请设置 KB_SERVICE_DIR 环境变量指向微服务根目录"
    echo -e "例如: KB_SERVICE_DIR=/path/to/ju $0"
    exit 1
fi

echo -e "${GREEN}=== 知识库微服务启动 ===${NC}"
echo -e "微服务目录: $KB_SERVICE_DIR"

# ---- 1. 加载中控台 .env（共享 LLM/Git 配置）----
ENV_FILE="$SCRIPT_DIR/backend/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}[1/3] 加载中控台配置: $ENV_FILE${NC}"
    set -a
    source "$ENV_FILE"
    set +a
    # 验证关键变量
    if [ -z "$DEEPSEEK_API_KEY" ]; then
        echo -e "${RED}警告: DEEPSEEK_API_KEY 未配置，微服务 LLM 调用会失败${NC}"
    fi
    if [ -z "$GL_TOKEN" ]; then
        echo -e "${RED}警告: GL_TOKEN 未配置，GitLab 同步会失败${NC}"
    fi
    echo -e "  DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:0:8}..."
    echo -e "  DEEPSEEK_BASE_URL: $DEEPSEEK_BASE_URL"
    echo -e "  LLM_MODEL: $LLM_MODEL"
    echo -e "  GL_TOKEN: ${GL_TOKEN:0:6}..."
else
    echo -e "${YELLOW}[1/3] 未找到中控台 .env ($ENV_FILE)，用微服务自己的 .env/默认值${NC}"
fi

# ---- 2. 激活微服务 venv ----
echo -e "${YELLOW}[2/3] 激活微服务虚拟环境${NC}"
if [ -f "$KB_SERVICE_DIR/.venv/bin/activate" ]; then
    source "$KB_SERVICE_DIR/.venv/bin/activate"
elif [ -f "$KB_SERVICE_DIR/venv/bin/activate" ]; then
    source "$KB_SERVICE_DIR/venv/bin/activate"
else
    echo -e "${YELLOW}  微服务无 venv，用系统 python${NC}"
fi

cd "$KB_SERVICE_DIR"

# ---- 3. 启动微服务 ----
echo -e "${YELLOW}[3/3] 启动微服务 (端口 8000)...${NC}"
echo -e "${GREEN}=== 微服务启动完成 ===${NC}"
echo -e "  访问: ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  停止: Ctrl+C"
echo -e ""

exec python src/api/agent_server.py