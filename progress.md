# AI 中控台 — Progress

> 实时进度日志，每次操作后更新

---

## 2026-06-24 20:22 · 项目名称清洗 + 合计行自动创建

### 项目名称清洗（统一辅助函数）
- **背景**：bitable 中的项目名格式为 `5.93（0529）Dsearch搜索引擎版本迭代`，需去掉版本前缀
- **新增** `_extract_project_name()` 统一处理 3 种格式（链接/markdown/纯文本）并去除 `X.XX（XXXX）` 前缀
- **替换 3 处**：`_fetch_bitable_project_map`、`/projects` 端点、write-bitable 中 `exact_map` 构建

### 合计行自动创建到飞书
- **背景**：前端计算的合计行写回 bitable 时无对应记录，进入 unmatched 不生效
- **修复**：write-bitable 检测 `project_name == "合计"` 的 unmatched 记录时，自动调用 `create_bitable_record()` 创建记录后写回
- **新增** `feishu_client.py` 的 `create_bitable_record()` 函数（使用 `+record-batch-create`）
- 后端返回新增 `create_bitable_record: true/false` 字段

### 涉及文件
- `backend/routers/iteration_stats.py` — 新增 `_extract_project_name()` + `_PROJECT_VERSION_RE`；替换 3 处清洗逻辑；write-bitable 新增自动创建合计行
- `backend/services/feishu_client.py` — 新增 `create_bitable_record()` 函数；加入 `re` import

---

## 2026-06-24 20:29 · Phase 4 — AI 编程数据报告模块（后端+前端）

### 后端实现
- **新增** `services/ai_measure_client.py` — 封装 ep-copilot2 API 直接 HTTP 调用（drilldown 查询），替代脚本 subprocess 方式
- **新增** `services/skills_query_client.py` — 封装 skills.dewu-inc.com API 直接 HTTP 调用
- **新增** `services/report_generator.py` — 报告编排器，串行调用 4 个查询模块 + Markdown 表格格式化。TL 固定名单 27 人硬编码
- **新增** `backend/services/ai_measure_scripts/` — 拷贝 ai-measure-query skill 的 4 个脚本（备用参考）
- **重写** `routers/ai_measure.py` — 3 个接口：
  - `POST /api/ai-measure/test-token` — 测试 Token 连通性
  - `POST /api/ai-measure/generate` — SSE 流式生成报告（progress → section_complete/section_error → complete）
  - `POST /api/ai-measure/write-to-feishu` — 将报告写入飞书文档（Markdown→XML 简化转换）

### 前端实现
- **新建** `api/aiMeasure.ts` — API 封装（testToken / generateReport / writeToFeishu）
- **新建** `components/ReportPreview.tsx` — 报告预览面板（Markdown 渲染 + 折叠模块 + 写入/复制按钮，最终未使用，全部集成在 AiMeasure.tsx 中）
- **重写** `pages/AiMeasure.tsx` — 完整 UI：配置区（Token+测试/试点名单+默认TL/时间范围/模块勾选）+ 竖向 Steps 进度 + Markdown 报告预览 + 写入飞书文档 + 复制 Markdown

### 与方案文档差异
- 📌 直接 HTTP 调用替代 `subprocess` 调用脚本（脚本输出格式化表格非 JSON）
- 📌 Skills 按贡献人聚合展示（多条 skill 用 " / " 连接）
- 📌 文件写入飞书使用 feishu_client.create_doc_xml 已有方法，Markdown→XML 简化转换
- 📌 SSE 事件名对齐：progress / section_complete / section_error / complete

### 涉及文件
- 新增: `backend/services/ai_measure_client.py`
- 新增: `backend/services/skills_query_client.py`
- 新增: `backend/services/report_generator.py`
- 新增: `backend/services/ai_measure_scripts/ai_measure.py`
- 新增: `backend/services/ai_measure_scripts/inactive_members.py`
- 新增: `backend/services/ai_measure_scripts/skills_query.py`
- 新增: `backend/services/ai_measure_scripts/dept_stats.py`
- 重写: `backend/routers/ai_measure.py`
- 新增: `frontend/src/api/aiMeasure.ts`
- 新增: `frontend/src/components/ReportPreview.tsx`
- 重写: `frontend/src/pages/AiMeasure.tsx`

### TL 列前缀 @ 未去掉
- **根因**：`tl_raw` 是 bitable 返回的 list（mention 格式），代码只拼接了 text 但未去掉 `@` 前缀
- **修复**：`.lstrip("@")` 处理每个文本片段

### 导出 xlsx 和飞书写入缺少合计行
- **根因**：`handleWriteBitable` 和 `handleExport` 都只发了 `result.rows`（各项目数据），前端计算的 `summaryRow` 未包含
- **修复**：
  - 新增 `computeRawSummary()` — 基于 `RawStatsRow[]` 计算合计行（返回 `RawStatsRow` 类型，不含前端展示字段）
  - 写入飞书时追加 `computeRawSummary(result.rows)`；飞书无"合计"记录时自动计入 unmatched 但不阻塞
  - 导出 xlsx 时同样追加合计行

### edit_file 空字符串 bug 再次触发 → 重写文件
- `frontend/src/api/iterationStats.ts` 被撑出重复代码 → 用 `write_file` 完整重写干净版本
- `progress.md` 也被撑出 8 重重复 → 用 `write_file` 完整重写

### 涉及文件
- `backend/routers/iteration_stats.py` — TL 清洗 `.lstrip("@")`
- `frontend/src/api/iterationStats.ts` — 完整重写 + 新增 `computeRawSummary()`
- `frontend/src/pages/IterationStats.tsx` — handleWriteBitable/handleExport 追加合计行
- `progress.md` — 重写清理重复

---

## 2026-06-24 17:43 · 修复导出 xlsx 500 与飞书写入消息错误

### 修复清单

**Bug 1 — 导出 xlsx 报 500**
- **根因 1**：循环中用了 `data["project_stats"]`，前端传的是 `"rows"` → `data["project_stats"]` 为 `None` → 500
- **根因 2**：`aicoding_ratio` 已经是字符串如 `"25.0%"`，但代码用了 `f'{...:.2f}%'` → `ValueError` → 500
- **修复**：改用本地变量 `project_stats`；ratio 字段做类型判断

**Bug 2 — 飞书写入后显示 "undefined 条记录"**
- **根因**：后端返回 `"updated"`，前端读 `res.updated_count` → `undefined`
- **修复**：后端改为 `"updated_count"` 返回

**UX — 写入后无跳转链接**
- Alert 增加 "🔗 打开飞书多维表格查看" 超链接

### 涉及文件
- `backend/routers/iteration_stats.py`
- `frontend/src/pages/IterationStats.tsx`

---

## 2026-06-24 16:26 · 前端布局优化：上传区压缩不因多文件撑开

