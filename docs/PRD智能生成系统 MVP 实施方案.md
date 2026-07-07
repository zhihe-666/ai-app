# PRD智能生成系统 MVP 实施方案


**关联文档**：《PRD智能生成系统方案》
**目标范围**：实现简单模式与中等模式的完整功能链路

---

## 一、MVP 目标与范围

### 1\.1 核心目标

在 1 周内交付一个可用的 PRD 生成工作台，满足日常轻量需求。

### 1\.2 范围界定

|维度|MVP 纳入|MVP 不纳入（后续迭代）|
|---|---|---|
|**生成模式**|简单模式 \+ 中等模式|深度模式（Agent 流水线）|
|**输入源**|A1（文字需求）、A2（飞书妙记链接）、A3（文件导入 \+ 临时/长期分类）|—|
|**知识层**|平台架构快照（project\_context\.md 注入）|RAG 向量检索、GraphRAG 知识图谱|
|**模型层**|DeepSeek\-V4\-Flash（统一适配器）|DeepSeek\-V4\-Pro 强推理模型|
|**编排引擎**|FastAPI 异步直调（中等模式用状态机管理对话轮次）|LangGraph 状态图|
|**输出层**|Markdown PRD 导出|飞书云文档同步、JSON Schema 原型、Machine\-Readable Spec|
|**交互层**|流式打字机输出、按块编辑、Git\-like Diff 对比|冲突提示面板（无多源冲突场景）|

### 1\.3 用户故事

1. 作为算法工程师，我能输入一句话需求，30 秒内获得一份结构化 PRD 草稿。

2. 作为产品经理，我能通过 3\-5 轮引导式问答补充需求细节，然后按章节流式生成完整 PRD。

3. 作为用户，我能上传参考文件并标注为"临时参考"或"长期入库"。

4. 作为用户，我能对生成的 PRD 逐章节编辑、重新生成，并通过 Diff 视图确认修改。

5. 作为用户，我能将最终 PRD 导出为 Markdown 文件。

6. 作为用户，我能粘贴飞书妙记链接，系统自动提取会议中的需求要点，作为生成 PRD 的输入素材。

---

## 二、MVP 架构设计

MVP 采用简化版三层架构，省略知识层和模型层的复杂调度：

### 架构说明

- **无独立知识层**：MVP 阶段通过 `project_context.md` 文件直接注入 System Prompt。

- **无 LangGraph**：中等模式的对话轮次管理用 Flask + SQLite 实现轻量状态机，不引入编排引擎，不依赖 Redis。

- **无 Celery**：简单模式为同步流式响应，中等模式的流式生成同样走 SSE 直连，无异步队列需求。

- **飞书妙记复用**：复用现有 `meeting_todo_service.py` 中妙记链接解析代码（`lark-cli subprocess` 获取逐字稿 + LLM 二次抽象），无需重新对接飞书 API。

- **文件分类**：用户上传时显式标注"临时参考"或"长期入库"，临时文件存本地目录并在会话结束后提示是否保留。

- **LLM 适配器复用**：复用现有 `llm_client.py` + `LLMConfigProvider`，无需重新开发。已有 API Key / Base URL / Model 三件套管理 + SSE 流式支持。

---

## 三、详细功能设计

### 3\.1 简单模式

#### 3\.1\.1 交互流程

```
用户输入一句话需求 → 点击"生成" → 系统生成大纲（展示给用户确认）→ 逐章节流式输出 → 可编辑/导出
```

#### 3\.1\.2 后端逻辑

1. 接收用户文字输入 + 模式参数（`mode=simple`）。

2. 从 `project_context.md` 加载平台上下文，拼装 System Prompt。

3. 调用 LLM 生成 PRD 大纲（章节列表），返回给前端展示。

4. 用户确认大纲后，后端逐章节调用 LLM 流式输出，每章节完成时发送 `section_complete` 事件。

5. 生成完成后，将完整 PRD 文本存入 SQLite，关联会话 ID。

> **说明**：简单模式与中等模式阶段二流程相同，区别在于简单模式跳过对话轮次，直接基于用户输入生成大纲和章节内容。分章节生成比一次性输出质量更稳定，避免 LLM 在长内容中遗漏非功能需求等章节。

#### 3\.1\.3 Prompt 模板

**大纲生成 Prompt**：

