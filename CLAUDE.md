# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AI 项目管理中控台 — Flask + React 全栈应用，4 个核心模块：

| 模块 | 路由 | 说明 |
|------|------|------|
| 会议 TODO 提取 | `/meeting-todo` | 妙记链接 → SSE 流式提取逐字稿 → LLM 分析待办 → 生成飞书文档 |
| 迭代数据统计 | `/iteration-stats` | 上传 xlsx → 解析统计 → 写入飞书多维表格 → 导出 xlsx |
| AI 编程数据报告 | `/ai-measure` | 配置 Token/名单/时间 → SSE 生成报告 → 写入飞书文档 |
| 无矩 2.0 知识库问答 | `/chat` | 问答代理到无矩 2.0 FastAPI 微服务 (SSE 流式) |

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
│   └── chat.py                  #   /api/chat/send (SSE 代理到无矩 2.0)
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
    │   └── Chat.tsx             # 知识库问答: 对话界面 + 引用来源
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
    │   └── chat.ts              # 知识库 API 类型 + 调用
    └── utils/
        ├── apiBase.ts           # API_BASE 常量
        └── sse.ts               # SSE 流式请求工具 (fetch + ReadableStream)
```

### SSE 流式通信模式

后端使用 Flask `Response(generator(), mimetype='text/event-stream')`, 前端使用 `fetch` + `ReadableStream` 解析. 事件格式: `event: {type}\ndata: {json}\n\n`. 支持事件类型: `progress`, `section_complete`, `section_error`, `complete`, `error`.

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

### 4. 知识库问答 (`chat.py`)
- 代理到无矩 2.0 FastAPI 微服务 (localhost:8000)
- SSE 流式返回 token + sources

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
- **无矩 2.0 知识问答**: localhost:8000 FastAPI 微服务, `/api/query/stream` SSE 端点
- **OpenAI 兼容 LLM**: 通过环境变量或前端输入配置 API Key / Base URL / Model
- **Playwright**: 可选, `playwright install chromium`