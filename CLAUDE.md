# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AI 项目管理中控台 — Flask + React 全栈应用，8 个核心模块：

| 模块 | 路由 | 说明 |
|------|------|------|
| **PRD 智能生成** | `/prd-gen` | 3 模式(简单/中等/深度) → 5 Agent 流水线 + 3 闸口 → 编辑/导出/原型 |
| **知识库管理** | `/kb-manage` | 代理无矩 2.0 微服务，5 Tab（概览/浏览/导入/同步/历史 PRD） |
| **会议 TODO 提取** | `/meeting-todo` | 妙记链接 → SSE 流式提取逐字稿 → LLM 分析待办 → 生成飞书文档 |
| **迭代数据统计** | `/iteration-stats` | 上传 xlsx → 解析统计 → 写入飞书多维表格 → 导出 xlsx |
| **AI 编程数据报告** | `/ai-measure` | 配置 Token/名单/时间 → SSE 生成报告 → 写入飞书文档 |
| **知识库问答** | `/chat` | 问答代理到无矩 2.0 FastAPI 微服务 (SSE 流式) |
| **功能变更分析** | `/code-analyze` | Git 仓库变更分析 → SSE 报告 → 导出 Markdown/飞书 |
| **无矩 2.0 知识问答** | `/chat` (复用) | SSE 流式问答 + 非流式查询 + 历史 CRUD |

## 启动方式

```bash
# 后端 (Flask, 端口 5000)
cd backend && pip install -r requirements.txt && python run.py

# 前端 (Vite dev server, 端口 5173, 自动代理 /api → :5000)
cd frontend && npm install && npm run dev

# 一键启动（自动 venv + pip + 启动后端，Flask serve 前端 dist/）
./start.sh

# 知识库微服务（可选，增强 PRD 生成）
# 需 ../ju 项目在同一父目录
./start_microservice.sh
```

## 项目架构

### 后端 (Flask)

```
backend/
├── app.py                       # Flask 入口, CORS, Blueprint 注册, LLM 配置注入
├── run.py                       # 启动入口 (端口 5000)
├── requirements.txt             # flask, flask-cors, openpyxl, pandas, httpx, openai
├── models.py                    # 数据模型 (dataclass)
├── routers/                     # API 路由 (Blueprint)
│   ├── prd_gen.py               #   POST /api/prd/sessions|deep-generate|deep/approve|deep/prototype|export
│   ├── kb_manage.py             #   /api/kb-manage/* (14 组代理: 概览/浏览/导入/同步/快照/图谱/PRD/组件)
│   ├── meeting_todo.py          #   /api/meeting-todo/extract|generate|search|preview
│   ├── iteration_stats.py       #   /api/stats/upload|write-bitable|export|projects|health
│   ├── ai_measure.py            #   /api/ai-measure/generate|test-token|pilot-names|tl-names|write-to-feishu
│   ├── chat.py                  #   /api/chat/send|query|conversations(CRUD)|health
│   └── code_analyze.py          #   /api/code-analyze/start|snapshot|export/markdown|export/feishu
├── services/                    # 业务逻辑
│   ├── deep_agents.py           #   深度模式 5 Agent (萃取/上下文/规格/撰写/原型)
│   ├── deep_gates.py            #   3 人工闸口 (threading.Event 挂起/恢复)
│   ├── validators.py            #   6 校验器 (Schema/Scope/Citation/Accept/Permission/Risk)
│   ├── model_router.py          #   双模型路由 (Agent2/3 pro, Agent1/4 flash)
│   ├── prototype_renderer.py    #   原型 HTML 渲染器 (纯 CSS)
│   ├── llm_client.py            #   OpenAI 兼容接口封装 (支持超时/流式)
│   ├── sse_helpers.py           #   SSE 流式响应辅助
│   ├── db.py                    #   SQLite 持久化 (9 张表 + 自动 migration)
│   ├── feishu_client.py         #   lark-cli subprocess 封装 (妙记/多维表格/文档)
│   ├── meeting_todo_service.py  #   会议 TODO 核心逻辑 (DDL 推理/跟进人匹配/JSON 容错)
│   ├── stats_engine.py          #   迭代统计引擎 (xlsx 解析/标签匹配/占比计算)
│   ├── ai_measure_client.py     #   EP drilldown API 封装
│   ├── skills_query_client.py   #   Skills API 封装
│   ├── report_generator.py      #   报告编排器 (4 模块串行 + SSE 推送)
│   ├── auth_middleware.py       #   LLM 配置认证中间件
│   ├── token_config.py          #   Token 配置管理
│   └── feishu_client.py         #   飞书操作 (妙记+多维表格+文档+通讯录)
├── data/app.db                  # SQLite 数据库 (自动创建)
└── .env                         # LLM Key 默认配置
```