```
[System]
你是机器学习平台的产品需求文档撰写助手。以下为平台背景信息：
{project_context}

[User]
请根据以下需求描述，生成 PRD 大纲（仅返回章节标题列表，JSON 格式）：
{
  "sections": ["overview", "roles", "features", "stories", "boundaries", "nonfunctional"]
}

需求描述：{user_input}
```

**章节生成 Prompt**（复用中等模式 Prompt 模板）：

```
[System]
你是机器学习平台的产品需求文档撰写助手。以下为平台背景信息：
{project_context}

已收集的需求信息：
{collected_info}

[User]
请撰写 PRD 的"{section_name}"章节。要求：
- 内容基于已收集的需求信息，不要臆造未提及的功能。
- 使用 Markdown 格式。
- 语言简洁、准确。
- 不要重复生成其他章节已包含的内容。
```

### 3\.2 中等模式

#### 3\.2\.1 交互流程

```
阶段一（定型）：系统引导 3-5 轮结构化问答 → 信息完备度达标 → 进入阶段二
阶段二（撰写）：展示大纲 → 用户逐章节触发流式生成 → 可随时编辑/重新生成 → 导出
```

#### 3\.2\.2 对话状态机设计

中等模式不引入 LangGraph，用 Redis 存储会话状态，FastAPI 管理流转：

#### 3\.2\.3 问答引导模板

每轮问答由系统根据当前缺失的信息项动态生成问题，而非固定脚本：

|轮次|信息项|引导问题示例|
|---|---|---|
|1|功能概述|"请简要描述这次需要实现的功能，它的核心目标是什么？"|
|2|用户角色|"这个功能主要面向哪些角色？如算法工程师、平台管理员。"|
|3|核心操作路径|"用户使用这个功能的主要操作步骤是什么？"|
|4|边界条件|"有没有特殊的限制条件？如训练任务并发上限、模型版本数量限制。"|
|5\+|补充缺失项|根据完备度检查结果，针对缺失项追问。|

#### 3\.2\.4 信息完备度检查

MVP 阶段采用简化版检查清单（6 项核心信息）：

|检查项|说明|缺失处理|
|---|---|---|
|功能概述|是否有一句话以上的功能描述|追问|
|用户角色|是否明确至少一个用户角色|追问|
|核心操作路径|是否描述了主要操作步骤|追问|
|边界条件|是否提及至少一个限制/约束|追问|
|输入输出|是否描述了功能的数据输入和输出|追问|
|依赖模块|是否提及依赖的已有平台模块|提示（可跳过）|

缺失项占比低于 20%（即至少 5/6 项完整）即可进入撰写阶段。

#### 3\.2\.5 阶段二：分章节流式生成

1. 系统根据阶段一收集的信息，生成 PRD 大纲（章节列表），展示给用户确认。

2. 用户确认大纲后，可逐章节点击"生成"，每个章节独立调用 LLM 流式输出。

3. 章节生成采用**串行模式**：用户点击指定章节 → 后端单线程生成 → SSE 流式返回。前端 UI 不阻塞其他章节的展示与操作，但后端在同一会话中不会并行处理多个章节的生成请求，避免对同一会话状态的竞态写入。

4. 用户在任一章节生成过程中可暂停、编辑文本，或点击"重新生成"。

5. 重新生成时，前端基于当前章节内容 + 新生成内容实时计算 Diff 对比，逐条确认修改。后端不存储 Diff 数据。

5. 重新生成时，系统展示 Git\-like Diff 对比视图，用户逐条确认修改。

#### 3\.2\.6 章节生成 Prompt 模板

```
[System]
你是机器学习平台的产品需求文档撰写助手。以下为平台背景信息：
{project_context}

已收集的需求信息：
{collected_requirements}

[User]
请撰写 PRD 的"{section_name}"章节。要求：
- 内容基于已收集的需求信息，不要臆造未提及的功能。
- 使用 Markdown 格式。
- 语言简洁、准确。
- 不要重复生成其他章节已包含的内容。
```

> **说明**：Prompt 末尾补充"不要重复生成其他章节已包含的内容"约束，防止 LLM 在生成"功能清单"章节时又写一遍"功能概述"已有内容。

### 3\.3 飞书妙记需求提取

#### 3\.3\.1 交互设计

1. 用户在输入页面粘贴飞书妙记链接（支持 `feishu.cn/minutes/` 格式）。

