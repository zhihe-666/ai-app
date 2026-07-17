# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AI 项目管理中控台 — Flask + React 全栈应用，5 个核心模块：

| 模块 | 路由 | 说明 |
|------|------|------|
| 会议 TODO 提取 | `/meeting-todo` | 妙记链接 → SSE 流式提取逐字稿 → LLM 分析待办 → 生成飞书文档 |
| 迭代数据统计 | `/iteration-stats` | 上传 xlsx → 解析统计 → 写入飞书多维表格 → 导出 xlsx |
| AI 编程数据报告 | `/ai-measure` | 配置 Token/名单/时间 → SSE 生成报告 → 写入飞书文档 |
| 无矩 2.0 知识库问答 | `/chat` | 问答代理到无矩 2.0 FastAPI 微服务 (SSE 流式) |
| PRD 智能生成 | `/prd-gen` | 3 模式(简单/中等/深度) → SSE 生成 → 编辑/导出/原型 |

## 启动方式

```bash
# 后端 (Flask, 端口 5000)
cd backend && pip install -r requirements.txt && python run.py

# 前端 (Vite dev server, 端口 5173, 自动代理 /api → :5000)
cd frontend && npm install && npm run dev

# 或使用启动脚本
python backend/launch.py    # 后台启动后端
python launch_frontend.py   # 后台启动前端
```

启动脚本: `backend/start.sh` (前台运行), `backend/launch.py` (后台进程), `launch_frontend.py` (前端后台).

## 项目架构

### 后端 (Flask)

```
backend/
├── app.py                       # Flask 入口, CORS, Blueprint 注册, LLM 配置注入
├── run.py / start.py / start_debug.py  # 启动入口
├── requirements.txt             # flask, flask-cors, openpyxl, pandas, httpx, openai, playwright
├── models.py                    # 数据模型 (dataclass)
├── routers/                     # API 路由 (Blueprint)
│   ├── meeting_todo.py          #   /api/meeting-todo/extract|generate|search
│   ├── iteration_stats.py       #   /api/stats/upload|write-bitable|export|projects
│   ├── ai_measure.py            #   /api/ai-measure/test-token|generate|write-to-feishu
│   ├── chat.py                  #   /api/chat/send (SSE+存历史) | /query | /conversations CRUD
│   ├── kb_manage.py             #   /api/kb-manage/* (代理微服务 admin, sync 3模式+快照回退+图谱+PRD CRUD+组件注册表)
│   ├── code_analyze.py          #   /api/code-analyze/start (SSE) | snapshot | export
│   └── prd_gen.py               #   /api/prd/* (PRD 智能生成, 3模式+深度模式SSE闸口+原型端点)
├── services/                    # 业务逻辑
│   ├── db.py                    #   SQLite 持久化 (user_config 表)
│   ├── feishu_client.py         #   lark-cli subprocess 封装 (妙记/多维表格/文档)
│   ├── llm_client.py            #   OpenAI 兼容接口封装
│   ├── sse_helpers.py           #   SSE 流式响应辅助
│   ├── meeting_todo_service.py  #   会议 TODO 核心逻辑 (LLM 分析/DDL 推理/跟进人匹配)
│   ├── stats_engine.py          #   迭代统计引擎 (xlsx 解析/标签匹配/占比计算)
│   ├── ai_measure_client.py     #   EP drilldown API 封装
│   ├── skills_query_client.py   #   Skills API 封装
│   ├── report_generator.py      #   报告编排器 (4 模块串行 + SSE 推送)
│   ├── auth_middleware.py       #   LLM 配置认证中间件
│   ├── deep_agents.py           #   深度模式 5 个 Agent(萃取/上下文/规格/撰写/原型)
│   ├── deep_gates.py            #   深度模式 3 人工闸口(threading.Event 挂起/恢复)
│   ├── validators.py            #   深度模式 6 校验器(Schema/Scope/Citation/Accept/Permission/Risk)
│   ├── model_router.py          #   双模型路由(Agent2/3 pro, Agent1/4 flash)
│   ├── token_config.py          #   Token 配置管理
│   └── sse_helpers.py           #   SSE 事件流辅助函数
├── data/app.db                  # SQLite 数据库 (自动创建)
├── tl_names.txt                 # TL 名单文件
└── ai_center.db                 # (可选) 兼容数据库
```

### 前端 (React 19 + TypeScript + Vite + Ant Design 6)

