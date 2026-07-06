# 前端代码时间段变更分析模块 — 技术设计文档

> **版本**：V1.3  
> **关联项目**：AI 中控台（Flask + React）  
> **分析目标仓库**：`algorithm-monorepo`（GitLab）  
> **状态**：已评审，待开发

---

## 一、概述

### 1.1 目标

在 AI 中控台内新增**前端代码变更分析**模块。给定 GitLab 仓库地址和时间段，自动拉取该时间段最旧和最新的代码，通过 AST 信号提取 + LLM 语义归纳，生成业务级功能变更报告。

### 1.2 核心能力

- 指定时间段 → 自动定位 Base/Target commit
- 双版本 Worktree 检出 → Diff 三件套
- 10 类 AST 信号提取 → Import Graph 聚类 → 优先级决策树分类
- 项目知识快照辅助 LLM 语义归纳
- 区分"功能变更" vs "纯 UI/样式调整"
- SSE 流式推送进度，沿用中控台现有模式

### 1.3 分析目标仓库

| 属性 | 值 |
|------|-----|
| 仓库地址 | `https://gitlab.shizhuang-inc.com/du-monorepo/algorithm-monorepo.git` |
| 分支 | `master` |
| 分析路径 | `apps/algorithm/ml-main`（主应用壳）、`apps/algorithm/ml-data`（业务子应用）、`apps/algorithm/_share`（共享组件/工具包） |
| 技术栈 | React 18 + TypeScript 5 + Umi Max 4 + Ant Design 5 + CSS Modules + qiankun 微前端 |

---

## 二、总体架构

### 2.1 三层漏斗模型

```
┌──────────────────────────────────────────────────────────┐
│                     AI 中控台 (Flask)                      │
│  POST /api/code-analyze/start  (SSE 流式响应)             │
│  ┌────────────────────────────────────────────┐          │
│  │ Orchestrator (code_analyze_service.py)      │          │
│  │  1. git fetch — bare repo 增量更新           │          │
│  │  2. resolve_commits — 定位 base/target      │          │
│  │  3. worktree checkout — 双版本并发检出       │          │
│  │  4. generate_diff — Diff 三件套             │          │
│  │  5. → subprocess Node.js CLI (AST 分析)     │          │
│  │  6. → LLM 语义归纳 (复用中控台配置)          │          │
│  │  7. cleanup — 清理 worktree + 返回结果      │          │
│  └────────────────────────────────────────────┘          │
└──────────────────────┬───────────────────────────────────┘
                       │ subprocess (--output 文件)
┌──────────────────────▼───────────────────────────────────┐
│  Node.js CLI (tools/code-analyzer/)                       │
│  ts-morph (no TypeChecker) → 10 类信号                    │
│  Import Graph 连通分量聚类 → Feature Group                │
│  双版本 Snippet 截取 (before/after)                       │
│  项目知识快照生成                                          │
│  输出: 结构化 JSON                                        │
└──────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 技术 | 职责 |
|------|------|------|
| Flask 编排器 | Python + git 命令 | 全生命周期管理，Git 操作，LLM 调用 |
| Node.js CLI | TypeScript + ts-morph | AST 信号提取，Import Graph 聚类，Snippet 截取，知识快照生成 |
| 前端页面 | React + Ant Design | 时间段选择，触发分析，SSE 进度展示，结果报告 |

---

## 三、Node.js CLI 工具 (tools/code-analyzer/)

### 3.1 目录结构

```
tools/code-analyzer/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts                # 入口: 参数解析 → 流程编排 → JSON 输出
│   ├── types.ts                 # 所有类型定义
│   ├── git/
│   │   └── parsePatch.ts        # 解析 raw.patch → HunkInfo[]
│   ├── signals/
│   │   ├── extractor.ts         # 10 类信号总入口
│   │   ├── routes.ts            # NEW_ROUTE / NEW_PAGE
│   │   ├── api.ts               # API_CALL
│   │   ├── state.ts             # STATE_ACTION
│   │   ├── permission.ts        # PERMISSION
│   │   ├── hooks.ts             # HOOK_DEF
│   │   ├── event.ts             # EVENT_HANDLER
│   │   ├── dataModel.ts         # DATA_MODEL
│   │   ├── config.ts            # CONFIG_CHANGE
│   │   └── style.ts             # STYLE_ONLY + 样式纯净度验证
│   ├── graph/
│   │   ├── importGraph.ts       # Import Graph 构建
│   │   └── cluster.ts           # 连通分量聚类
│   ├── classify/
│   │   └── decisionTree.ts      # 优先级覆盖决策树
│   ├── snippet/
│   │   └── extractSnippet.ts    # 双版本行号对齐 + 函数级 Snippet
│   └── knowledge/
│       └── snapshot.ts          # 项目知识快照生成
```

### 3.2 CLI 接口

```bash
# 常规分析模式
node tools/code-analyzer/dist/index.js \
  --base BASE_PATH \
  --target TARGET_PATH \
  --frontend-paths "apps/algorithm/ml-main,apps/algorithm/ml-data,apps/algorithm/_share" \
  --diff-dir DIFF_DIR \
  --output /tmp/analyze_task_result.json \
  --mode analyze

