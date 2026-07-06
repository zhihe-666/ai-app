# AI 项目管理中控台 — 项目实现 Plan

> 基于《AI中控台-MVP完整实现方案.md》和产品原型 `all-in-one.html`
> 技术栈：FastAPI (后端) + React/Vite/TypeScript/Ant Design (前端)
> 部署类型：flask-react（dclaw.yaml）

---

## 项目总览

将四个已有能力（会议 TODO 提取、迭代数据统计、AI 编程数据报告、无矩 2.0 知识库问答）统一封装为 Web 界面。

**核心架构调整**：方案原文使用 FastAPI 后端，但 dclaw.yaml 定义为 `flask-react` 类型（Flask + Gunicorn + Nginx）。因此后端统一使用 **Flask**，用 Flask-SSE 或生成器实现流式响应，替代 FastAPI 的 `StreamingResponse`。

---

## Phase 0：项目骨架搭建

### 目标
搭建前后端脚手架，打通开发环境联调。

### 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app.py` | 修改 | Flask 入口，CORS 中间件，注册 blueprint |
| `backend/requirements.txt` | 修改 | Flask + 依赖 |
| `backend/routers/__init__.py` | 新建 | |
| `backend/routers/meeting_todo.py` | 新建 | Blueprint |
| `backend/routers/iteration_stats.py` | 新建 | Blueprint |
| `backend/routers/ai_measure.py` | 新建 | Blueprint |
| `backend/routers/chat.py` | 新建 | Blueprint |
| `backend/services/__init__.py` | 新建 | |
| `backend/services/feishu_client.py` | 新建 | lark-cli 封装 |
| `backend/services/llm_client.py` | 新建 | LLM 调用封装 |
| `backend/services/sse_helpers.py` | 新建 | Flask SSE 流式辅助函数 |
| `frontend/src/main.tsx` | 修改 | 挂载 BrowserRouter with basename |
| `frontend/src/App.tsx` | 修改 | Routes 定义 |
| `frontend/src/pages/` | 新建 | 四个页面空壳 |
| `frontend/src/components/AppLayout.tsx` | 新建 | 侧边栏布局 |
| `frontend/src/api/client.ts` | 新建 | Axios 实例 |
| `frontend/src/utils/sse.ts` | 新建 | SSE 流式请求 |
| `frontend/src/utils/apiBase.ts` | 新建 | API_BASE = `${BASE_URL}/api` |

### 关键细节

1. **`main.tsx`** 中 `<BrowserRouter basename={import.meta.env.BASE_URL}>`
2. **`App.tsx`** 只写 `<Routes>`，不包 BrowserRouter
3. **所有 fetch/axios 调用**使用 `API_BASE` 而非硬编码 `/api`
4. **Vite proxy** 配置 `/api` → `http://localhost:5000`（Flask 端口）
5. 侧边栏使用 Ant Design `Menu` + `Layout.Sider`
6. 四个路由：`/meeting-todo`, `/iteration-stats`, `/ai-measure`, `/chat`
7. 侧边栏增加 4 个 disabled 项：需求理解 Agent、知识库管理、PRD/原型生成、周报自动生成（灰色 + ComingSoon）

---

## Phase 1：公共基础设施

### 1.1 后端基础设施

#### `backend/services/sse_helpers.py`
Flask 不支持 `StreamingResponse`，改用生成器 + `Response`：

```python
from flask import Response
import json

def sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

def sse_stream(generator_fn):
    """Flask SSE Response 封装"""
    return Response(generator_fn(), mimetype='text/event-stream')
```

#### `backend/services/feishu_client.py`
封装 lark-cli 调用（subprocess）：
- `run_lark_cli(args)` → 通用执行器
- `create_doc(title, content_md)` → 创建飞书文档
- `get_minute_info(minute_token)` → 妙记基础信息
- `get_vc_notes(minute_token)` → 妙记纪要产物
- `fetch_doc_markdown(doc_token)` → 文档 Markdown 内容
- `search_minutes(keyword, start_time)` → 搜索妙记
- `upsert_bitable_record(base_token, table_id, record_id, data)` → 多维表格写入

#### `backend/services/llm_client.py`
OpenAI 兼容接口封装：
- `chat(system, user, temperature)` → 返回文本
- 环境变量：`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`

#### `backend/models.py`
数据模型（Flask 用 dataclass / dict，或 pydantic）：
- `MeetingTodoExtractRequest`
- `MeetingDocGenerateRequest`
- `IterStatsUploadRequest`（multipart form）
- `IterStatsCrawlRequest`
- `ReportGenerateRequest`
- `ReportWriteRequest`
- `ChatRequest`

### 1.2 前端基础设施