```
frontend/
├── index.html
├── vite.config.ts               # Vite 配置 (proxy /api → localhost:5000)
├── package.json                 # react 19, antd 6, axios, react-router-dom 7, react-markdown
├── tsconfig.json
└── src/
    ├── main.tsx                 # 入口: BrowserRouter + ConfigProvider(主题 #6366f1) + LLMConfigProvider
    ├── App.tsx                  # Routes 定义 (/ → /meeting-todo, 4 个子路由)
    ├── pages/
    │   ├── MeetingTodo.tsx      # 会议 TODO: 输入链接 → 分屏(逐字稿|待办) → 生成文档
    │   ├── IterationStats.tsx   # 迭代统计: 上传 xlsx → 表格展示 → 写入/导出
    │   ├── AiMeasure.tsx        # AI 报告: 配置 → SSE 流式 → 报告预览(Table + Markdown)
    │   ├── Chat.tsx             # 知识库问答: 对话界面 + 引用来源
    │   ├── PrdGen.tsx           # PRD 生成 3 模式 + Agent 流水线 + 闸口 + 原型
    │   └── KbManage.tsx         # 知识库管理 + 历史 PRD CRUD
    ├── components/
    │   ├── AppLayout.tsx        # 侧边栏布局 (260px, 8 个菜单项, 4 个 disabled)
    │   ├── LLMConfigProvider.tsx # LLM 全局配置 Context
    │   ├── TranscriptPanel.tsx  # 逐字稿面板
    │   ├── TodoPanel.tsx        # 待办面板 (按模块分组)
    │   ├── TodoCard.tsx         # 待办卡片 (内联编辑/删除/DDL/跟进人)
    │   ├── ReportPreview.tsx    # 报告预览 (备用)
    │   └── ComingSoon.tsx       # 即将上线占位
    ├── api/
    │   ├── client.ts            # Axios 实例 (baseURL = API_BASE)
    │   ├── meetingTodo.ts       # 会议 TODO API 类型 + 调用
    │   ├── iterationStats.ts    # 迭代统计 API 类型 + 调用
    │   ├── aiMeasure.ts         # AI 报告 API 类型 + SSE 回调
    │   ├── chat.ts              # 知识库 API 类型 + 调用
    │   ├── prdGen.ts            # PRD 生成 API(3 模式 + 深度 SSE + 闸口 + 原型)
    │   └── kbManage.ts          # 知识库管理 API(图谱/PRD CRUD/组件注册表)
    └── utils/
        ├── apiBase.ts           # API_BASE 常量
        └── sse.ts               # SSE 流式请求工具 (fetch + ReadableStream)
```

## 深度模式关键实现细节

### 流水线架构
```
Agent1(需求萃取,flash) → 审核闸口 → Agent2(上下文分析,pro,调知识库图谱)
  → 影响闸口 → Agent3(功能规格,pro) → V:6 校验器 → 规格闸口
  → Agent4(PRD 撰写,flash) → V:风险 → [可选]Agent5(原型生成,flash) → 完成
```

### 5 Agent 职责

| Agent | 模型 | 输入 | 输出 |
|-------|------|------|------|
| Agent1 需求萃取 | flash | 用户需求 + 妙记 + 文件 + 知识库问答 | 结构化需求 + 冲突 + 信息缺口 |
| Agent2 上下文分析 | pro | Agent1 + 平台架构快照 + 影响范围 | 模块关系 + 缺失依赖 + 预警 |
| Agent3 功能规格 | pro | Agent1+Agent2 | features + user_stories + data_models |
| Agent4 PRD 撰写 | flash | Agent1/2/3 产出 | 9 章节 Markdown PRD + JSON Spec |
| Agent5 原型生成 | flash | PRD + Spec + 组件注册表 | 产品原型 HTML |

### 3 人工闸口
`threading.Event` 挂起 SSE generator，用户 POST `/deep/approve` 唤醒。
- **需求审核闸口**:显示 requirements + gaps + conflicts，支持采纳/忽略/修改
- **影响范围闸口**:显示 impact_warnings，支持勾选保留 + 编辑文字
- **规格闸口**:可编辑表格(名称/优先级下拉/移除恢复)，提交修改(```edits```)传给后续 Agent

### 6 校验器
`validators.py`: Schema/Scope/Citation/Acceptance/Permission/Risk。error 级回退 Agent 重跑(≤2 次)，warn 级标记继续。

### 双模型路由
`model_router.py`: Agent2/3 强制 `deepseek-v4-pro`(强推理)，Agent1/4/5 用用户配置(默认 flash)。
Agent2/3 的 base_url 指向 DeepSeek 域，不随用户配置。

### 原型生成
Agent5 调用微服务 `GET /api/admin/design-layouts`(页面布局) + `GET /api/admin/component-registry`(606 组件)→ 注入 prompt 要求参考平台布局和组件。
`prototype_renderer.py` 将结构化 sections(table/stat_grid/diff/actions/form) 渲染为纯 CSS HTML。

### 历史 PRD 管理（API_PRD.md）
kb_manage.py 代理 7 个端点(CRUD + 搜索 + design-layouts + component-registry)。
KbManage.tsx "历史 PRD" Tab 支持搜索/状态筛选/分页/查看全文/文件导入/删除。

