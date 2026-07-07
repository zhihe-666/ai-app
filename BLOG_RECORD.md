# AI 中控台 — 博客叙事档案

> 写给博客读者看的：需求的来龙去脉、技术决策的 why、踩坑现场
> 每次有意义交互后追加，不要攒到 Phase 结束再写

---

## 1. 项目背景

**时间：** 2026-06-23
**来源：** 技术项目推进中，产品/研发/测试/反馈各环节信息散落在飞书文档、多维表格、聊天记录等多处。项目成员（尤其 PM / 运营）在会议纪要、进度汇总、周报撰写等重复性文档工作上消耗大量时间。
**目标：** 以无矩 2.0 为试点项目，构建一个 Web 端的 AI 项目中控台，MVP 聚焦四个已沉淀为 Skill / 脚本的功能模块，统一封装为 Web 界面。
**原始方案文档：** 由黎国友编写的《AI中控台-MVP完整实现方案.md》
**产品原型：** 一份 all-in-one.html 的 HTML 原型

---

## 2. 需求演变

### Episode 1: 项目初始化（2026-06-23）

**用户需求：** 根据方案文档和 HTML 原型，写具体项目实现 plan 文档，先核对审查。

**我的做法：**
1. 阅读完整方案文档（1877 行）和 HTML 原型（750 行）
2. 发现方案中后端用 FastAPI，但项目的 `dclaw.yaml` 被定义为 `flask-react` 类型 → 需要适配调整
3. 编写了 `IMPLEMENTATION_PLAN.md`，包含 6 个 Phase + 7 天排期

**关键决策：** 后端从 FastAPI 改为 Flask，因为部署平台固定了 flask-react 类型。

### Episode 2: 持久化规划（2026-06-23）

**用户需求：** 建立进度追踪和项目记忆，防止 LLM 上下文压缩丢失目标。

**我的做法：**
1. 创建 `task_plan.md` — 阶段追踪（每个 Phase 的 Tasks + checklist + 错误+决策记录）
2. 创建 `findings.md` — 研究发现和技术踩坑记录
3. 创建 `progress.md` — 进度日志（实时记录每次操作）

**思考：** 用户担心 LLM 的 20K 上下文压缩后目标丢失，所以用文件系统做"持久化存储"。

### Episode 3: Phase 0 骨架搭建（2026-06-23）

**用户需求：** 开始 Phase 0，搭建项目骨架。

**我的做法：**
1. 读出现有脚手架文件（Flask app.py 骨架 + Vite React 空项目）
2. **后端：** 升级 app.py 到 4 个 Blueprint 路由结构，创建 10 个接口桩（返回 501 待实现）
3. **前端：** 配置 BrowserRouter + basename（部署子路径必须），实现侧边栏布局，创建 4 个页面组件 + ComingSoon 弹窗 + Axios 实例 + SSE 封装 + 4 个 API 模块
4. **联调：** tsc 编译零错误、Vite build 成功、后端 5 个接口全部正常响应

**踩坑：** JSX 中的中文引号（" "）被当成了 JSX 属性分隔符，导致编译报错。需要换成 `{'...'}` 或 `{'>'}` 绕过。这说明 TypeScript 的 JSX 解析器对 Unicode 字符的处理需要注意。

### Episode 4: 博客素材需求（2026-06-23）

**用户需求：** 希望保存博客素材，并且要求细粒度的文档更新时机，不能等到 Phase 结束再更新。

**我的做法：**
1. 创建本文件 `BLOG_RECORD.md`，作为博客叙事档案
2. 设计了一个"原子级文档更新协议"（详见 findings.md 中的 Document Update Protocol）
3. 协议核心：**每次有意义的操作后立即更新对应文档，不攒到 Phase 结束**

**思考：** 用户的担心是对的 — LLM 的上下文窗口约 20K，一段对话可能做很多事，上下文压缩后如果忘记更新文档，这些记录就丢了。所以文档更新必须和代码操作绑在一起，成为不可分割的原子操作。

### Episode 5: 唤醒协议的认知迭代（2026-06-23）

**用户质疑：** 你把更新协议写在 findings.md 里，但新会话不一定会主动读 findings.md，怎么办？

**我的做法：**
1. 承认漏洞 — 协议放在 findings.md 确实没有强制力
2. 把唤醒入口升级到 **MEMORY.md**（AGENTS.md 定义它为"长期记忆"，新会话有义务读取）
3. 在 MEMORY.md 中内置：
   - **新会话唤醒清单**：6 步读取顺序（MEMORY.md → task_plan → progress → findings → BLOG_RECORD → IMPLEMENTATION_PLAN）
   - **原子级文档更新协议完整版**：7 种更新时机 + 一句话规则
   - **项目文件索引**：所有关键文件的路径和用途
4. findings.md 中的协议转指向 MEMORY.md，避免信息分散

**反思：** 这是一个很好的设计迭代 — 把"我应该记得读"变成"系统强制我读"。AGENTS.md → MEMORY.md（唤醒清单 + 协议）→ 其他文件，形成了一条**不可跳过的读取链**。写博客时可以把这个过程称为"AI 工作记忆的分层存储"。

### Episode 5: Phase 1 公共基础设施（2026-06-23）

**用户需求：** Phase 1 开始，问是否需要提供什么。

**我的做法：** 确认用户不需要提供任何东西后直接开工，额外做了两个设计调整：

**调整 1: LLM Token 全局管理**
用户要求"Token 只填一次，所有功能共用"。方案原是每个接口各自传 Token，改了设计：
1. **前端** — `TokenProvider` 上下文组件，Token 存 localStorage，axios interceptor 自动注入 `X-Access-Token` 请求头
2. **后端** — `before_request` 钩子自动从请求头提取 Token 注入 `g.access_token`，所有路由通过 `g.access_token` 获取
3. **首次引导** — 未配置 Token 时自动弹出配置弹窗，侧边栏底部有 Token 状态指示器
4. **验证** — `/api/auth/verify` 接口用 Token 调 LLM 列举模型来验证有效性

**调整 2: Ant Design 全局主题**
安装了 `antd` 后顺手配置了 `ConfigProvider` 统一主题色 `#6366f1`（和原型一致）。

**后端 4 个公共模块：**
| 模块 | 内容 |
|------|------|
| `sse_helpers.py` | `sse_event()` + `sse_stream()` — Flask SSE 封装 |
| `feishu_client.py` | `run_lark_cli()` 通用执行器 + 7 个飞书操作 |
| `llm_client.py` | `LLMClient` — OpenAI 兼容接口封装 |
| `models.py` | 6 个 dataclass 模型 |

### Episode 6: Phase 2 前端分屏交互实现（2026-06-23）

**用户需求：** 继续实现 Phase 2 前端部分 — 会议 TODO 提取的分屏交互页面，集成 SSE 流式展示，打通从妙记链接输入到待办展示到文档生成的完整流程。

**我的做法：**
1. **3 个新组件**：TranscriptPanel（逐字稿面板）、TodoCard（待办卡片）、TodoPanel（待办面板）
2. **重写主页面 MeetingTodo.tsx**：三步状态机 + 4 步 Steps 进度条 + 分屏 flex 1:1 布局
3. **SSE 工具升级**：添加请求头注入 + HTTP 状态码检查

**顺手修了 2 个问题：** app.py 中 before_request 重复注册、meeting_todo.py 中导入来源错误

### Episode 7~10: Phase 2 三轮迭代（2026-06-24）

**用户持续反馈，三轮 Prompt 迭代：**
- DDL 推理优化（从"下周三"→"2026-06-03"，默认当天）
- 跟进人匹配（简称→全称映射，多人跟进人，判断矩阵 3 种场景）
- JSON 5 层容错解析（标准→宽松→尾随逗号→部分→截断）
- 描述自动清洗（后端兜底移除"找XX"、"和XX"结构）
- 文档打开方式（绿色卡片 direct link，避免 window.open 被拦截）

---

## Episode 11: Phase 3 迭代数据统计（2026-06-24）

**用户需求：** 实现 Phase 3 迭代数据统计模块 — 上传 RDC 导出的 xlsx → 自动解析统计 AIcoding/SDD/端到端 → 写入飞书多维表格 → 导出 xlsx。

**特殊前置条件：** 用户明确要求先建立文档同步自动化机制。

**Step 1: 文档同步自动化（先于开发）**
1. 创建 `tools/doc_sync.sh` — 比较代码与文档的修改时间，过期则阻断
2. 更新 `AGENTS.md` — 插入"文档同步规则 — 完成前强制检查"
3. 更新 `MEMORY.md` — 顶部加提醒横幅

**Step 2~4: 技术调研**
- 读取桌面 `iteration-stats` skill 的 3 个脚本 + 3 个 reference 文档
- 用 `lark-cli sheets +read` 读取飞书 wiki 嵌入表格，获得 12 个项目精确列结构
- 架构决策：不使用 Playwright，沿用桌面 xlsx 方案，新增 bitable 项目列表 API