# 知识快照模式（仅生成项目知识快照）
node tools/code-analyzer/dist/index.js \
  --target TARGET_PATH \
  --frontend-paths "apps/algorithm/ml-main,apps/algorithm/ml-data,apps/algorithm/_share" \
  --output /tmp/analyze_task_snapshot.json \
  --mode snapshot
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--base` | analyze 模式 | Base 版本 worktree 路径 |
| `--target` | 是 | Target 版本 worktree 路径 |
| `--frontend-paths` | 是 | 逗号分隔的前端子路径（如 `apps/algorithm/ml-main,apps/algorithm/ml-data,apps/algorithm/_share`） |
| `--diff-dir` | 是 | Flask 生成的 diff 文件目录 |
| `--output` | 是 | 结果 JSON 输出路径 |
| `--mode` | 是 | `analyze` 或 `snapshot` |

**输出：写入 `--output` 指定路径的 JSON 文件**，Flask 编排器读取文件获取结果。stdout 留给进度日志（可选，被 SSE 转发），stderr 留给错误信息。异常时 exit code 非 0。

**重要约束：**
- 所有 `--frontend-paths` 下的变更文件加载到**同一个 ts-morph Project 实例**中。路径别名解析需覆盖所有 frontend-paths 和 shared packages 的路径映射，确保 Import Graph 不会在路径边界处断裂。
- `@@/` 路径别名指向 `src/.umi/`（Umi 自动生成目录），须排除在分析之外。
- workspace 包（`@algorithm/*`）通过 monorepo 路径映射解析，不依赖 `node_modules`。

### 3.3 10 类 AST 信号

| 信号 | 优先级 | AST 匹配逻辑 |
|------|--------|-------------|
| NEW_ROUTE | P0 | 两模式覆盖：<br>① **Umi 配置式路由**：解析 `config/config.ts` 中 `defineConfig({ routes: [...] })` 的 `routes` 数组。递归提取每个路由对象的 `{ path, component }`，Base 和 Target 版本分别解析为 RouteNode[]，按 path 做 join 对比：仅在 Target 中出现的 path → NEW_ROUTE；path 相同但 component 不同的 → 路由指向变更（功能修改）<br>② **JSX 路由**：`Route` 组件的 `path` prop 变更，或 `createBrowserRouter` 新增对象<br><br>**轻量兜底**：Phase 1a 可先对 `config/config.ts` 的 diff hunk 做文本级分析，在 `+` 行搜索 `"path":` 或 `path:` 模式提取新增路由值，跑通后再升级为完整树 diff |
| NEW_PAGE | P0 | 新增文件在 `pages/` 目录，存在 `export default` 组件 |
| API_CALL | P1 | CallExpression: `axios.get/post/put`、`fetch(`、`request(`、`api.post`、`useRequest` |
| STATE_ACTION | P1 | useState setter 调用、`dispatch(`、`commit(`、defineStore actions |
| PERMISSION | P1 | 条件表达式中出现 `role`、`permission`、`auth`、`isAdmin`、`hasAccess` |
| HOOK_DEF | P1 | 函数名以 `use` 开头，体内调用其他 Hook |
| EVENT_HANDLER | P2 | JSX 属性 `onClick`、`onSubmit`、`onChange` 等 |
| DATA_MODEL | P2 | InterfaceDeclaration、TypeAliasDeclaration、EnumDeclaration 新增或修改 |
| CONFIG_CHANGE | P2 | `.env*`、`vite.config.*`、`config/config.ts` 等配置文件变更 |
| STYLE_ONLY | P3 | 纯样式文件或样式纯净度验证通过 |

### 3.4 文档上下文收集

在 Snippet 截取阶段，对每个 P0/P1 文件提取以下三类文档上下文，辅助 LLM 理解功能语义：

```typescript
interface DocContext {
  jsDoc: string[];            // 文件中导出函数/类的 JSDoc 注释
  testDescriptions: string[]; // 对应测试文件的 describe/it 文本
  readme: string | null;      // 同目录 README 前 50 行（如有）
}
```

- **JSDoc**：ts-morph 内置 `node.getJsDocs()` API，禁用 TypeChecker 也不影响
- **测试描述**：根据文件路径推断测试文件位置，用正则提取 `describe`/`it`/`test` 文本
- **README**：检查文件所在目录及父目录是否有 `README.md`

`doc_context` 作为 Feature Group 的附加字段输出到 JSON 中，注入 LLM 输入。

### 3.5 技术约束

- **ts-morph 轻量模式**：不指定 `tsconfig.json`，不加载 `node_modules`，`useInMemoryFileSystem: true`
- **零外部依赖**（除 ts-morph 外）：不依赖分析目标项目的 `node_modules`
- **路径别名解析**：读取 `tsconfig.json` 的 `paths` 字段和 `vite.config.ts` 的 `resolve.alias`

---

## 四、项目知识快照

### 4.1 生成方式

纯静态 AST 扫描，零 LLM 调用。5-10 秒完成，磁盘 ~50KB。

### 4.2 快照内容

```json
{
  "project_name": "algorithm-monorepo",
  "generated_at": "2026-07-01T10:00:00+08:00",
  "applications": [
    {
      "name": "ml-main",
      "path": "apps/algorithm/ml-main",
      "role": "qiankun master",
      "routes": [
        { "path": "/main", "component": "layouts/index", "description": "主布局" }
      ],
      "api_modules": [],
      "components": ["GlobalErrorCollector", "LogViewer"],
      "modules": ["layouts", "qiankun", "stores", "hooks"]
    },
    {
      "name": "ml-data",
      "path": "apps/algorithm/ml-data",
      "role": "qiankun slave",
      "routes": [
        { "path": "/dataApp/resourceManagement/list", "description": "资源管理列表页" },
        { "path": "/dataApp/sampleManagement/list", "description": "样本管理列表页" },
        { "path": "/dataApp/modalTraining/list", "description": "模型训练列表页" },
        { "path": "/dataApp/onlineService/list", "description": "在线服务列表页" }
      ],
      "api_modules": [
        { "name": "resourceManagement", "endpoints": ["createResource", "listResources", "deleteResource"] },
        { "name": "sampleManagement", "endpoints": ["createSample", "listSamples", "deleteSample"] },
        { "name": "modalTraining", "endpoints": ["createTask", "listTasks", "stopTask"] }
      ],
      "components": ["DynamicForm", "GlobalStateContainer"],
      "modules": ["resourceManagement", "sampleManagement", "modalTraining", "onlineService"]
    }
  ],
  "shared_packages": [
    {
      "name": "@algorithm/basic",
      "path": "apps/algorithm/_share/components",
      "components": ["AppModal", "UserSelector", "FeiShuUserCard"]
    },
    {
      "name": "@algorithm/request",
      "path": "apps/algorithm/_share/utils",
      "exports": ["request", "getBaseUrl"]
    }
  ]
}
```

### 4.3 生成时机

- **首次任务前**自动生成
- **用户手动刷新**（页面上的"刷新知识库"按钮）
- **自动过期**：快照超过 3 天自动重新生成，在 `ensure_knowledge_snapshot()` 中检查 `generated_at` 字段

---

## 五、Flask 编排器

### 5.1 文件清单

```
backend/
├── routers/
│   └── code_analyze.py           # Blueprint: /api/code-analyze/*
└── services/
    └── code_analyze_service.py    # 编排器
```

### 5.2 API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/api/code-analyze/start` | 创建分析任务（SSE 响应） |
| `GET` | `/api/code-analyze/status/<task_id>` | 轮询任务状态 |
| `POST` | `/api/code-analyze/refresh-snapshot` | 手动刷新知识快照（SSE 响应） |
| `GET` | `/api/code-analyze/snapshot` | 获取当前知识快照信息 |

### 5.3 POST /api/code-analyze/start

**请求：**
```json
{
  "repo_url": "https://oauth2:TOKEN@gitlab.shizhuang-inc.com/du-monorepo/algorithm-monorepo.git",
  "branch": "master",
  "frontend_paths": ["apps/algorithm/ml-main", "apps/algorithm/ml-data"],
  "start_time": "2026-06-25T00:00:00+08:00",
  "end_time": "2026-06-30T23:59:59+08:00"
}
```

**SSE 事件流：**
```
event: progress  → 当前步骤 + 百分比
event: section_complete  → 某步骤完成 + 中间数据
event: complete  → 分析完成 + 完整报告
event: error  → 分析失败 + 错误信息
```

### 5.4 编排器流程

```
1. init_task() → 生成 task_id，初始化状态
2. ensure_knowledge_snapshot()
   → 快照不存在或超过 3 天? 调用 Node.js CLI --mode snapshot
3. git_fetch()
   → 检查 /data/git-cache/algorithm-monorepo.git 是否存在
   → 不存在: git clone --mirror (超时 600s)
   → 存在: git fetch --all --prune (超时 120s)
   → 所有 git 命令指定 cwd=/data/git-cache/algorithm-monorepo.git
4. resolve_commits()
   → base = git rev-list --before="start_time" -n 1 refs/heads/${branch}
   → target = git rev-list --before="end_time" -n 1 refs/heads/${branch}
   → 校验 base ≠ target
   → cwd=/data/git-cache/algorithm-monorepo.git
5. collect_commit_messages()
   → git log --format="%s" ${base}..${target} -- ${frontend_paths}
   → stdout 按行读取，存入 commit_messages 列表
   → cwd=/data/git-cache/algorithm-monorepo.git
6. checkout_worktree()
   → task_id_safe = task_id.replace(/[^a-zA-Z0-9_-]/g, '_')  # 去掉特殊字符
   → cwd=/data/git-cache/algorithm-monorepo.git
   → git worktree add /tmp/analyze_{task_id_safe}_base {base}
   → git worktree add /tmp/analyze_{task_id_safe}_target {target}
7. generate_diff()
   → 对每个 frontend_path:
     git diff --name-status --find-renames=80% $BASE $TARGET -- "$FRONTEND_PATH" \
       ':!package-lock.json' ':!yarn.lock' ':!pnpm-lock.yaml' \
       ':!*.min.js' ':!*.map' ':!node_modules/' ':!dist/' ':!build/' \
       ':!__snapshots__/' ':!coverage/' > file_changes.txt
     → 同理生成 numstat 和 raw.patch
   → 重命名文件 (R080+) 标记 isRenameOnly=true，归为 REFACTOR
   → page-logic/ 不在 diff 层排除，改在结果层去重（见 5.8）
8. ast_analysis()
   → subprocess.run(["node", "tools/code-analyzer/dist/index.js",
       "--base", worktree_base,
       "--target", worktree_target,
       "--diff-dir", diff_dir,
       "--frontend-paths", "apps/algorithm/ml-main,apps/algorithm/ml-data,apps/algorithm/_share",
       "--output", f"/tmp/analyze_{task_id}_result.json",
       "--mode", "analyze"],
       timeout=180)
   → 读取输出 JSON → feature_groups
9. llm_summarize()
   → 构建输入: 知识快照 + commit_messages + feature_groups + snippets
   → 调用 llm_client.py
   → JSON Schema 校验 → 降级
10. cleanup()
    → git worktree remove --force
    → 更新 task 状态为 completed
```

### 5.5 错误处理

| 场景 | 行为 |
|------|------|
| 时间段内无 commit | `event: error` → "指定时间段内无 commit" |
| 前端路径不存在 | `event: error` → "frontend_path X 在 target commit 中不存在" |
| Node.js CLI 超时 | 分析模式 180s 超时，快照模式 60s 超时，kill 子进程，返回 error |
| LLM 解析失败 | 降级为规则层结果，`llm_status: "failed"` |
| Worktree 清理失败 | 记录日志，不阻塞响应 |

### 5.6 安全约束

- **Git token 不在日志中打印**：`repo_url` 中 `oauth2:TOKEN@` 部分在日志中替换为 `***`
- **Git token 存储**：MVP 阶段请求体传递 token，后续改为环境变量存储，请求体只传仓库标识
- **Worktree 清理**：无论成功/失败，`finally` 块中强制清理 worktree
- **Worktree 孤儿清理**：编排器启动时扫描 `/tmp/analyze_*` 目录，清理上次残留的 worktree
- **任务超时**：首次 clone 600s，增量分析整体任务 360s 硬超时

### 5.7 SSE 断线重连策略

分析任务可能耗时 5 分钟以上（首次 clone），浏览器 SSE 可能因超时断连。策略：

- 前端 `EventSource` 设置 `withCredentials`，监听 `onerror` 事件
- 断连后自动重试，指数退避（1s, 2s, 4s, 8s, max 30s）
- 重连后调用 `GET /api/code-analyze/status/<task_id>` 获取当前进度
- status API 响应格式与 SSE progress 事件同构，前端可无缝切换：

```json
// GET /api/code-analyze/status/<task_id>
{
  "task_id": "task_abc123",
  "status": "running",
  "current_step": "ast_analysis",
  "step_index": 4,
  "total_steps": 6,
  "percentage": 65
}

// SSE event: progress 的 payload 格式
{
  "step": "ast_analysis",
  "step_index": 4,
  "total_steps": 6,
  "message": "正在执行 AST 信号提取...",
  "percentage": 65
}
```

### 5.8 注意事项

- **`page-logic/` 结果层去重**：ml-data 的 `src/page-logic/` 是 logic-sync 维护的 UI 逻辑镜像，变更来自 `src/pages/` 的同步复制。处理策略：
  - 同一 Feature Group 中同时有 `pages/X.tsx` 和 `page-logic/X.tsx` → 只保留 `pages/` 的信号和 Snippet，`page-logic/` 作为附属证据文件列出
  - 只有 `page-logic/` 变更无对应 `pages/` 变更 → 正常分析但 confidence 降低 0.1（可能是自动同步而非人工修改）
  - 实现层：Node.js CLI 在聚类完成后做一次去重扫描
- **`@@/` 路径别名处理**：`@@/` 指向 `src/.umi/`（Umi 自动生成目录）。在 `resolveAlias()` 中检测到 `@@/` 前缀时返回 `null`，Import Graph 构建时跳过无法解析的 import（不添加边）。孤立节点走目录聚类兜底。聚类时适当放宽粒度（如同 `pages/` 子目录下的文件归为一组）补偿 import 断裂导致碎片化。
- **`huatuo-attribute-web`**：目标仓库包含第 4 个应用（归因平台），当前未纳入分析范围。如需分析，需在 `frontend_paths` 中追加。
- **文件路径基准**：CLI 输出 JSON 中所有文件路径使用相对于 worktree 根目录的完整路径（如 `apps/algorithm/ml-data/src/pages/training/BatchImport.tsx`），避免多 frontend_path 下路径歧义。

---

## 六、前端页面

### 6.1 页面位置

- 路由：`/code-analyze`
- 侧边栏菜单项：`CodeAnalyzeOutlined` 图标 + "代码变更分析" 标签
- 放在 `comingSoonItems` 后的活跃菜单项

### 6.2 页面布局

```
┌─────────────────────────────────────────────────────┐
│  配置区 (Card)                                        │
│  ┌──────────────────────────────────────────────┐   │
│  │  repo_url: [固定显示, 不可编辑]                │   │
│  │  branch: [master ✓]  start_time: [DatePicker] │   │
│  │  end_time: [DatePicker]  frontend_paths: 勾选 │   │
│  │  □ ml-main  □ ml-data  □ 共享包               │   │
│  │  [刷新知识库] [开始分析]                        │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  进度区 (Card, 分析中显示)                           │
│  ┌──────────────────────────────────────────────┐   │
│  │  Steps 进度条 (同 AiMeasure)                  │   │
│  │  ├─ 拉取仓库 ✓                                │   │
│  │  ├─ 定位 commits ✓                            │   │
│  │  ├─ 检出代码 ◎                                │   │
│  │  ├─ 生成 diff ☐                               │   │
│  │  ├─ AST 分析 ☐                                │   │
│  │  └─ LLM 归纳 ☐                                │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  结果区 (Card, 分析完成后显示)                       │
│  ┌──────────────────────────────────────────────┐   │
│  │  Summary: 7 feature groups, 3 functional      │   │
│  │                                                │   │
│  │  Tab: 新增功能 / 功能修改 / 下线功能 / UI      │   │
│  │                                                │   │
│  │  --- 新增功能 ---                              │   │
│  │  🟢 训练任务批量导入  confidence: 0.92        │   │
│  │     新增 /training/batch-import 路由和页面     │   │
│  │     证据文件: BatchImport.tsx, api/training.ts│   │
│  │                                                │   │
│  │  --- 功能修改 ---                              │   │
│  │  🟡 导出权限放宽  confidence: 0.88            │   │
│  │     条件从 status===1 扩展为 status===1||5     │   │
│  │     证据文件: utils/export.ts                  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 6.3 交互流程

1. 用户进入页面，自动加载当前知识快照状态（如有）
2. 选择时间段 + 勾选分析路径 → 点击"开始分析"
3. SSE 连接建立，实时展示 Steps 进度
4. 分析完成 → 报告展示区渲染
5. 失败 → Alert 展示错误信息
6. "刷新知识库" → 独立 SSE 流程，仅刷新快照

### 6.4 使用的中控台现有模式

- `sse.ts` 的 `streamRequest` 函数（SSE 按 `\n\n` 切分）
- `Steps` 组件 + `status` 状态机（`pending` → `process` → `finish`/`error`）
- `llm_client.py` 的 LLM 调用（复用中控台已配置的 API Key / Base URL / Model）
- Ant Design `Card`、`DatePicker`、`Checkbox`、`Steps`、`Tag`、`Tabs`

---

## 七、LLM 语义归纳

### 7.1 输入数据结构

```json
{
  "projectContext": {
    "name": "Algorithm Monorepo",
    "domain": "机器学习模型训练与管理平台",
    "apps": {
      "ml-main": "主应用，负责布局、菜单、鉴权、空间切换",
      "ml-data": "子应用，负责资源管理、样本管理、模型训练、在线服务"
    }
  },
  "commit_messages": [
    "feat: add batch import for training tasks",
    "fix: adjust export permission for status=5"
  ],
  "feature_groups": [
    {
      "type": "NEW_FEATURE",
      "confidence": 0.92,
      "files": ["apps/algorithm/ml-data/src/pages/training/BatchImport.tsx"],
      "signals": ["NEW_PAGE", "API_CALL"],
      "snippet": {
        "before": null,
        "after": "export default function BatchImport() { ... }"
      },
      "doc_context": {
        "jsDoc": ["批量导入训练任务页面，支持 CSV 上传，单次限制 500 条"],
        "testDescriptions": ["should upload CSV and create training tasks"],
        "readme": null
      }
    }
  ]
}
```

### 7.2 System Prompt 要点

- 引用知识快照中的路由/API/模块名辅助识别功能归属
- 优先使用 `doc_context` 中的描述来命名和说明功能，snippet 作为验证和补充
- 要求输出具体业务值和字段名，禁止模糊词汇
- 区分 `user_visible: true/false`
- 输出仅限合法 JSON，JSON Schema 校验

### 7.3 Confidence 客观计算

不使用 LLM 自评分数，基于信号覆盖度计算：

- 基础分 0.5
- NEW_ROUTE + API_CALL 同时命中 → +0.2
- NEW_PAGE → +0.15
- 3 个以上文件参与 → +0.1
- 单文件单信号 → -0.2
- 含 UNKNOWN 信号 → -0.1

---

## 八、文件清单

### 8.1 新增文件

| 文件 | 说明 |
|------|------|
| `tools/code-analyzer/package.json` | Node.js CLI 依赖 |
| `tools/code-analyzer/tsconfig.json` | TypeScript 配置 |
| `tools/code-analyzer/src/index.ts` | CLI 入口 |
| `tools/code-analyzer/src/types.ts` | 类型定义 |
| `tools/code-analyzer/src/git/parsePatch.ts` | Patch 解析 |
| `tools/code-analyzer/src/signals/extractor.ts` | 信号提取入口 |
| `tools/code-analyzer/src/signals/routes.ts` | 路由/页面信号 |
| `tools/code-analyzer/src/signals/api.ts` | API 调用信号 |
| `tools/code-analyzer/src/signals/state.ts` | 状态变更信号 |
| `tools/code-analyzer/src/signals/permission.ts` | 权限信号 |
| `tools/code-analyzer/src/signals/hooks.ts` | Hook 定义信号 |
| `tools/code-analyzer/src/signals/event.ts` | 事件处理信号 |
| `tools/code-analyzer/src/signals/dataModel.ts` | 数据模型信号 |
| `tools/code-analyzer/src/signals/config.ts` | 配置变更信号 |
| `tools/code-analyzer/src/signals/style.ts` | 样式信号 + 纯净度验证 |
| `tools/code-analyzer/src/graph/importGraph.ts` | Import Graph 构建 |
| `tools/code-analyzer/src/graph/cluster.ts` | 连通分量聚类 |
| `tools/code-analyzer/src/classify/decisionTree.ts` | 决策树分类 |
| `tools/code-analyzer/src/snippet/extractSnippet.ts` | 双版本 Snippet 截取 |
| `tools/code-analyzer/src/knowledge/snapshot.ts` | 项目知识快照 |
| `backend/routers/code_analyze.py` | Flask Blueprint |
| `backend/services/code_analyze_service.py` | 编排器 |
| `frontend/src/pages/CodeAnalyze.tsx` | 前端页面 |
| `frontend/src/api/codeAnalyze.ts` | API 封装 |

### 8.2 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app.py` | 注册 `code_analyze_bp` |
| `frontend/src/App.tsx` | 新增 `/code-analyze` 路由 |
| `frontend/src/components/AppLayout.tsx` | 侧边栏新增菜单项 |

---

## 九、实施路线图

| 阶段 | 周期 | 交付内容 |
|------|------|---------|
| **Phase 1a** | 1.5 人日 | CLI 骨架 + 4 个核心信号（NEW_ROUTE、NEW_PAGE、API_CALL、STATE_ACTION）+ 决策树 + Snippet 截取 + 重命名检测 → 端到端链路跑通 |
| **Phase 1b** | 1.5 人日 | 补齐剩余 6 类信号（PERMISSION、HOOK_DEF、EVENT_HANDLER、DATA_MODEL、CONFIG_CHANGE、STYLE_ONLY 纯净度验证）+ Import Graph 聚类 + 文档上下文收集 |
| **Phase 2** | 1 人日 | 项目知识快照生成（`snapshot.ts`）+ 自动过期机制<br>**Benchmark**：用真实 algorithm-monorepo 仓库跑一次快照生成，验证 5-10 秒估算。如超过 30 秒，增加进度日志（stdout → SSE 转发）防前端卡死 |
| **Phase 3** | 1 人日 | Flask 编排器 + API 端点 + SSE 流式 + 文件传递输出模式 |
| **Phase 4** | 1 人日 | 前端页面 + 结果展示 + 路由/侧边栏集成 |
| **Phase 5** | 1 人日 | LLM 语义归纳集成 + Prompt 迭代 + 端到端测试 |

**总计约 7 人日。**

---

## 十、未涵盖范围（后续迭代）

- 增量 Commit 链分析（追踪功能添加又回滚）
- 变更影响面评估（Import Graph 计算受影响页面）
- 历史趋势分析（多次分析结果累积）
- 自定义信号规则引擎