#### `frontend/src/utils/apiBase.ts`
```ts
export const API_BASE = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/api`
```

#### `frontend/src/api/client.ts`
Axios 实例，baseURL 使用 `API_BASE`。

#### `frontend/src/utils/sse.ts`
原生 `fetch` + `ReadableStream` 解析 SSE 事件。

#### `frontend/src/components/AppLayout.tsx`
- 侧边栏宽度 260px，包含：
  - Logo + 标题（"AI 中控台"）
  - 导航菜单（4 个功能项 + 1 个分割线 + 4 个预留项 disabled）
  - 底部 "即将上线" 标签
- 内容区通过 `Outlet`（react-router）渲染页面
- 响应原型 HTML 中的设计风格（紫色主色调 #6366f1）

---

## Phase 2：模块一 — 会议 TODO 提取

### 2.1 后端 API

#### `backend/services/meeting_todo_service.py`
核心业务逻辑：
1. 从妙记链接提取 `minute_token`
2. 调用 `get_minute_info(minute_token)` 获取妙记信息（含 `create_time` 时间戳）
3. 调用 `get_transcript(minute_token)` 获取逐字稿内容（text/plain）
4. 清洗逐字稿控制字符后调用 LLM 分析待办
5. LLM 注入以下上下文：
   - **会议日期**：通过 `format_meeting_date_context(ts_ms)` 生成 `{年/月/日/星期}` 上下文，用于 DDL 推理
   - **说话人列表**：自动提取 `姓名(英文名)` 格式的所有说话人完整姓名，指导 LLM 纠正简称
   - **跟进人规则**：场景判断矩阵（主动认领→说话人、协作双方均提取→说话人+被提及人、移交→仅被提及人）
   - **描述清洗规则**：提取跟进人后从描述中移除"找/与/和/给+人名"结构
6. 后端兜底：`_clean_description()` 在 `_parse_llm_response` 中自动清洗，支持简称→全称模糊匹配
7. JSON 解析容错：5 层递进解析（标准→宽松→尾随逗号→部分解析→截断），`temperature=0.0`, `max_tokens=8192`, 最多 3 次重试
8. 跟进人 open_id 匹配：在 `generate_meeting_doc()` 中拆分"、"分隔的多人，逐个调用 `match_assignee_open_id()` 搜索

#### `backend/routers/meeting_todo.py`

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/meeting-todo/extract` | POST（SSE） | 妙记链接 → 流式返回逐字稿 + 待办 |
| `/api/meeting-todo/generate` | POST | 确认后的待办 → 创建飞书文档（`<ol>`+`<cite>` XML 模板） |
| `/api/meeting-todo/search` | POST | 关键词搜索妙记 |

**SSE 事件流**：
```
event: progress  → {step: "getting_info", message: "正在获取妙记信息..."}
event: progress  → {step: "extracting_transcript", message: "正在提取逐字稿..."}
event: section_complete → {transcript_ready → meeting_info + content}
event: progress  → {step: "analyzing", message: "AI 正在分析待办..."}
event: complete  → {module_groups: [...]}
```

### 2.2 前端页面

#### `frontend/src/pages/MeetingTodo.tsx`
- **输入区**：Input（妙记链接）+ Button（提取）+ Steps 进度条
- **分屏区**：左右 50% 分屏，提取完成后展示
  - 左屏：`TranscriptPanel` — 可滚动的逐字稿
  - 右屏：`TodoPanel` — 按模块分组的待办列表（支持编辑/删除/新增）
- **文档生成提示卡**：成功文档链接显示在输入区和分屏之间（绿色卡片 + `<a>` 直链，彻底避免弹窗拦截）

#### `frontend/src/components/TranscriptPanel.tsx`
- 渲染逐字稿文本（标题 + 时间 + 内容）
- 支持 loading 状态展示

#### `frontend/src/components/TodoPanel.tsx`
- 按模块分组（技术类 / 运营类 / 其他类），每组色码标记
- 每组包含多个 `TodoCard`
- 底部 "+ 添加待办" 按钮 + "生成飞书文档" 按钮
- key 受 `extractKey` 控制，每次新提取强制重新挂载清空编辑缓存

#### `frontend/src/components/TodoCard.tsx`
- 显示待办内容、⚠️ 不确定标记、DDL、跟进人
- 操作按钮：编辑 ✏️、删除 🗑️
- DDL/edit 支持内联编辑

### 2.3 交互流程
1. 用户粘贴妙记链接 → 点击提取
2. SSE 展示 4 步进度
3. 分屏渲染：左=逐字稿，右=待办
4. 用户逐条核对（确认/修改/删除/新增）
5. 点击"生成飞书文档" → POST → 返回文档 URL → 显示在输入区下方绿色卡片中 → 用户点击打开文档

---

## Phase 3：模块二 — 迭代数据统计 ✅ 已完成

### 3.1 实际架构变更（与初始方案不同）

- ❌ 移除了 `iwork_crawler.py`（浏览器爬虫 — Token 消耗大、不稳定、登录态复杂）
- ❌ 移除了 `components/StatsTable.tsx` 和 `components/FileUploader.tsx`（全部集成在 `IterationStats.tsx` 一个页面中）
- ❌ 移除了 `POST /api/iter-stats/crawl` SSE 爬取端点（不采用 Playwright 方案）
- ✅ 新增 `GET /api/stats/projects` — 从飞书多维表格读取项目列表，合并 TL
- ✅ 新增 `POST /api/stats/export` — 导出 xlsx
- ✅ 路由前缀从 `/api/iter-stats/` 改为 `/api/stats/`（与其他 blueprints 一致）
- ✅ 标签列名采用轮询策略（`["自定义标签","自...标签","标签","需求标签"]`），兼容不同版本 xlsx
- ✅ 上传端点预合并飞书标准名称/TL（upload 后自动匹配 bitable 记录，返回 tl 和标准化 project_name）
- ✅ 前端本地 computeSummary（占比计算：aicoding_ratio = aicoding / engineering, sdd_ratio = sdd / aicoding）

