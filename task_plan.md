# AI 中控台 — Task Plan

> 目标：基于《AI中控台-MVP完整实现方案.md》和产品原型，搭建 AI 项目管理中控台 Web 应用
> 技术栈：Flask (后端) + React/Vite/TypeScript/Ant Design (前端)
> 部署类型：flask-react（dclaw.yaml）

## Project Status

- **Status:** in_progress
- **Current Phase:** Phase 4 🚧
- **Started:** 2026-06-23
- **End time:** —
- **Implementation Plan:** `IMPLEMENTATION_PLAN.md`
- **Reference:** `方案文档` → `/Users/admin/.dewuclaw/workspaces/default/media/3aadf25f72ea41a0ac1a561a5cc2af77_AI中控台-MVP完整实现方案.md`
- **产品原型:** `/Users/admin/.dewuclaw/workspaces/default/media/3939f65cbdcd4975a99d27e9da57801b_all-in-one.html`

## 关键约束（不得违反）

1. **后端必须用 Flask**（不是 FastAPI），dclaw.yaml 类型为 flask-react
2. **`BrowserRouter` 必须在 `main.tsx`**，带 `basename={import.meta.env.BASE_URL}`
3. **所有 API 路径用 `API_BASE`**，禁止硬编码 `/api`
4. **页面跳转用 `useNavigate`**，禁止 `window.location.href`
5. 外部脚本需拷贝到 backend/services/ai_measure_scripts/

---

## Phases

### Phase 0: 项目骨架搭建
- **Status:** done ✅
- **目标:** 搭建前后端脚手架，打通开发环境联调
- **Tasks:**
  - [x] 搭建 Flask 后端骨架（app.py + CORS + Blueprint 注册）
  - [x] 配置 requirements.txt + pip install
  - [x] 搭建 React 前端骨架（main.tsx + App.tsx + 路由）
  - [x] 实现 AppLayout 侧边栏组件
  - [x] 创建四个空页面（MeetingTodo / IterationStats / AiMeasure / Chat）
  - [x] 创建 ComingSoon 组件
  - [x] 配置 Axios 实例 + SSE 封装 + API_BASE
  - [x] 配置 Vite proxy → Flask
  - [x] 跑通 /api/health 联调（后端 5 个接口全部 200/501 正常）
  - [x] 前端 TypeScript 编译通过 + Vite build 成功

### Phase 1: 公共基础设施
- **Status:** done ✅
- **目标:** 封装公共服务模块 + 全局 Token 管理
- **Tasks:**
  - [x] services/sse_helpers.py — Flask SSE 流式辅助
  - [x] services/feishu_client.py — lark-cli 封装（妙记/文档/多维表格）
  - [x] services/llm_client.py — LLM 调用封装（从请求头取 Token）
  - [x] models.py — 数据模型定义（dataclass）
  - [x] 全局 Token 管理机制（前端 localStorage + 后端 auth middleware + axios interceptor 自动注入）
  - [x] 前端全局 Token 提示弹窗（首次访问自动弹出 + 侧边栏底部状态指示）
  - [x] 后端 /api/auth/verify + /api/auth/presets 接口
  - [x] main.tsx 挂载 TokenProvider + ConfigProvider（antd 主题）
  - [x] TokenProvider 重构为 LLMConfigProvider（API Key + Base URL + Model 三件套）
  - [x] Provider 预设（OpenAI/DeepSeek/通义千问/硅基流动）
  - [x] 侧边栏指示器改为显示 LLM Provider 名称和状态
  - [x] 删除旧 TokenProvider.tsx
  - [x] 验证：TypeScript 编译通过 + 前端构建成功 + 后端接口正常

### Phase 2: 模块一 — 会议 TODO 提取
- **Status:** done ✅
- **End time:** 2026-06-24 02:30
- **目标:** 妙记链接 → 逐字稿 + AI 待办分屏 → 飞书文档生成
- **已完成的架构变迁：**
  - 方案 A（lark-cli subprocess）→ 方案 B（Device Code Flow 直调 REST API）→ **回退方案 A**（Device Code Flow 被证伪：需要 app_secret，且正确端点与文档描述完全不同）
  - 最终架构：纯 `lark-cli api` subprocess 方案，自动管理 token/keychain
- **完成项：**
  - [x] services/meeting_todo_service.py — 核心业务逻辑
  - [x] services/feishu_client.py — lark-cli subprocess 封装（get_minute_info/get_transcript/search_minutes/create_doc_xml/search_user_by_name）
  - [x] routers/meeting_todo.py — 3 个 API 端点（extract SSE / generate / search / preview）
  - [x] pages/MeetingTodo.tsx — 输入区 + 分屏布局 + SSE 流式全流程
  - [x] components/TranscriptPanel.tsx — 逐字稿面板
  - [x] components/TodoPanel.tsx — 待办面板（含编辑/删除/新增 — Phase 4 人工校验）
  - [x] components/TodoCard.tsx — 待办卡片
  - [x] utils/sse.ts — 自动注入 LLM 请求头
  - [x] **端到端测试通过**（长妙记 7模块10条待办 ✅ / 短妙记 3模块14条待办 ✅ / 文档生成成功 ✅）