**Step 5~6: 实现与集成测试**
- 后端：`stats_engine.py`（移植核心逻辑）+ `iteration_stats.py`（4 端点）
- 前端：重写 `IterationStats.tsx`（拖拽/统计表格/汇总行/写入/导出）
- 测试：4 端点全部 200 ✅，TypeScript 零错误 ✅

**踩坑：** bitable TL 字段为 markdown 链接格式；项目名称需要模糊匹配（版本前缀 vs 简称）

---

## Episode 12: Phase 3 验收修复 — 三个隐藏的 Bug（2026-06-24 16:09~16:21）

**用户一口气提了三个问题：**

1️⃣ **统计结果在页面下方，需要滚动才能看到**
2️⃣ **AIcoding/SDD/端到端全为 0（总需求和工程需求正确）**
3️⃣ **项目名称和 TL 没有对齐飞书模板**

**排查过程：**

问题 2 最让我紧张 — 统计引擎是核心代码。打开 `stats_engine.py`，看到 `row.get("自...标签", "")` 时愣住了。一个"..."的笔误，导致所有标签匹配失败。这证明了移植代码时逐行对照原始代码的重要性。

问题 3 的根因是 `/upload` 端点只返回 xlsx 原始数据，不合并飞书多维表格的标准名称和 TL。新增 `_fetch_bitable_project_map()` + `_match_bitable_project()` 自动匹配合并。

问题 1 是纯 UI 问题 — 改为全屏 `100vh` 布局，上传区压缩为一行，自动 `scrollIntoView`。

**踩坑：** 修复过程中不小心用 `edit_file` 的 `old_text=""` 把 `findings.md` 从 150 行膨胀到 465,692 行（35MB）。教训：`edit_file` 的 `old_text` 必须是文件中实际存在的非空字符串。

**交付状态：** 三项修复全部完成 ✅，Python lint 零警告，TypeScript 零错误，所有文档同步更新。

---

## Episode 13: 上传区被多文件撑高 — 再次进场的隐藏坑（2026-06-24 16:26）

**用户反馈**："上传多个 xlsx 后，上传区被拉到很长，表格被压缩的很小。"

这次修复让我哭笑不得 — 之前为了"紧凑布局"已经把上传区压缩为一行，但 Ant Design 的 `Dragger` 在内部渲染文件列表（每个文件名一行），拖拽 5 个文件后自动长到 200px+。

**修复极其简单**：`<Dragger showUploadList={false} />` — 就一行代码。文件名改到上传区下方的 `<Tag closable>` 行展示。

**反思**：Ant Design 的默认行为往往不合预期。`Dragger` 的 `showUploadList` 默认 `true`，意味着"拖拽区本身的文件列表是默认功能"。但在这个全屏布局中，上传区应该只负责"触发上传"，文件列表信息用更紧凑的方式展示。

**跟进修复**：这次修复还触发了文档同步检查（`doc_sync.sh` exit code 1），发现之前的 `edit_file` 空字符串 bug 不只是弄坏了 `findings.md`，还包括：
- `MEMORY.md` — 从 ~60 行膨胀到 79,351 行
- `BLOG_RECORD.md` — 从 ~170 行膨胀到 23,000+ 行

两个文档都需要全部重写。这让我真正意识到文档同步检查工具的价值 — 它不只是检查"过期"，还能发现"损坏"。

**当前状态**：所有 6 个文档已全部修复并同步 ✅。Phase 3 正式收官。

---

## 3. 技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 后端框架 | Flask（非方案中的 FastAPI） | dclaw.yaml 已固定为 flask-react |
| SSE 实现 | Flask generator + Response | Flask 无 StreamingResponse |
| 前端路由配置 | BrowserRouter + basename | 部署子路径下需要前缀 |
| API 路径 | 变量 API_BASE | 避免硬编码 /api 导致部署后 404 |
| 页面跳转 | useNavigate | 避免 window.location.href 跳出子路径 |
| 持久化规划 | planning-with-files 三文件 | 上下文丢失后可从文件恢复 |
| 唤醒入口 | MEMORY.md 作为新会话必读 | AGENTS.md → MEMORY.md → 其他文件形成强制链 |
| 文档更新协议 | MEMORY.md 内置协议 + 唤醒清单 | 不可跳过的门禁 |
| 飞书 API 调用 | lark-cli subprocess | lark-cli 自动管理 token |
| 妙记逐字稿接口 | `GET /minutes/v1/{token}/transcript` | vc/notes 已失效 |
| 跟进人提取策略 | Prompt 判断矩阵 + 后端兜底 | LLM 不一定 100% 遵守规则 |
| LLM 稳定性 | temperature=0.0 + max_tokens=8192 + 重试 3 次 | 最大程度降低非确定性 |
| JSON 解析 | 5 层递进容错 | LLM 输出不可控 |
| 文档打开方式 | `<a href>` 直链 | window.open 在 await 后被拦截 |
| xlsx 统计方案 | 本地移植桌面 skill（非 Playwright） | Token 消耗小、无登录态 |
| 标签列名策略 | 优先级轮询 `["自定义标签","自...标签","标签","需求标签"]` | 兼容不同版本 RDC xlsx |
| TL 合并时机 | upload 端点内聚合并 | 减少前端复杂度 |
| 项目名称匹配 | 精确匹配 → 子串模糊匹配 | 兼容 bitable 版本前缀 |

---

## 4. 踩坑集合

### [P0-001] JSX 中文引号问题
**现象：** `npx tsc --noEmit` 报错 `Identifier expected`
**原因：** JSX 属性值中的中文双引号被当成了属性值边界符
**解决：** 用 JSX 表达式 `{'点击「提取」'}` 包裹

### [P0-002] Device Code Flow 需要 app_secret 🚫
**现象：** 第三方教程称 Device Code Flow 不需要 app_secret，实际飞书要求 Basic Auth
**教训：** 提前阅读平台官方文档，不轻信第三方博客

### [P0-003] lark-cli `--content @file` 只接受相对路径
**解决：** `os.getcwd() + '/_doc.xml'` + 传 `@_doc.xml`

### [P0-004] Flask 子进程缺失 `LARKSUITE_CLI_CONFIG_DIR`
**解决：** 定义 `_lark_env()` 手动注入环境变量

### [P0-005] JSON 控制字符删除破坏字符串边界 🎯
**现象：** 正则删 `\x00-\x1f` 波及了 JSON 字符串内的 `\n`
**解决：** 只删 `[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]`，保留 `\n\t\r`

### [P0-006] edit_file 空字符串陷阱
**现象：** `old_text=""` 导致文件从 150 行膨胀到 465,692 行（35MB）
**教训：** `edit_file` 的 `old_text` 必须是文件中实际存在的非空字符串。追加内容应 `read_file` + 拼接到内存 + `write_file`

---

## 5. 开发日志

### 2026-06-23

