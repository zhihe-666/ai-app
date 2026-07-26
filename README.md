# AI 项目管理中控台

基于 Flask + React 19 + TypeScript + Ant Design 的全栈 AI 项目管理平台，将多个 AI 辅助能力统一封装为 Web 界面。

一站式完成**会议纪要提取、迭代数据统计、AI 编程数据报告、知识库问答、PRD 智能生成、代码变更分析、知识库管理**等工作。

---

## 目录

- [核心模块](#核心模块)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [模块详解](#模块详解)
- [API 概览](#api-概览)
- [SSE 流式通信](#sse-流式通信)
- [LLM 配置](#llm-配置)
- [数据库](#数据库)
- [部署](#部署)
- [外部依赖](#外部依赖)
- [开发记录](#开发记录)

---

## 核心模块

| 模块 | 路由 | 功能简介 |
|------|------|---------|
| **PRD 智能生成** | `/prd-gen` | 3 种模式（简单/中等/深度），深度模式为 5 Agent 流水线 + 3 人工闸口 + 6 校验器，支持原型 HTML 生成 |
| **知识库管理** | `/kb-manage` | 4 Tab 管理无矩 2.0 知识库，支持文本/文件导入、代码同步、快照回退、知识图谱查询 |
| **会议 TODO 提取** | `/meeting-todo` | 输入飞书妙记链接 → SSE 流式提取逐字稿 → LLM 分析待办 → 生成飞书文档 |
| **迭代数据统计** | `/iteration-stats` | 上传 RDC xlsx → 自动解析统计 AIcoding / SDD / 端到端 → 写入飞书多维表格 → 导出 |
| **AI 编程数据报告** | `/ai-measure` | 配置 Token/名单/时间 → SSE 流式生成 4 模块报告 → 写入飞书文档 |
| **知识库问答** | `/chat` | 类 ChatGPT 对话界面，SSE 代理到无矩 2.0 FastAPI 微服务，带历史管理 |
| **功能变更分析** | `/code-analyze` | 分析 Git 仓库变更 AST → 14 类信号提取 + LLM 语义归纳 → Markdown/飞书导出 |
| **无矩 2.0 知识问答** | `/chat`（复用） | SSE 流式问答 + 非流式查询 + 历史 CRUD |

---

## 技术栈

### 后端

| 技术 | 说明 |
|------|------|
| **Python 3.10+** | 后端语言 |
| **Flask** | Web 框架（因部署平台限制，替代方案中的 FastAPI） |
| **Flask-CORS** | 跨域支持 |
| **SQLite** | 持久化存储，9 张表自动 migration |
| **openpyxl** | xlsx 解析与导出 |
| **httpx / requests** | LLM API 与微服务 HTTP 调用 |
| **lark-cli** | 飞书操作（妙记、多维表格、文档、通讯录）子进程封装 |

### 前端

| 技术 | 说明 |
|------|------|
| **React 19** | UI 框架 |
| **TypeScript** | 类型安全 |
| **Vite** | 构建工具，dev server 自动 proxy `/api` → Flask |
| **Ant Design 6** | 组件库，主题色 `#6366f1` |
| **Axios** | HTTP 客户端 |
| **react-markdown** | Markdown 渲染 |

### 外部服务

| 服务 | 用途 |
|------|------|
| **无矩 2.0 FastAPI 微服务**（`localhost:8000`） | 知识库问答 + 代码图谱 + PRD 向量检索 |
| **OpenAI 兼容 LLM API**（DeepSeek 等） | 所有 AI 生成能力 |
| **飞书 Open API**（通过 lark-cli） | 妙记、多维表格、文档、通讯录 |
| **Git** | 功能变更分析仓库缓存 |

---

## 快速开始

### 开发环境

```bash
# 1. 后端
cd backend
pip install -r requirements.txt
python run.py
# 服务启动在 http://127.0.0.1:5000

# 2. 前端（新终端）
cd frontend
npm install
npm run dev
# 开发服务器启动在 http://localhost:5173，自动代理 /api → :5000
```

### 一键启动

```bash
# 自动 venv + pip install + 启动后端，Flask serve 前端 dist/
./start.sh
```

### Docker 部署

```bash
docker compose up -d --build
# 访问 http://localhost:5000
```

首次构建约 5-10 分钟（安装 Node/Python 依赖、lark-cli）。

### 启动后配置

1. 侧边栏底部打开 **全局配置**
2. 填入 LLM API Key / Base URL / Model（OpenAI 兼容）
3. 各模块即可使用

---

## 项目结构

```
ai-app/
├── backend/                    # Flask 后端
│   ├── app.py                  # Flask 入口, CORS, Blueprint 注册
│   ├── run.py / launch.py      # 启动入口（端口 5000）
│   ├── models.py               # 数据模型（dataclass）
│   ├── requirements.txt        # Python 依赖
│   ├── routers/                # API 路由（Blueprint）
│   │   ├── prd_gen.py          # PRD 智能生成（3 模式 + 5 Agent 流水线）
│   │   ├── kb_manage.py        # 知识库管理（14 个代理端点）
│   │   ├── meeting_todo.py     # 会议 TODO 提取
│   │   ├── iteration_stats.py  # 迭代数据统计
│   │   ├── ai_measure.py       # AI 编程数据报告
│   │   ├── chat.py             # 知识库问答（SSE 代理）
│   │   └── code_analyze.py     # 功能变更分析
│   ├── services/               # 业务逻辑
│   │   ├── deep_agents.py      # 深度模式 5 Agent 编排
│   │   ├── deep_gates.py       # 3 个人工闸口（threading.Event）
│   │   ├── validators.py       # 6 校验器（Schema/Scope/Citation...）
│   │   ├── model_router.py     # 双模型路由（pro / flash）
│   │   ├── prototype_renderer.py  # 原型 HTML 渲染器
│   │   ├── llm_client.py       # OpenAI 兼容 LLM 封装
│   │   ├── feishu_client.py    # lark-cli 子进程封装
│   │   ├── meeting_todo_service.py # 会议 TODO 核心逻辑
│   │   ├── stats_engine.py     # 迭代统计引擎
│   │   ├── ai_measure_client.py    # EP drilldown API 封装
│   │   ├── report_generator.py # 报告编排器
│   │   ├── auth_middleware.py   # LLM 配置认证中间件
│   │   ├── db.py               # SQLite 持久化（9 表 + 自动 migration）
│   │   └── sse_helpers.py      # Flask SSE 流式辅助
│   ├── ai_measure_scripts/     # AI 编程数据报告外部脚本
│   └── data/                   # SQLite 数据库（自动创建）
│
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── main.tsx            # 入口（BrowserRouter + Ant Design 主题）
│   │   ├── App.tsx             # 路由定义
│   │   ├── pages/              # 页面组件
│   │   │   ├── PrdGen.tsx      # PRD 生成工作台
│   │   │   ├── KbManage.tsx    # 知识库管理（4 Tab）
│   │   │   ├── MeetingTodo.tsx # 会议 TODO 分屏
│   │   │   ├── IterationStats.tsx # 迭代统计
│   │   │   ├── AiMeasure.tsx   # AI 报告
│   │   │   ├── Chat.tsx        # 知识库问答
│   │   │   └── CodeAnalyze.tsx # 代码变更分析
│   │   ├── components/         # 通用组件
│   │   │   ├── AppLayout.tsx   # 侧边栏布局（可收起）
│   │   │   ├── LLMConfigProvider.tsx # LLM 全局配置
│   │   │   ├── ReportPreview.tsx / TranscriptPanel.tsx / TodoPanel.tsx / TodoCard.tsx
│   │   │   └── RenderEngine.tsx / ComingSoon.tsx
│   │   ├── api/                # API 封装层
│   │   └── utils/              # SSE 流式请求等工具
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
│
├── tools/
│   ├── code-analyzer/          # TypeScript CLI: AST 信号提取 + Git 分析
│   └── doc_sync.sh             # 文档同步检查脚本
│
├── docs/                       # 设计文档
│   ├── PRD*.md                 # PRD 方案文档
│   └── superpowers/            # 功能分析设计文档
│
├── lark-config/                # 飞书 lark-cli 配置
├── Dockerfile
├── docker-compose.yml
├── dclaw.yaml
├── start.sh / start.bat
└── README.md
```

---

## 模块详解

### 1. PRD 智能生成

三种模式适配不同场景：

| 模式 | 流程 | 适用场景 |
|------|------|---------|
| 简单 | 输入 → 大纲 → 逐章节 SSE 生成 → 编辑/导出 | 需求明确 |
| 中等 | 输入 → 7 话题问答引导 → 确认 → 大纲 → 逐章节生成 → 编辑/导出 | 需求模糊 |
| 深度 | 5 Agent 流水线 + 3 闸口 + 6 校验器 → PRD → 可选原型 | 复杂功能 |

**深度模式流水线：**

```
Agent1（需求萃取，flash）→ 审核闸口
  → Agent2（上下文分析，pro，调知识库图谱）→ 影响闸口
    → Agent3（功能规格，pro）→ 6 校验器 → 规格闸口
      → Agent4（PRD 撰写，flash）→ 风险校验
        → [可选] Agent5（原型生成，flash）→ 完成
```

**双模型路由：** Agent2/3 强制 `deepseek-v4-pro`，Agent1/4/5 用用户配置（默认 flash）。

**3 个人工闸口：** 使用 `threading.Event` 挂起 SSE generator，等待前端审批后继续，每条闸口数据均可编辑。

**6 校验器：** Schema（必填字段）/ Scope（范围蔓延）/ Citation（防幻觉）/ Acceptance（验收标准）/ Permission（权限）/ Risk（异常性能）。

**原型生成：** Agent5 读取设计布局（22 页）和组件注册表（606 组件），调用 `prototype_renderer.py` 渲染纯 CSS HTML。

### 2. 知识库管理

4 个 Tab 管理无矩 2.0 知识库：

- **概览**：统计卡片 + Collection 列表
- **浏览**：分页 + 关键词搜索 + Drawer 全文查看
- **导入**：左侧文本导入 + 右侧文件上传（PDF/Word/MD/TXT/XLSX/PPT）
- **同步**：3 种同步模式（代码/核心KB/Wiki/全量）+ dry-run 预览 + 轮询进度

所有接口代理到无矩 2.0 FastAPI 微服务（`localhost:8000`），统一 `{status, data, error}` 响应格式，3 层异常捕获。

### 3. 会议 TODO 提取

输入飞书妙记链接 → SSE 流式提取 → 分屏展示逐字稿和待办 → 生成飞书文档。

**关键实现：**
- `lark-cli` subprocess 获取妙记逐字稿
- DDL 推理：LLM 从会议上下文推断 deadline
- 跟进人匹配：简称 → 全称映射 + 飞书通讯录搜索
- JSON 5 层容错解析（标准 → 宽松 → 尾随逗号 → 部分 → 截断修复）
- 文档模板：飞书 docx XML 格式，支持多个 `<cite>` 提及人标签

### 4. 迭代数据统计

上传 RDC 导出的 xlsx → 自动解析 AIcoding / SDD / 端到端数据 → 写入飞书多维表格 → 导出 xlsx。

**关键实现：**
- 标签列名优先级轮询（兼容不同版本 RDC xlsx）
- 自动合并飞书多维表格标准项目名称和 TL
- TL 为人员字段类型，自动清洗 `@` 前缀
- 项目名称精确 + 子串模糊匹配
- 自动创建合计行

### 5. AI 编程数据报告

配置 EP Token / 试点名单 / TL 名单 → SSE 流式生成 4 模块报告 → 写入飞书文档。

**4 模块串行：** 活跃率 → 不活跃成员 → Skills 查询 → TL 报告

### 6. 知识库问答

类 ChatGPT 对话界面，SSE 代理到无矩 2.0 FastAPI 微服务。

**SSE 事件：** `sources` → `token` → `done` / `error`

### 7. 功能变更分析

分析 Git 仓库指定时间段的变更 → AST 信号提取 → LLM 语义归纳 → Markdown / 飞书文档导出。

**14 类 AST 信号：**
- NEW_ROUTE / NEW_PAGE / API_CALL / STATE_ACTION / DATA_MODEL
- PERMISSION / HOOK_DEF / EVENT_HANDLER / CONFIG_CHANGE / STYLE_ONLY
- GENERIC_CHANGE / TEXT_CHANGE / TYPE_CHANGE / TEST_CHANGE

**双层过滤：** 正则发现（高召回）→ AST 验证（高精确）→ LLM 语义归类

**分析流程：** git diff → 代码层覆盖计算 → Import Graph 聚类 → LLM 逐一描述 → 报告组装

---

## API 概览

### PRD 智能生成

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/prd/sessions` | 创建会话（mode=simple/medium/deep） |
| POST | `/api/prd/sessions/{id}/simple-generate` | 简单模式 SSE 生成 |
| POST | `/api/prd/sessions/{id}/start-chat` | 中等模式开始 |
| POST | `/api/prd/sessions/{id}/chat` | 中等模式对话 |
| POST | `/api/prd/sessions/{id}/deep-generate` | 深度模式 SSE（5 Agent + 3 闸口） |
| POST | `/api/prd/sessions/{id}/deep/approve` | 闸口审批 |
| GET | `/api/prd/sessions/{id}/export` | 导出 Markdown |
| PUT | `/api/prd/sessions/{id}/sections/{section}` | 编辑章节 |
| GET | `/api/prd/sessions/{id}/versions` | 版本列表 |

### 会议 TODO

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/meeting-todo/extract` | SSE 流式提取妙记待办 |
| POST | `/api/meeting-todo/generate` | 生成飞书纪要文档 |
| POST | `/api/meeting-todo/search` | 搜索飞书妙记 |
| POST | `/api/meeting-todo/preview` | 预览妙记（不调 LLM） |

### 迭代数据统计

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/stats/upload` | 上传 xlsx 解析统计 |
| POST | `/api/stats/write-bitable` | 写入飞书多维表格 |
| POST | `/api/stats/export` | 导出 xlsx |
| GET | `/api/stats/projects` | 项目列表 |

### AI 编程数据报告

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/ai-measure/generate` | SSE 流式生成报告 |
| POST | `/api/ai-measure/test-token` | 测试 Token 连通性 |
| POST | `/api/ai-measure/write-to-feishu` | 写入飞书文档 |

### 知识库问答

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/chat/send` | SSE 流式问答 |
| POST | `/api/chat/query` | 非流式查询 |
| GET | `/api/chat/conversations` | 历史列表 |
| DELETE | `/api/chat/conversations/{id}` | 删除历史 |

### 功能变更分析

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/code-analyze/start` | SSE 流式分析 |
| GET | `/api/code-analyze/snapshot` | 知识快照信息 |
| POST | `/api/code-analyze/export/markdown` | 导出 Markdown |
| POST | `/api/code-analyze/export/feishu` | 导出飞书文档 |

### 知识库管理

| 方法 | 端点模式 | 说明 |
|------|----------|------|
| GET | `/api/kb-manage/collections` | 概览 |
| GET | `/api/kb-manage/browse` | 分页浏览 |
| POST | `/api/kb-manage/import` | 文本导入 |
| POST | `/api/kb-manage/import/file` | 文件上传 |
| POST | `/api/kb-manage/sync` | 代码同步 |
| GET | `/api/kb-manage/modules` | 知识图谱模块 |
| POST/GET/DELETE | `/api/kb-manage/snapshots` | 快照 CRUD |

---

## SSE 流式通信

后端使用 Flask `Response(generator(), mimetype='text/event-stream')` + `stream_with_context` 实现 SSE。

前端使用 `fetch` + `ReadableStream` 逐行解析。事件格式：

```
event: {type}
data: {json}

```

**事件类型：** `progress` | `section_complete` | `agent_complete` | `gate` | `validation` | `complete` | `error`

**深度模式 PRD：** `gate` 事件后 generator 挂起（`threading.Event`），等待 `POST /deep/approve` 唤醒。

---

## LLM 配置

**配置优先级：**

请求头（`X-Api-Key` / `X-Base-Url` / `X-Model`）> DB（`user_config` 表）> `backend/.env`（`DEFAULT_*`）

前端"全局配置"弹窗可覆盖以上所有设置。支持预设：
- OpenAI
- DeepSeek
- 通义千问
- 硅基流动

**双模型路由（PRD 深度模式）：**
- Agent2/3 强制 `deepseek-v4-pro`（base_url 直连 DeepSeek 域）
- Agent1/4/5 使用用户配置（默认 flash）

---

## 数据库

SQLite，9 张表，自动 schema migration：

| 表名 | 用途 |
|------|------|
| `user_config` | LLM 全局配置（单行） |
| `feishu_tokens` | 飞书 OAuth Token |
| `repo_cache` | 仓库缓存 |
| `commit_cache` | Commit 缓存 |
| `prd_sessions` | PRD 会话 |
| `prd_versions` | PRD 版本快照 |
| `prd_files` | PRD 文件 |
| `prd_chat_messages` | PRD 对话记录 |
| `chat_sessions` | 问答历史 |

数据库重置：删除 `backend/data/app.db` 后重启自动重建。

---

## 部署

### Docker（推荐）

```bash
docker compose up -d --build
```

一键启动，镜像内置 Node / Python / lark-cli 环境。

**数据卷：**

| 宿主机路径 | 容器路径 | 作用 |
|-----------|---------|------|
| `./data` | `/app/backend/data` | SQLite 数据库 |
| `./git-cache` | `/app/data/git-cache` | Git 裸仓库缓存 |
| `./lark-config` | `/app/.dewuclaw/lark-cli-config` | 飞书 lark-cli token |

**环境变量：**

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `LARK_CONFIG_DIR` | lark-cli 配置目录 | `/app/.dewuclaw/lark-cli-config/cli_aa847daba1bc1bb3` |
| `EP_TOKEN` | AI 编程数据报告的 Access Token | 空（通过前端界面填写） |

### 手动部署

```bash
# 构建前端
cd frontend && npm install && npm run build

# 启动后端（自动 serve dist/）
cd ../backend && python start.py
```

---

## 外部依赖

- **lark-cli**：飞书操作（妙记、多维表格、文档、通讯录），通过 subprocess 调用
- **无矩 2.0 知识问答**：`localhost:8000` FastAPI 微服务，提供知识库检索、代码图谱、PRD 向量搜索
- **知识库微服务（ju）**：代码图谱 / 组件注册表 / 页面布局 / PRD 向量检索，与 `ai-app` 同父目录部署
- **OpenAI 兼容 LLM**：DeepSeek API 等，支持 flash / pro 双模型路由

> 注意：知识库问答和知识库管理模块依赖无矩 2.0 FastAPI 微服务（`localhost:8000`），如该服务不可用则对应模块无法使用。其他模块均可独立运行。

---

## 开发记录

项目从 2026-06-23 启动，按 Phase 迭代开发：

- **Phase 0**：项目骨架搭建
- **Phase 1**：公共基础设施（SSE / 飞书 / LLM / 全局 Token）
- **Phase 2**：会议 TODO 提取模块
- **Phase 3**：迭代数据统计模块
- **Phase 4**：AI 编程数据报告模块
- **Phase 5**：知识库问答模块
- **Phase 6**：知识库管理模块
- **Phase 7**：功能变更分析模块（含 Node.js CLI 工具）
- **Phase 8**：PRD 智能生成模块

详细开发日志见 `BLOG_RECORD.md`，任务追踪见 `task_plan.md`。

---

## License

MIT