- **缺陷修复（2026-06-23 第11次会话）：**
  - [x] **DDL 提取修正** — 新增 `format_meeting_date_context()` 从时间戳推算会议日期注入 Prompt；Prompt 改为要求输出具体日期
  - [x] **跟进人匹配** — 新增 `match_assignee_open_id()` 调用 `lark-cli contact +search-user`；`generate_meeting_doc()` 中自动匹配
  - [x] **文档模板重写** — `_build_doc_xml()` 使用 `<ol>` + `<cite>` 格式（符合 skill document-template.xml）
  - [x] **前端 MeetingInfo 接口** — 增加 `create_time_ms` 字段
  - [x] 修复"妙计"错别字为"妙记"
  - [x] 修复 `/preview` 路由使用 `get_transcript` 替代废弃 `get_vc_notes`
  - [x] 新增 `_xml_escape()` 防止 XML 注入
- **缺陷修复（2026-06-24 第12-13次会话 最终轮）：**
  - [x] **跟进人规则判据重写** — 判断矩阵（主动认领→说话人、找/与/和协作→双方均提取、移交→仅被提及者）
  - [x] **描述清洗场景化** — 找人型/协作型/移交型三类输入→输出对照
  - [x] **`_clean_description()` 后端兜底清洗** — 支持简称→全称模糊匹配
  - [x] **docUrl 卡片上移** — 从页面底端移到输入区与分屏之间，始终可见
  - [x] **LLM 非确定性优化** — `temperature=0.0`, `max_tokens=8192`, 重试 3 次
  - [x] **JSON 解析 5 层容错** — 标准→宽松→尾随逗号→部分解析→截断修复
  - [x] **多人跟进人** — assignee 支持"、"分隔，`_build_doc_xml()` 生成多个 `<cite>`

### Phase 3: 模块二 — 迭代数据统计
- **Status:** done ✅
- **End time:** 2026-06-24 17:43
- **目标:** xlsx 上传 → 统计表格 → 多维表格写入 / 导出
- **完成项：**
  - [x] 文档同步自动化机制：tools/doc_sync.sh + AGENTS.md 硬规则 + MEMORY.md 提醒
  - [x] 桌面 iteration-stats skill 摸底：读取全部参考文档（stats_from_xlsx / update_feishu_table / 统计规则 / 字段映射）
  - [x] 分析目标飞书 wiki 页面内嵌表格：读取 12 行数据，确认列格式
  - [x] services/stats_engine.py — 统计引擎（xlsx 解析 → 工程/AIcoding/SDD/端到端计数）
  - [x] services/feishu_client.py 扩展 — get_bitable_records() + batch_update_bitable()
  - [x] routers/iteration_stats.py — 4 个 API 端点（projects/upload/write-bitable/export）
  - [x] pages/IterationStats.tsx — 完整 UI（拖拽上传/统计表格/汇总行/写入飞书/导出/结果提示）
  - [x] api/iterationStats.ts — 前端 API 封装
  - [x] TL 清洗修复：正则处理 [@姓名(英文)](url) 格式
  - [x] 项目名称模糊匹配：精确 + 子串匹配（bitable 带版本后缀 vs 简称）
  - [x] 集成测试通过：projects 12 项 ✅ / write-bitable 3/3 匹配 ✅ / export 200 ✅ / TypeScript 零错误 ✅
- **验收修复（2026-06-24）：**
  - [x] **问题 2 — AIcoding/SDD/端到端全为 0**：标签列名从 `"自...标签"` 改为轮询 `["自定义标签", "自...标签", "标签", "需求标签"]`
  - [x] **问题 3 — 项目名称/TL 未对齐模板**：新增 `_fetch_bitable_project_map()` + `_match_bitable_project()`，在上传后自动匹配飞书标准名称+TL
  - [x] **问题 1 — 统计结果需滚动才能看**：布局改为 `100vh` 全屏 + 压缩上传区为单行 + 结果区 `overflow: auto`
  - [x] `computeSummary` 占比分母修正（与后端一致）：AIcoding占比=AIcoding/工程，SDD占比=SDD/AIcoding
  - [x] **上传区撑高问题** — Dragger 多文件时内部列表撑高、结果区被压缩：`showUploadList={false}` 固定 48px 高度，文件名改用紧凑 Tag 行 + closable
  - [x] Python lint + TypeScript 零错误
  - [x] **导出 xlsx 500 修复** — 变量名 `data["project_stats"]` → `project_stats`；aicoding_ratio 字符串格式化 ValueError 修复
  - [x] **飞书写入消息"undefined"修复** — 后端返回字段 `"updated"` → `"updated_count"`
  - [x] **UX: 写入后跳转链接** — Alert 增加 "🔗 打开飞书多维表格查看" 超链接
  - [x] **TL 列 @ 前缀清除** — tl_raw 拼接 text 时 `.lstrip("@")`
  - [x] **导出 xlsx 缺合计行** — 新增 `computeRawSummary()`，导出和飞书写入均追加合计行
  - [x] **项目名称清洗** — 新增 `_extract_project_name()` 统一函数 + `_PROJECT_VERSION_RE` 正则去除 `5.93（0529）` 版本前缀，替换 3 处代码
  - [x] **合计行自动创建到飞书** — write-bitable 检测 "合计" 未匹配时自动调用 `create_bitable_record()` 创建记录并写入