### Agent1 伪 Agentic
双 pass: pass1 产出 ```questions_to_kb``` → 后端调 KB `/api/query` → pass2 融合 KB 答案产出最终需求。
prompt 要求 Agent1 主动查询"平台已有相关功能""已有页面和组件""后台 API 和数据模型""现有流程"。

### SSE 流式通信模式

后端使用 Flask `Response(generator(), mimetype='text/event-stream')`, 前端使用 `fetch` + `ReadableStream` 解析. 事件格式: `event: {type}\ndata: {json}\n\n`. 支持事件类型: `progress`, `section_complete`, `section_error`, `agent_complete`, `gate`, `validation`, `complete`, `error`。深度模式闸口: `gate` 事件后 generator 挂起, 等待 `POST /deep/approve`。

## 关键实现细节

### 1. 会议 TODO 提取 (`meeting_todo_service.py`)
- 妙记链接 → `lark-cli` subprocess 获取逐字稿 → LLM 分析待办
- DDL 推理: 根据会议日期生成上下文, LLM 推断 deadline
- 跟进人匹配: `lark-cli` 搜索 open_id
- JSON 解析容错: 5 层递进解析 (标准→宽松→尾随逗号→部分→截断)
- SSE 事件: progress → section_complete(逐字稿) → progress → complete(待办)

### 2. 迭代数据统计 (`stats_engine.py`)
- xlsx 解析 → 标签列名轮询 (`["自定义标签","自...标签","标签","需求标签"]`)
- 12 个项目名+TL 硬编码为 `PROJECT_MAP`, 废弃正则解析
- 前端本地 computeSummary: `aicoding_ratio = aicoding/engineering`, `sdd_ratio = sdd/aicoding`

### 3. AI 编程数据报告 (`report_generator.py`)
- 4 模块串行: 活跃率 → 不活跃 → Skills → TL 使用, 每个模块独立 SSE 事件
- TL 名单硬编码 (27 人)
- 直接 HTTP 调用 EP drilldown API + Skills API

### 5. PRD 深度模式 (`prd_gen_service.py + deep_agents.py`)
- 5 Agent 流水线 + 3 闸口 + 6 校验器, SSE 流式编排
- Agent1 双 pass(伪 Agentic, 自动问 KB 补充平台信息)
- Agent2 调知识库图谱 API(modules/impact/flow/node) + design_layouts
- Agent4 prompt 注入前序 Agent 全部产出 + 用户闸口修改(user_ctx)
- Agent5 读 component_registry + design_layouts → prototype_renderer 产 HTML
- 空 section 自动重试 1 次

### 4. 知识库问答 (`chat.py`)
- 代理到无矩 2.0 FastAPI 微服务 (localhost:8000)
- SSE 流式返回 token + sources，流式累积 answer/sources，`[DONE]` 时存历史到 `chat_sessions` 表
- 问答历史 CRUD：`GET /conversations`（列表）、`GET /conversations/{id}`（详情）、`DELETE /conversations/{id}`（删单条）、`DELETE /conversations`（清空）
- 非流式查询 `POST /api/chat/query`（对齐 T025 文档 2.2，返回 contexts）
- 前端 Chat.tsx 左侧历史侧边栏 + ReactMarkdown 渲染回答（`chat-markdown.css` 样式）
- 微服务配置共享：中控台 `backend/.env` 含 `DEEPSEEK_API_KEY`/`GL_TOKEN` 等同名环境变量，`start_microservice.sh` 加载后 export 给微服务进程

## 常用命令

```bash
# 后端
pip install -r requirements.txt   # 安装依赖
python run.py                     # 启动 (端口 5000)
python start_debug.py             # 调试模式启动

# 前端
npm install                       # 安装依赖
npm run dev                       # 开发服务器 (端口 5173)
npm run build                     # 生产构建

# 数据库重置: 删除 backend/data/app.db 后重启自动重建
```

## 外部依赖

- **`lark-cli`**: subprocess 调用, 用于飞书操作 (妙记/多维表格/文档/通讯录)
- **无矩 2.0 知识问答**: localhost:8000 FastAPI 微服务, `/api/query/stream` SSE 端点。`start_microservice.sh` 加载中控台 `.env` 共享配置（`DEEPSEEK_API_KEY`/`GL_TOKEN` 等），默认微服务目录 `../ju`
- **OpenAI 兼容 LLM**: 配置优先级 请求头 > DB(user_config 表) > `backend/.env`(DEFAULT_*)。前端"全局配置"弹窗可覆盖
- **`backend/.env`**: 默认配置（DEFAULT_API_KEY/GIT_TOKEN + 微服务共享 DEEPSEEK_API_KEY/GL_TOKEN），对方零配置上手