2. 系统自动解析链接，拉取妙记逐字稿、会议总结和待办事项。

3. 大模型对会议文本进行二次抽象，提取功能需求点、涉及的干系人和约束条件。

4. 提取结果展示在页面上，用户可确认或编辑后作为生成 PRD 的输入素材。

5. 妙记提取结果可独立使用，也可与 A1（文字需求）、A3（文件上传）组合使用。

#### 3\.3\.2 后端逻辑

|步骤|处理|
|---|---|
|链接校验|校验 URL 格式，提取 minute_token|
|调用飞书 API|**复用现有 `meeting_todo_service.py` 代码**：`feishu_client.get_minute_info()` 获取妙记元数据，`get_transcript()` 拉取逐字稿|
|文本预处理|清理逐字稿中的口语化表达、重复内容和无关寒暄|
|需求抽象|调用 LLM 适配器，将会议文本抽象为结构化需求要点（JSON 格式），复用现有 `llm_client.py` 调用逻辑|
|结果存储|将提取结果存入 SQLite sessions 表 `minutes_extract` 字段，关联会话 ID|
|注入上下文|生成 PRD 时，将妙记提取的需求要点拼接进上下文组装模块|

> **说明**：妙记解析功能完全复用现有代码。`meeting_todo_service.py` 中 `_fetch_minute_transcript()` 方法已实现 `lark-cli` subprocess 获取逐字稿的全链路，`feishu_client.py` 中 `get_minute_info()` 和 `get_transcript()` 方法可直接调用。无需重新对接飞书 API。

#### 3\.3\.3 需求提取 Prompt 模板

```
[System]
你是机器学习平台的需求分析助手。请从以下飞书会议纪要中提取与产品功能需求相关的信息。

[User]
会议纪要：
{minutes_text}

请提取以下信息，以 JSON 格式返回：
{
  "featurePoints": ["功能需求点1", "功能需求点2"],
  "stakeholders": ["涉及的干系人/角色"],
  "constraints": ["约束条件/限制"],
  "background": "需求产生的背景和动机"
}
```

#### 3\.3\.4 多源融合

当用户同时提供妙记链接和文字需求时，系统按优先级规则融合：

```
1. [当前手写文字需求] — 最高权威
2. [飞书妙记提取的需求要点] — 次高权威，作为补充背景
```

若两来源信息无冲突，直接合并注入；若存在冲突（如文字需求与妙记结论矛盾），以文字需求为准，妙记要点作为参考标注。

### 3\.4 文件上传与分类

#### 3\.4\.1 交互设计

1. 用户在输入页面上传文件（支持 \.md / \.txt / \.docx）。

2. 上传时弹窗提示选择分类："临时参考"或"长期入库"。

3. 选择"临时参考"的文件仅在当前会话中注入 Prompt，会话结束后提示是否转为长期。

4. 选择"长期入库"的文件存储到固定目录，标记为可供后续检索。

#### 3\.4\.2 后端逻辑

|步骤|处理|
|---|---|
|接收文件|Flask `request.files` 接收，校验格式与大小（≤10MB）|
|提取文本|\.md/\.txt 直接读取；\.docx 用 python\-docx 提取|
|分类标记|根据用户选择，在 sqlite 记录 `file_type: temporary / permanent`|
|临时文件|存储到 `/tmp/sessions/{session_id}/` 目录|
|长期文件|存储到 `/data/knowledge/permanent/` 目录|
|注入 Prompt|生成时将临时文件文本拼接进 User Prompt 的上下文段|

### 3\.5 PRD 编辑器

#### 3\.5\.1 核心功能

|功能|说明|
|---|---|
|Markdown 渲染|使用 react-markdown + remark-gfm 实时预览生成的 PRD 内容|
|分块编辑|PRD 按章节分块，每块可独立编辑|
|重新生成|对指定章节调用 LLM 重新生成，新内容流式返回|
|Diff 对比|重新生成时，**前端**基于当前章节内容 + 新生成内容实时计算 Diff，使用 react-diff-viewer 展示修改前/后对比，逐条接受/拒绝。后端不存储 Diff 数据|
|版本快照|每次重新生成前自动保存当前版本快照到 SQLite prd_versions 表，只保留最近 3 个版本（插入新版本时清理最旧版本）。回退操作通过读取指定版本的 content 字段实现|
|导出|一键导出完整 PRD 为 .md 文件，使用 GET 请求返回 Content-Disposition: attachment|