### 前端 (React 19 + TypeScript + Vite + Ant Design 6)

```
frontend/
├── src/
│   ├── main.tsx                 # 入口: BrowserRouter + ConfigProvider(主题 #6366f1) + LLMConfigProvider
│   ├── App.tsx                  # Routes (/ → /meeting-todo, /iteration-stats, /ai-measure, /chat, /code-analyze, /prd-gen, /kb-manage)
│   ├── pages/
│   │   ├── PrdGen.tsx           # PRD 生成: 3 模式 + 5 Agent 流水线 + 3 闸口 + 编辑器 + 原型
│   │   ├── KbManage.tsx         # 知识库管理: 5 Tab (概览/浏览/导入/同步/历史 PRD)
│   │   ├── MeetingTodo.tsx      # 会议 TODO: 输入链接 → 分屏(逐字稿|待办) → 生成文档
│   │   ├── IterationStats.tsx   # 迭代统计: 上传 xlsx → 表格展示 → 写入/导出
│   │   ├── AiMeasure.tsx        # AI 报告: 配置 → SSE 流式 → 报告预览
│   │   ├── Chat.tsx             # 知识库问答: 对话 + 历史侧边栏 + Markdown 渲染
│   │   └── CodeAnalyze.tsx      # 代码变更分析 (SSE 流式报告)
│   ├── components/
│   │   ├── AppLayout.tsx        # 侧边栏布局 (可收起 260↔80px)
│   │   ├── LLMConfigProvider.tsx# LLM 全局配置 Context
│   │   ├── TranscriptPanel.tsx  # 逐字稿面板
│   │   ├── TodoPanel.tsx        # 待办面板 (按模块分组)
│   │   ├── TodoCard.tsx         # 待办卡片 (内联编辑/删除/DDL/跟进人)
│   │   ├── ReportPreview.tsx    # 报告预览
│   │   └── ComingSoon.tsx       # 即将上线占位
│   ├── api/                     # API 封装层 (Axios 实例 + SSE 流式)
│   │   ├── client.ts            # Axios 实例 (baseURL = API_BASE)
│   │   ├── prdGen.ts            # PRD 生成 API (3 模式 + 深度 SSE + 闸口 + 原型)
│   │   ├── kbManage.ts          # 知识库管理 API (图谱/PRD CRUD/组件注册表)
│   │   ├── meetingTodo.ts       # 会议 TODO API
│   │   ├── iterationStats.ts    # 迭代统计 API
│   │   ├── aiMeasure.ts         # AI 报告 API
│   │   └── chat.ts              # 知识库问答 API
│   └── utils/
│       ├── apiBase.ts           # API_BASE 常量
│       └── sse.ts               # SSE 流式请求工具 (fetch + ReadableStream)
```

## 模块详解

### 1. PRD 智能生成 (`prd_gen.py + prd_gen_service.py + deep_agents.py`)

**三种模式：**

| 模式 | 流程 | 适用场景 |
|------|------|---------|
| 简单 | 输入 → 大纲 → 逐章节 SSE 生成 → 编辑/导出 | 需求明确 |
| 中等 | 输入 → 7 话题问答引导 → 确认 → 大纲 → 逐章节生成 → 编辑/导出 | 需求模糊 |
| 深度 | 5 Agent 流水线 + 3 闸口 + 6 校验器 → PRD → 可选原型 | 复杂功能 |

