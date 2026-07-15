# AI 中控台 — Docker 部署指南

> 对方只需 Docker 即可一键部署。

---

## 一、前置条件

对方机器需要：
- **Docker** 20.10+
- **Docker Compose** v2+
- 约 2GB 磁盘空间

无需 Node、Python、lark-cli，镜像内已全部包含。

---

## 二、部署步骤

### 1. 解压项目

```bash
tar -xzf ai-app.tar.gz
cd ai-app
```

### 2. 配置飞书 lark-cli token

把你的 lark-cli 配置目录拷贝到 `lark-config/`：

```bash
# 你本机执行（打包 token 配置给对方）
cp -r ~/.dewuclaw/lark-cli-config ./lark-config

# 然后连同项目一起发给对方，对方解压后 lark-config/ 已就位
```

或者对方自己用 lark-cli 登录（需要 lark-cli 装在宿主机，不推荐）。

### 3. 配置 EP Token（AI 编程数据报告模块用，可选）

```bash
# 创建 .env 文件
echo "EP_TOKEN=你的EP_TOKEN值" > .env
```

### 4. 启动

```bash
docker compose up -d --build
```

首次构建约 5-10 分钟（装 Node、Python 依赖、lark-cli）。

### 5. 访问

浏览器打开 **http://localhost:5000**

---

## 三、配置说明

### 环境变量

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `LARK_CONFIG_DIR` | lark-cli 配置目录 | `/app/.dewuclaw/lark-cli-config/cli_aa847daba1bc1bb3` |
| `EP_TOKEN` | AI 编程数据报告的 Access Token | 空（通过前端界面填） |

### 数据卷

| 宿主机路径 | 容器路径 | 作用 |
|-----------|---------|------|
| `./data` | `/app/backend/data` | SQLite 数据库（用户配置、PRD 会话等） |
| `./git-cache` | `/app/data/git-cache` | Git 裸仓库缓存 |
| `./lark-config` | `/app/.dewuclaw/lark-cli-config` | 飞书 lark-cli token |

数据持久化在宿主机，容器重建不丢失。

---

## 四、用户使用流程

启动后，对方在浏览器 **http://localhost:5000** 配置：

1. **全局配置**（侧边栏底部）：
   - LLM API Key / Base URL / Model（OpenAI 兼容）
   - Git Token（GitLab 访问令牌）
2. 各模块直接使用

---

## 五、打包发送

你本机执行：

```bash
# 1. 清理不需要的文件
rm -rf frontend/node_modules backend/venv
rm -rf backend/data/*.db  # 可选：清空数据库给对方干净环境

# 2. 打包
tar -xzf ai-app.tar.gz . \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='venv' \
  --exclude='data/git-cache' \
  --exclude='*.log'

# 3. 附带 lark-cli 配置
cp -r ~/.dewuclaw/lark-cli-config ./lark-config
tar -rf ai-app.tar ./lark-config
gzip ai-app.tar
```

发送 `ai-app.tar.gz`（约 50-100MB）给对方。

---

## 六、常见问题

### Q1: 启动后访问 5000 端口打不开？
```bash
docker compose logs ai-app
```
看后端日志，常见原因：lark-config 路径不对、端口被占用。

### Q2: 飞书功能报错"未找到 lark-cli 命令"？
镜像内已装 lark-cli，但配置目录路径不对。确认 `lark-config/` 下有 `cli_aa847daba1bc1bb3` 目录。

### Q3: Git clone 失败？
对方需要在全局配置里填自己的 GitLab Token（有仓库读权限）。

### Q4: 功能变更分析模块 AST 报错？
镜像内已 build code-analyzer CLI（`tools/code-analyzer/dist/`），无需额外操作。

### Q5: 想更新代码？
```bash
# 重新 build
docker compose up -d --build
```

---

## 七、模块清单

| 模块 | 路由 | 是否可用 |
|------|------|---------|
| 会议 TODO 提取 | `/meeting-todo` | ✅ 需飞书 token |
| 迭代数据统计 | `/iteration-stats` | ✅ |
| AI 编程数据报告 | `/ai-measure` | ✅ 需 EP_TOKEN |
| 知识库问答 | `/chat` | ⚠️ 需无矩2.0微服务（:8000） |
| 知识库管理 | `/kb-manage` | ⚠️ 同上 |
| 功能变更分析 | `/code-analyze` | ✅ 需 Git Token |
| PRD 智能生成 | `/prd` | ✅ |

**注意**：知识库问答/管理依赖无矩2.0 FastAPI 微服务（localhost:8000），如果对方机器没有这个微服务，这两个模块不可用。其他模块均可正常使用。