---

## 四、API 设计

### 4\.1 接口总览

|方法|路径|说明|
|---|---|---|
|POST|`/api/prd/sessions`|创建会话（指定模式）|
|POST|`/api/prd/sessions/{id}/simple-generate`|简单模式生成（SSE 流式）|
|POST|`/api/prd/sessions/{id}/chat`|中等模式对话轮次（返回引导问题）|
|GET|`/api/prd/sessions/{id}/completeness`|查询信息完备度|
|POST|`/api/prd/sessions/{id}/outline`|生成 PRD 大纲|
|POST|`/api/prd/sessions/{id}/sections/{section}/generate`|按章节流式生成（SSE）|
|PUT|`/api/prd/sessions/{id}/sections/{section}`|编辑章节内容|
|POST|`/api/prd/sessions/{id}/sections/{section}/regenerate`|重新生成章节（返回新内容，前端 Diff 对比）|
|GET|`/api/prd/sessions/{id}/versions`|获取版本快照列表（最近 3 版）|
|GET|`/api/prd/sessions/{id}/export`|导出 PRD Markdown 文件（`Content-Disposition: attachment`）|
|POST|`/api/prd/files/upload`|上传文件（带分类标记）|
|POST|`/api/prd/sessions/{id}/minutes`|解析飞书妙记链接，提取需求要点|

> **说明**：
> - 所有接口统一注册为 Flask Blueprint，url_prefix `/api/prd`
> - 导出接口使用 GET 方法，返回 `Content-Disposition: attachment` 文件流
> - SSE 流式接口继承现有 `utils/sse.ts` 的 `event: {type}\ndata: {json}\n\n` 格式

### 4\.2 关键接口详细设计

#### 4\.2\.1 创建会话

```
POST /api/prd/sessions
Request:
{
  "mode": "simple" | "medium",
  "userInput": "一句话需求描述（简单模式必填，中等模式可选）"
}
Response:
{
  "sessionId": "uuid",
  "status": "init" | "chatting" | "writing" | "done"
}
```

#### 4\.2\.2 简单模式生成（SSE）

简单模式跳过对话轮次，直接进入分章节生成流程：

```
POST /api/prd/sessions/{id}/simple-generate
Headers: Accept: text/event-stream
Response (SSE):
data: {"chunk": "## 功能概述\n"}
data: {"chunk": "本次需求实现..."}
data: {"chunk": "section_complete", "section": "overview"}
data: {"chunk": "## 用户角色\n"}
...
data: {"chunk": "done"}
```

后端先生成大纲，然后逐章节调用 LLM 流式输出（同中等模式阶段二），每个章节完成时发送 `section_complete` 事件。SSE 格式继承现有 `utils/sse.ts` 的 `event: {type}\ndata: {json}\n\n` 规范。

#### 4\.2\.3 中等模式对话

```
POST /api/prd/sessions/{id}/chat
Request:
{
  "answer": "用户对上一轮问题的回答"
}
Response:
{
  "round": 3,
  "question": "这个功能主要面向哪些角色？如算法工程师、平台管理员、数据科学家。",
  "infoItems": {
    "featureOverview": "已收集",
    "userRoles": "待收集",
    ...
  },
  "completeness": 0.5
}
```

后端根据当前轮次和已收集信息，动态生成下一个引导问题。当 `completeness >= 0.8` 时返回 `status: ready_for_outline`。对话状态存储在 SQLite sessions 表中，不依赖 Redis。

#### 4\.2\.4 章节流式生成（SSE）

```
POST /api/prd/sessions/{id}/sections/{section}/generate
Path: section = "overview" | "roles" | "features" | "stories" | "boundaries" | "nonfunctional"
Headers: Accept: text/event-stream
Response (SSE):
data: {"chunk": "## 功能概述\n"}
...
data: {"chunk": "done", "versionId": "v3"}
```

> **说明**：章节生成采用串行模式。用户逐章节点击触发生成，每个章节独立调用 LLM 流式输出，不阻塞其他章节的 UI 展示。重新生成时，前端基于当前内容 + 新内容实时计算 Diff 对比，不存储 Diff 数据。

#### 4\.2\.5 飞书妙记解析