- `showUploadList={false}` — 不让 Dragger 内部渲染文件列表，固定 48px 高度
- 已选文件名用紧凑 `<Tag closable>` 行展示
- `handleReset` 清除所有状态

### 涉及文件
- `frontend/src/pages/IterationStats.tsx`

---

## 2026-06-24 16:09~16:21 · Phase 3 三项验收问题修复

### 修复清单

**问题 1 — 统计结果在页面下方需滚动**
- 布局改为 `height:100vh;overflow:hidden` 全屏 + 上传区单行压缩 + 结果区独立滚动 + 自动 scrollIntoView

**问题 2 — AIcoding/SDD/端到端全为 0**
- `stats_engine.py` 列名轮询 `["自定义标签","自...标签","标签","需求标签"]`

**问题 3 — 项目名称/TL 未对齐模板**
- 新增 `_fetch_bitable_project_map()` + `_match_bitable_project()`，上传后自动合并标准名称+TL

### 涉及文件
- `backend/services/stats_engine.py`
- `backend/routers/iteration_stats.py`
- `frontend/src/pages/IterationStats.tsx`

---

## 2026-06-24 02:00 · Phase 2 最终修正

- 跟进人规则重写为判断矩阵（3 种场景）
- 描述清洗三类场景（找人/协作/移交）
- docUrl 成功卡片移到输入区下方固定位置
- temperature=0.0 + max_tokens=8192 + 重试 3 次
- 5 层 JSON 降级解析

---

## 2026-06-24 00:30 · Phase 2 三项优化

- DDL 默认当天
- 多人跟进人（顿号分隔，多 `<cite>` 标签）
- 简称→全称映射（说话人列表注入 Prompt）

---

## 2026-06-23 21:30 · JSON 解析加固

- 控制字符只删 `[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]`（保留 `\n\t\r`）
- 5 层递进容错解析

---

## 2026-06-24 21:31 · Phase 3 全面改用硬编码项目映射（彻底解决名称/TL问题）

### 问题分析
用户反馈3个问题全部**根源于同一个底层问题**：正则解析 bitable 项目名称不可靠。

### 解决方案
**废弃所有正则解析，改用固定 PROJECT_MAP 硬编码表**

| 旧方案 | 新方案 |
|--------|--------|
| `_extract_project_name()` 用正则去版本号 | 删除，改用 `_find_project_by_bitable_name()` 子串匹配标准名 |
| `_fetch_bitable_project_map()` 从 bitable 字段解析 TL | 删除解析逻辑，TL 从硬编码 `PROJECT_NAME_TO_TL` 查 |
| write-bitable 用 exact_map 模糊匹配 | 改用 `_find_project_by_bitable_name()` 匹配标准名 |
| `/projects` 端点独立解析项目名+TL | 统一用 PROJECT_MAP 返回标准名+TL |

### 核心改动
- 新增硬编码 `PROJECT_MAP`（12 条，项目名→TL，来自飞书 wiki 图片）
- 新增 `_find_project_by_bitable_name()`：反向匹配（子串查找 `标准名 in bitable名`）
- 删除 `_PROJECT_VERSION_RE`、`_extract_project_name()`、`re` 模块
- 重写 `_fetch_bitable_project_map()`：仅从 bitable 获取 `record_id`
- 重写 write-bitable 匹配逻辑：用 PROJECT_MAP 覆盖前端传入的 `project_name` 和 `tl`

### 涉及文件
- `backend/routers/iteration_stats.py` — 核心重写（-正则解析 + 硬编码映射）
- `backend/services/feishu_client.py` — 之前已修复 `_fmt_ratio`

### Bug 1：项目名称末尾版本号未清洗（如「DPP双周迭代 5.93版本（0529）」）
- **根因**：`_PROJECT_VERSION_RE` 正则 `^\d+\.\d+[（(]\d+[）)]\s*` 只匹配版本号在**开头**，未覆盖末尾格式
- **修复**：正则增加后缀分支 `|\s*\d+\.\d+版本?[（(]?\d*[）)]?\s*$`
- **涉及文件**：`routers/iteration_stats.py`

### Bug 2：TL 只显示前两个人
- **根因**：`_fetch_bitable_project_map()` 和 `/projects` 端点两次清洗 TL 都用了 `re.search()`（只返回第一个匹配），多人 TL 时只提取了第一个人
- **修复**：改为 `re.findall()`，全部匹配后用 `",".join()` 拼接
- **涉及文件**：`routers/iteration_stats.py`

### Bug 3：写入飞书报错 `Unknown format code 'f'`
- **根因**：`update_bitable_record()` 中 `f'{stats.get("aicoding_ratio", 0):.2f}%'` 未做类型判断——当 ratio 已是字符串（如 `"68.57%"`）时 `:.2f` 抛异常
- **修复**：新增模块级 `_fmt_ratio()` 统一函数（判断 `isinstance(v, (int, float))`），移除 `create_bitable_record` 中重复的本地嵌套函数
- **涉及文件**：`services/feishu_client.py`

### 涉及文件
- `backend/routers/iteration_stats.py` — 正则 + `re.search`→`re.findall`
- `backend/services/feishu_client.py` — 新增 `_fmt_ratio()` 模块级函数

- `search_user_by_name()` 使用 `--page-size 5 --as user`
- `create_doc_xml()` 临时文件相对路径
- 文档标题去重
- Flask 子进程注入 `LARKSUITE_CLI_CONFIG_DIR`

---

## 2026-06-23 19:50 · Phase 2 后端 + 前端完整实现

- meeting_todo_service.py（DDL 推理/跟进人/文档模板）
- MeetingTodo.tsx（分屏布局/SSE/3 组件）
- TodoCard / TodoPanel / TranscriptPanel

---

## 2026-06-23 · Phase 1 公共基础设施

- SSE 封装（sse_event / sse_stream）
- feishu_client（lark-cli subprocess）
- llm_client（OpenAI 兼容）
- models（6 个 dataclass）
- LLMConfig Provider（三件套 + SQLite 持久化）
- Token 全局管理（前端 Provider + axios 拦截器 + 后端 before_request）

---

## 2026-06-23 · Phase 0 项目骨架

- Flask app.py（4 Blueprints，10 端点桩）
- 前端 BrowserRouter + basename + 侧边栏布局
- 4 页面组件 + ComingSoon
- Axios + SSE 封装 + 4 API 模块

---

## 2026-06-30 · Phase 4 AI 编程数据报告 — SSE chunk 截断 Bug 定位修复

### 问题现象
网页报告生成时 active_rate 显示"查询失败"，后端 curl 测试正常返回（4 模块全部 section_complete）。

### 排查
Console 输出 `completedRef: Array(3)` 缺 active_rate。根因: 手写 SSE 解析器按 `\n` 切分，`section_complete` 事件 payload 跨 TCP chunk 时 `data:` JSON 被截断解析失败静默丢弃。

