# AI 中控台 — 长期记忆 (MEMORY)

> 新会话唤醒此文件后，按以下清单逐项检查，不可跳过。

---

## ⚡ 新会话唤醒清单

1. ✅ **阅读本文件（MEMORY.md）** — 了解 Phase 状态、项目结构、协议
2. ✅ **阅读 `task_plan.md`** — 确认当前 Phase 的 Tasks 进度
3. ✅ **阅读 `progress.md`** — 了解最近的操作记录
4. ✅ **阅读 `findings.md`** — 熟悉已踩过的坑和技术决策
5. ✅ **阅读 `BLOG_RECORD.md`** — 了解需求演变和故事背景
6. ✅ **阅读 `IMPLEMENTATION_PLAN.md`** — 对齐方案和实际实现

---

## 🚦 项目状态

- **Phase 3 — 迭代数据统计** ✅ 已完成
- **Phase 4 — AI 编程数据报告** ✅ 已完成（后端+前端+SSE chunk 截断修复）
- **Phase 5 — 无矩 2.0 知识库问答** ✅ 已完成（SSE 代理对话 + 引用来源展示）
- **Phase 6 — 知识库管理** ✅ 已完成（4 Tab 管理页 + 同步模式选择）
- **Phase 7 — 代码变更分析** ✅ 已完成（Node.js CLI + Flask 编排器 + 前端页面 + LLM 归一化 + 导出功能 + 稳定性修复）
- **最近修改：** 2026-07-06 知识快照注入 LLM Prompt + 废弃 project_context.md

---

## 📁 项目文件索引

| 文件 | 用途 |
|------|------|
| `backend/app.py` | Flask 入口 + CORS + before_request |
| `backend/routers/iteration_stats.py` | 📌 Phase 3 — 迭代统计 4 端点 |
| `backend/routers/meeting_todo.py` | ✅ Phase 2 — 会议 TODO 提取 |
| `backend/services/stats_engine.py` | 📌 统计引擎（xlsx 解析 → AIcoding/SDD/端到端） |
| `backend/services/meeting_todo_service.py` | ✅ 会议 TODO 核心逻辑 |
| `backend/services/feishu_client.py` | lark-cli 封装（文档/妙记/bitable） |
| `backend/services/llm_client.py` | OpenAI 兼容接口封装 |
| `backend/services/sse_helpers.py` | Flask SSE 流式辅助函数 |
| `frontend/src/pages/IterationStats.tsx` | 📌 Phase 3 — 迭代统计页面 |
| `frontend/src/pages/MeetingTodo.tsx` | ✅ Phase 2 — 会议 TODO 页面 |
| `frontend/src/api/iterationStats.ts` | 📌 迭代统计 API 封装 |
| `frontend/src/api/aiMeasure.ts` | 📌 Phase 4 — AI 编程数据报告 API 封装 |
| `frontend/src/components/ReportPreview.tsx` | 📌 Phase 4 — 报告预览组件 |
| `frontend/src/pages/AiMeasure.tsx` | 📌 Phase 4 — AI 编程数据报告页面 |
| `backend/services/ai_measure_client.py` | 📌 Phase 4 — EP API HTTP 客户端 |
| `backend/services/skills_query_client.py` | 📌 Phase 4 — Skills API HTTP 客户端 |
| `backend/services/report_generator.py` | 📌 Phase 4 — 报告编排器 |
| `backend/services/ai_measure_scripts/` | 📌 Phase 4 — ai-measure-query 脚本备份 |
| `backend/routers/chat.py` | ✅ Phase 5 - SSE 代理到无矩2.0 |
| `frontend/src/pages/Chat.tsx` | ✅ Phase 5 - 知识库问答对话页面 |
| `backend/routers/kb_manage.py` | ✅ Phase 6 - 知识库管理代理（10 端点） |
| `frontend/src/pages/KbManage.tsx` | ✅ Phase 6 - 4 Tab 管理页面 |
| `frontend/src/api/kbManage.ts` | ✅ Phase 6 - API 封装 |
| `tools/code-analyzer/` | ✅ Phase 7 - Node.js CLI（AST 信号 + Import Graph + 快照） |
| `backend/services/code_analyze_service.py` | ✅ Phase 7 - Flask 编排器 |
| `backend/routers/code_analyze.py` | ✅ Phase 7 - 4 端点 + 2 导出端点 |
| `frontend/src/pages/CodeAnalyze.tsx` | ✅ Phase 7 - 代码变更分析页面 |
| `frontend/src/api/codeAnalyze.ts` | ✅ Phase 7 - API 封装 |
| `docs/superpowers/specs/2026-07-01-code-analyzer-design.md` | 📌 Phase 7 - 设计文档 V1.3 |
| `docs/superpowers/plans/2026-07-01-code-analyzer-plan.md` | 📌 Phase 7 - 实现计划 |
| `docs/功能变更分析模块介绍.md` | 📌 Phase 7 - 介绍文档（领导层汇报用） |
| `tools/doc_sync.sh` | 📌 文档同步检查脚本 |