```
POST /api/prd/sessions/{id}/minutes
Request:
{
  "url": "https://poizon.feishu.cn/minutes/xxxxx"
}
Response:
{
  "status": "success",
  "minuteTitle": "模型版本管理需求评审",
  "extractedPoints": {
    "featurePoints": ["模型注册", "版本对比", "灰度发布"],
    "stakeholders": ["算法工程师", "平台管理员"],
    "constraints": ["同一模型仅一个production版本"],
    "background": "当前模型管理缺乏版本控制，回滚困难"
  },
  "rawTranscriptLength": 15200,
  "warning": null
}
```

后端复用已有妙记解析代码，调用飞书 API 获取逐字稿后，通过 LLM 二次抽象提取结构化需求要点。提取结果存入会话上下文，供后续生成使用。

---

## 五、数据模型

### 5\.1 sqlite表设计

#### sessions 表

|字段|类型|说明|
|---|---|---|
|id|UUID PK|会话 ID|
|user_id|VARCHAR|用户标识|
|mode|VARCHAR(10)|生成模式（simple / medium）|
|status|VARCHAR(10)|会话状态（init / chatting / writing / done）|
|user_input|TEXT|用户输入的需求描述|
|collected_info|TEXT|中等模式收集的需求信息（JSON 字符串，Python `json.loads/dumps` 处理）|
|minutes_extract|TEXT|飞书妙记提取的需求要点（JSON 字符串）|
|current_round|INT|当前对话轮次|
|completeness|FLOAT|信息完备度（0-1）|
|outline|TEXT|PRD 大纲结构（JSON 字符串）|
|created_at|TIMESTAMP|创建时间|
|updated_at|TIMESTAMP|更新时间|

> **说明**：SQLite 不支持 JSONB 类型，所有结构化字段（collected_info、minutes_extract、outline）均使用 TEXT 类型存储 JSON 字符串，由 Python 层 `json.loads/dumps` 处理序列化与反序列化。

#### prd_versions 表

|字段|类型|说明|
|---|---|---|
|id|UUID PK|版本 ID|
|session_id|UUID FK|关联会话|
|section|VARCHAR|章节标识|
|content|TEXT|章节内容（Markdown）|
|version_num|INT|版本号（同一章节递增）|
|created_at|TIMESTAMP|创建时间|

> **说明**：版本管理简化设计：
> - 每次重新生成前自动保存当前版本快照
> - 只保留最近 3 个版本（插入新版本时删除最旧版本）
> - Diff 对比由前端基于当前内容 + 新内容实时计算，不存储 Diff 数据
> - 回退操作仅需读取指定版本的 content 字段即可

#### files 表

|字段|类型|说明|
|---|---|---|
|id|UUID PK|文件 ID|
|session_id|UUID FK|关联会话（临时文件）|
|filename|VARCHAR|原始文件名|
|file_type|VARCHAR(10)|分类标记（temporary / permanent）|
|storage_path|VARCHAR|存储路径|
|text_content|TEXT|提取的文本内容|
|created_at|TIMESTAMP|上传时间|

### 5\.2 状态管理说明

MVP 阶段**不引入 Redis**，所有状态存储在 SQLite 中：

- **对话状态**：存储在 `sessions` 表的 `status`、`current_round`、`collected_info` 字段中
- **对话历史**：新增 `chat_messages` 表，存储用户回答与系统问题列表
- **流式生成状态**：由前端维护，后端不存储流式状态

#### chat_messages 表

|字段|类型|说明|
|---|---|---|
|id|UUID PK|消息 ID|
|session_id|UUID FK|关联会话|
|role|VARCHAR(10)|消息角色（system / user）|
|content|TEXT|消息内容|
|round|INT|对话轮次|
|created_at|TIMESTAMP|创建时间|

---

## 六、技术选型（MVP 裁剪版）

### 6\.1 后端

|组件|方案|说明|
|---|---|---|
|**Web 框架**|Python Flask|与现有 AI 中控台一致，通过 Blueprint 注册 `/api/prd/*` 路由，SSE 流式使用 `Response(generator(), mimetype='text/event-stream')`|
|**LLM 适配器**|复用现有 `llm_client.py` + `LLMConfigProvider`|已有 API Key / Base URL / Model 三件套管理，支持多 Provider 预设，无需重新开发|
|**飞书妙记**|复用现有 `meeting_todo_service.py`|通过 `lark-cli` subprocess 获取逐字稿，LLM 二次抽象提取需求要点|
|**持久化**|SQLite|会话、PRD 版本、文件记录、妙记提取结果、对话历史|
|**缓存/状态**|SQLite（不引入 Redis）|对话状态、流式状态全部存储在 SQLite 表中，MVP 阶段无需 Redis|
|**文件存储**|本地文件系统|MVP 阶段不引入对象存储|