| 时间 | 事件 | 涉及文件 |
|------|------|---------|
| — | 阅读方案文档 + 产品原型 | media/*.md, media/*.html |
| — | 创建 IMPLEMENTATION_PLAN.md | IMPLEMENTATION_PLAN.md |
| — | 创建 planning-with-files 三件套 | task_plan.md, findings.md, progress.md |
| — | Phase 0 后端骨架搭建 | backend/app.py, backend/routers/*.py |
| — | Phase 0 前端骨架搭建 | frontend/src/**（16 个文件） |
| — | 前后端联调验证 | — |
| — | 创建博客素材档案 + 文档更新协议 | BLOG_RECORD.md, findings.md |
| — | Device Code Flow 被证伪，回归 lark-cli | feishu_client.py |

### 2026-06-24

| 时间 | 事件 | 涉及文件 |
|------|------|---------|
| 00:00~02:30 | Phase 2 三轮迭代（DDL/跟进人/JSON 容错） | meeting_todo_service.py, feishu_client.py |
| 14:00~15:00 | Phase 3 实现（stats_engine + 4 端点） | stats_engine.py, iteration_stats.py |
| 15:00~15:30 | Phase 3 前端页面 + 集成测试 | IterationStats.tsx, iterationStats.ts |
| 15:30 | 文档同步（开发后） | 全部 6 个文档 |
| 16:09~16:21 | Phase 3 验收修复（布局/标签列名/TL合并） | stats_engine.py, IterationStats.tsx, iteration_stats.py |
| 16:26 | 上传区被多文件撑高修复（showUploadList=false） | IterationStats.tsx |
| 16:53~17:00 | 文档同步修复：MEMORY.md/BLOG_RECORD.md 被 edit_file bug 损坏后重写 | MEMORY.md, BLOG_RECORD.md |

---

## 6. 当前成果（截至 Phase 3）

### Phase 2 — 会议 TODO 提取 ✅

| 能力 | 状态 |
|------|------|
| 妙记链接 → SSE 流式提取 → 分屏展示 → 飞书文档 | ✅ |
| 跟进人智能提取（判断矩阵：3 种场景 → 3 种规则） | ✅ 真实妙记验证 |
| 描述自动清洗（后端 _clean_description 兜底） | ✅ 10 个边界用例 |
| 多人跟进人（顿号分隔 + 多个 `<cite>` 标签） | ✅ |
| 简称 → 全称映射（"瘦子" → "大瘦子"） | ✅ 说话人列表注入 |
| DDL 具体日期推理 | ✅ 时间戳 → 日期上下文 |
| JSON 5 层容错解析 | ✅ |
| 2 个真实妙记 E2E 验证 | ✅ 05-28(19min) + 06-02(69min) |

### Phase 3 — 迭代数据统计 ✅

| 能力 | 状态 |
|------|------|
| RDC xlsx 上传 → 自动统计 AIcoding/SDD/端到端 | ✅ |
| 飞书多维表格项目列表读取 + TL 清洗 | ✅ 12 项目 |
| 上传时自动合并飞书标准名称和 TL | ✅ 精确+模糊匹配 |
| 统计结果写入飞书多维表格 | ✅ |
| 导出 xlsx | ✅ |
| 标签列名跨版本兼容（优先级轮询） | ✅ |
| 全屏布局 + 紧凑上传区 + 自动滚动 | ✅ |
| TypeScript 零错误 + Python lint 零警告 | ✅ |
| 6 个文档全部同步 | ✅ |

---

## Episode 13: "undefined" 与 500 — 两个不起眼但花了 40 分钟的 Bug

**时间：** 2026-06-24 17:00~17:43
**来源用户：** 孙源

### 症状

用户点统计完点了两个按钮：
1. "写入飞书多维表格" → Alert 显示 `"✅ 成功更新飞书多维表格 — undefined 条记录"`
2. "导出 xlsx" → 浏览器控制台报 500

两个 bug 都不算大，但都是"差一点就对"的写法导致的。

### Bug 1：字段名错位

前端 API 封装层定义的接口是 `BitableWriteResult { updated_count: number }`，后端返回的是 `{"success": true, "updated": 10}`。前端读 `res.updated_count` → undefined。

**根因**：Flask 后端是 Python dict，没有类型检查。前端 TypeScript 写的接口定义和后端实际返的字段名差了 `_count` 两个单词。没人会刻意检查这类对账——代码看上去都是对的，跑起来就有问题了。

**教训**：说到底就是**缺少一层契约验证**。如果是 FastAPI with Pydantic，响应模型能确保前后端字段名一致。Flask 没有这个保障，全靠人肉对齐。想到的办法是在 Router 的 route map 打印时顺带打印响应结构，或者写一个简单的 schema 文档生成。

### Bug 2：变量没用对

导出 500 的根因更基础——典型的"改了一半没改完"：

```python
# 入口处做了兼容（但后续代码没改过来）
project_stats = data.get("project_stats") or data.get("rows", [])

# 遍历的时候忘了用 project_stats，用了 data["project_stats"]
for row_idx, ps in enumerate(data["project_stats"], 2):  # ← None 时崩
```

而且还藏了第二个坑：`aicoding_ratio` 从 xlsx 解析出来已经是 `"25.0%"` 字符串了，但导出代码还在用 `:.2f` 数值格式化——`ValueError` 直接 500。

**教训**：同一份数据在"上传→展示→写入→导出"链路上每个环节的数据类型要保持一致，或者每个环节都做类型判断。特别是 ratio 这种显示和计算的混合字段。

### 附赠优化

除了修两个 bug，顺手加了个 UX 小改进——写入成功后直接给个 `🔗 打开飞书多维表格查看` 的超链接。用户不需要自己去飞书翻。

### 反思

Phase 3 验收测试过了，但其实只测了"统计能出结果"、"精确匹配能写入"、"导出能下载"这三个核心路径。边界场景（多字段名兼容、字段值格式）没有覆盖到。下一次验收清单应该加一项：**"检查后端返回的 JSON 字段名是否和前端接口定义完全一致"。**

---

## Episode 14: 合计行消失 + TL 的 @ 前缀 + 文件再次被 edit_file 吃胖

**时间：** 2026-06-24 17:50~18:03
**来源用户：** 孙源

### 三个问题，一个比一个细

用户又提了两个问题：TL 列不对、合计行没有出现在导出和飞书里。

**问题 1 — TL 多了个 @ 前缀**

飞书多维表格中，TL 是"人员"字段类型。bitable API 返回的不是纯文本，而是一个数组：

```json
[
  {"text": "@黎国友", "type": "mention"},
  {"text": " ", "type": "text"},
  {"text": "@李四", "type": "mention"}
]
```

代码只做了 `item["text"]` 的拼接，没有去掉 `@` 前缀。看了四遍才注意到——因为那段清洗逻辑是两次写出来的（`_fetch_bitable_project_map` 和 `/projects` 端点各有一份），之前只改了字符串路径的 `replace("@", "")` 没改 list 路径的。**重复代码必然导致修复遗漏。**

**问题 2 — 合计行去哪了**

这个更直白：前端表格里的合计行是 `computeSummary` 本地算的，数据从没发到后端。导出 xlsx 和写飞书都只传了 `result.rows`。解决方案就是在两个 handler 里都把合计行 append 进去——一个 `computeRawSummary` 函数，导出发一份，飞书写入发一份。

飞书写入时，"合计"行不会匹配任何 bitable 记录，自然 fallthrough 到 unmatched，但不阻塞其他项目更新。

**问题 3 — edit_file 又双叒叕把文件撑大了**

修到一半发现 `api/iterationStats.ts` 编译不过。打开一看——重复了三份 `computeRawSummary` 函数体。`edit_file` 的 `old_text` 空字符串 bug 再次触发。

这次还附带污染了 `progress.md`（8 重重复）。只能 `write_file` 完整重写。

### 持续攻击同一个弱点

这是第二次被 `edit_file` 空字符串 bug 坑。第一次在 Episode 12（MEMORY.md 被撑到 79K 行）。第二次还是踩同一个坑。根本原因是 **`edit_file` 的参数匹配机制**：当 `old_text` 在文件中以意外方式重复出现时，它会匹配到多余的实例，不断插入。写文件时还是 `write_file` 写完整内容最安全——每次都是原子操作，不会产生中间状态。

---

## Episode 15: 项目名称清洗 + 合计行自动创建 — 飞书 bitable 终于有合计行了

**时间：** 2026-06-24 19:15~20:22
**来源用户：** 孙源

### 两个独立问题

用户在 Episode 14 的最后留了两个 pending 问题：
1. **飞书 bitable 还是没有合计行** — 虽然 xlsx 导出已修复，但 bitable 写入靠"匹配现有记录更新"，"合计"不匹配任何记录 → 不写入
2. **项目名称需要去掉版本前缀** — bitable 中存储的是 `5.93（0529）Dsearch搜索引擎版本迭代`，用户想看到的是 `Dsearch搜索引擎版本迭代`，但链接（iwork 链接）保持不变

### 用户的倾向

这次我没有猜用户要什么，而是给了三个选项：

**合计行问题：**
1. ❌ 不动（只在 Web 展示，bitable 不存）
2. ✅ **自动创建合计行记录** — write-bitable 检测不到"合计"时自动新增
3. ❌ 手动在 bitable 加一条

**项目名称清洗：**
- 加正则 `^\d+\.\d+[（(]\d+[）)]\s*` 去除版本前缀

用户回复很明确：**自动创建合计行记录，同时项目名称清洗也要进行修正。**

这让我长出一口气——用户直接确认了方案，不用反复确认。

### 实现

**项目名称清洗 — 统一辅助函数**

之前 3 处代码重复实现了类似的清洗逻辑（`_fetch_bitable_project_map`、`/projects` 端点、write-bitable 的 exact_map 构建），但每处写法略有不同。趁这次机会统一成一个 `_extract_project_name()` 函数：

```python
_PROJECT_VERSION_RE = re.compile(r'^\d+\.\d+[（(]\d+[）)]\s*')

def _extract_project_name(name_raw) -> str:
    # 1. 处理 markdown 链接 [name](url) → name
    # 2. 处理富文本数组 → 拼接 text
    # 3. 正则去除版本前缀
    return _PROJECT_VERSION_RE.sub('', cleaned_name).strip()
```

三处全部替换为 `_extract_project_name(name_raw)`，一处修改、处处生效。

**合计行自动创建 — create_bitable_record**

在 `feishu_client.py` 新增 `create_bitable_record()`，使用 `lark-cli base +record-batch-create`：

```python
fields = ["项目名称", "TL", "总需求数【完全排期】", ...]
row = [stats.get("project_name"), stats.get("tl"), stats.get("total"), ...]
```

然后在 write-bitable 端点中，匹配循环结束后检测 unmatched：

```python
if "合计" in unmatched:
    created = create_bitable_record(BASE_TOKEN, TABLE_ID, summary_row)
    records_data.append({"record_id": created["record_id"], "stats": summary_row})
    unmatched.remove("合计")
```

### 踩坑

之前 `findings.md` 被 `edit_file` 空字符串 bug 撑到 4,348 行，在这次更新时利用写博客的机会顺便彻底重写了它——删除了所有重复内容（原来有 11 遍重复的同一个 finding），从 4,348 行精简到 ~210 行。一个干净的 findings.md 比修复这个文件的过程本身更有价值。

### 技术反思

**重复代码是万恶之源。** 这不是鸡汤，是实实在在的教训。`_fetch_bitable_project_map` 和 `/projects` 端点的清洗逻辑，因为写了两份，第一次改 TL 清洗时只改了其中一个。这次项目名称清洗抓住了机会统一，一下子消除了 3 个维护点。

**选择方案时给选项而不是直接做决定。** 上次合计行问题我误判了用户倾向（我以为用户会接受"只在 Web 展示"），导致多了一次来回确认。这次直接给选项让用户选，一次对齐。

---

## Episode 16: AI 编程数据报告 — 从 subprocess 到直接 HTTP 的架构转身（2026-06-24）

**时间：** 2026-06-24 20:22~20:29
**来源用户：** Phase 4 开发任务

### 背景

Phase 4 的目标是做一个"AI 编程数据报告"模块——配置 Token 和试点名单，查询 AI 编程工具的使用数据（活跃率、不活跃人员、Skills 技能列表、TL 使用情况），生成 Markdown 报告。

已有的基础设施是 `ai-measure-query` skill 中的 4 个 Python 脚本（`ai_measure.py`、`dept_stats.py`、`skills_query.py`、`inactive_members.py`），这些脚本通过命令行接受参数，调用内部 API，然后输出格式化表格。

### 初始方案 vs 实际实现

方案文档的 Phase 4 写的是"封装子脚本"，意思是用 subprocess 调用这些脚本，解析它们的表格输出。

但仔细看了脚本的输出后发现：格式化表格是用 tabulate 或 print 打出来的，表格宽度、对齐方式、是否包含表头，完全取决于调用时的参数。要从中提取结构化数据就得用正则解析——脆弱、难调试、表格格式一变就崩。

**决策：直接 HTTP 调用背后的 REST API 替代 subprocess。**

### 两层 HTTP 客户端

1. **`AiMeasureClient`** — 调用 `ep-copilot2` 的 `/v1/ai-tool-measure/drilldown` API
2. **`SkillsQueryClient`** — 调用 `skills.dewu-inc.com/v1/skills` API

两个客户端都直接 `requests.post()` 拿 JSON 回应，干净、可控。原脚本保留在 `ai_measure_scripts/` 目录作为参考。

特别注意的是 Skills API 的返回结构——它返回的是自描述 schema（schema 告诉你字段名和类型，数据在 `data` 数组），而不是固定字段。客户端需要做一次 schema 到字段名映射。

### 报告编排器：串行 SSE + 模块隔离

`ReportGenerator` 串行执行 4 个查询，每个查询完成后立即通过 SSE 推送 `section_complete` 事件。关键设计原则：

- **模块隔离** — 一个模块出错（`section_error`）不影响其他模块继续
- **实时进度** — 每个模块开始/进行中/完成，用户都能看到
- **流式累积** — 前端逐步累积 Markdown，不用等全部完成

TL 使用情况是特殊模块——没有独立的 TL API，而是查全部数据再用固定的 27 人名单过滤。效率不是最优，但够用。

### 前端：配置 + 进度 + 预览三合一

AiMeasure.tsx 页面把三件事整合在一起：

1. **配置区** — 2×2 Grid：Token+测试连接 / 试点名单+一键填充 / 日期范围 / 模块勾选
2. **进度区** — 竖向 Steps（wait→process→finish/error），每个模块独立状态
3. **预览区** — Markdown 渲染 + 复制 + 写入飞书

使用 `react-markdown` 渲染报告，`CopyOutlined` 复制全文，`FileAddOutlined` 写入飞书文档。

### 与之前模块的差异

这是第一个不依赖 lark-cli 子进程的模块——HTTP 调用是更轻量、更可控的方式。不过它依赖的外部 API（ep-copilot2、skills.dewu-inc.com）理论上不如 lark-cli 稳定，而且需要有效的 EP Token。

### 当前状态

代码完成，TypeScript 零错误 ✅，Python 编译通过 ✅。待用户提供有效 EP Token 后进行端到端验证。

---

## Episode 17: 三个熟悉的陌生人 — TL 多人版、版本号尾缀、ratio 的第三次访问（2026-06-24 20:53）

**用户反馈了三个问题：**
1. 项目名称清洗不彻底——"DPP双周迭代 5.93版本（0529）"末尾还有版本号
2. 网页表格 TL 只显示前两个人，后面为空
3. 写入飞书报错 `Unknown format code 'f' for object of type 'str'`

这三个问题让我心情复杂——每个看起来都很眼熟。

### Bug 1：版本号尾缀

眼熟指数：★★☆☆☆

`_PROJECT_VERSION_RE` 之前写的正则只匹配开头 `^\d+\.\d+[（(]\d+[）)]\s*`，用于处理 `5.93（0529）项目名` 这种格式。但实际数据中版本号也会在**末尾**出现：`DPP双周迭代 5.93版本（0529）`。

修复就是在正则后面加个 `|` 分支匹配后缀。不过想到一点：会不会还有中间的情况？比如 `5.93（0529）DPP双周迭代 5.94`？先不管了，等报再补。

### Bug 2：TL 多人问题

眼熟指数：★★★★★

之前修过 TL 的 @ 前缀（Episode 14），那次是 `item["text"]` 没 strip `@`。这次是多人 TL 只提取了第一个——因为 `re.search()` 只返回第一个匹配项。

重复代码又害了我。`_fetch_bitable_project_map` 和 `/projects` 端点各有一份 TL 清洗逻辑，都要从 `re.search` 改为 `re.findall`。虽然不是难改，但每次都因为有两处而来回检查。

这让我想起之前承诺过"最好提取统一函数"——为什么没做？因为两处代码的上下文略有不同（一处生成项目映射 dict，一处直接返回 list），加上每次修 TL 都是"顺手修"（不是专门的任务），优先级不够。

**等退役了一定要把 TL 清洗提成一个 `_extract_tl_names()` 函数。**

### Bug 3：ratio 的第三次访问

眼熟指数：★★★★★（满分）

```
❌ export 端点 → 已修（加 isinstance 判断）→ 2026-06-24 17:43
❌ export 端点变量 bug → 已修（用局部变量）→ 2026-06-24 17:43  
❌ update_bitable_record → 没修！→ 2026-06-24 20:53
```

同一问题的第三次出现。前两次都发生在 `export` 端点（xlsx 导出），我都修了。但忘记检查 `update_bitable_record`——它在 `feishu_client.py` 中，不是 `iteration_stats.py` 的一部分，写方案时容易忽略。

修复方案很简单：`create_bitable_record` 里已经有一个 `_fmt_ratio()` 本地嵌套函数用来做这件事（因为它也需要格式化占比），但 `update_bitable_record` 里没有。把 `_fmt_ratio` 提到模块级别，两处共用。

**系统性反思：** 这已经是我第三次被 ratio 字段的 int/str 二象性坑了。PV（Phase 3 只有 4 个文件涉及 bitable 写入，就应该统一在某个 schema 层做数据转换，而不是每个函数各自写格式化逻辑。这次把 `_fmt_ratio` 提升到模块级算是第一步，后续可以把所有 bitable 字段格式化汇总到一个函数。

### 三修完成后

三处改动加起来不到 20 行代码，改动文件只有 2 个。但验证范围涉及 export xlsx 和 write-bitable 两条路径。可惜没有 EP Token 做端到端测试——开发环境的"全部编译通过"只是个基础保障，不是真正的验收。

### 教训速览

| # | 问题 | 根因 | 怎么避免 |
|---|------|------|----------|
| 1 | 版本号在末尾 | 正则只覆盖开头位置 | 写正则时考虑所有可能的位置 |
| 2 | TL 只显示一人 | `re.search()` 只返回第一个 | 重复代码需要统一函数 |
| 3 | ratio 的第三次 | 同一 bug 在第 3 个文件出现，前 2 个修了但没覆盖全局 | schema 层统一格式化

---

## Episode 18: 放弃正则，拥抱硬编码（2026-06-24 21:31）

**当用户说"一个都没解决"时，就已经说明问题不在修补上，而在方案本身。**

### 真实的项目名称长什么样

这次从飞书多维表格 dump 了实际数据：

| 原始 bitable 项目名 | 版本号位置 | 格式特点 |
|---|---|---|
| `95分算法 5.93（0529）` | 末尾 | 纯数字括号 |
| `DPP双周迭代 5.93版本（0529）` | 末尾 | 带"版本"字样 |
| `商业化V5.93迭代（5月29日灰度）` | 末尾 | V 开头 + 中文日期 |
| `交易搜索5.93（5月29日灰度）` | 末尾 | 中文日期不匹配 \d |
| `5.93（0529）Dsearch搜索引擎版本迭代` | 开头 | 前缀标准格式 |

没有两种格式是一样的。正则补了后缀分支，但 `5月29日灰度` 里的中文让 `\d*` 直接不匹配。再补一层？能补，但下一批导入的数据又可能有新格式。

### 你给的方案

你给了我两张图，明确展示了前两列固定的 12 个项目名和对应 TL。**我不再需要从 bitable 解析任何项目名和 TL**，只需要用标准名去 bitable 里定位 record_id。

### 最终实现

```python
PROJECT_MAP = [
    ("DPP双周迭代", "樊少"),
    ("Dsearch搜索引擎版本迭代", "樊少"),
    ("Dgraph", "樊少"),
    ("交易搜索", "天央"),
    ("商业化", "天央"),
    ("社区搜索", "啊俊"),
    ("交易推荐", "三白"),
    ("用户&营销算法", "培成"),
    ("增长算法迭代", "培成"),
    ("95分算法", "岱锋"),
    ("国际算法迭代", "岱锋"),
    ("社区推荐", "则明"),
]
```

匹配策略反过来：`标准名 in bitable名`（子串查找），只取 record_id，项目名和 TL 全部从硬编码的 PROJECT_MAP 拿。

实测全部 12 个匹配成功。

### 删掉的东西

| 文件/函数 | 行数 | 原因 |
|---|---|---|
| `_PROJECT_VERSION_RE` | 4 | 正则不够用 |
| `_extract_project_name()` | ~25 | 函数体全删 |
| `_fetch_bitable_project_map()` 的 TL 解析 | ~20 | 改用 PROJECT_MAP 查 |
| `/projects` 的 TL 解析 | ~20 | 同上 |
| write-bitable 的 exact_map | ~15 | 改用标准名匹配 |
| `import re` | 1 | 不再需要 |
| **总计** | **~85行** | |

删了 85 行，新增不到 30 行。代码少了，逻辑更清晰，对 bug 的抵抗力更强了。

### 反思

**用了 3 轮正则修补都不够，直到第 4 轮用硬编码才刹住车。** 问题不在于"正则写不对"，而是"这个场景根本不适合用解析器"。当数据源是人工输入的文本时，枚举空间有限的场景直接用硬编码——它不优雅，但它确定。

---

## Episode 19: 查了三个小时，根因是 \n 和 \n\n 的区别

**时间：** 2026-06-30
**来源：** Phase 4 的 AI 编程数据报告 — 试点人员活跃率查询"失败"

### 症状

用户的体验很一致：点击"生成报告"后四个模块逐个显示完成，但活跃率模块最终显示"查询失败"。后端没有报错，前端显示 `4/4 模块`。但无论试几次，活跃率模块的 Steps 状态都是红色。

我第一反应是后端 API 报错。curl 了 EP 的 drilldown 接口——1.7 秒返回 642 人的完整数据。然后 curl 了完整的 4 模块 SSE 生成接口——6.87 秒返回 4 个 `section_complete` 事件，一个 `section_error` 都没有。

后端是正常的。

那问题一定在前端。我加了 console.log 看 `onComplete` 的 payload：

```
[AiMeasure] onComplete: {sections_completed: 4, total_sections: 4} completedRef: Array(3)
```

### 铁证

4 个模块都完成了（`sections_completed: 4`），但 `completedRef`——我用来跟踪回调执行情况的 Set——只记录了 3 个。**缺失的那个就是活跃率。**

这就意味着：活跃率的 `section_complete` 事件**从来没到达过回调函数**。不是数据问题，不是 API 问题，是事件根本没被识别。

### 排查对象：手写的 SSE 解析器

`utils/sse.ts` 里有一段我（和模板项目）一直用的 SSE 解析逻辑：

```javascript
const decoder = new TextDecoder()
let buffer = ''
// 按行切分
const lines = buffer.split('\n')
buffer = lines.pop() || ''
let eventType = ''
for (const line of lines) {
    if (line.startsWith('event: ')) { eventType = line.slice(7).trim() }
    else if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6))
        switch (eventType) { /* 分发到对应回调 */ }
    }
}
```

看起来没问题。SSE 协议的每一行以 `\n` 结尾，`event:` 标识事件类型，`data:` 标识数据。一行一行读，类型对了就分发。

问题在 TCP 分片。

HTTP 响应的数据在传输层被切成 TCP segment，每个 segment 的大小受 MTU（通常 1500 字节）限制。SSE 的 `section_complete` 事件包含整个 `rows` 数组和 `markdown` 字段，payload 轻松超过 1500 字节。

所以真实的传输可能是这样的：

```
TCP Segment 1:
  event: section_complete\ndata: {"section":"active_rate","row_count":2,"rows":[{"name":"大怪兽(Danie

TCP Segment 2:
  l)",...]}\n\nevent: progress\ndata: ...
```

Segment 1 中，`data:` 后面的 JSON 被截断了。`JSON.parse('{"section":"active_rate","row_count":2,"rows":[{"name":"大怪兽(Danie')` 必然失败，被 `catch` 静默丢弃。

Segment 2 中的 `event: progress` 覆盖了 `eventType`。后续 `data: {inactive...}` 虽然解析成功了，但 `switch('progress')` 分发了错误类型。

**这就是活跃率事件丢失的全部过程。**

### 为什么另外三个模块正常？

- `inactive` 返回 0 行，payload 小 → 不会跨 segment
- `skills` 返回 0 行，payload 小 → 不会跨 segment
- `tl_usage` 26 行，payload 最大。但它排在最后，后面没有 `event:` 来覆盖它的 `eventType`。哪怕 JSON 也被截断了一次，但 `\n\n` 边界在 segment 边界之前，不会导致截断

### 修复

按 `\n\n`（SSE 规范的事件分隔符）切分，而不是 `\n`。

```javascript
const parts = buffer.split('\n\n')  // 按事件边界切
buffer = parts.pop() || ''
for (const part of parts) {
    const { eventType, dataStr } = parseSseBlock(part)
    // dataStr 是整个 data: 后面的内容，不会截断
    JSON.parse(dataStr)  // 现在不会失败了
}
```

`\n\n` 是 SSE 规范定义的**事件分隔符**。一个完整的事件是两个换行之间的一组行。这样切分保证：哪怕 TCP segment 在事件中间断开，解析器也只会在拿到 `\n\n` 后才处理这个事件。

### 反思

**手写 SSE 解析器的人都知道 `\n\n`，但写的时候还是会默认用 `\n`。** 因为大多数时候 payload 够小，不会跨 TCP segment，`\n` 和 `\n\n` 切分的结果一样。问题只会在 payload 足够大时才暴露——而 AI 数据报告的 `section_complete` 事件恰好就那么大。

这个 bug 难查的点在于：**后端日志正常、网络正常、curl 正常、不报错、不抛异常。** 唯一的线索是前端的 `completedRef` 少了一个——这几乎不可能主动想到是 TCP 分片导致的。如果不是 console.log 打出了 `completedRef: Array(3)`，我可能还在查后端的超时配置。

顺带修复了三个相关的小问题：
1. Flask 的 generator 不加 `stream_with_context` 会被 buffering
2. EP API 的硬超时（requests timeout 只控制字节间隔，不是总耗时）
3. 前端 React batch 中 `onComplete` 的 state 覆盖

---

## Episode 20: 知识库管理 — 10 个代理端点的流水线

**时间：** 2026-06-30

知识库管理是追加的 Phase 6。后端接口已在无矩2.0 微服务中存在，我的工作就是翻译 —— 10 个管理 API 在前端后面开一条"代理通道"。

流程高度模式化：每个 Flask 端点读请求参数、拼 URL、调 requests、三层 catch、返回 JSON。`_proxy_get` / `_proxy_post` / `_proxy_delete` 三个通用函数覆盖所有场景。唯一需要额外处理的是文件上传（`_proxy_files`，转发 multipart/form-data）。

前端页面 4 个 Tab：概览 -> 浏览 -> 导入 -> 同步。每个 Tab 独立 state，用 `useCallback` 封装 handler。同步 Tab 花费了最多时间：用户要求 Radio 模式选择器（4 种模式）、dry-run 预览按钮、轮询时的中文进度文本（"代码同步中…" / "重建核心 KB 中…"）、以及一个知识库组成说明 Table。

后端改了一行 `trigger_sync` 的 query 参数拼接（加 `rebuild_core` / `rebuild_wiki`）。前端改了两个文件：API 封装加参数、页面加 UI。

这段经历的感觉是：架构搭好后，新功能的边际成本下降得很明显。路由模式、代理模式、前端三态渲染（loading / content / empty）都已在之前 Phase 定型，新模块只需要套模板。

---

## Episode 21: 代码变更分析 — 从方案评审到 Phase 7 全部交付

**时间：** 2026-07-01

### 起点：一个看起来很酷的方案

"指定时间段后，git 拉取最旧和最新的前端代码做 diff，LLM 分析功能变更。"

听起来简单。但用户给的方案文档（V3.0 终版）有 1300 行——ts-morph AST 10 类信号、Import Graph 连通分量聚类、LLM 语义归纳——每个环节都是独立的子系统。

### 两轮评审

方案写完后我做了评审，用户找了另一个 AI 也做了评审。结果：

| 来源 | 发现问题 | 采纳率 |
|------|---------|--------|
| 我的自审 | 6 个（NEW_ROUTE 不兼容 Umi 配置路由 + 共享包路径错误 + @@/ 别名未排除 + worktree 孤儿清理 + 参数表重复 + huatuo-attribute-web 遗漏） | 100% |
| 另一 AI 评审 | 13 个（doc_context 落地缺失 + page-logic 去重策略 + Umi 路由算法 + @@/ 处理策略 + Worktree cwd + SSE 格式 + 7 个小点） | 12/13 |

唯一未采纳的是 `modalTraining` → `modelTraining` typo，因为这是目标仓库的实际目录名，不是笔误。

两轮共修复了 18 个问题，版本从 V1.0 到 V1.3。

### 实施中的惊喜

方案拆为 5 个 Phase、~30 个 Task，每个 Task 独立验证。

**Phase 1a 4 个核心信号** — 冒烟测试一次通过。但用真实仓库（algorithm-monorepo）的 87 个文件、460KB patch 跑完整验证时，发现了 3 个优化点。

**Phase 1b 补齐 6 个信号** — 有个坑：`String.prototype.matchAll` 要求 regex 带 `/g` 标志，否则直接抛 `TypeError`。ESLint 不会警告、TypeScript 不会报错、运行时才崩。

**Phase 2 知识快照** — 才发现用户路由用的是模板字符串 `` path: `/${appName}/...` ``。静态分析无法解析 `appName` 变量，只能从 `package.json` 读取。东八区时间戳 + 共享包递归扫描 + 过滤 `.dumi/` 目录。

**Phase 3 Flask 编排器** — `generate_diff` 非生成器但用了 `yield from` 调用，`TypeError: NoneType is not iterable`。最简单的修复：末尾加 `yield`。另外 `git log` 的 pathspec 必须放在 `--` 后面，否则全空。

**Phase 5 端到端** — 快照在 worktree 之前生成，产生 133 bytes 空文件。调换顺序后 9590 bytes 正常。LLM 用 test key 预期降级到规则层，不崩溃。

### 最有价值的发现

SN 学习到的最大教训是：**真实仓库验证和 mock 测试的差距是巨大的。**

`NEW_ROUTE` 信号在 mock patch 中完美运行，但在 algorithm-monorepo 的真实 diff 中——87 个文件、460KB——暴露了 import 解析、page-logic 去重、非代码文件过滤等一系列问题。

另外，README 中的 signal 说明表格第一版写了 10 类，但实际只有 `UNKNOWN` 信号从未被主动生成——它是决策树中的兜底分类，不是可提取信号。

### 结尾

Phase 7 全部 5 个子 Phase 在一天内完成：
- ✅ Phase 1a: CLI 骨架 + 4 核心信号
- ✅ Phase 1b: 10 类信号 + Import Graph + 文档上下文
- ✅ Phase 2: 知识快照
- ✅ Phase 3: Flask 编排器 + 4 API 端点
- ✅ Phase 4: 前端页面（配置/进度/报告）
- ✅ Phase 5: LLM 集成 + 端到端验证

等待实际使用后反馈，再回头修复已知的 3 个优化点（JSON 文件过滤、NEW_PAGE 误判、page-logic 跨 cluster 去重）。

---

## Episode 22: 生产调试——LLM 格式归一化与漫长的稳定化

**时间：** 2026-07-02

### 从"跑通"到"跑稳"

Phase 7 代码完成后，从"能跑"到"稳定跑"花了整整一天。核心问题：LLM 返回格式不受控。

### LLM 的 5 种输出格式

同一份 Prompt、同一个模型（deepseek-v4-flash）、同样输入，LLM 可能返回：

1. `{"report": [{"category": "...", "description": "..."}]}`
2. `{"changeReport": [...]}`
3. `{"changes": [...]}`
4. `[{"category": "...", "description": "..."}]`（裸数组）
5. `{"new_features": [...], "modified_features": [...]}`（正确格式）

前四种都会导致规则层降级——前端显示"LLM 失败"但用户不知道为什么。

### 变量名覆盖 Flask `g`

`item for g in ast_result.get("featureGroups", [])` 看起来无害，但 `g` 变量覆盖了 `from flask import g`。`g.llm_config` 拿到的是 Feature Group 对象而不是 Flask 的全局上下文，报 `NoneType is not subscriptable`。Python 不报错，代码降级到规则层。

### 7 次修复迭代

| # | 问题 | 现象 | 修复 |
|---|------|------|------|
| 1 | 重复 `yield from` | `NoneType is not iterable` | 非生成器函数去掉 yield |
| 2 | 404 路径 | 请求失败 | `API_BASE` 已含 `/api` |
| 3 | `for g in` 覆盖 | 规则层降级 | 改 `for fg in` |
| 4 | LLM 裸数组 | `list has no keys` | 归一化支持 list |
| 5 | `conf` 变量错误 | 规则层降级 | `float(matched_conf)` |
| 6 | category→name | 显示"未知变更" | elif 补自动映射 |
| 7 | 飞书空文档 | 文档 URL 正确但空白 | 加 `<title>` 标签 |

### 感悟

四个字：**防御性编程**。LLM 的输出不是 REST API——没有 schema 保证，同一个 Prompt 在不同时间可能产生完全不同的 JSON 结构。归一化层不能只写一次，需要持续迭代补充新发现的格式。

同时，Python 的变量作用域问题（列表推导式变量泄露到外层）在这次狠狠坑了一次。这是 Python 2 遗留的行为（Python 3 修复了但 `for g in [...]` 在函数作用域中仍然会覆盖局部变量）。

### 当前状态

Phase 7 全部功能已稳定：
- ✅ CLI 骨架 + 10 类 AST 信号 + Import Graph 聚类
- ✅ 知识快照
- ✅ Flask 编排器 + SSE 进度
- ✅ LLM 语义归纳（含格式归一化，5 种格式兼容）
- ✅ 导出 Markdown + 飞书文档
- ✅ 已知 3 个优化点已记录（待 MVP 后处理）

---

## Episode 23: LLM 不可靠的教训（2026-07-03）

**需求：** 验证功能变更分析的稳定性，看三次相同日期输出是否一致。

**发现：** AST 分析完美一致（61 Feature Groups，3 次完全一样 ✅），但 LLM 输出乱了——第一次 59 项、第二次 27 项、第三次 92 项。

**为什么 LLM 会这样？** 给它 61 个 Feature Groups，它要么合并相似的（61→27），要么把一项拆成多条（61→92）。`temperature=0` 不够，加了 `seed=42` 也不够——DeepSeek 的 seed 实现不彻底，分布式 GPU 浮点运算的非确定性仍然存在。

**解决方案：** 不再让 LLM 做批量归纳。改为每个 Feature Group 单独调一次 LLM，AST 自己决定每条属于新增还是修改，LLM 只负责写业务描述。这样输出数量一定对得上，LLM 只需专注做它擅长的语义描述。

**教训：** LLM 适合做"理解"和"描述"，不适合做"计数"和"分类"。分类决策应该由确定性代码完成。这个教训从 Phase 2 的 JSON 解析容错就开始积累了——LLM 的输出格式都不可控，更别说让它做数值对齐了。

**其他修复：**
- 重启后端时发现 `app.py` 忘了 `import request`，修复
- `_preserve_debug_files` 使 result.json 不再被 cleanup 删除
- 前端全局配置弹窗加了 Git Token 区域

---

## Episode 24: 正则不够，AST 来凑（2026-07-03）

**需求：** 用户发现信号提取用的是正则而不是真实 AST，准确性不可保证。

**分析：** 正则没问题的地方——`api.get(`、`fetch(`、`onClick={` 这些模式几乎没有误判。正则有问题的地方——`setTimeout(` 被误判为 STATE_ACTION、注释里的 `interface` 被误判为 DATA_MODEL。假阳性率不高，但确实存在。

**为什么不重写 9 个信号提取器？** 在每个提取器中加 AST 验证会导致大量重复的 try/catch 和行号匹配代码。更好的设计是：正则保持简单，新增一个集中验证层来过滤假阳性。

**怎么做：** 给所有 9 个信号提取器加了"保险"——正则发现候选信号后，丢给 `astValidator.ts`，它在 ts-morph AST 节点上一一确认。是真正的 `CallExpression` 才保留，是注释/字符串里的就过滤掉。

**另一个改进：** LLM 逐组调用时加 `type` 字段。AST 说这个是 STYLE_ONLY，但 LLM 看代码后发现"这个 CSS 实际上是权限控制"，可以在输出中修正分类。当然有限制——不能把 STYLE_ONLY 改成 NEW_FEATURE（样式不可能变成新功能），但 STYLE_ONLY ↔ FEATURE_MODIFY 是允许的。

**教训：** 10 类信号每种都有不同的"假阳性模式"，正则的定位是"筛查"不是"确诊"。AST 验证层的定位才是"确诊"。两个角色分开，比混在一起好维护。

---

## Episode 25: 验证器太严了（2026-07-03）

**问题：** AST 验证器上线后，`useInstanceDetail.ts` 这种有 Hook 有逻辑的文件被归为 STYLE_ONLY。因为验证器找不到 AST 节点就直接移除信号，文件变成 0 信号 → 决策树归为 STYLE_ONLY。

**修复：** 验证策略从"找不到就移除"改为"不确定就保留"。STYLE_ONLY 更特殊——被移除时用 GENERIC_CHANGE 信号代替，让决策树至少能归为 FEATURE_MODIFY 而不是 STYLE_ONLY。

**教训：** 验证器的三个策略是"确认假阳性才移除"、"确认假阳性且无替代时替换"、"不确定时保留"。一开始选了最严格的"找不到就移除"，结果过度过滤。验证器应该保守——宁愿漏掉一个假阳性，也不能错杀一个真信号。

---

## Episode 26: 信号拆细了，但 LLM 反而更稳了（2026-07-03）

**需求：** 用户验收了 5 项优化中的 5 项（方向 6 描述质量校验层暂时不搞），优先级：信号细粒度（constant/types 拆分 + 新增 TEXT/TYPE/TEST 信号）→ 两步 LLM 回归单步。

### 信号细粒度：三个小改动

**改动 1 — 聚类后拆分 constant/types 文件**

之前 `constant.ts` 和功能组件通过 import 关系聚在同一组，LLM 描述把文案和功能混在一起。`cluster.ts` 加了一个 `splitTextFileClusters()` 函数：检测 3 文件以上的大簇，把 `constant.ts`、`types.ts`、`contant.ts` 抽出来独立成组。

**改动 2 — 新增 3 种信号类型**

- `TEXT_CHANGE`：`constant.ts` 文件内容变更 → 归为"文案变更"
- `TYPE_CHANGE`：`types.ts` 新增 interface/type/enum → 归为 INFRA_CHANGE
- `TEST_CHANGE`：`*.test.ts`/`*.spec.ts` 文件变更 → 单独展示

每个新增的信号提取器不超过 40 行，全部在 `contentType.ts` 中。简单到不需要 AST 验证——文件名匹配 + 行内容正则就够了。

**改动 3 — 行号级信号定位**

`Signal` 类型加了 `line` 字段。`extractor.ts` 在提取信号后，自动用 addedLines 的前 30 字符匹配确定行号。LLM 输入中会附带行号信息。

### LLM 回归：从两步回到单步

之前为了减少报错，把 LLM 拆成了两步——step1 概括 category，step2 展开 description。结果：

- 两步各可能失败 → 报错率翻倍
- 失败组返回空 category → 多个组重叠显示"未知变更"
- step1 和 step2 的 type 分类可能不一致

用户说："不用担心 token 消耗，我要的是确保提取质量足够高。"

于是回归单步调用。`max_tokens` 从 1024 提升到 4096，加了一层重试（解析失败时重试 1 次），加了一层代码级别覆盖——如果 category 以"新增"开头，type 强制设为 NEW_FEATURE。失败了就用文件名兜底，不再出现空 category 和重复名称。

### 最终模块状态

经过 7 月 3 日全天的 5 项优化迭代，功能变更分析模块达到以下状态：

| 维度 | 状态 |
|------|------|
| 信号类型 | 14 种（NEW_ROUTE / NEW_PAGE / API_CALL / STATE_ACTION / PERMISSION / HOOK_DEF / EVENT_HANDLER / DATA_MODEL / CONFIG_CHANGE / STYLE_ONLY / GENERIC_CHANGE / TEXT_CHANGE / TYPE_CHANGE / TEST_CHANGE） |
| 信号提取 | 正则发现 + AST 验证双层过滤（保守策略：不确定时保留） |
| 聚类 | Import Graph 连通分量 + 目录聚类兜底 + page-logic/pages 合并 + constant/types 拆分 |
| 分类 | AST 决策树 + LLM type 修正（单步调用，max_tokens=4096） |
| 稳定性 | seed=42 + temperature=0.0 + 逐组调用（1:1 对齐） |
| 导出 | Markdown 下载 + 飞书文档 |
| 多仓库 | 可编辑 URL/分支，SQLite 缓存配置 |

---

## Episode 27: PRD 智能生成系统 MVP — 塑料焊工的一次正经工程实践

**时间：** 2026-07-06

### 背景

功能变更分析模块做完之后，下一个明确需求是"PRD 智能生成系统"。两篇文档已经写好了（完整方案和 MVP 方案），但完整方案有过度设计嫌疑（GraphRAG、JSON Schema 原型引擎），而 MVP 方案假设 FastAPI + Redis + Milkdown 等，与现有 Flask + SQLite + Ant Design 技术栈不一致。

### 文档修改

和之前几轮一样，先改文档再写代码。这次的主要改动：

| 文档 | 改动项 |
|------|--------|
| 完整方案 | FastAPI→Flask、PostgreSQL→SQLite、模型层命名修正（pro/flash 互转）、LLM 适配器复用标注、飞书妙记复用标注、前端技术栈适配 |
| MVP 方案 | FastAPI→Flask、Redis→SQLite 全量存储、JSONB→TEXT、并发生成→串行、版本管理简化（3 版）、简单模式分章节生成、导出接口 GET、复用现有代码标注、Prompt 防重复约束、API 路径统一 `/api/prd/*` |

### 7 个 Phase 的实现

#### Phase 1: 数据库扩展

4 张表全部用 TEXT 存 JSON，SQLite 不支持 JSONB，`collected_info`、`minutes_extract`、`outline`、`section_contents` 全部用 Python `json.loads/dumps` 处理。

最意外的是测试时发现 `get_db()` 依赖 Flask 的 `g` 对象，直接在命令行跑会报 `RuntimeError: Working outside of application context`。最后用原生 sqlite3 写 SQL 验证。

#### Phase 2: LLM 流式

`chat_stream()` 方法只有 20 行，但它是后面所有 SSE 流式生成的基础。`stream=True` 逐 token yield，前端用 ReactMarkdown 实时渲染。

#### Phase 3: 核心服务

`PRDGenService` 是这一轮最大的文件。主要逻辑：

- **简单模式**：大纲 → 逐章节流式生成，每章节完发送 `section_complete` 事件
- **中等模式**：问答轮次 → LLM 提取结构化信息到 `collected_info` → 完备度检查（6 项核心信息，前 5 项必填，≥80% 达标）→ 大纲 → 章节生成
- **版本管理**：`save_prd_version` 自动保存快照 + `cleanup_old_versions` 保留最近 3 版
- **妙记解析**：复用 `feishu_client.get_minute_info()` + `get_transcript()`
- **JSON 解析**：4 层递进容错（同 meeting_todo_service 的既存模式）

#### Phase 4-5: 路由 + 前端 API

13 个端点，统一注册 `/api/prd/*`。前端 `prdGen.ts` 含 13 个 API 函数（SSE 复用 `streamRequest`，导出用 `window.open` 触发 GET 下载）。

#### Phase 6: 前端页面

`PrdGen.tsx` 是最大的前端文件。布局：

```
步骤条（4 步）→ 输入区（文字/妙记/文件 Tab）
→ Q&A 区（中等模式，含 Progress 进度条）
→ 大纲区（章节按钮 + 状态标签）
→ 编辑器（Markdown 渲染 + 编辑切换 + Diff 对比 + 版本管理）
```

覆盖了 loading、empty、error、streaming 四种状态。

#### Phase 7: 路由集成

从 comingSoon 移到 activeNav，用户即点即用。

### 一些技术细节

- **`section_contents` 字段**：session 表里的 TEXT 字段存所有章节内容，替代每次从版本表读取，编辑和导出时省去了一次查询
- **`update_prd_session` 自动 JSON 序列化**：四个 JSON 字段传 dict/list 时自动 `json.dumps`，调用方不用管序列化
- **Diff 前端计算**：重新生成时后端只返回新内容，前端用 `react-diff-viewer-continued` 实时对比新旧内容，后端不存 Diff 数据
- **生成按钮智能禁用**：生成中只禁用当前章节按钮，其他章节仍可查看，不会阻塞用户体验

### 涉及文件

```
backend/services/db.py              — 4 表 + 14 CRUD
backend/services/llm_client.py       — chat_stream()
backend/services/prd_gen_service.py  — 新建（核心服务）
backend/services/project_context.md  — 新建（平台快照）
backend/routers/prd_gen.py           — 新建（13 端点）
backend/app.py                       — 注册 blueprint
frontend/src/api/prdGen.ts           — 新建
frontend/src/pages/PrdGen.tsx        — 新建
frontend/src/App.tsx                 — 路由
frontend/src/components/AppLayout.tsx — 侧边栏
```

### 迭代：中等模式对话质量优化

MVP 实现后，中等模式对话轮次经历了 4 轮迭代：

| 轮次 | 方案 | 问题 |
|------|------|------|
| 1 | 将用户回答填入 6 个固定字段 + 硬指标检查完备度 | LLM 幻觉填充所有字段，1 轮就 100% |
| 2 | LLM 基于对话历史判断完备度 + 代码层不满 4 轮强制继续 | LLM 判断太宽松，2 轮就说够了 |
| 3 | 7 个话题逐轮引导，LLM 判断是否进入下一话题 | 纠结一个话题反复问、问无关问题（战略对齐等）、多轮后遗忘重复 |
| 4 | 参考 `prd-skeleton.md` 重构输出模板为 9 节，优化 Prompt 约束体系 | 仍在迭代中 |

**核心教训**：LLM 不适合做"是否该进入下一话题"的精确判断，但也不能一刀切限制。需要更精细的 Prompt 约束 + 代码层安全兜底。

**当前状态**：PRD 模块阶段性完成，切换回前端代码优化。

---

## Episode 28: PRD Prompt 深度优化 — 从"写好"到"高质量可交付"（2026-07-08）

### 背景

用户测试 PRD 生成后反馈："生成的 PRD 过于粗糙，对 prompt 进行深度优化，确保生成的 PRD 是高质量可交付的。"

检查了现有 Prompt，确实问题明显：

| 问题 | 原来的写法 |
|------|-----------|
| 系统 Prompt 只有一句话 | "你是机器学习平台的产品需求文档撰写助手。" |
| 大纲 Prompt 只输出章节列表 | `["overview", "background", ...]` |
| 章节 Prompt 只有 2-3 句话 | "请撰写 PRD 的「XX」章节。要求：..." |
| 没有质量门禁 | 没有 ✅ 要求和 ❌ 禁止 |
| 没有具体示例 | 只有描述没有示范 |

### 改动思路

这次改动的核心是**把"质量标准"写到 Prompt 里**，而不是指望 LLM 自己知道什么是好的 PRD。

1. **系统 Prompt 从"助手"升级为"资深产品经理"**——角色定义决定了输出质量
2. **每个章节增加质量门禁**——✅ 要求 / ❌ 禁止，LLM 自检清单
3. **增加具体示例**——用户故事章节给了完整的 US-001 示例，LLM 可以参考格式
4. **大纲从纯列表改为 `{id, focus}` 结构**——每章带一句核心方向说明

### 一些设计决策

**质量门禁写在哪？** 一开始考虑写系统 Prompt 里，但 9 个章节各有不同的质量要求（overview 要求指标有基线值，stories 要求验收标准覆盖异常路径），共享的系统 Prompt 不够精确。最终每个章节 Prompt 尾部各自带质量门禁。

**反模式约束比正向要求更有效。** 比如"禁止：需求描述模糊（如'支持版本管理'——太粗，必须拆分为具体功能点）"比"请写清楚需求"有效得多。LLM 对"不要做什么"的执行力通常高于"要做什么"。

---

## Episode 29: 话题切换的视觉困境（2026-07-08）

### 问题

中等模式 7 个话题的对话全部挤在同一个对话框里，唯一的区分是左上角一个灰色小字"当前话题：XXX"。用户反馈"很难发现，用户很难知道进入到了哪个话题"。

### 3 层改进方案

我做了三个 HTML 原型（方案 A/B/C），让用户直观对比后选方案 A 落地：

1. **话题流水线 Steps**（对话区顶部 7 步横向进度条）
2. **话题切换分隔线**（紫色 Tag "🎯 进入话题：XXX"）
3. **话题进度指示**（"💬 当前话题：核心功能（3/7）"）

### 修复前的隐秘 bug

做原型时发现前端 `topicLabels` 和后端 `_QUESTION_TOPICS` 是两套完全不同的名字——前端是 `['问题与方案', '背景与战略', '用户与场景', ...]`，后端是 `['问题与解决方案', '用户与使用场景', '核心功能与优先级', ...]`。这导致话题索引计算一直不对，用户看到的"当前话题"永远无法正确匹配 Steps 进度条。这个 bug 在之前的迭代中从未被发现，因为话题名只在 UI 左上角显示，没人注意到它和实际后端返回的话题名不一致。

---

## Episode 30: 用户说"下一话题"——关键词强制推进（2026-07-08）

### 问题

用户要求："当用户表达需要进入下一个话题时，必须直接进入下一个话题，不能再纠结与当前话题。"

之前的方案完全依赖 LLM 判断"是否足够进入下一话题"，但 LLM 的判断不可靠——有时问 5 轮还在同一个话题，有时 1 轮就过了。虽然有 3 轮上限兜底，但用户主动说"下一话题"时，LLM 可能还会再追问一轮。

### 解法

关键词检测 + 强制推进：

```python
_NEXT_TOPIC_KEYWORDS = ["下一话题", "下一个", "继续", "跳过", "next topic", "进入下一话题", "换话题", "够了"]

if any(kw in answer for kw in _NEXT_TOPIC_KEYWORDS):
    force_advance = True
```

同时在 `_QUESTION_PROMPT` 中加第 7 条规则告知 LLM，双重保障。

### 区分

这里有三个推进机制，按优先级：

| 机制 | 触发条件 | 优先级 |
|------|---------|--------|
| 关键词强制推进 | 用户说"下一话题/继续/跳过" | 最高 |
| 代码层 3 轮上限 | 同话题超过 3 轮 | 中 |
| LLM 自主判断 | 根据对话历史判断"是否足够" | 最低（默认路径） |

---

## Episode 31: 全部话题完成后的回顾审查屏（2026-07-08）

### 背景

全部 7 个话题完成后，原来直接跳转到写大纲阶段。用户要求"最后所有流程走完后，需要给用户一个可修改回复以及可对某一个步骤进行进一步讨论的选项"。

### 回顾审查屏

不再直接跳转，改为展示**回顾审查屏**：

- 顶部 Alert "🎉 所有话题已收集完成"
- 中间 7 个话题列表，每个显示 ✅ + 话题名 + 回答条数
- 每个话题右侧有"修改"按钮
- 底部"确认，开始生成大纲"和"还需要补充"两个按钮

### 后端 rechat_topic 逻辑

点击"修改"后，需要后端配合：

1. 将指定话题从 `completed_topics` 移除
2. 回退 `_current_topic_idx` 到该话题位置
3. 清理该话题之后已完成的话题（因为后续需要重新走）
4. LLM 根据之前该话题的对话历史生成承上启下的引导问题

这个逻辑的关键在于：**回退时要清理后续话题**，否则用户修改了前面的内容，后面的章节还是基于旧信息生成的。

---

## Episode 32: 前序章节内容摘要注入（2026-07-08）

### 背景

用户问了一个关键问题："如果我修改了第一章节，第二章节会知道吗？"

答案是：**不会。** 每个章节生成时只依赖 `collected_info`（问答阶段收集的信息）+ 用户原始输入 + 妙记提取结果，完全不知道其他章节写了什么。

### 问题场景

如果用户在章节 1 中补充了"支持 3 种模型格式"，章节 2 生成时完全不知道这个信息，可能只写了 2 种，或者写的内容和章节 1 矛盾。

### 解法

新增 `_build_preceding_sections_text()`，按大纲顺序提取已生成的前序章节，取前 150 字作为摘要，注入 Prompt。

```python
def _build_preceding_sections_text(session, current_section):
    outline = json.loads(session.get('outline', '[]'))
    contents = json.loads(session.get('section_contents', '{}'))
    for section in outline:
        if section == current_section:
            break
        content = contents.get(section, '')
        if content:
            summary = content[:150] + '…'
            preceding.append(f'「{section_name}」：{summary}')
```

### Prompt 最终组成

每个章节生成时，LLM 看到的完整上下文：

```
【用户原始需求】→ 用户输入的描述
【问答收集】→ 6 个结构化字段
【会议提取】→ 妙记需求点
【已生成的前序章节内容摘要】→ 前 150 字摘要
⚠️ 一致性约束 → "必须与上述内容保持一致，不要重复"
```

### 改动范围

`simple_generate()` 和 `generate_section()` 都改了，简单模式和中等模式都受益。TypeScript 零错误，Python import 正常。