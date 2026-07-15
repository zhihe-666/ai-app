# ── Stage 1: Build frontend ──
FROM node:20-alpine AS frontend-builder
# 使用淘宝 npm 镜像加速
RUN npm config set registry https://registry.npmmirror.com
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Build code-analyzer CLI ──
FROM node:20-alpine AS analyzer-builder
RUN npm config set registry https://registry.npmmirror.com
WORKDIR /app/tools/code-analyzer
COPY tools/code-analyzer/package*.json ./
RUN npm ci || npm install
COPY tools/code-analyzer/ ./
RUN npm run build

# ── Stage 3: Final runtime image ──
FROM python:3.12-slim

# 配置 debian 国内源（清华）加速 apt
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null \
    || true

# 使用国内 pip 镜像加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# Install system deps + Node (for lark-cli)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install lark-cli globally (npm 国内源)
RUN npm config set registry https://registry.npmmirror.com \
    && npm install -g lark-cli

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend (serve as static)
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy built code-analyzer
COPY --from=analyzer-builder /app/tools/code-analyzer/dist ./tools/code-analyzer/dist
COPY tools/code-analyzer/package.json ./tools/code-analyzer/package.json

# Copy frontend index.html / vite config for reference
COPY frontend/index.html ./frontend/index.html

# Ensure data dirs exist
RUN mkdir -p /app/backend/data /app/data/git-cache

# Expose port
EXPOSE 5000

# Environment defaults (override at runtime)
ENV LARK_CONFIG_DIR=/app/.dewuclaw/lark-cli-config/cli_aa847daba1bc1bb3
ENV PYTHONUNBUFFERED=1

# Run Flask (gunicorn for production)
WORKDIR /app/backend
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "run:app"]