### 6\.2 前端

|组件|方案|说明|
|---|---|---|
|**框架**|React 19 + TypeScript + Vite|与现有 AI 中控台完全一致|
|**UI 组件库**|Ant Design 6|现有组件库，Tabs、Card、Form、Upload、Select 等直接可用|
|**Markdown 渲染**|react-markdown + remark-gfm|复用现有组件，支持实时预览与分块编辑|
|**SSE 流式接收**|复用现有 `utils/sse.ts`|基于 `fetch` + `ReadableStream`，支持 `event: {type}\ndata: {json}\n\n` 格式|
|**Diff 对比**|react-diff-viewer|代码级 Diff 展示|
|**文件上传**|antd Upload|文件上传与分类标记交互|
|**妙记输入**|自研|链接输入框 + 解析状态展示 + 提取结果确认|

### 6\.3 MVP 不引入的组件

|组件|原因|
|---|---|
|**LangGraph**|MVP 中等模式用 Flask + SQLite 状态机管理对话轮次即可|
|**Celery**|无异步队列需求，流式生成走 SSE 直连|
|**Redis**|对话状态全部存储在 SQLite，无需独立缓存层|
|**Chroma/Milvus**|MVP 不做向量检索，平台上下文通过 `project_context.md` 直接注入|
|**Neo4j/NetworkX**|MVP 不做知识图谱|
|**飞书云文档 API**|MVP 仅接入妙记解析，不接入云文档同步|
|**Milkdown**|使用现有 `react-markdown` 替代，减少依赖引入|

---

## 七、验收标准

|编号|验收项|通过标准|
|---|---|---|
|F1|简单模式生成|输入一句话需求，30 秒内开始流式输出，输出内容包含 6 个标准章节|
|F2|中等模式对话|系统引导 3\-5 轮问答，每轮问题与用户回答相关，非固定脚本|
|F3|完备度检查|6 项核心信息中缺失超过 1 项时，系统继续追问|
|F4|大纲生成|阶段一完成后生成大纲，用户可确认或调整|
|F5|分章节生成|用户点击章节后独立流式生成，不阻塞其他章节|
|F6|重新生成 \+ Diff|对已有章节重新生成后，展示修改前/后对比，可逐条接受|
|F7|版本回退|可查看历史版本并回退至任意版本|
|F8|文件上传|上传 \.md/\.txt/\.docx 文件，选择临时/长期分类，临时文件内容注入生成上下文|
|F9|飞书妙记解析|粘贴妙记链接后，系统提取出结构化需求要点（功能需求点/干系人/约束条件），可确认或编辑|
|F10|多源融合|同时提供妙记链接和文字需求时，系统按优先级规则融合，生成结果体现两来源信息|
|F11|导出|导出完整 PRD 为 \.md 文件，格式无损|

---

## 八、MVP 与完整方案的衔接

MVP 完成后，后续迭代按完整方案 Phase 2\-4 逐步叠加：

|MVP 已实现|后续迭代叠加|衔接方式|
|---|---|---|
|project\_context\.md 直接注入|RAG 向量检索|将 project\_context\.md 纳入知识库，新增向量检索 \+ Few\-shot 注入|
|Redis 轻量状态机|LangGraph 状态图|中等模式保持现有状态机；深度模式引入 LangGraph 编排 4 个 Agent|
|DeepSeek\-V4\-Flash 统一调用|双模型分流|LLM 适配器增加 DeepSeek\-V4\-Pro 路由逻辑|
|Markdown 导出|飞书云文档同步 \+ JSON Schema 原型 \+ Machine\-Readable Spec|在输出层增加并行输出通道|
|文件分类标记（仅存储）|向量化 \+ 图谱构建|将长期标记的文件批量导入向量库和图谱|
|妙记解析（复用已有代码）|多源冲突检测面板|引入 A2 与 A1/A3 组合使用后，在融合阶段增加冲突检测与提示面板|



> (注：内容由 AI 生成，请谨慎参考）