### 修复
- `utils/sse.ts` — 解析器改为按 `\n\n`（SSE 规范事件分隔符）切分
- `sse_helpers.py` — 用 `stream_with_context` 实时推送
- `AiMeasure.tsx` — `completedRef` ref 跟踪已完成模块，避免 React batch 覆盖
- `ai_measure_client.py` — 硬超时 + 自动重试

### 涉及文件
- `frontend/src/utils/sse.ts`
- `frontend/src/pages/AiMeasure.tsx`
- `backend/services/sse_helpers.py`
- `backend/services/ai_measure_client.py`
- 前后端联调验证通过

---

## 2026-06-30 · Phase 5 知识库问答 — 单页对话 + SSE 代理

### 实际实现 vs 方案
- `backend/routers/chat.py` — 3 端点: send (SSE 代理到无矩2.0 :8000) / conversations / health
- `frontend/src/pages/Chat.tsx` — 单页对话 UI: 建议卡片 / 消息列表 / SSE 流式展示 / 引用来源折叠
- 无 `kb_agent.py` — 后端仅 HTTP 代理转发，不调 LLM
- 无 `ChatMessage.tsx` — 消息渲染内联在 Chat.tsx

### 涉及文件
- `backend/routers/chat.py` — 重写
- `frontend/src/pages/Chat.tsx` — 新建
- `frontend/src/api/chat.ts` — 存在但 Chat.tsx 直接用 fetch

---

## 2026-06-30 · Phase 6 知识库管理 — 4 Tab 管理页面 + 同步模式选择

### 实现内容
- `backend/routers/kb_manage.py` — 10 个代理端点（collections / browse / doc / sqlite / import / import-file / delete / sync / sync-status / health）
- `frontend/src/api/kbManage.ts` — 10 个 API 函数，完整 TypeScript 类型定义
- `frontend/src/pages/KbManage.tsx` — 4 Tab 管理页面
  - Tab 1 概览：统计卡片 + Collection 列表 Table（可点击跳转到浏览）
  - Tab 2 浏览：Select 选择 collection + 关键词搜索 + 分页 Table + 文档全文 Drawer + 删除确认
  - Tab 3 导入：文本导入（TextArea） + 文件上传（Dragger）双列布局
  - Tab 4 同步：Radio 模式选择（代码/核心KB/Wiki/全量）+ dry-run 预览 + 轮询进度 + 知识库组成说明 Table
- 侧边栏新增"知识库管理"入口，`/kb-manage` 路由

### 涉及文件
- `backend/routers/kb_manage.py` — 新建
- `backend/app.py` — 注册 blueprint
- `frontend/src/api/kbManage.ts` — 新建
- `frontend/src/pages/KbManage.tsx` — 新建
- `frontend/src/App.tsx` — 新增路由
- `frontend/src/components/AppLayout.tsx` — 侧边栏

---

## 2026-07-01 · Phase 7 Phase 1a — CLI 骨架 + 4 核心信号