---

## 📜 原子级文档更新协议

**一句话规则：**
> progress.md 实时记 → task_plan 任务完成时记 → MEMORY.md Phase 结束时记 → 其他 3 个被动触发但不可跳过。

### 七个更新时机

| 时机 | 更新文档 | 内容 |
|------|----------|------|
| 每一次有意义操作（改代码/修 bug/测试通过） | `progress.md` 追加 | 做了什么 + 改了哪里 + 结果 |
| 每一次 Phase 完成 / 修复完成 / 工具配置变更 | `MEMORY.md` 更新 | Phase 状态、修复方案、工具设置 |
| 每一次 Task 状态变化 / Phase 开始或结束 | `task_plan.md` 更新 | checklist 状态（done/in_progress）、end_time |
| 实际实现与方案描述不一致时 | `IMPLEMENTATION_PLAN.md` 更新 | API 路径、接口名称、交互流程等对齐 |
| 发现技术教训 / 踩坑 / 逆向直觉的 bug | `findings.md` 追加 | 背景 + 根因 + 修复 + 教训 |
| 有值得记录的故事性事件 | `BLOG_RECORD.md` 追加 | 需求来源 + 做法 + 反思 |
| 声称任务完成 / 声明进入下一阶段前 | `bash tools/doc_sync.sh` 强制检查 | 全部 6 个文档必须与代码同步 |

---

## 🛠 工具设置

- **LARKSUITE_CLI_CONFIG_DIR:** `/Users/admin/.dewuclaw/lark-cli-config/cli_aa847daba1bc1bb3`
- **Flask 子进程手动注入:** `feishu_client.py` 中 `_lark_env()` 函数
- **已授权用户:** 黎国友（ou_5df3accc2134f25bbe480cb9134b032b），token 自动续期
- **lark-cli 已授权 scope:** docs/docx、minutes、bitable、sheets、contact、calendar、vc
- **SSE 实现:** Flask generator + Response（非 FastAPI StreamingResponse）
- **LLM 配置持久化:** SQLite `llm_config.db`
- **LLM Token 传递:** 前端 localStorage → axios interceptor → X-Access-Token header → Flask `g.access_token`
- **SSE 前端解析:** 按 `\n\n` 事件分隔符切分（非逐行），防 TCP chunk 截断丢失事件
- **硬超时保护:** `concurrent.futures.ThreadPoolExecutor` 施加硬墙钟超时（`requests` timeout 只控制字节间隔）
- **AI 编程 EP API:** 带 2 次自动重试抵御瞬时错误
- **AST 信号提取:** 正则提取候选信号 → `astValidator.ts` 集中 AST 验证过滤假阳性。9 个信号提取器保持简单正则实现，验证层独立。ts-morph 轻量模式（skipFileDependencyResolution=true），仅加载 changed files
- **LLM 逐组调用:** 每组 Feature Group 单独调 LLM，输出 `{category, description, type}`。LLM 可修正 AST 分类，但修正范围受限（仅 STYLE_ONLY↔FEATURE_MODIFY、UI_INTERACTION→FEATURE_MODIFY）
- **API_CALL import 来源检查:** 增加正则解析 import 声明，确认 `api` 来自项目内部 request 模块