### Phase 4: 模块三 — AI 编程数据报告
- **Status:** in_progress
- **目标:** 配置参数 → SSE 流式查询 → Markdown 报告 → 飞书文档
- **Tasks:**
  - [x] services/ai_measure_client.py — AI 编程数据查询（直接 HTTP 调用替代 subprocess）
  - [x] services/skills_query_client.py — Skills 查询（HTTP 直接调用）
  - [x] services/report_generator.py — 报告生成器（4 模块编排 + TL 固定名单 27 人）
  - [x] routers/ai_measure.py — API 接口（test-token / generate SSE / write-to-feishu）
  - [x] pages/AiMeasure.tsx — 配置区 + 竖向 Steps 进度 + 报告预览 + 写入飞书
  - [x] components/ReportPreview.tsx — 报告预览（备用，功能已集成到页面中）
  - [x] 前端 API 对接（api/aiMeasure.ts，使用现有 streamRequest 实现 SSE）
- **待验证：** 端到端集成测试（需要有效 EP Token）
  - [x] **Bug 修复：SSE chunk 截断导致 active_rate 丢失** — sse.ts 解析器改为按 `\n\n` 切分 + stream_with_context 实时推送 + completedRef 防 React batch 覆盖 + 硬超时+重试

### Phase 5: 模块四 — 无矩 2.0 知识库问答
- **Status:** done ✅
- **End time:** 2026-06-30
- **目标:** ChatGPT 式对话界面 + SSE 代理到无矩2.0 微服务
- **Tasks:**
  - [x] backend/routers/chat.py — 3 端点（send SSE 代理 / conversations 占位 / health）
  - [x] frontend/src/pages/Chat.tsx — 单页对话 UI（建议卡片 / 消息列表 / 引用来源折叠 / SSE 流式渲染）
  - [x] frontend/src/api/chat.ts — API 封装（未使用，Chat.tsx 直接用 fetch）

### Phase 6: 知识库管理
- **Status:** done ✅
- **End time:** 2026-06-30
- **目标:** 管理无矩2.0 知识库集合、文档导入和代码同步
- **Tasks:**
  - [x] backend/routers/kb_manage.py — 10 个代理端点
  - [x] frontend/src/api/kbManage.ts — API 封装（10 个函数 + 完整类型）
  - [x] frontend/src/pages/KbManage.tsx — 4 Tab 页面（概览/浏览/导入/同步）
  - [x] 侧边栏 + 路由集成
  - [x] 同步 Tab 改造：Radio 模式选择（代码/核心KB/Wiki/全量）+ dry-run 预览 + 轮询进度 + 知识库组成说明
  - [x] TypeScript 零错误 + 后端 /api/kb-manage/collections 返回正常

### Phase 7: 代码变更分析模块
- **Status:** done ✅
- **Start time:** 2026-07-01
- **End time:** 2026-07-02
- **目标:** GitLab 时间段 → AST 信号提取 → LLM 语义归纳 → 业务变更报告
- **设计文档:** `docs/superpowers/specs/2026-07-01-code-analyzer-design.md` V1.3
- **实现计划:** `docs/superpowers/plans/2026-07-01-code-analyzer-plan.md`

#### Phase 1a: CLI 骨架 + 4 核心信号
- [x] Task 1a.1: 脚手架 Node.js CLI 项目
- [x] Task 1a.2: 定义共享类型
- [x] Task 1a.3: CLI 入口（参数解析 + 编排）
- [x] Task 1a.4: Patch 解析器
- [x] Task 1a.5: 4 个核心信号提取器（NEW_ROUTE/NEW_PAGE/API_CALL/STATE_ACTION）
- [x] Task 1a.6: 决策树 + 重命名检测
- [x] Task 1a.7: Snippet 提取
- [x] Task 1a.8: 端到端冒烟测试 ✅