### 实现内容
- **tools/code-analyzer/** — Node.js CLI 项目脚手架（package.json + tsconfig.json + ts-morph）
- **types.ts** — 共享类型定义（HunkInfo, Signal, FeatureGroup, AnalysisResult 等）
- **index.ts** — CLI 入口（arg parse → 编排 → 输出 JSON 文件）
- **git/parsePatch.ts** — diff raw.patch → HunkInfo[] 解析
- **signals/extractor.ts** — 4 核心信号入口：NEW_ROUTE/NEW_PAGE/API_CALL/STATE_ACTION
- **signals/routes.ts** — 支持 Umi 配置式路由 `config/config.ts` 和 JSX `<Route>`
- **signals/api.ts** — API_CALL 检测（api.*, fetch, axios, useRequest）
- **signals/state.ts** — STATE_ACTION 检测（setXxx, dispatch, commit, useState）
- **classify/decisionTree.ts** — 优先级覆盖决策树（P0→P4）
- **snippet/extractSnippet.ts** — 双版本 Snippet 截取

### 冒烟测试
- 测试 patch 含 2 个文件（BatchImport.tsx 新增 + config.ts 路由新增）
- 4 核心信号全部正确检出 ✅
- 分类正确：NEW_FEATURE 含 NEW_PAGE+API_CALL+STATE_ACTION → 聚合为 2 个 Feature Groups

### 涉及文件
- `tools/code-analyzer/package.json` — 新建
- `tools/code-analyzer/tsconfig.json` — 新建
- `tools/code-analyzer/src/types.ts` — 新建
- `tools/code-analyzer/src/index.ts` — 新建
- `tools/code-analyzer/src/git/parsePatch.ts` — 新建
- `tools/code-analyzer/src/signals/extractor.ts` — 新建
- `tools/code-analyzer/src/signals/routes.ts` — 新建
- `tools/code-analyzer/src/signals/api.ts` — 新建
- `tools/code-analyzer/src/signals/state.ts` — 新建
- `tools/code-analyzer/src/classify/decisionTree.ts` — 新建
- `tools/code-analyzer/src/snippet/extractSnippet.ts` — 新建

### 修复记录
- 路由 `path:` 正则支持无引号 key（`["']?path["']?` → `path` 在 Umi config 中无引号）

---

## 2026-07-01 · Phase 7 Phase 1b — 补齐 6 类信号 + Import Graph 聚类 + 文档上下文

### 实现内容
- **新增 6 信号提取器**：PERMISSION、HOOK_DEF、EVENT_HANDLER、DATA_MODEL、CONFIG_CHANGE、STYLE_ONLY（含样式纯净度验证）
- **Import Graph 构建**：`graph/importGraph.ts` — 基于 import 声明解析文件依赖
- **连通分量聚类**：`graph/cluster.ts` — import 关系聚类 + 兜底目录聚类
- **文档上下文收集**：`snippet/extractSnippet.ts` — JSDoc 注释 + 测试描述提取
- **index.ts 重写**：集成聚类流程 + page-logic/ 结果层去重 + 客观 Confidence 计算

### 冒烟测试
- 10 类信号全部检出 ✅（NEW_ROUTE/NEW_PAGE/API_CALL/STATE_ACTION/PERMISSION/HOOK_DEF/EVENT_HANDLER/DATA_MODEL/CONFIG_CHANGE/STYLE_ONLY）
- 聚类正确：3 个 Feature Groups（页面新增 + 路由配置 + 类型修改）
- Confidence 计算正确（0.65 / 0.5 / 0.5）

### 涉及文件
- `tools/code-analyzer/src/signals/permission.ts` — 新建
- `tools/code-analyzer/src/signals/hooks.ts` — 新建
- `tools/code-analyzer/src/signals/event.ts` — 新建
- `tools/code-analyzer/src/signals/dataModel.ts` — 新建
- `tools/code-analyzer/src/signals/config.ts` — 新建
- `tools/code-analyzer/src/signals/style.ts` — 新建
- `tools/code-analyzer/src/signals/extractor.ts` — 重写（集成全部 10 信号）
- `tools/code-analyzer/src/graph/importGraph.ts` — 新建
- `tools/code-analyzer/src/graph/cluster.ts` — 新建
- `tools/code-analyzer/src/snippet/extractSnippet.ts` — 重写（新增 doc context）
- `tools/code-analyzer/src/index.ts` — 重写（集成聚类 + confidence + page-logic 去重）

### 修复记录
- `event.ts` matchAll 需要 global regex（`/g` 标志）
- `hooks.ts` 正则支持 `(` 结尾（`useXxx()` 函数声明）

---

## 2026-07-01 · Phase 7 Phase 2 — 项目知识快照

### 实现内容
- **knowledge/snapshot.ts** — 扫描目标仓库目录结构生成知识快照
  - 路由表：从 `config/config.ts`、`config/routes.ts`、`.umirc.ts` 提取 path/component
  - 模块结构：扫描 `src/pages/` 目录映射业务模块
  - API 模块：扫描 `src/service/` 目录提取接口端点
  - 共享组件：扫描 `src/components/` 和 `_share/components/`
- **CLI --mode snapshot** — 接入 snapshot 模式

### 真实仓库验证
- 目标：`/tmp/analyze_real_test_target`（algorithm-monorepo HEAD）
- 结果：ml-main 4 routes / ml-data 13 routes / 7 业务模块 / 7 API 模块 / 9 组件 / 1 共享包
- 耗时：~5s ✅

### 涉及文件
- `tools/code-analyzer/src/knowledge/snapshot.ts` — 新建
- `tools/code-analyzer/src/index.ts` — 修改（snapshot 模式接入）

### 修复记录
- 路由配置支持 `config/routes.ts`（独立文件而非内联）
- 路由路径正则支持模板字符串 `` `...${var}...` `` 格式
- 模板变量 `${appName}` 从 `package.json` 的 `appName` 字段读取并解析为实际值
- 快照时间改为 `+08:00` 东八区格式
- 共享包 exports 递归扫描所有子目录，过滤 `.dumi/`、`.test.`、`.d.ts`

---

## 2026-07-01 · Phase 7 Phase 3 — Flask 编排器 + API 端点

### 实现内容
- **code_analyze_service.py** — 完整编排器（8 步流程）
  1. 知识快照（自动过期 3 天）
  2. Git fetch（bare repo 增量更新）
  3. 定位 commits（显式 refs/heads/branch）
  4. 收集 commit messages
  5. 双版本 worktree 检出
  6. 生成 diff（含 noise 文件过滤：`plugin_exec_result.json` 等）
  7. AST 分析（subprocess Node.js CLI，文件传递输出）
  8. LLM 语义归纳（LLMClient.chat，降级到规则层）
- **code_analyze.py** — Flask Blueprint（4 端点）
  - `POST /api/code-analyze/start` — SSE 流式分析
  - `GET /api/code-analyze/status/<task_id>` — 轮询状态
  - `POST /api/code-analyze/refresh-snapshot` — 刷新知识快照
  - `GET /api/code-analyze/snapshot` — 获取快照信息
- **app.py** — 注册 `code_analyze_bp`

### 涉及文件
- `backend/services/code_analyze_service.py` — 新建
- `backend/routers/code_analyze.py` — 新建
- `backend/app.py` — 修改（注册 blueprint）
- `backend/venv/` — 新建（Python venv）

### 修复记录
- LLMClient API 适配：`llm_client.py` 是 `LLMClient.chat(system=, user=)` 类，不是 `llm_complete()` 函数
- `get_snapshot_info()` 改为模块级缓存替代动态 import

---

## 2026-07-01 · Phase 7 Phase 4 — 前端页面

### 实现内容
- **api/codeAnalyze.ts** — API 封装层
  - `startAnalysis()` — SSE 流式分析（AbortController 支持取消）
  - `refreshSnapshot()` — 刷新知识快照
  - `getSnapshotInfo()` / `getTaskStatus()` — 查询接口
  - 完整 TypeScript 类型定义
- **pages/CodeAnalyze.tsx** — 完整页面组件
  - 配置区：仓库信息 + 时间段选择器 + 分析路径勾选
  - 8 步 Steps 进度条（同 AiMeasure 模式）
  - 结果区：统计卡片 + 新增/修改/下线/UI 分类报告
  - 知识快照刷新按钮 + 状态展示
- **App.tsx** — 注册 `/code-analyze` 路由
- **AppLayout.tsx** — 侧边栏新增"代码变更分析"菜单项

### 涉及文件
- `frontend/src/api/codeAnalyze.ts` — 新建
- `frontend/src/pages/CodeAnalyze.tsx` — 新建
- `frontend/src/App.tsx` — 修改
- `frontend/src/components/AppLayout.tsx` — 修改

### 验证
- TypeScript: `tsc --noEmit` 零错误 ✅

---

## 2026-07-01 · Phase 7 Phase 5 — LLM 集成 + 端到端验证

### 验证内容
- **Flask 路由注册**：4 个 `/api/code-analyze/*` 端点全部注册 ✅
- **前端构建**：`npm run build` 成功 ✅
- **端到端流程**：git fetch → resolve commits → commit messages → worktree → snapshot → diff → AST → LLM，全链路打通 ✅
- **LLM 降级**：API key 无效时降级到规则层结果，不崩溃 ✅

### 修复
- **Snapshot 顺序**：原在 worktree 之前生成，导致 target_worktree 不存在时走 `"."` 兜底产生空快照。改为 worktree 之后生成
- **前端 Steps 顺序**：同步更新为 8 步新顺序

### 涉及文件
- `backend/services/code_analyze_service.py` — 修改（snapshot 挪到 worktree 之后）
- `frontend/src/pages/CodeAnalyze.tsx` — 修改（Steps 顺序同步）

### 修复记录
- Snapshot 生成必须在 worktree 检出之后，否则 target_worktree 不存在
- `GIT_CACHE_DIR` 路径多了一层 `backend/`，导致每次请求都在重新 clone 200MB+ 仓库。修复：路径上溯到项目根目录 + 创建 symlink 兼容旧路径
- `_git_fetch`/`_run_ast_analysis`/`_ensure_knowledge_snapshot` 非生成器被 `yield from` 调用 → `NoneType not iterable`

---

## 2026-07-02 · Phase 7 生产调试 — LLM 归一化 + 导出修复 + 前端优化

### 前端问题修复
- **Steps 卡转圈**：`onComplete` 回调中未标记 `llm` 步骤为完成，UI 一直显示"进行中"。修复：`completedRef.current.add('llm')` + `next['llm'] = 'finish'`
- **API 路径重复 404**：`codeAnalyze.ts` 路径写为 `/api/code-analyze/start`，但 `API_BASE` 已含 `/api` 前缀。修复：去除 `/api` 前缀

### LLM 调用问题修复
- **`for g in` 变量覆盖 Flask `g`**：列表推导式 `item for g in ast_result.get("featureGroups")` 中的 `g` 覆盖了 `from flask import g`，`g.llm_config` 报错
- **LLM 超时降级**：从 30s→60s→300s，最终稳定
- **LLM 格式不统一**：LLM 返回了 `{report: [...]}`, `{changeReport: [...]}`, `{changes: [...]}`, 裸数组 `[...]`, `{new_features: [...]}` 等多种格式。归一化层支持任意格式
- **LLM 返回裸数组**：`isinstance(data, list)` 未处理，抛 `AttributeError` 降级到规则层
- **`conf` 变量名错误**：归一化代码 `float(conf)` 用了上层作用域残留变量，应为 `float(matched_conf)`。未报错但 conf 值不对
- **`category`→`name` 映射缺失**：LLM 返回 `category` 字段但前端读 `name`，显示"未知变更"。修复：`elif` 分支补自动映射
- **`max_tokens` 不足**：从 4096 提升到 8192，避免 LLM 输出被截断

### Summary 统计字段修复
- `analyzed_files` 从 LLM 结果数改为 AST 原始 `totalChangedFiles`
- `feature_groups` 从 LLM 结果数改为 AST 原始聚类组数
- `functional_changes` 保留 LLM 归纳的新增+修改数
- 三者取自不同来源，不会永远相同

### Prompt 优化
- 新增分类规则：新增 vs 修改 vs 下线的区分标准
- 引用 AST `feature_group.type` 作为分类依据
- 互斥规则：同一变更只能归入一个类别

### 飞书导出修复
- **空白文档**：`create_doc_xml` 要求 XML 以 `<title>` 标签开头，导出代码用 `<text_tag>` 且无标题标签。修复：`<title>开头 + <p>/<b>` 标签格式

### 导出功能
- 新增 `POST /api/code-analyze/export/markdown` — 下载 `.md` 文件
- 新增 `POST /api/code-analyze/export/feishu` — 创建飞书文档
- 前端新增"导出 Markdown"和"导出到飞书文档"按钮

### 涉及文件
- `backend/services/code_analyze_service.py` — 重写 _llm_summarize（归一化 + 超时 + category 映射）
- `backend/routers/code_analyze.py` — 新增 export/markdown + export/feishu 端点
- `frontend/src/api/codeAnalyze.ts` — 修复 404 路径 + 新增导出函数
- `frontend/src/pages/CodeAnalyze.tsx` — 修复 Steps 状态 + 新增导出按钮
	
---

## 2026-07-03 · 功能变更分析模块 — 优化与重构

### LLM 稳定性问题定位与修复
- **问题**：相同日期三次分析，Feature Groups 一致（61 组），但 LLM 输出项数分别为 59、27、92，每次不一样
- **根因 1**：`temperature=0` 不足以保证确定性，需加 `seed=42` 参数（DeepSeek/OpenAI 分布式 GPU 节点浮点运算非确定性）
- **根因 2**：LLM 批量归纳时无法稳定——合并（61→27）或拆分（61→92），`seed=42` 也不够
- **修复**：改为按组逐一调用 LLM，AST 决策树决定分类，LLM 只做描述生成

### 重构：逐组 LLM 调用
- `_llm_summarize` 重写：不再一次性给 LLM 全部 61 组，而是每组单独调用
- 每个 Feature Group 的 `type` 字段直接决定归属：NEW_FEATURE→新增、FEATURE_MODIFY→修改、STYLE_ONLY→UI
- LLM 只输出 `{category, description}`，不做分类决策
- AST confidence 直接作为输出 confidence，不用 LLM 自评
- ThreadPoolExecutor(max_workers=5) 并行调用，单组超时 120s

### 其他优化
- `app.py` 修复 `request` 未导入导致的 500 错误
- `_preserve_debug_files` 新增：cleanup 前将 result.json 和 LLM 响应复制到 `/tmp/analyze_debug/` 持久化
- 前端：侧边栏"LLM 配置"改为"全局配置" + Git Token 区域
- 标签列等宽对齐（`width: 80, textAlign: 'right'`）
- `dayjs.locale('zh-cn')` + Ant Design `ConfigProvider locale={zhCN}` 中文日期选择器
- ADR: 禁用未来日期选择

### 涉及文件
- `backend/services/code_analyze_service.py` — 重写 _llm_summarize（逐组调用）+ _preserve_debug_files
- `backend/services/llm_client.py` — 新增 `seed` 参数
- `backend/services/db.py` — user_config 加 git_token + 新建 commit_cache 表 + repo_cache
- `backend/services/auth_middleware.py` — 扩展 git_token 字段 + repo-cache 端点
- `backend/app.py` — 修复 request 导入 + git_token 注入
- `backend/routers/code_analyze.py` — 传递 git_token
- `frontend/src/components/AppLayout.tsx` — LLM 配置→全局配置
- `frontend/src/components/LLMConfigProvider.tsx` — 加 Git Token 区域
- `frontend/src/pages/CodeAnalyze.tsx` — 可编辑仓库 URL/分支/路径 + 标签对齐 + 中文日期
- `frontend/src/api/codeAnalyze.ts` — 传 git_token + repo_cache 函数
- `frontend/src/main.tsx` — ConfigProvider locale={zhCN}

### 文档更新
- `docs/功能变更分析模块介绍.md` — 新增知识快照和 AST 分析详细说明章节

---

## 2026-07-03 · AST 信号验证层 + LLM type 修正

### AST 验证层（astValidator.ts）
- 新增集中 AST 验证层，在 ts-morph AST 节点上逐一检查正则提取的信号
- 验证逻辑：STATE_ACTION 排除 setTimeout/setInterval/setAttribute；API_CALL 检查 import 来源；PERMISSION 检查 IfStatement/BinaryExpression 条件；DATA_MODEL 检查真实声明节点；NEW_PAGE 检查 export default；STYLE_ONLY 检查是否有逻辑声明
- 保持轻量模式（skipFileDependencyResolution=true），仅加载 changed files
- 正则提取器保持不变，验证层独立

### LLM 输出加 type 字段
- Prompt 新增 type 修正规则，允许 LLM 修正 AST 分类
- 允许方向：STYLE_ONLY ↔ FEATURE_MODIFY、UI_INTERACTION → FEATURE_MODIFY
- 禁止方向：STYLE_ONLY → NEW_FEATURE
- 后端 `describe_group` 返回 {category, description, type}
- 输出构建时优先用 LLM type，兜底用 AST type

### 涉及文件
- `tools/code-analyzer/src/signals/astValidator.ts` — 新建
- `tools/code-analyzer/src/signals/extractor.ts` — 新增 project 参数 + 调用 validator
- `tools/code-analyzer/src/index.ts` — 创建 Project + 加载源文件 + 传递 project
- `backend/services/code_analyze_service.py` — LLM type 修正 + Prompt 更新

---

## 2026-07-03 · 修复 AST 验证器过度过滤

### 问题
- `astValidator.ts` 过度过滤：`useInstanceDetail.ts` 等有 Hook/逻辑的文件被归为 STYLE_ONLY，大量真实信号被移除
- 验证器策略是"找不到 AST 节点就移除信号"，过于激进

### 修复
- 验证器返回类型从 `boolean` 改为 `'keep' | 'remove'`，STYLE_ONLY 额外支持 `'replace'`
- 新增 `GENERIC_CHANGE` 信号类型，STYLE_ONLY 验证不通过时替换为 GENERIC_CHANGE
- 决策树处理 GENERIC_CHANGE → 归为 FEATURE_MODIFY
- 策略改为：不确定时保留信号，只移除明确能确认的假阳性

### 涉及文件
- `tools/code-analyzer/src/signals/astValidator.ts` — 重写验证逻辑
- `tools/code-analyzer/src/types.ts` — 新增 GENERIC_CHANGE
- `tools/code-analyzer/src/classify/decisionTree.ts` — 处理 GENERIC_CHANGE

---

## 2026-07-03 · 信号细粒度优化 + LLM 单步回归

### 信号细粒度优化（3 项优化完成）

#### 优化 1：聚类后拆分 constant/types 文件
- **问题**：`constant.ts`/`types.ts` 文案文件和 `index.tsx` 功能组件聚在同一组，LLM 描述时文案和功能混在一起
- **修复**：`cluster.ts` 新增 `splitTextFileClusters()` post-processing 函数，检测组内纯 `constant.ts`/`types.ts`/`contant.ts` 文件，拆成独立组
- 只拆分 3+ 文件的大簇，小簇保持完整

#### 优化 2：新增 TEXT_CHANGE / TYPE_CHANGE / TEST_CHANGE 信号类型
- **TEXT_CHANGE**：`constant.ts` 文件内容变更（字符串/对象字面量）→ 归为"文案变更"
- **TYPE_CHANGE**：`types.ts` 文件新增 interface/type/enum → 归为 INFRA_CHANGE
- **TEST_CHANGE**：`*.test.ts`/`*.spec.ts` 文件变更 → 单独展示
- 新增 `contentType.ts` 信号提取器

#### 优化 3：行号级信号定位
- `Signal` 类型新增 `line` 字段
- `extractor.ts` 在提取后自动匹配 addedLines 的前 30 字符填充行号

### LLM 优化：从两步回归单步

#### 背景
之前为了减少 LLM 报错，将 LLM 拆为两步（step1 概括 category + step2 展开 description），但两步调用导致：
- 报错率翻倍（两步各可能失败）
- 重复名称：失败组返回空 category → 多组重叠
- 分类不一致：step1 和 step2 可能对同一组有不同判断

#### 修复
- 回归单步调用 `describe_group()`，一次性输出 `{category, description, type}`
- `max_tokens` 从 1024(step2) 提升到 4096
- 重试机制：解析失败时自动重试 1 次
- 代码层 category→type 覆盖：`"新增"`/`"新建"` → NEW_FEATURE，`"移除"`/`"删除"` → FEATURE_REMOVAL
- Promp 明确约束："如果 category 以'新增'或'新建'开头，type 必须为 NEW_FEATURE"
- 失败兜底：文件名作为 category，error 信息作为 description

### 涉及文件
- `backend/services/code_analyze_service.py` — 重写 describe_group（单步+max_tokens=4096+重试+代码层覆盖）
- `tools/code-analyzer/src/signals/contentType.ts` — 新建
- `tools/code-analyzer/src/signals/extractor.ts` — 注册 contentType 信号 + 行号匹配
- `tools/code-analyzer/src/graph/cluster.ts` — 新增 splitTextFileClusters + mergePageLogicClusters
- `tools/code-analyzer/src/types.ts` — 新增 GENERIC_CHANGE / TEXT_CHANGE / TYPE_CHANGE / TEST_CHANGE + line 字段
- `tools/code-analyzer/src/classify/decisionTree.ts` — 处理新信号类型

---

## 2026-07-06 · PRD 智能生成模块 — MVP 全流程实现

### 前置准备
- **文档更新**：`PRD智能生成系统方案.md` 和 `PRD智能生成系统 MVP 实施方案.md` 完成技术栈适配（FastAPI→Flask，PostgreSQL→SQLite，Milkdown→react-markdown，Redis→SQLite 全量存储，JSONB→TEXT）
- **开发计划**：`PRD智能生成系统MVP开发计划.md` — 7 个 Phase，预计 5 天

### Phase 1: 数据库扩展 — 4 张表
- **prd_sessions** — 会话表（id, mode, status, user_input, collected_info TEXT, minutes_extract TEXT, outline TEXT, section_contents TEXT, completeness, current_round）
- **prd_versions** — 版本表（id, session_id, section, content, version_num），保留最近 3 版
- **prd_files** — 文件表（id, session_id, filename, file_type, storage_path, text_content）
- **prd_chat_messages** — 对话消息表（id, session_id, role, content, round）
- 全部使用 TEXT 类型存储 JSON 字符串，Python 层 `json.loads/dumps` 处理
- 2 个索引：`idx_prd_versions_session`、`idx_prd_messages_session`
- SQL 级别 CRUD 测试通过 ✅

### Phase 2: LLM 流式支持
- `llm_client.py` 新增 `chat_stream()` 方法，使用 `stream=True` 逐 token yield

### Phase 3: 后端核心服务
- `prd_gen_service.py` — `PRDGenService` 类
- **会话管理**：create/get/update session
- **简单模式**：大纲 → 逐章节 SSE 流式生成
- **中等模式**：问答轮次 → LLM 提取结构化信息 → 完备度检查 → 大纲 → 章节生成
- **信息完备度检查**：6 项核心信息，前 5 项必填，≥ 80% 达标
- **版本管理**：`save_prd_version` 自动保存快照 + `cleanup_old_versions` 保留最近 3 版
- **妙记解析**：复用 `feishu_client.get_minute_info()` + `get_transcript()`
- **文件上传**：支持 .md/.txt/.docx，≤10MB，临时/长期分类
- **导出**：按大纲顺序拼接完整 Markdown
- **JSON 解析容错**：4 层递进容错（标准→清理→尾随逗号→截断修复）
- `project_context.md` 默认模板创建

### Phase 4: Flask Blueprint
- `routers/prd_gen.py` — 13 个端点，统一注册 `/api/prd/*`
- `app.py` — 注册 `prd_gen_bp`

### Phase 5: 前端 API 层
- `api/prdGen.ts` — 13 个 API 函数 + 完整 TypeScript 类型定义
- SSE 接口复用 `streamRequest()`，导出接口用 `window.open()`

### Phase 6: 前端页面
- `pages/PrdGen.tsx` — 完整 PRD 生成工作台
- 布局：步骤条（4 步）→ 输入区（文字/妙记/文件 Tab）→ Q&A 区（中等模式）→ 大纲→ 编辑器+Diff 对比
- 覆盖 loading、empty、error、streaming 四种状态
- 章节生成按钮智能禁用（只禁用当前生成中的章节）
- Diff 对比使用 `react-diff-viewer-continued`
- 版本管理 Modal 展示版本列表 + 恢复操作

### Phase 7: 路由集成
- `App.tsx` — 新增 `/prd-gen` 路由
- `AppLayout.tsx` — 从 comingSoon 移到 activeNav

### 中间方案调整
- **`section_contents` 字段**：session 表新增 TEXT 字段存储章节内容，替代每次从版本表读取，提升编辑和导出性能
- **`update_prd_session` 自动 JSON 序列化**：`collected_info`/`minutes_extract`/`outline`/`section_contents` 传 dict/list 时自动 json.dumps
- **导出函数复用 outline 顺序**：按大纲章节顺序拼接，确保导出 PRD 结构正确
- **`react-diff-viewer-continued`**：使用社区维护版替代原 `react-diff-viewer`

### 涉及文件
- `backend/services/db.py` — 新增 4 张表 + 14 个 CRUD 函数
- `backend/services/llm_client.py` — 新增 `chat_stream()`
- `backend/services/prd_gen_service.py` — 新建
- `backend/services/project_context.md` — 新建
- `backend/routers/prd_gen.py` — 新建
- `backend/app.py` — 注册 blueprint
- `frontend/src/api/prdGen.ts` — 新建
- `frontend/src/pages/PrdGen.tsx` — 新建
- `frontend/src/App.tsx` — 新增路由
- `frontend/src/components/AppLayout.tsx` — 侧边栏

### 中等模式对话优化迭代（2026-07-06 持续）
- **参考方案**：参考 `prd-skeleton.md` 9 节模板，重构输出模板为 9 节
- **对话引导**：7 个话题按顺序引导，LLM 逐轮判断是否完成
- **Prompt 迭代**：多轮优化，核心约束：每轮一问、不问无关问题、避免重复、2-3 轮/话题、信息充分时推进
- **代码层兜底**：同话题超过 3 轮强制推进
- **用户确认闸口**：全部话题完成由用户确认是否开始生成
- **当前状态**：核心流程就绪，对话质量持续迭代中
- **涉及文件**：`prd_gen_service.py`、`prd_gen.py`、`PrdGen.tsx`、`prdGen.ts`

---

## 2026-07-06 · 代码变更分析优化

### 变更内容
1. **知识快照注入 LLM Prompt**（优先级 1）
   -  将知识快照格式化为路由/模块/API 摘要
   - 注入 ，LLM 现在能看到项目背景
   - 涉及文件：

2. **废弃 project_context.md**（优先级 3）
   - 删除 
   - 清除  中 、、 全部引用
   -  直接返回模板字符串
   - 涉及文件：、（已删除）

3. **GitLab Token 记录**
   - 保存到 


---

## 2026-07-06 · 代码变更分析优化

### 变更内容
1. **知识快照注入 LLM Prompt**（优先级 1）
   - `_format_snapshot_context()` 将知识快照格式化为路由/模块/API 摘要
   - 注入 `group_prompt`，LLM 现在能看到项目背景
   - 涉及文件：`backend/services/code_analyze_service.py`

2. **废弃 project_context.md**（优先级 3）
   - 删除 `backend/services/project_context.md`
   - 清除 `prd_gen_service.py` 中 `_PROJECT_CONTEXT_PATH`、`_load_project_context()`、`_project_context_cache` 全部引用
   - `_build_system_prompt()` 直接返回模板字符串
   - 涉及文件：`backend/services/prd_gen_service.py`、`backend/services/project_context.md`（已删除）

3. **GitLab Token 记录**
   - 保存到 `memory/gitlab-token.md`

---

## 2026-07-08 · 代码变更分析前端优化 + PRD 模块准备

### 代码变更分析前端优化
- **移除"刷新知识快照"按钮**：删除了 `refreshSnapshot`、`getSnapshotInfo`、`ReloadOutlined` 相关全部代码
- **横向 Steps 流水线**：Steps 改为默认横向，右侧显示状态标签（如"6/8 步完成"）
- **配置区 UI 美化**：两行布局，图标前缀（GitHub/Branch/Calendar/Folder），小标签说明，圆角输入框
- **整体色系**：`#6366f1` 紫蓝色主色，`#f5f5ff` 背景
- **新增 `user_visible` 过滤**：前端过滤 `user_visible === false` 的条目
- **TypeScript 类型修正**：`user_visible` 类型从 `boolean` 改为 `boolean | "partial"`
- 前端 TypeScript 编译零错误 ✅

### 涉及文件
- `frontend/src/pages/CodeAnalyze.tsx` — 重写（移除刷新按钮、横向 Steps、美化配置区、主题色）
- `frontend/src/api/codeAnalyze.ts` — `user_visible` 类型改为 `boolean | "partial"`

---

## 2026-07-10 · 功能变更分析模块全面优化

### 问题背景
功能变更分析模块存在多个问题：AST 分析秒过、git fetch 失败、合并不稳定（有时过度合并 108→8 条，有时完全不合并）、提取 prompt 信息不足、取消不生效、提取遗漏（全局搜索缺失）、日志不实时、去重效果差、过滤不彻底。

### 修复清单

#### 1. 提取 prompt 增强
- **输入**：`file_content`（第一文件前 50 行）→ `diff_snippets`（每个文件的 git diff patch，含前后各 50 行上下文）
- **新增**：`signal_details`，传具体 API 路径、状态名、路由名等细节
- **max_tokens**：4096 → 8192
- **diff 上下文**：`git diff -U50`（前后各 50 行），AST 工具截断到 5000 字符
- 涉及文件：`backend/services/code_analyze_service.py`、`tools/code-analyzer/src/snippet/extractSnippet.ts`

#### 2. 合并策略重写（三级流水线）
- **Level 1 目录聚类**：按 `pages/xxx` 模块名聚类，`page-logic/` 归一化为 `pages/`
- **Level 2 堆内 LLM 合并**：每堆独立调用 LLM
- **Level 3 全量二次合并**：直接全局语义合并，不再依赖证据文件匹配
- **新增 prompt 规则**：同类操作跨页面合并（如多个埋点条目合并为一条）
- 涉及文件：`backend/services/code_analyze_service.py`

#### 3. 过滤 prompt 加强
- 明确列出反例（纯枚举/常量/类型定义变更、纯参数调整、代码重构/重命名）
- 改"拿不准时归入 keep" → "拿不准时不要默认归入 keep"
- 涉及文件：`backend/services/code_analyze_service.py`

#### 4. git fetch 修复
- `git fetch --all --prune` → `git fetch origin +refs/heads/*:refs/heads/* --prune --force`
- 失败后自动 re-clone
- 删除 stale commit cache
- 涉及文件：`backend/services/code_analyze_service.py`

#### 5. 日志实时化
- `print()` 输出被 pipe 缓冲 → `sys.stdout.reconfigure(line_buffering=True)`
- 每步加时间戳日志 `[CodeAnalyze] [HH:MM:SS] 步骤名 (耗时)`
- AST 子进程加 retcode、耗时、stdout/stderr 日志
- 涉及文件：`backend/services/code_analyze_service.py`

#### 6. 中间结果保存（调试用）
- 保存 per-group LLM 结果 → `{task_id}_llm_per_group.json`
- 保存合并前后列表 → `{task_id}_merge_pipeline.json`
- 保存最终结果 → `{task_id}_llm_final.json`
- 涉及文件：`backend/services/code_analyze_service.py`

#### 7. 前端路径默认值
- `['apps/algorithm/ml-data']` → `['apps/algorithm/ml-data', 'apps/algorithm/ml-main']`
- 补全全局搜索（GlobalSearch）等功能提取
- 涉及文件：`frontend/src/pages/CodeAnalyze.tsx`

#### 8. 前端文件展示限制
- 证据文件最多展示 20 个，超出显示 "+N 个文件"
- 涉及文件：`frontend/src/pages/CodeAnalyze.tsx`

### 涉及文件
- `backend/services/code_analyze_service.py` — 提取 prompt、合并策略、过滤、fetch、日志、调试保存
- `backend/routers/code_analyze.py` — 移除不存在的 `request.is_disconnected()`
- `tools/code-analyzer/src/snippet/extractSnippet.ts` — diffHunk 截断 1000→5000 字符
- `frontend/src/pages/CodeAnalyze.tsx` — 默认路径双项、文件展示限制 20 个
- `docs/功能变更分析模块介绍.md` — 同步更新文档

---

## 2026-07-08 · PRD 模块状态总览

### 当前状态
- 完整前后端链路已搭建（Phase 1-7 全部完成）
- 两种模式：简单模式（大纲→逐章节流式）、中等模式（7 话题问答引导→大纲→章节）
- 9 节输出模板（Overview/Background/Stories/Requirements/Design/Technical/Rollout/Questions/Appendix）
- 信息完备度检查、版本管理（最近 3 版）、Diff 对比、妙记解析、文件上传、导出
- 中等模式对话质量仍在迭代中（4 轮迭代后暂停，切换回前端优化）

### Prompt 深度优化（2026-07-08）
- **系统 Prompt**：从"你是机器学习平台的产品需求文档撰写助手"升级为"资深产品经理" persona，增加 5 条质量标准（精确性/完整性/可执行性/结构化/数据驱动）和 6 条写作原则
- **大纲 Prompt**：从纯章节列表改为 `{id, focus}` 结构，每章带核心方向说明
- **9 章节 Prompt 全部重写**：每章增加：
  - 详细子节结构（3-4 个子节，含具体示例）
  - 质量门禁（✅ 要求 / ❌ 禁止）
  - 反模式约束（如"需求题不能没有优先级标注"）
  - 具体示例（如用户故事章节带完整 US-001 示例）
- **妙记提取 Prompt**：增加 `existing_workflow`、`pain_points` 字段，添加过滤规则（过滤寒暄/会议流程/非技术讨论）
- 涉及文件：`backend/services/prd_gen_service.py`

### 中等模式话题转换视觉优化（2026-07-08）
- **修复前后端话题名不对齐**：前端 `topicLabels` 之前是硬编码的 7 个不同名字，与后端 `_QUESTION_TOPICS` 不匹配，现在统一用 `TOPIC_STEPS` 常量对齐
- **新增话题流水线 Steps**：对话区顶部横向 7 步进度条，已完成 ✅ / 当前 ⏳ / 待开始
- **话题切换分隔线**：话题切换时自动插入紫色 Tag 分隔线 "🎯 进入话题：XXX"
- **当前话题高亮**：当前话题的消息气泡带紫色左边框 + 浅蓝背景
- **话题进度指示**：当前话题卡片显示 "💬 当前话题：XXX（3/7）"
- **ChatMsg 接口扩展**：新增 `topic` 字段，追踪每条消息所属话题
- 涉及文件：`frontend/src/pages/PrdGen.tsx`

### 中等模式话题推进逻辑优化（2026-07-08）
- **关键词强制推进**：用户说"下一话题/继续/跳过"等关键词 → `force_advance = True`，直接进入下一话题，不给 LLM 判断机会
- 关键词列表：`下一话题, 下一个, 继续, 跳过, next topic, 进入下一话题, 换话题, 够了`
- **Prompt 告知 LLM**：`_QUESTION_PROMPT` 新增第 7 条规则，告知 LLM 用户可以说"下一话题"
- 原有 3 轮上限兜底保留（双重保障）
- 涉及文件：`backend/services/prd_gen_service.py`

### 中等模式全部话题完成后的回顾审查屏（2026-07-08）
- **新增回顾审查屏**：全部 7 话题完成后不再直接跳转大纲，而是展示所有话题列表（✅ + 话题名 + 回答条数）
- **"修改"按钮**：每个话题右侧有"修改"按钮，点击触发 `rechat_topic`，重新进入该话题讨论
- **后端新增 `rechat_topic()`**：将指定话题从 `completed_topics` 移除，回退 `_current_topic_idx`，LLM 根据历史对话生成承上启下的引导问题
- **新增端点**：`POST /api/prd/sessions/{id}/rechat-topic`
- 涉及文件：`backend/services/prd_gen_service.py`、`backend/routers/prd_gen.py`、`frontend/src/pages/PrdGen.tsx`、`frontend/src/api/prdGen.ts`

### 章节生成注入前序章节内容摘要（2026-07-08）
- **新增 `_build_preceding_sections_text()`**：按大纲顺序提取已生成的前序章节，取前 150 字摘要，注入 Prompt
- **注入内容**：章节名称 + 前 150 字摘要 + 一致性约束
- **效果**：后续章节能看到前面章节写了什么，避免矛盾和不一致
- **简单模式 & 中等模式**都受益（`simple_generate()` 和 `generate_section()` 均修改）
- **Prompt 变更**：每个章节 Prompt 现在包含 `collected_info（三来源）+ 前序章节摘要 + 一致性约束`
- 涉及文件：`backend/services/prd_gen_service.py`
- 涉及文件：`frontend/src/pages/PrdGen.tsx`