**深度模式流水线：**
```
Agent1(需求萃取,flash) → 审核闸口 → Agent2(上下文分析,pro,调知识库图谱)
  → 影响闸口 → Agent3(功能规格,pro) → V:6 校验器 → 规格闸口
  → Agent4(PRD 撰写,flash) → V:风险 → [可选]Agent5(原型生成,flash) → 完成
```

**5 Agent 职责：**

| Agent | 模型 | 输入 | 输出 |
|-------|------|------|------|
| Agent1 | flash | 用户需求 + 妙记 + 文件 + 平台上下文 + KB 问答 | 结构化需求 + 冲突 + 信息缺口 |
| Agent2 | pro | Agent1 + 平台架构快照 + 影响范围 | 模块关系 + 缺失依赖 + 预警 |
| Agent3 | pro | Agent1+Agent2 | features + user_stories + data_models |
| Agent4 | flash | Agent1/2/3 + 用户闸口修改 | 9 章节 Markdown PRD + JSON Spec |
| Agent5 | flash | PRD + Spec + 组件注册表 + 页面布局 | 产品原型 HTML |

**3 个人工闸口：** `threading.Event` 挂起 SSE generator，`POST /deep/approve` 唤醒。每条闸口数据可编辑(冲突:采纳/忽略/修改, 影响:勾选+编辑, 规格:可编辑表格)。修改内容通过 `user_fixes` → `user_ctx` 传递后续 Agent。

**6 校验器：** Schema(必填字段)/Scope(范围蔓延)/Citation(防幻觉)/Acceptance(验收标准)/Permission(权限)/Risk(异常性能)。error → 回退 Agent 重跑(≤2 次), warn → 标记继续。

**双模型路由：** `model_router.py` - Agent2/3 强制 `deepseek-v4-pro`, Agent1/4/5 用用户配置(默认 flash)。Agent2/3 的 base_url 指向 DeepSeek 域。

**Agent1 伪 Agentic：** 双 pass: pass1 产出 `questions_to_kb` → 后端调 KB `/api/query`(全 collection) → pass2 融合。prompt 要求主动查询"已有功能""页面组件""API 数据模型""现有流程"。

**原型生成：** Agent5 读 `design_layouts`(22 页) + `component_registry`(606 组件) → `prototype_renderer.py` 渲染纯 CSS HTML。空 section 自动重试 1 次。

**SSE 事件类型:** `progress`, `agent_complete`, `gate`, `validation`, `complete`, `error`。