#### Phase 1b: 补齐 6 类信号 + Import Graph + 文档上下文
- [x] Task 1b.1: PERMISSION / HOOK_DEF / EVENT_HANDLER 提取器
- [x] Task 1b.2: DATA_MODEL / CONFIG_CHANGE / STYLE_ONLY 提取器
- [x] Task 1b.3: Import Graph + 连通分量聚类
- [x] Task 1b.4: 文档上下文收集 ✅

#### Phase 2: 项目知识快照
- [x] Task 2.1: Snapshot 生成器 ✅

#### Phase 3: Flask 编排器 + API
- [x] Task 3.1: 编排器服务
- [x] Task 3.2: Flask Blueprint + app 注册 ✅

#### Phase 4: 前端页面
- [x] Task 4.1: API 层
- [x] Task 4.2: 页面组件
- [x] Task 4.3: 路由 + 侧边栏 ✅

#### Phase 5: LLM 集成 + 端到端
- [x] Task 5.1: LLM 输入构建 + Prompt 迭代
- [x] Task 5.2: 端到端验证 ✅

### 生产调试（开发后验证阶段）
- [x] 401 路径修复
- [x] `for g in` 变量覆盖 Flask `g` 修复
- [x] LLM 格式归一化（5 种格式兼容）
- [x] Steps 状态修复（`completedRef.add('llm')`）
- [x] `category`→`name` 映射修复
- [x] `conf` 变量名错误修复
- [x] Summary 统计字段独立化
- [x] Prompt 分类规则优化
- [x] 导出 Markdown + 飞书文档
- [x] 飞书导出空白文档修复（`<title>` 标签必需）

### 优化迭代（2026-07-03 稳定性+准确性修复）
- [x] 非代码文件过滤（JSON/MD/CSV/LOG 扩展名）
- [x] NEW_PAGE 检测加固（仅 .tsx + 深度 ≤ 2）
- [x] page-logic ↔ pages 跨 cluster 合并
- [x] git diff shell=True → 数组参数安全化
- [x] _checkout_worktree 加 returncode 校验
- [x] `_build_rule_based_result` 处理 FEATURE_REMOVAL
- [x] LLM debug 文件用 task_id 区分
- [x] importGraph.ts import 正则从变量名改为路径（`from '...'`）
- [x] section_complete event 字段与 Steps key 对齐（`git_diff`→`diff`）
- [x] `_preserve_debug_files` 持久化 AST result.json
- [x] `temperature=0.0` + `seed=42` LLM 确定性
- [x] 逐组 LLM 调用（AST 决定分类，LLM 只做描述）
- [x] 全局配置 Git Token + 仓库缓存 + commit_cache
- [x] 前端中文日期 + 标签对齐 + 可编辑仓库 URL/分支
- [x] `astValidator.ts` 集中 AST 假阳性过滤（9 种信号类型）
- [x] LLM 逐组输出加 `type` 字段（允许修正 AST 分类）
- [x] index.ts 创建 ts-morph Project + 加载源文件传入 extractor
- [x] 修复 validator 过度过滤（`keep`/`remove`/`replace` 策略 + `GENERIC_CHANGE` 信号）

---

## Errors Encountered

## Errors Encountered

| Error | Phase | Attempt | Resolution |
|-------|-------|---------|------------|
| 项目名称/TL/写入飞书500（3 个平行 bug） | Phase 3 | — | 改用硬编码 PROJECT_MAP 替代正则解析，彻底解决 |

---

## Decisions

| 决策 | 理由 | 日期 |
|------|------|------|
| 后端用 Flask 替代方案中的 FastAPI | dclaw.yaml 已定义为 flask-react 类型，需与部署类型一致 | 2026-06-23 |
| SSE 用 Flask generator 替代 StreamingResponse | Flask 不支持 FastAPI 的 StreamingResponse | 2026-06-23 |
| 数据模型使用 pydantic 或 dataclass | Flask 无自动验证，需手动处理或引入 pydantic | 2026-06-23 |
| Device Code Flow 直调飞书 Open API 替代 lark-cli 子进程 | 实现多用户独立 token 管理；绕过 app_secret 依赖（仅需 app_id）；更可控的 API 调用链路 | 2026-06-23 |
| `create_doc_xml` 保留 lark-cli 子进程 | 飞书 docx API 的 block tree 组装过于复杂，lark-cli 已有封装 | 2026-06-23 |
| 正则提取 + AST 验证两层分离 | 正则负责召回率高，AST 负责精确率高，不混合 | 2026-07-03 |
| LLM 逐组调用可修正 type | LLM 比纯代码更懂业务意图，但有严格约束（仅 STYLE_ONLY↔FEATURE_MODIFY） | 2026-07-03 |
| ts-morph 保持轻量模式 | 无需 TypeChecker，节省 2-5 分钟加载时间，收益有限 | 2026-07-03 |