### 3.2 后端 API

#### `backend/services/stats_engine.py`
移植自桌面 `iteration-stats` skill 的 `stats_from_xlsx.py` 核心逻辑：
- `calculate_stats(df)` — 解析 DataFrame，统计工程/AIcoding/SDD/端到端计数 + 占比计算
- `parse_project_xlsx(filepath)` — 读取 xlsx 为 DataFrame
- 统计规则：标签匹配（"端到端"/"aicoding"/"sdd"关键词）+ 工程工时列 + 负责人列过滤
- **标签列名轮询**：按优先级遍历 `["自定义标签","自...标签","标签","需求标签"]` 定位标签列，提高跨版本兼容性

#### `backend/routers/iteration_stats.py`

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /api/stats/projects` | GET | 从飞书多维表格读取 12 个项目记录，清洗后返回 `{record_id, project_name, tl}` |
| `POST /api/stats/upload` | POST（multipart） | 上传 xlsx → 解析统计 → 自动合并 bitable 标准名/TL → 返回含 `tl` 和标准化 `project_name` 的 rows |
| `POST /api/stats/write-bitable` | POST | 将统计结果写入飞书多维表格（精确+模糊匹配 vs bitable 项目名） |
| `POST /api/stats/export` | POST | 导出统计结果为 xlsx 文件 |

**关键修复（验收后合并入实现）：**
1. **布局全屏化** — 改为 `height:100vh;overflow:hidden`，上传区单行压缩，结果区独立滚动，统计后自动 scrollIntoView
2. **标签列名轮询** — `stats_engine.py` 从硬编码 `"自...标签"` 改为轮询 `["自定义标签","自...标签","标签","需求标签"]`
3. **upload 端点合并飞书数据** — 新增 `_fetch_bitable_project_map()` + `_match_bitable_project()`，上传后自动合并 TL 和标准名称
4. **TL清洗正则** — `[@?(姓名(?:\(英文名\))?)]\(https?://` 提取纯姓名
5. **前端占比修正** — 前端 `computeSummary` 中 aicoding_ratio 分母=engineering, sdd_ratio 分母=aicoding
6. **上传区多文件撑高修复** — Dragger 设置 `showUploadList={false}` 固定 48px 高度，文件名改用紧凑 `<Tag closable>` 行展示
7. **导出 xlsx 500 修复** — 循环变量从 `data["project_stats"]` 改为局部变量 `project_stats`（兼容前端传 `rows`）；ratio 字段类型判断（字符串直接使用，数值再格式化）
8. **飞书写入 undefined 修复** — 后端返回字段 `"updated"` → `"updated_count"`，与前端 TypeScript 接口对齐
9. **写入后跳转链接** — Alert 新增 "🔗 打开飞书多维表格查看" 超链接
10. **TL 列 @ 前缀清除** — bitable TL 字段为 mention 格式 list，拼接 text 时 `.lstrip("@")`
11. **合计行导出** — 新增 `computeRawSummary()` 函数，handleWriteBitable 和 handleExport 均追加合计行
12. **项目名称正则加后缀匹配** — `_PROJECT_VERSION_RE` 增加分支 `|\s*\d+\.\d+版本?[（(]?\d*[）)]?\s*$` 以匹配末尾版本号（如 `DPP双周迭代 5.93版本（0529）`）
13. **TL 多人提取** — `re.search()` → `re.findall()` + `",".join()`，两处 TL 清洗同步修复
14. **`_fmt_ratio` 统一函数** — 从 `create_bitable_record` 的本地嵌套函数提升为模块级函数，`update_bitable_record` 共用，避免第三次 ratio 格式化抛异常
15. **全面改用硬编码 PROJECT_MAP** — 废弃所有正则解析（`_extract_project_name`、`_PROJECT_VERSION_RE`、`re.search/findall`），12 个项目名+TL 硬编码为 `PROJECT_MAP`。新增 `_find_project_by_bitable_name()` 子串反向匹配，`_fetch_bitable_project_map` 和 write-bitable 都基于此映射

### 3.3 前端页面

#### `frontend/src/pages/IterationStats.tsx`
（重写，不再使用简单的上传/爬取切换，功能合并在一个页面中）
- **上传区**：单行紧凑布局（版本号 Input + 紧凑型 Upload 拖拽 + 紫色"开始统计"按钮并排）
- **汇总统计**：6 个 `Statistic` 卡片（项目数/总需求/工程/AIcoding占比/SDD占比/端到端）
- **结果表格**：Ant Design `Table`，列结构与飞书 wiki 一致
  - 项目名称（可点击跳飞书）/ TL / 总需求数 / 算法工程需求 / AIcoding需求数 / AIcoding占比 / SDD需求数 / SDD占比 / 端到端
  - 汇总行（紫色背景 `#f5f3ff`）
  - 数据来源：后端 upload 返回的 rows（已合并 TL 和标准化 project_name）
- **操作按钮**：
  - "写入飞书表格"（`POST /api/stats/write-bitable`）
  - "导出 xlsx"（`POST /api/stats/export`，浏览器下载）
- **自动滚动**：统计完成后 `resultRef.current.scrollIntoView()` 自动滚动到结果区
- **状态管理**：状态包括 `projects`（bitable 项目列表）、`statsResult`（统计结果）、`loading`、`writing`、`writeResult`，重置按钮清除全部

**交互流程**：
1. 页面加载 → 自动 `fetch /api/stats/projects` 获取位图项目列表
2. 用户拖拽 xlsx + 填写版本号 → 点击"开始统计"
3. 后端解析 xlsx 并自动合并飞书项目名/TL → 返回带 `tl` 和标准化 `project_name` 的 rows
4. 前端 `normalizeRows()` 归一化 → `computeSummary()` 本地计算汇总
5. 用户确认 → 点击"写入飞书表格"或"导出 xlsx"
6. 写入完成后 Alert 提示成功/失败/未匹配信息

---

## Phase 4：模块三 — AI 编程数据报告

### 4.1 后端 API（实际实现 vs 初始方案）

**初始方案 vs 实际差异：**
- ❌ **不使用 subprocess 调用脚本**（脚本输出格式化表格非 JSON，直接 HTTP 调用更可靠）
- ✅ **直接 HTTP API 调用**：`AiMeasureClient` 封装 `ep-copilot2` 的 `/v1/ai-tool-measure/drilldown` API
- ✅ **直接 HTTP API 调用**：`SkillsQueryClient` 封装 `skills.dewu-inc.com/v1/skills` API
- ✅ **新增 `test-token` 端点**（方案中无独立验证）
- ✅ **TL 使用情况**：复用 `AiMeasureClient.query_drilldown()` 查全部，再用 TL 固定名单（27 人）过滤
- ✅ **Skills 按贡献人聚合**：同一个人有多条 skill 用 " / " 连接展示
- ✅ **SSE 事件新增 `section_error`**：单模块失败时独立标记，不影响其他模块
- ✅ **`sse_helpers.py` 使用 `stream_with_context`**：确保 werkzeug 实时推送，不缓冲到 generator 结束
- ✅ **`ai_measure_client.py` 硬墙钟超时 + 自动重试**：`concurrent.futures.ThreadPoolExecutor` 120s 超时（requests timeout 只控制字节间隔），2 次退避重试
- ✅ **`sse.ts` 按 `\n\n` 事件分隔符切分**：避免 TCP chunk 截断导致 `data:` JSON 被静默丢弃
- ✅ **`AiMeasure.tsx` 用 `completedRef` 防 React batch 覆盖**：避免 `onComplete` 将 `finish` 误标为 `error`

#### `backend/services/ai_measure_client.py`
封装 EP 的 drilldown API（直接 HTTP 调用）：
- `test_connection(token)` → 测试 Token 有效性
- `query_drilldown(token, start_date, end_date, names=None)` → 调用 drilldown API，可选按成员过滤
- `query_active_rate(token, start_date, end_date, names)` → 计算试点人员活跃率
- `query_inactive(token, start_date, end_date, names)` → 不活跃人员查询（drilldown + 0 提交过滤）

#### `backend/services/skills_query_client.py`
封装 skills API（直接 HTTP 调用）：
- `test_connection(token)` → 测试 Token 连通性
- `query_skills(token, start_date, end_date, names)` → 按贡献人查询 + 聚合多条 skill

#### `backend/services/report_generator.py`
报告编排器：
- 串行执行 4 个查询模块（active_rate / inactive / skills / tl_usage）
- 每个模块完成后 SSE 推送 `section_complete` 事件（含 `markdown`, `row_count`）
- 模块出错推送 `section_error`（不影响后续模块）
- TL 固定名单硬编码（27 人）：`"叶程,徐行,乐天,无际,陳飞,清山,王屹,费曼,馬彦,芋头,弹剑,高飞,维特,允中,罗斯,祝余,张辽,虚空,天央,啊俊,岱锋,樊少,三白,艾力欧,幽柏,溜溜球"`
- 报告 Markdown 表头对齐（`| --- | ---:` 等）

#### `backend/routers/ai_measure.py`

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/ai-measure/test-token` | POST | 测试 Token 连通性（需 access_token 参数） |
| `/api/ai-measure/generate` | POST（SSE） | 配置参数（access_token, pilot_names, start_date, end_date, sections）→ 流式生成报告 |
| `/api/ai-measure/write-to-feishu` | POST | 将报告内容写入飞书文档（Markdown→XML 简化转换） |

**SSE 事件流**：
```
event: progress  → {section, message}
event: section_complete → {section, title, row_count, markdown, status: "complete"}
event: section_error → {section, message, status: "error"}
event: complete  → {report_markdown, sections_completed, total_sections}
```

### 4.2 前端页面（实际实现）

#### `frontend/src/pages/AiMeasure.tsx`
- **配置区**（4 格 2×2 Grid 布局）：
  - Token 输入框（Password）+ "测试连接"按钮（3 态：untested/testing/valid/invalid），测试结果用 Tag 展示
  - 试点名单输入 + "使用 TL 默认名单"一键填充（27 人逗号分隔）
  - 时间范围（RangePicker，默认近 14 天）
  - 报告模块勾选（4 个 Checkbox，每个带彩色 Tag）：活跃率 / 不活跃人员 / Skills / TL 使用
- **进度区**：Ant Design Steps 竖向排列，5 个 step（wait / process / finish / error），显示状态图标 + 描述文字
- **报告预览区**：Markdown 渲染（react-markdown），顶部显示 `completedSections / totalSections`，底部操作按钮
- **操作按钮**：
  - "复制 Markdown" → clipboard API
  - "写入飞书文档" → POST write-to-feishu → Alert 显示文档超链接
- **状态管理**：用 `useState` + `useCallback`，SSE 事件依次更新对应的 step 状态

#### `frontend/src/components/ReportPreview.tsx`
（已创建但功能集成到 AiMeasure.tsx 页面中，当前为备用）

#### `frontend/src/api/aiMeasure.ts`
- 类型定义：`TestTokenResult`, `GenerateRequest`, `ProgressEvent`, `SectionCompleteEvent`, `SectionErrorEvent`, `CompleteEvent`, `WriteRequest`, `WriteResult`
- 函数：`testToken()`, `generateReport()`, `writeToFeishu()`
- SSE 使用现有 `streamRequest`（来自 `sse.ts`）
- 回调接口：`onProgress`, `onSectionComplete`, `onSectionError`, `onComplete`, `onError`

### 4.3 交互流程
1. 用户填写 Token → 测试连接（可选，但推荐验证）
2. 填写/选择试点名单、时间范围、报告模块
3. 点击"开始生成"
4. SSE 流式推送：每个模块独立 Progress → complete/error
5. 进度 Steps 实时更新（process → finish/error）
6. 报告预览逐模块累积展示
7. 用户可 "复制 Markdown" 或 "写入飞书文档"
8. 写入成功后 Alert 显示飞书文档链接

---

## Phase 5：模块四 — 无矩 2.0 知识库问答（实际实现）

### 5.1 实际架构（与初始方案不同）

**实际实现 vs 初始方案差异：**
- ❌ 无 `services/kb_agent.py` — 后端不做 LLM 调用/向量检索，仅作为 HTTP 代理
- ❌ 无 `components/ChatMessage.tsx` — 消息渲染内联在 Chat.tsx 中
- ❌ 无左侧会话列表 — 页面为单屏对话（无会话列表/搜索/分组）
- ✅ `chat.py` 后端仅做 SSE 代理转发到无矩2.0 微服务
- ✅ `/api/chat/conversations` 返回占位空数组
- ✅ 新增 `/api/chat/health` 检查微服务连通性
- ✅ SSE 事件透传（`data:` 原样转发，保持无矩2.0 协议字段不变）
- ✅ `api/chat.ts` 存在但 Chat.tsx 直接用原生 fetch（非 axios）

### 5.2 后端 API

#### `backend/routers/chat.py`
后端无业务逻辑，纯 SSE 代理：

```python
POST /api/chat/send   # 请求 {"query": "..."} → 透传 SSE 到无矩2.0 :8000
GET  /api/chat/conversations  # 返回 {"conversations": []}（占位）
GET  /api/chat/health  # 检查 :8000 连通性
```

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat/send` | POST | SSE 代理转发到 `localhost:8000/api/query/stream` |
| `/api/chat/conversations` | GET | 占位（返回空数组） |
| `/api/chat/health` | GET | 检查无矩2.0 连通性 |

**SSE 事件流（透传无矩2.0 原始协议）**：
```
data: {"type":"sources","sources":[...]}
data: {"type":"token","content":"..."}
data: {"type":"done"}
data: {"type":"error","content":"..."}
```

**转发实现**：`requests.post(stream=True).iter_lines()` 逐行原样 yield。

### 5.3 前端页面

#### `frontend/src/pages/Chat.tsx`
- **单屏对话**（无左侧会话列表/搜索框）：
  - 空状态：4 张建议问题卡片（架构概览/配置说明/节点配置/算子使用）
  - 消息列表：用户气泡（紫色右对齐）、AI 气泡（白底左对齐）
  - 引用来源：AI 消息下方可折叠 `Collapse`，显示来源文档名+相关性评分
  - SSE 流式渲染：`fetch` + `ReadableStream` 解析 token 逐字追加
  - 加载态：Spin 指示器
  - 错误态：红色 banner + 消息文本标记 ❌

---

## Phase 6：全局打磨与部署

### 6.1 知识库管理模块（实际实现）

#### 后端代理 `backend/routers/kb_manage.py`
10 个端点全部代理到无矩2.0 FastAPI 微服务的 `/api/admin/*`：
- 通用代理函数 `_proxy_get` / `_proxy_post` / `_proxy_delete` / `_proxy_files`
- 三层异常捕获: `ConnectionError` / `Timeout` / `RequestException`

| 前端路径（/api/kb-manage） | 方法 | 代理到（:8000/api/admin） |
|---------------------------|------|--------------------------|
| `/collections` | GET | `/collections` |
| `/browse` | GET | `/{collection}/browse?page=&page_size=&keyword=` |
| `/doc` | GET | `/{collection}/doc/{doc_id}` |
| `/sqlite/tables` | GET | `/sqlite/tables` |
| `/sqlite/table` | GET | `/sqlite/{db_name}/{table_name}` |
| `/import` | POST | `/import` |
| `/import/file` | POST (multipart) | `/import/file` |
| `/delete` | DELETE | `/{collection}/doc/{doc_id}` |
| `/sync` | POST | `/sync?dry_run=&rebuild_core=&rebuild_wiki=` |
| `/sync/status` | GET | `/sync/status/{task_id}` |

#### 前端页面
- `pages/KbManage.tsx` — 4 Tab 布局（概览/浏览/导入/同步）
- 同步 Tab 支持 4 种模式（仅代码/代码+核心KB/代码+Wiki/全量）+ dry-run 预览 + 轮询进度 + 知识库组成说明表

#### 注册
- `app.py` 注册 `kb_manage_bp`，url_prefix `/api/kb-manage`
- `App.tsx` 添加 `/kb-manage` 路由
- `AppLayout.tsx` 侧边栏核心功能添加"知识库管理"

---

## Phase 7：代码变更分析模块

### 7.1 架构总览

**三层漏斗模型：**
- CLI 层（Node.js + ts-morph）：AST 信号提取 + Import Graph 聚类 + Snippet 截取 + 知识快照生成
- 编排器层（Flask Python）：Git 生命周期管理 + subprocess CLI + LLM 归纳
- 前端层（React + Ant Design）：时间段配置 + SSE 进度 + 变更报告展示

**设计文档：** `docs/superpowers/specs/2026-07-01-code-analyzer-design.md` V1.3
**实现计划：** `docs/superpowers/plans/2026-07-01-code-analyzer-plan.md`

### 7.2 Node.js CLI (tools/code-analyzer/)

**目录结构：**
```
tools/code-analyzer/
├── package.json              # ts-morph 依赖
├── tsconfig.json
└── src/
    ├── index.ts              # 入口：arg parse → 编排 → 输出 JSON 文件
    ├── types.ts              # 所有类型定义
    ├── git/parsePatch.ts     # 解析 raw.patch → HunkInfo[]
    ├── signals/
    │   ├── extractor.ts      # 10 类信号总入口
    │   ├── routes.ts         # NEW_ROUTE (Umi config + JSX) + NEW_PAGE
    │   ├── api.ts            # API_CALL
    │   ├── state.ts          # STATE_ACTION
    │   ├── permission.ts     # PERMISSION
    │   ├── hooks.ts          # HOOK_DEF
    │   ├── event.ts          # EVENT_HANDLER
    │   ├── dataModel.ts      # DATA_MODEL
    │   ├── config.ts         # CONFIG_CHANGE
    │   └── style.ts          # STYLE_ONLY + 样式纯净度验证
    ├── graph/
    │   ├── importGraph.ts    # Import Graph 构建
    │   └── cluster.ts        # 连通分量聚类 + 目录聚类兜底
    ├── classify/
    │   └── decisionTree.ts   # 优先级覆盖决策树 (P0→P4)
    ├── snippet/
    │   └── extractSnippet.ts # 双版本 Snippet + doc context
    └── knowledge/
        └── snapshot.ts       # 项目知识快照生成
```

**CLI 接口：**
```bash
# 分析模式
node dist/index.js --base BASE --target TARGET --frontend-paths "..." --diff-dir D --output result.json --mode analyze

# 快照模式
node dist/index.js --target TARGET --frontend-paths "..." --output snapshot.json --mode snapshot
```

### 7.3 10 类 AST 信号

| 信号 | 优先级 | 匹配逻辑 |
|------|--------|---------|
| NEW_ROUTE | P0 | Umi 配置式路由 `config/config.ts` `routes` 数组 + JSX `<Route>` |
| NEW_PAGE | P0 | 新增文件在 `pages/` 目录 + export default 组件 |
| API_CALL | P1 | `api.*`、`fetch`、`axios`、`useRequest` |
| STATE_ACTION | P1 | `setXxx`、`dispatch`、`commit`、`useState`、`defineStore` |
| PERMISSION | P1 | 条件表达式中出现 `role`、`permission`、`auth`、`isAdmin` |
| HOOK_DEF | P1 | 函数名以 `use` 开头，体内调用其他 Hook |
| EVENT_HANDLER | P2 | JSX 属性 `onClick`、`onSubmit`、`onChange` 等 |
| DATA_MODEL | P2 | `interface`、`type`、`enum` 新增或修改 |
| CONFIG_CHANGE | P2 | `.env*`、`config/*`、`.umirc.*` 等配置文件变更 |
| STYLE_ONLY | P3 | 纯样式文件或样式纯净度验证通过 |

### 7.4 Flask 编排器

**文件：** `backend/services/code_analyze_service.py` + `backend/routers/code_analyze.py`

**8 步流程：**
1. Git fetch（bare repo 增量更新，首次 clone 600s 超时）
2. 定位 commits（`refs/heads/${branch}` 显式引用）
3. 收集 commit messages（`git log --format="%s" base..target -- paths`）
4. 双版本 worktree 检出
5. 知识快照生成（自动过期 3 天）
6. 生成 diff（含 noise 过滤：JSON/`.map`/`.min.js`/`__snapshots__` 等）
7. AST 分析（subprocess Node.js CLI，文件传递输出，180s 超时）
8. LLM 语义归纳（`LLMClient.chat`，失效时降级规则层）

**API 端点：**
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/code-analyze/start` | SSE 流式分析 |
| GET | `/api/code-analyze/status/<task_id>` | 轮询状态 |
| POST | `/api/code-analyze/refresh-snapshot` | 刷新知识快照 |
| GET | `/api/code-analyze/snapshot` | 获取快照信息 |

### 7.5 前端页面

**文件：** `frontend/src/pages/CodeAnalyze.tsx` + `frontend/src/api/codeAnalyze.ts`

- 配置区：仓库信息 + 时间段选择器 + 分析路径勾选 (ml-main/ml-data/_share)
- 8 步 Steps 进度条（同 AiMeasure 模式，`completedRef` 防 React batch 覆盖）
- 结果区：统计卡片 + 新增/修改/下线/UI 分类报告
- 知识快照刷新按钮 + 状态展示

### 7.6 项目知识快照

纯静态 AST 扫描，零 LLM 调用。扫描目标仓库目录结构生成：
- 路由表（从 `config/config.ts`/`config/routes.ts`/`.umirc.ts` 提取，支持模板变量解析）
- 业务模块（`src/pages/` 目录映射）
- API 模块（`src/service/` 目录）
- 共享组件（`src/components/` + `_share/` 递归扫描）

### 7.7 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Language | Node.js CLI (ts-morph) | AST 精度最高，与 Flask 解耦 |
| 输出方式 | `--output` 文件传递 | 避免 stdout pipe buffer 阻塞 |
| 聚类 | Import Graph 连通分量 + 目录兜底 | 无 import 关系时降级 |
| page-logic 去重 | 结果层去重非 diff 排除 | 防止自动同步逻辑不可见 |
| @@/ 别名 | resolveAlias 返回 null，跳过 import 边 | `src/.umi/` 自动生成目录排除 |
| SSE 断线 | status API polling + 指数退避重连 | 适应 5 分钟+长任务 |
| 快照过期 | 3 天自动过期 | 避免 LLM 使用过时模块映射 |

### 7.8 生产调试修复（2026-07-02）

| 问题 | 修复 | 
|------|------|
| API 路径 404 | 去除重复的 `/api` 前缀 |
| `for g in` 变量覆盖 Flask `g` | 改 `for fg in` |
| `yield from` 非生成器 | 非 SSE 函数去掉 yield |
| LLM 格式不统一（5 种） | 归一化层：遍历 value 找 list-of-dicts |
| LLM 裸数组 | 支持 `isinstance(list)` |
| `conf` 变量残留 | `float(matched_conf)` |
| `category`→`name` 映射 | elif 分支补自动映射 |
| 飞书导出空白文档 | XML 加 `<title>` 标签 |
| Steps 卡转圈 | `completedRef.add('llm')` |
| Summary 统计重复 | 三者取自不同来源 |

### 7.9 新增导出端点

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/code-analyze/export/markdown` | 下载 `.md` 文件 |
| POST | `/api/code-analyze/export/feishu` | 创建飞书文档 |

## 开发排期（实际完成）

| 天 | 任务 | 产出 |
|----|------|------|
| Day 1 | Phase 0：项目骨架搭建 + 前后端联调 | 骨架完成 |
| Day 1 | Phase 1：公共基础设施（SSE/飞书客户端/LLM/LLMConfig/全局主题） | 基础设施就绪 |
| Day 1-2 | Phase 2：会议 TODO 提取（妙记提取 + LLM 分析 + 分屏前端 + 文档生成） | TODO 模块完成 |
| Day 2 | Phase 2 缺陷修复（DDL 推理/跟进人匹配/文档格式/Prompt 三轮迭代/容错加固） | TODO 稳定可用 |
| Day 3 | Phase 3：迭代数据统计（xlsx 上传 + 统计引擎 + bitable 写入 + 导出）| Phase 3 完成 ✅ |
| Day 3 | Phase 4：AI 编程数据报告（后端直接 HTTP 调用 + SSE + 前端完整页面） | Phase 4 🚧 代码完成（待端到端验证） |
| 待排 | Phase 5：知识库问答（Chat UI + Agent） | — |
| 待排 | Phase 6：全局打磨 + README + 部署准备 | — |

---

## 技术注意事项

### 1. 后端框架适配
方案原文用 FastAPI，但项目脚手架是 `flask-react` 类型，需调整：
- `StreamingResponse` → Flask `Response(generator, mimetype='text/event-stream')`
- Pydantic model → 手动 `request.get_json()` 或引入 pydantic
- Blueprint 替代 FastAPI Router

### 2. React 路由规范
- `BrowserRouter` 必须在 `main.tsx`，带 `basename={import.meta.env.BASE_URL}`
- 页面跳转用 `useNavigate`，禁止 `window.location.href`
- 所有 API 路径用 `API_BASE`，禁止硬编码 `/api`

### 3. 外部依赖处理
以下脚本/工具需在本地环境存在：
- `lark-cli`（飞书操作）— 通过 subprocess 调用
- `stats_from_xlsx.py`（迭代统计）— 需拷贝到 backend/services/
- `ai_measure.py` / `dept_stats.py` / `skills_query.py` / `inactive_members.py` — 需拷贝到 backend/services/ai_measure_scripts/
- Playwright chromium — 需 `playwright install chromium`

### 4. MVP 简化策略
- **知识库问答**：MVP 阶段可先用纯 LLM 回答（无向量检索），后续再接知识库
- **iwork 爬取**：若 Playwright 环境受限，可先只提供手动上传模式
- **LLM 调用**：使用环境变量配置，兼容 OpenAI 或内部 LLM

### 5. 安全
- Token / Cookie 等凭证不存入代码，通过前端输入或环境变量传递
- 所有外部调用（lark-cli、LLM）做好超时和异常处理

---

## 文件清单（完整）

### 后端
```
backend/
├── app.py                          # Flask 入口
├── requirements.txt                # 依赖
├── models.py                       # 数据模型
├── routers/
│   ├── __init__.py
│   ├── meeting_todo.py             # /api/meeting-todo/*
│   ├── iteration_stats.py          # /api/iter-stats/*
│   ├── ai_measure.py               # /api/ai-measure/*
│   └── chat.py                     # /api/chat/*
├── services/
│   ├── __init__.py
│   ├── feishu_client.py            # lark-cli 封装
│   ├── llm_client.py               # LLM 调用
│   ├── sse_helpers.py              # SSE 辅助
│   ├── meeting_todo_service.py     # 会议 TODO 核心逻辑
│   ├── stats_engine.py             # 迭代统计引擎
│   ├── iwork_crawler.py            # iwork 爬虫
│   ├── ai_measure_client.py        # AI 编程数据查询
│   ├── skills_query_client.py      # Skills 查询
│   ├── report_generator.py         # 报告生成器
│   ├── kb_agent.py                 # 知识库问答 Agent
│   └── ai_measure_scripts/         # 现有脚本拷贝
│       ├── ai_measure.py
│       ├── dept_stats.py
│       ├── skills_query.py
│       └── inactive_members.py
```

### 前端
```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.tsx                    # 入口 + BrowserRouter
    ├── App.tsx                     # Routes
    ├── pages/
    │   ├── MeetingTodo.tsx         # 会议 TODO
    │   ├── IterationStats.tsx      # 迭代统计
    │   ├── AiMeasure.tsx           # 数据报告
    │   └── Chat.tsx                # 知识库问答
    ├── components/
    │   ├── AppLayout.tsx           # 侧边栏布局
    │   ├── TranscriptPanel.tsx     # 逐字稿面板
    │   ├── TodoPanel.tsx           # 待办纪要面板
    │   ├── TodoCard.tsx            # 待办卡片
    │   ├── StatsTable.tsx          # 统计表格
    │   ├── FileUploader.tsx        # 文件上传
    │   ├── ReportPreview.tsx       # 报告预览
    │   ├── ChatMessage.tsx         # 聊天消息
    │   ├── ProgressSteps.tsx       # 进度步骤
    │   └── ComingSoon.tsx          # 即将上线占位
    ├── api/
    │   ├── client.ts               # Axios 实例
    │   ├── meetingTodo.ts          # 会议 TODO API
    │   ├── iterationStats.ts       # 迭代统计 API
    │   ├── aiMeasure.ts            # 数据报告 API
    │   └── chat.ts                 # 问答 API
    └── utils/
        ├── sse.ts                  # SSE 流式请求
        └── apiBase.ts              # API_BASE 常量
```

---

## 实际实现差异（截至 2026-07-03）

### 代码变更分析模块 — 主要架构变更

| 原始方案 | 实际实现 | 原因 |
|---------|---------|------|
| LLM 一次性批量归纳所有 Feature Groups | **逐组调用 LLM**，每组单独生成 description | LLM 批量归纳不稳定（61 组输出 27-92 项不等），无法保证数量对齐 |
| LLM 自行决定分类（新增/修改/UI） | **AST 决策树**决定分类，LLM 只做语义描述 | LLM 分类不可靠，AST 决策树确定可复现 |
| LLM 自评 confidence | **AST 客观计算**confidence（信号覆盖度） | LLM 自评分数不可靠 |
| `temperature=0` 保证确定性 | **temperature=0 + seed=42** | 分布式 GPU 浮点非确定性，seed 进一步约束 |

### 新增功能

- **多仓库支持**：仓库 URL/分支/路径可编辑，SQLite 缓存配置
- **Git 令牌管理**：全局配置弹窗 Git Token 区域
- **commit_cache**：相同时间范围复用相同 commit hash，保证结果一致
- **调试持久化**：`_preserve_debug_files` 保存 AST result.json 到 `/tmp/analyze_debug/`

### 架构变更

| 原始方案 | 实际实现 | 原因 |
|---------|---------|------|
| 信号提取器全用正则 | **正则提取 + astValidator.ts AST 验证**双层分离 | 正则召回率高但假阳性多，AST 精确率高但复杂；两层各司其职 |
| LLM 输出仅 {category, description} | **LLM 输出 {category, description, type}**，可修正 AST 分类 | LLM 比代码更懂业务意图（如 CSS 隐藏本质是权限控制） |
| ts-morph 轻量模式 | 不变，保持 skipFileDependencyResolution=true | 无需 TypeChecker，节省 2-5 分钟加载时间 |