**API 端点：**

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/prd/sessions` | 创建会话 (mode=simple/medium/deep) |
| POST | `/api/prd/sessions/{id}/simple-generate` | 简单模式 SSE |
| POST | `/api/prd/sessions/{id}/start-chat` | 中等模式开始 |
| POST | `/api/prd/sessions/{id}/chat` | 中等模式对话 |
| POST | `/api/prd/sessions/{id}/deep-generate` | 深度模式 SSE (5 Agent + 3 闸口) |
| POST | `/api/prd/sessions/{id}/deep/approve` | 闸口审批 |
| POST | `/api/prd/sessions/{id}/deep/prototype` | AI 原型生成 |
| GET | `/api/prd/sessions/{id}/export` | 导出 Markdown |
| POST | `/api/prd/sessions/{id}/export/feishu` | 导出飞书文档 |
| PUT | `/api/prd/sessions/{id}/sections/{section}` | 编辑章节 |
| GET | `/api/prd/sessions/{id}/versions` | 版本列表 |

### 2. 知识库管理 (`kb_manage.py` + `KbManage.tsx`)

所有接口代理到无矩 2.0 FastAPI 微服务 (`localhost:8000/api/admin/*`)，统一 `{status, data, error}` 响应格式。提供 `_proxy_get/post/put/delete/files` 五种代理方法，3 层异常捕获(ConnectionError/Timeout/RequestException)。

**功能分组：**

| 组 | 端点 | 说明 |
|----|------|------|
| 概览 | `GET /collections` | 文档数/类型/同步状态 |
| 浏览 | `GET /browse` | 分页 + 关键词搜索 |
| 文档 | `GET /doc` | 单条全文 |
| SQLite | `GET /sqlite/tables`, `/sqlite/table` | 查看微服务数据库 |
| 导入文本 | `POST /import` | 文本 → manual_kb |
| 导入文件 | `POST /import/file` | 文件上传 (PDF/Word/MD/TXT/XLSX/PPT) |
| 删除 | `DELETE /delete` | 删文档 (Chroma+SQLite 同步) |
| 代码同步 | `POST /sync` | 3 模式: backend(支持 dry_run)/frontend/full |
| 同步状态 | `GET /sync/status` | 轮询任务状态 |
| 快照 | `POST/GET /snapshots`, `GET/DELETE /snapshots/{id}` | KB 快照 CRUD |
| 回退 | `POST /rollback` | 一键回退到快照 |
| 图谱查询 | `GET /modules`, `/modules/{name}`, `/graph/impact`, `/graph/flow`, `/graph/node/{id}` | 12 模块 + 影响范围 |
| 历史 PRD | `GET/POST /prds`, `GET/PUT/DELETE /prds/{id}`, `POST /prds/search` | PRD CRUD + 语义搜索 |
| 设计/组件 | `GET /design-layouts`, `/components/registry` | 22 页布局 + 606 组件 |

**前端 5 Tab：** 概览(统计卡片+Collection 列表) / 浏览(分页+搜索+Drawer 全文) / 导入(左文本+右文件) / 同步(3 模式+轮询) / 历史 PRD(搜索+筛选+导入 Modal+Markdown 渲染)。

### 3. 会议 TODO 提取 (`meeting_todo.py + meeting_todo_service.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/meeting-todo/extract` | POST | SSE 流式提取 (妙记链接 → 逐字稿 → LLM 待办) |
| `/api/meeting-todo/generate` | POST | 生成飞书纪要文档 |
| `/api/meeting-todo/search` | POST | 搜索飞书妙记 |
| `/api/meeting-todo/preview` | POST | 预览妙记 (不调 LLM) |

**关键实现：** `lark-cli` subprocess 获取逐字稿。DDL 推理 LLM 推断 deadline。跟进人匹配搜索 open_id。JSON 5 层容错解析(标准→宽松→尾随逗号→部分→截断)。SSE: progress → section_complete(逐字稿) → progress → complete(待办)。

**数据模型：** `MeetingInfo`(title/time/link/token), `TodoItem`(description/module/ddl/assignee), `ModuleGroup`(name/todos)。

### 4. 迭代数据统计 (`iteration_stats.py + stats_engine.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/stats/upload` | POST | 上传 xlsx → 解析统计 → 合并飞书 TL |
| `/api/stats/write-bitable` | POST | 写入飞书多维表格 (批量更新+自动合计行) |
| `/api/stats/export` | POST | 导出 xlsx 下载 |
| `/api/stats/projects` | GET | 获取项目列表 (PROJECT_MAP 12 项) |
| `/api/stats/health` | GET | 健康检查 |

**关键实现：** 标签列名轮询 `["自定义标签","自...标签","标签","需求标签"]`。12 项目 `PROJECT_MAP` 硬编码。前端本地计算 `aicoding_ratio = aicoding/engineering`, `sdd_ratio = sdd/aicoding`。

### 5. AI 编程数据报告 (`ai_measure.py + report_generator.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/ai-measure/generate` | POST | SSE 流式生成 (4 模块串行: 活跃率→不活跃→Skills→TL) |
| `/api/ai-measure/test-token` | POST | 测试 Token 连通性 |
| `/api/ai-measure/pilot-names` | GET/POST | 试点名单 CRUD |
| `/api/ai-measure/tl-names` | GET/POST | TL 名单 CRUD (硬编码 27 人) |
| `/api/ai-measure/write-to-feishu` | POST | Markdown → 飞书文档 (含表格转换) |

**关键实现：** 直接 HTTP 调用 EP drilldown API + Skills API。`_md_to_docx_xml()` 转 Markdown 为飞书 DocxXML。

### 6. 知识库问答 (`chat.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat/send` | POST | SSE 流式问答 (透传微服务 SSE, 流结束存历史) |
| `/api/chat/query` | POST | 非流式查询 (返回 contexts) |
| `/api/chat/conversations` | GET/DELETE | 历史列表/清空 |
| `/api/chat/conversations/{id}` | GET/DELETE | 历史详情/删除 |
| `/api/chat/health` | GET | 连通性检查 |

**SSE 事件:** `sources` → `token` → `done/error`。`save_chat_session` 用独立 `_connect()` 而非 Flask g(流式 generator 在请求上下文外执行)。

### 7. 功能变更分析 (`code_analyze.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/code-analyze/start` | POST | SSE 流式分析 (参数: repo_url, branch, start/end_time, frontend_paths, git_token) |
| `/api/code-analyze/snapshot` | GET | 当前快照信息 |
| `/api/code-analyze/refresh-snapshot` | POST | SSE 刷新知识快照 |
| `/api/code-analyze/export/markdown` | POST | 导出 Markdown 文件 |
| `/api/code-analyze/export/feishu` | POST | 导出飞书文档 |

## 数据库 (SQLite, 9 张表)

| 表 | 用途 | 说明 |
|----|------|------|
| `user_config` | LLM 全局配置 | 单行, provider/api_key/base_url/model/git_token |
| `feishu_tokens` | 飞书 OAuth Token | open_id(PK), access/refresh_token, expires_at |
| `repo_cache` | 仓库缓存 | repo_url+branch+frontend_paths |
| `commit_cache` | Commit 缓存 | (repo_url,branch,start_time,end_time) 联合 PK |
| `prd_sessions` | PRD 会话 | mode/status/deep_state/deep_artifacts/feishu_doc_url |
| `prd_versions` | PRD 版本 | (session_id,section,version_num) 快照 |
| `prd_files` | PRD 文件 | session_id+filename+text_content |
| `prd_chat_messages` | PRD 对话 | session_id+role+round |
| `chat_sessions` | 问答历史 | title+query+answer+sources(JSON) |

**Schema Migration:** `_has_column()` 自动检测补列(git_token, deep_state, deep_artifacts, feishu_doc_url)。

## SSE 流式通信

后端: Flask `Response(generator(), mimetype='text/event-stream')` + `stream_with_context`。
前端: `fetch` + `ReadableStream` 逐行解析。事件格式: `event: {type}\ndata: {json}\n\n`。

**事件类型:** `progress`, `section_complete`, `section_error`, `agent_complete`, `gate`, `validation`, `complete`, `error`。
深度模式闸口: `gate` 事件后 generator 挂起(threading.Event), 等待 `POST /deep/approve` 唤醒。

## LLM 配置优先级

请求头 (`X-Api-Key/X-Base-Url/X-Model`) > DB(`user_config` 表) > `backend/.env`(`DEFAULT_*`)。前端"全局配置"弹窗可覆盖。

## 常用命令

```bash
# 后端
pip install -r requirements.txt   # 安装依赖
python run.py                     # 启动 (端口 5000)

# 前端
npm install                       # 安装依赖
npm run dev                       # 开发服务器 (端口 5173)
npm run build                     # 生产构建

# 数据库重置: 删除 data/app.db 后重启自动重建
# 知识库微服务: ./start_microservice.sh (需 ../ju 项目)
```

## 外部依赖

- **`lark-cli`**: subprocess 调用, 飞书操作 (妙记/多维表格/文档/通讯录)
- **无矩 2.0 知识问答**: localhost:8000 FastAPI 微服务。`start_microservice.sh` 加载中控台 `.env` 共享配置。
- **知识库微服务 (ju)**: 代码图谱/组件注册表/页面布局/PRD 向量检索。与 `ai-app` 同父目录部署。
- **OpenAI 兼容 LLM**: DeepSeek API, 支持 flash/pro 双模型路由。