---

## ✅ Phase 3 验收修复（2026-06-24）

### 三个问题根因与修复

**1. 标签列名错误 → AIcoding/SDD/端到端全为 0**
- `stats_engine.py` 中列名写为 `"自...标签"`，实际为 `"自定义标签"`
- 修复：改为按优先级轮询 `["自定义标签", "自...标签", "标签", "需求标签"]`

**2. 上传端点不合并飞书标准名称/TL**
- `/upload` 端点只返回 xlsx 原始数据，项目名和 TL 不匹配飞书模板
- 修复：新增 `_fetch_bitable_project_map()` + `_match_bitable_project()`，上传后自动匹配合并

**3. 布局需滚动查看统计结果**
- 修复：`100vh` 全屏布局，上传区压缩为单行，结果区 `overflow: auto`
- 自动 `scrollIntoView` 到结果区域

### 其他修复
- 前端 `computeSummary` 占比分母修正（AIcoding/工程，SDD/AIcoding）
- 上传区 Dragger 用 `showUploadList={false}`，文件名改用紧凑 `<Tag closable>`，固定 48px 高度
- Python flake8 + TypeScript 零错误

### 额外 Bug 修复（2026-06-24 17:43）
- **导出 xlsx 500（根因 1）**：循环中 `data["project_stats"]` 在前端传 `rows` 时是 `None`，改用局部变量 `project_stats`
- **导出 xlsx 500（根因 2）**：`aicoding_ratio` 已是字符串 `"25.0%"`，`f'{...:.2f}%'` 抛出 `ValueError`
- **飞书写入显示 "undefined 条记录"**：后端返 `"updated"`，前端读 `res.updated_count` → `undefined`，后端改为 `"updated_count"`
- **UX：写入后无跳转链接** → Alert 新增 "🔗 打开飞书多维表格查看" 超链接

### 额外 Bug 修复（2026-06-24 18:03）
- **TL 列显示 @ 前缀** — tl_raw 是 bitable list（mention 格式），拼接 text 时未 `.lstrip("@")`
- **合计行缺失** — handleWriteBitable/handleExport 只传 result.rows（各项目数据），未追加 summaryRow
- **修复**：新增 `computeRawSummary()`（RawStatsRow 版合计行），写入和导出均追加

### 额外功能（2026-06-24 20:22）
- **项目名称清洗**：新增 `_extract_project_name()` 统一函数，正则 `^\d+\.\d+[（(]\d+[）)]\s*` 去掉 `5.93（0529）` 前缀
- **合计行自动创建**：write-bitable 检测到 "合计" 未匹配时自动调用 `+record-batch-create` 创建记录并写入
- **新增** `feishu_client.py` 的 `create_bitable_record()` 函数

### 文档再次被 edit_file bug 污染
- `progress.md` + `frontend/src/api/iterationStats.ts` 被 edit_file 重复膨胀
- 修复：write_file 完整重写

### 关键教训
- **标签列名不要硬编码**，用轮询策略兼容不同版本 xlsx
- **upload 端点必须提前合并飞书数据**，展示层需要标准名称和 TL
- **上传区不占太多空间**，紧凑布局为主，结果区才是主角
- **`edit_file` 的 `old_text` 必须是文件中实际存在的非空字符串**，空字符串会导致文件灾难性膨胀

### Phase 3 后修复（2026-06-24 21:31）
**彻底方案：废弃正则解析 → 硬编码 PROJECT_MAP**
- 正则版本号清洗无论如何补都覆盖不全（`5.93(0529)` / `5.93版本(0529)` / `V5.93迭代(5月29日灰度)`）
- TL 解析同理（mention 格式/list 格式/多人 TL）
- 新方案：12 个项目的标准名+TL 直接硬编码在 `PROJECT_MAP` 中
- `_find_project_by_bitable_name()`：用子串 `标准名 in bitable名` 反向查找
- 删除 `_PROJECT_VERSION_RE`、`_extract_project_name()`、`re` 模块

---

## 🟢 Phase 4 — AI 编程数据报告（已完成 2026-06-30）

### 架构决策
- **直接 HTTP API 替代 subprocess 调用脚本**
- **Services 三层分离**：`AiMeasureClient` / `SkillsQueryClient` → `ReportGenerator` → `ai_measure.py` router
- **SSE 事件流**：`progress` → `section_complete` / `section_error` → `complete`

### 修复：SSE chunk 截断导致 active_rate 丢失
- `sse.ts` 解析器从按 `\n` 逐行切分改为按 `\n\n` 事件边界切分
- `sse_helpers.py` 用 `stream_with_context` 实时推送
- `ai_measure_client.py` 硬墙钟超时 + 2 次自动重试
- `AiMeasure.tsx` `completedRef` 防 React batch 覆盖

### 与方案文档差异
- 直接 HTTP 调用替代 subprocess（脚本输出表格非 JSON）
- Skills 按贡献人聚合展示
- SSE 事件名与现有 sse.ts 处理逻辑对齐

---

## 🟢 Phase 5 — 无矩 2.0 知识库问答（已完成 2026-06-30）

### 架构
- `backend/routers/chat.py` — 3 端点（send SSE 代理到无矩2.0 :8000 / conversations / health）
- `frontend/src/pages/Chat.tsx` — 单页对话 UI（建议卡片 / 消息列表 / 引用来源折叠 / SSE 流式渲染）
- 无 `kb_agent.py` — 后端不做 LLM 调用，仅 HTTP 转发
- 无 `ChatMessage.tsx` — 消息渲染内联 Chat.tsx
- `api/chat.ts` 存在但 Chat.tsx 直接用原生 fetch（不用 axios）

### SSE 事件格式（透传无矩2.0 协议）
```
data: {"type":"sources","sources":[...]}
data: {"type":"token","content":"..."}
data: {"type":"done"}
data: {"type":"error","content":"..."}
```

### 涉及文件
| 文件 | 说明 |
|------|------|
| `backend/routers/chat.py` | SSE 代理（requests.iter_lines 逐行转发） |
| `frontend/src/pages/Chat.tsx` | 对话页面（fetch + ReadableStream + 引用展示） |
| `frontend/src/api/chat.ts` | API 封装（未使用，Chat.tsx 直接用 fetch） |

---

## 🟢 Phase 6 — 知识库管理（已完成 2026-06-30）

### 架构
- `backend/routers/kb_manage.py` — 10 个代理端点，全部转发到 `:8000/api/admin/*`
- 通用代理函数: `_proxy_get` / `_proxy_post` / `_proxy_delete` / `_proxy_files`，三层异常捕获（ConnectionError / Timeout / RequestException）

### 前端页面 — 4 Tab
| Tab | 内容 |
|-----|------|
| 概览 | 统计卡片（文档数/知识库数/同步） + Collection Table（可点击跳转浏览） |
| 浏览 | Select + 关键词搜索 + 分页 Table + 文档全文 Drawer + 删除确认 |
| 导入 | 文本导入（TextArea）+ 文件上传（Dragger）双列 |
| 同步 | Radio 模式选择（代码/核心KB/Wiki/全量）+ dry-run 预览 + 轮询进度 + 知识库组成 Table |

### 后端新增参数
`POST /api/admin/sync?dry_run=&rebuild_core=&rebuild_wiki=` — 支持 3 种同步模式参数透传