"""
prd_gen_service.py — PRD 智能生成核心业务逻辑

工作流：
  简单模式：用户输入 → 大纲 → 逐章节流式生成 → 导出
  中等模式：用户输入 → 3-5 轮问答 → 大纲 → 逐章节流式生成 → 导出

依赖：
  - services/db.py — 数据库 CRUD
  - services/llm_client.py — LLM 调用（含流式）
  - services/feishu_client.py — 飞书妙记解析（复用）
  - services/sse_helpers.py — SSE 事件构造
"""

import json
import logging
import os
import uuid

import requests

from .db import (
    create_prd_session, get_prd_session, update_prd_session,
    save_prd_version, get_prd_versions, get_prd_version_content,
    add_chat_message, get_chat_messages,
    save_prd_file, get_prd_files, get_prd_file,
)
from .llm_client import LLMClient
from .sse_helpers import sse_event

logger = logging.getLogger(__name__)

# 无矩2.0 知识库微服务基地址（RAG 检索 + 后续图谱查询共用）
KB_BASE_URL = os.environ.get('KB_BASE_URL', 'http://localhost:8000')
# 历史 PRD 集合名（待用户提供历史 PRD 后导入）
PRD_HISTORY_COLLECTION = 'prd_history'


# ── Prompt 模板 ──

_SYSTEM_PROMPT_TEMPLATE = """你是资深产品经理（Senior Product Manager），专精于 B 端平台产品需求文档撰写。你的输出直接交付给研发团队使用，必须达到以下标准：

## 质量标准
1. **精确性**：每个论断必须有依据，不臆测、不编造。用"建议"标注不确定的推断。
2. **完整性**：覆盖功能定义、用户流程、边界条件、验收标准、非功能需求，不留空白。
3. **可执行性**：研发拿到后能直接拆卡开发，不需要反复找 PM 确认细节。
4. **结构化**：层级清晰（章节 → 子节 → 要点），长段落拆分为列表。
5. **数据驱动**：指标必须有基线值（当前值），没有基线就不能算指标。

## 写作原则
- 用简洁、准确的中文撰写，避免啰嗦的修饰语
- 每个功能点必须描述"做什么"和"为什么做"，缺一不可
- 用户故事必须有可测试的验收标准（Acceptance Criteria）
- 边界条件必须包括：空状态、错误状态、异常流程、极限情况
- 优先级必须明确标注 P0/P1/P2，P0=必须有，P1=应该有，P2=可以有
- 非功能需求必须包含具体数值（性能指标、并发量、响应时间等）"""

_OUTLINE_PROMPT = """请根据以下需求描述，生成 PRD 大纲。每个章节需要说明其核心内容方向。

输出格式（严格 JSON，不要包含其他内容）：
{{
  "sections": [
    {{"id": "overview", "focus": "一句话说明本节核心"}},
    {{"id": "background", "focus": "一句话说明本节核心"}},
    ...
  ]
}}

可用章节列表（必须全部包含，顺序固定）：
1. overview: 功能概述 — 问题陈述、解决方案、成功指标、目标用户
2. background: 背景与上下文 — 为什么现在做、战略对齐、竞品/研究总结
3. stories: 用户故事 — 3-7 条 As a/I want/So that 用户故事 + 验收标准
4. requirements: 需求定义 — 功能需求（P0/P1/P2 Table）+ 非功能需求（性能/安全/可访问性）
5. design: 设计与交互 — 用户流程、页面布局、交互状态（Loading/Empty/Error/Edge）
6. technical: 技术考虑 — 架构依赖、风险与缓解、数据模型
7. rollout: 分阶段发布计划 — MVP→阶段2→阶段3，每阶段范围+门禁
8. questions: 开放问题 — 待决策的事项列表
9. appendix: 附录 — 参考链接、术语表、竞品分析笔记

为每个章节的 focus 字段填写一句核心内容方向，说明本章要解决什么问题。

需求描述：
{user_input}"""

# 9 个章节的详细 Prompt
_SECTION_PROMPTS = {
    "overview": """请撰写 PRD 的「功能概述」章节。这是整份 PRD 最重要的章节，读者（研发/测试/PM）通过它判断是否要继续读下去。

## 必须包含以下 3 个子节，顺序固定：

### 1. 问题陈述
- 从用户视角描述当前痛点，2-3 句话
- 包含具体数据或频率描述（如"每周约 5 次因版本回滚导致线上事故"）
- 说明不解决的后果（如"每次版本推送需要 2 名工程师手动操作 30 分钟"）

### 2. 解决方案
- 高层方案描述，3-5 句话
- 说明"做了什么"和"怎么做的"，但不涉及实现细节
- 明确本功能的范围边界（什么做、什么不做）

### 3. 成功指标
| 指标 | 当前基线 | 目标值 | 衡量时间 |
|---|---|---|---|
| 采用率 | x% | y% | 上线后 N 周 |
| 核心效果 | x | y | 上线后 N 周 |
| 业务影响 | x | y | 上线后 N 周 |
| 防护指标 | x | y | 上线后 N 周 |

- 每个指标必须有基线值（当前值是多少），没有基线就不能算指标
- 至少包含一个防护指标（"什么不能变差"）
- 指标必须与功能行为直接相关，可量化

### 4. 目标用户
- 列出本功能面向的用户角色（如算法工程师、标注管理员、平台运营）
- 简要说明各角色如何使用本功能

## 质量门禁：
- ❌ 禁止："优化了体验"、"提升了效率"等模糊表述
- ❌ 禁止：没有基线的指标
- ✅ 要求：每个痛点都有数据支撑
- ✅ 要求：方案描述让研发能判断实现复杂度

已收集的需求信息：
{collected_info}""",

    "background": """请撰写 PRD 的「背景与上下文」章节。说明为什么这个功能现在做、不做会怎样。

## 必须包含以下 3 个子节：

### 1. 为什么现在做
- 触发事件（下降的指标、用户投诉、竞争对手动作、战略押注、技术债务到期等）
- 当前的业务或技术痛点是什么
- 如果不做，短期和中期的影响是什么

### 2. 战略对齐
- 对齐的公司/团队目标（如"本季度 O 项目标是提升模型迭代效率"）
- 本功能对目标的贡献度评估（直接贡献 / 间接支撑 / 基础设施）

### 3. 相关研究（可选，有则写）
- 竞品分析发现（附竞品名称和关键差异）
- 用户调研发现（附样本量，如"N=15 人访谈"）
- 数据分析发现（如"后台数据显示 80% 的回滚由版本管理不当导致"）

## 质量门禁：
- ❌ 禁止：空泛的战略描述（如"响应公司数字化转型号召"）
- ✅ 要求：每个触发事件都有具体来源（数据/用户反馈/竞品动态）
- ✅ 要求：说明不做的影响，而不仅仅是做的价值

已收集的需求信息：
{collected_info}""",

    "stories": """请撰写 PRD 的「用户故事」章节。

## 格式要求：
- 3-7 条用户故事，按优先级排列
- 格式：**As a** [用户角色], **I want to** [动作], **So that** [收益/价值]
- 每条故事必须附带可测试的验收标准（Acceptance Criteria）

## 示例：
```
### US-001: 模型版本注册
- **As a** 算法工程师
- **I want to** 在训练完成后将模型注册到版本管理系统，填写模型名称、描述和标签
- **So that** 模型可以被团队其他成员查看和使用
- **优先级**: P0
- **验收标准**:
  1. 用户可输入模型名称（必填，50 字以内）
  2. 用户可输入描述（选填，500 字以内）
  3. 用户可选择 1-3 个标签（预定义标签列表）
  4. 注册成功后自动生成版本号（v{major}.{minor}.{patch}）
  5. 版本号不可重复，重复时提示"该版本号已存在"
  6. 注册失败时保留已填内容，不丢失
```

## 验收标准必须覆盖：
- 正常流程（Happy Path）
- 异常流程（必填项为空、重复提交、网络失败）
- 边界条件（输入长度限制、特殊字符、并发操作）

## 质量门禁：
- ❌ 禁止：没有验收标准的用户故事
- ❌ 禁止：故事粒度过大（如"作为用户，我能管理模型"——太粗，应拆分为注册/查看/对比/删除等多个故事）
- ✅ 要求：每个故事可独立开发、独立测试
- ✅ 要求：验收标准包含正常路径和至少一条异常路径

已收集的需求信息：
{collected_info}""",

    "requirements": """请撰写 PRD 的「需求」章节。这是研发直接用来拆卡的部分，必须精确、完整。

## 必须包含以下 2 个子节：

### 1. 功能需求（Table 格式）
| ID | 模块 | 需求描述 | 优先级 | 关联用户故事 |
|---|---|---|---|---|
| F1 | 模型注册 | 支持模型注册，填写名称/描述/标签后自动生成版本号 | P0 | US-001 |
| F2 | 版本对比 | 支持选择两个版本进行差异对比，展示参数/指标/代码差异 | P0 | US-002 |
| F3 | 版本回滚 | 支持一键回滚到指定历史版本，需二次确认 | P1 | US-003 |

- P0 = 必须有（MVP 必须包含，否则无法上线）
- P1 = 应该有（重要但不阻塞上线）
- P2 = 可以有（锦上添花，后续迭代安排）
- 每行需求必须描述清晰，研发能直接评估工作量

### 2. 非功能需求
- **性能**：具体数值（如"页面加载时间 p95 < 800ms"，"列表查询 p99 < 2s"）
- **安全与权限**：涉及的数据范围、访问控制规则、操作审计要求
- **可访问性**：无障碍标准（如"支持键盘 Tab 导航"）
- **兼容性**：支持的浏览器/分辨率、API 兼容性要求
- **可靠性**：SLA 目标、容错机制、数据一致性要求

## 质量门禁：
- ❌ 禁止：模糊的需求描述（如"支持版本管理"——太粗，必须拆分为具体功能点）
- ❌ 禁止：没有优先级标注的需求
- ✅ 要求：功能需求与用户故事可追溯关联
- ✅ 要求：非功能需求有具体数值

已收集的需求信息：
{collected_info}""",

    "design": """请撰写 PRD 的「设计与交互」章节。描述用户使用该功能时的完整体验，但不需要 UI 设计稿级别的细节。

## 必须包含以下内容：

### 1. 核心用户流程
- 描述用户完成主要任务的操作步骤（步骤编号列表）
- 示例：
  ```
  1. 用户进入"模型版本管理"页面，默认展示当前模型列表
  2. 用户点击"注册新版本"按钮，弹出注册表单
  3. 用户填写名称/描述/标签，点击"确认注册"
  4. 系统生成版本号，返回成功，列表自动刷新
  5. 用户可在列表中找到新注册的版本
  ```

### 2. 页面布局说明（文字描述，不需要图示）
- 主要页面/弹窗/侧边栏的功能分区
- 页面导航层级（从哪个入口进入，如何返回）

### 3. 状态覆盖
每个关键交互至少覆盖以下 4 种状态：
- **Loading 状态**：数据加载中的展示
- **Empty 状态**：无数据时的展示（如"暂无模型版本"）
- **Error 状态**：操作失败时的提示和恢复方式
- **Edge 状态**：边界情况（如列表超过 100 条时分页、名称超长时截断）

### 4. 交互反馈
- 操作成功/失败的反馈方式（Toast / Alert / 行内提示）
- 需要用户确认的操作（如删除、回滚）→ 二次确认弹窗
- 长时间操作的进度提示（如"模型正在注册中…"）

## 质量门禁：
- ❌ 禁止：只有流程没有状态覆盖
- ❌ 禁止：只描述"正常情况"不描述"出错怎么办"
- ✅ 要求：每个主要操作步骤都标注了对应的状态覆盖
- ✅ 要求：用户能清晰理解"我从哪进、怎么用、出错了怎么办"

已收集的需求信息：
{collected_info}""",

    "technical": """请撰写 PRD 的「技术考虑」章节。注意：这是 PRD 级别的技术考虑，不是技术方案文档，不需要实现细节。

## 必须包含以下内容：

### 1. 依赖的系统与模块
- 本功能依赖的已有平台模块（如"用户权限系统"、"模型训练平台"）
- 依赖的外部系统（如"飞书审批 API"、"GitLab CI"）
- 依赖的团队（如"需要基础架构团队提供 GPU 资源调度接口"）

### 2. 风险与缓解措施
| 风险 | 影响 | 概率 | 缓解措施 |
|---|---|---|---|
| 模型版本并发写入导致冲突 | 高 | 中 | 乐观锁 + 冲突提示 |
| 历史版本数据量过大影响查询 | 中 | 高 | 分页 + 索引 + 冷热数据分离 |

- 至少列出 3 个风险项
- 概率用"高/中/低"标注
- 缓解措施必须是具体可执行的方案

### 3. 数据模型（可选，有则写）
- 核心数据实体及其关键字段（简单描述，不需要完整的 ER 图）
- 数据量和存储需求预估

## 质量门禁：
- ❌ 禁止：写实现细节（如"用 Redis 缓存"、"用消息队列"——那是技术方案的事）
- ❌ 禁止：风险项只有描述没有缓解措施
- ✅ 要求：依赖项标注了是否已存在（已有/待开发/待调研）
- ✅ 要求：风险项至少有 3 条

已收集的需求信息：
{collected_info}""",

    "rollout": """请撰写 PRD 的「分阶段发布计划」章节。

## 格式要求：
| 阶段 | 范围 | 目标用户 | 进入下一阶段的门禁 |
|---|---|---|---|
| MVP | 核心功能清单 | 内部试点团队（N 人） | 1. P0 功能全部通过 QA<br>2. 无 P0/P1 级别的线上 Bug<br>3. 试点团队使用满意度 ≥ 4/5 |
| 阶段 2 | 扩展功能清单 | 全部内部用户 | 1. P1 功能通过 QA<br>2. 灰度 3 天无重大事故 |
| 阶段 3 | 后续迭代 | 全部用户 + 外部客户（如有） | 1. 稳定运行 2 周<br>2. 性能指标达标 |

## 必须包含：
- 每个阶段的具体功能范围（引用需求 ID 或用户故事 ID）
- 明确的目标用户群体和规模
- 可量化的门禁标准（不是"测试通过"而是"P0 功能全部通过 QA"）
- 每个阶段的预期交付时间范围（如"MVP 预计 2 周"）

## 质量门禁：
- ❌ 禁止：门禁标准模糊（如"质量达标"、"性能满足要求"）
- ✅ 要求：每个阶段都有退出标准（Exit Criteria）
- ✅ 要求：MVP 范围明确标注了 P0 功能列表

已收集的需求信息：
{collected_info}""",

    "questions": """请撰写 PRD 的「开放问题」章节。列出所有需要产品/技术决策的事项。

## 格式要求：
| 问题编号 | 问题描述 | 影响范围 | 建议方案 | 需要决策人 | 需要决策时间 |
|---|---|---|---|---|---|
| Q1 | 版本号格式采用语义化版本（SemVer）还是自增序号？ | 影响所有版本操作 | 建议 SemVer，兼容现有系统 | 技术负责人 | 开发前 |
| Q2 | 回滚操作是否需要审批流程？ | 影响回滚功能设计 | 建议 P0 回滚需审批，P1 无需 | 技术负责人 + PM | 开发前 |
| Q3 | 历史版本保留多久？ | 影响存储方案 | 建议保留最近 50 个版本，更早的归档 | 技术负责人 | 开发前 |

## 必须包含：
- 至少 3 个开放问题（如果确实没有，写"无"）
- 每个问题必须有建议方案（不能只提问不表态）
- 标注需要决策的时间节点（"开发前"、"上线前"、"迭代中"）

## 质量门禁：
- ❌ 禁止：只有问题没有建议方案（那是甩锅，不是 PRD）
- ✅ 要求：每个问题都标注了"不决策的后果"（如"不决策则默认使用自增序号"）

已收集的需求信息：
{collected_info}""",

    "appendix": """请撰写 PRD 的「附录」章节。存放正文中提及的补充材料。

## 必须包含以下内容：

### 1. 参考链接与文档
- 引用的外部文档、设计稿、调研报告链接
- 相关的竞品文档链接
- 关联的 PRD 或技术方案文档

### 2. 术语表（如果涉及新概念）
| 术语 | 英文 | 定义 |
|---|---|---|
| 模型版本 | Model Version | 一次训练产出的完整模型+参数+代码的快照 |
| 灰度发布 | Canary Release | 先对部分用户发布，验证稳定后再全量 |

### 3. 竞品分析笔记（可选，有则写）
- 简要对比 2-3 个竞品的相关功能
- 核心差异点和借鉴点

## 质量门禁：
- ❌ 禁止：空附录（"暂无"——如果真的没有就不写这个子节）
- ✅ 要求：引用链接可访问、术语表定义清晰

已收集的需求信息：
{collected_info}""",
}

_SECTION_NAMES = {
    "overview": "功能概述",
    "background": "背景与上下文",
    "stories": "用户故事",
    "requirements": "需求定义",
    "design": "设计与交互",
    "technical": "技术考虑",
    "rollout": "分阶段发布计划",
    "questions": "开放问题",
    "appendix": "附录",
}

# 中等模式引导话题（7 个话题，LLM 逐轮判断是否完成）
_QUESTION_TOPICS = [
    {
        "topic": "问题与解决方案",
        "guide": "引导用户描述当前遇到了什么具体问题/痛点，期望的解决方案是什么",
        "check": "用户是否描述了：当前的问题是什么、期望的解决方案方向",
    },
    {
        "topic": "用户与使用场景",
        "guide": "引导用户明确这个功能主要面向哪些用户角色，在什么场景下使用",
        "check": "用户是否描述了：目标用户角色、核心使用场景",
    },
    {
        "topic": "核心功能与优先级",
        "guide": "引导用户列出核心功能点，区分必须有的（P0）和后续做的（P1）",
        "check": "用户是否描述了：核心功能列表、P0/P1 优先级区分",
    },
    {
        "topic": "操作流程",
        "guide": "引导用户描述用户使用该功能的主要操作步骤",
        "check": "用户是否描述了：核心操作路径和步骤",
    },
    {
        "topic": "边界与约束",
        "guide": "引导用户明确限制条件、异常处理、约束（如版本数量限制、回滚审批等）",
        "check": "用户是否描述了：边界条件、限制约束、异常处理要求",
    },
    {
        "topic": "非功能需求",
        "guide": "引导用户明确性能、安全、审计等方面的要求",
        "check": "用户是否描述了：性能指标、安全/审计要求",
    },
    {
        "topic": "技术依赖与发布范围",
        "guide": "引导用户说明依赖哪些已有模块，MVP 范围和后续阶段",
        "check": "用户是否描述了：依赖的模块/系统、MVP 范围",
    },
]

# 用户说"下一话题"时的关键词检测
_NEXT_TOPIC_KEYWORDS = ["下一话题", "下一个", "继续", "跳过", "next topic", "进入下一话题", "换话题", "够了"]

_QUESTION_PROMPT = """你是机器学习平台产品的需求分析助手，正在通过多轮对话收集 PRD 所需信息。你的目标是引导用户提供足够的信息，以便产生一份高质量、可交付的 PRD。

## 核心原则
1. 每一轮只问一个问题，一次只聚焦一个话题
2. 问题要具体、有引导性（不要问"请描述"，而是问"平均每天有多少次模型推送？"）
3. 不要问与 PRD 功能需求无关的问题（如公司战略、团队目标、组织架构等）
4. 参考对话历史，不要重复问已经回答过的问题
5. 如果用户回答中说"不知道"或"没有"，视为该话题已覆盖，进入下一话题
6. 用户回答的信息越具体越好，如果回答模糊，追问具体细节
7. **如果用户说"下一话题"、"继续"、"跳过"等，说明用户想直接进入下一话题，不要再追问当前话题**

## 用户原始需求
{user_input}

## 对话历史（完整记录，包含之前所有问答）
{chat_history}

## 当前引导话题
当前话题：{current_topic}
引导说明：{current_guide}
完成标准：{current_check}

## 输出格式
返回严格 JSON，不要包含其他内容：

如果继续追问当前话题：
{{"status": "continue", "question": "针对当前话题的追问（简洁、具体，聚焦细节补充）", "topic_done": false, "reason": "为什么还需要追问"}}

如果当前话题已足够，进入下一话题：
{{"status": "continue", "question": "下一话题的引导问题（结合历史，承上启下）", "topic_done": true, "items_covered": ["已覆盖的话题名称1", "已覆盖的话题名称2"]}}

如果所有 7 个话题都已覆盖：
{{"status": "complete", "reason": "全部 7 个话题已收集完毕", "items_covered": ["话题1", "话题2", "话题3", "topic4", "topic5", "topic6", "topic7"]}}"""

_MINUTES_EXTRACT_PROMPT = """你是机器学习平台的需求分析专家。请从以下飞书会议纪要中提取与产品功能需求相关的信息。

## 提取要求
- 只提取与产品功能需求直接相关的信息
- 过滤掉：寒暄、会议流程、进度同步、非技术讨论
- 如果会议中未提及某类信息，对应字段返回空数组

## 输出格式（严格 JSON，不要包含其他内容）：
{{
  "featurePoints": ["功能需求点1（具体描述，包含动作和场景）", "功能需求点2"],
  "stakeholders": ["涉及的干系人/角色（如算法工程师、标注团队、平台管理员）"],
  "constraints": ["约束条件/限制（如单模型版本数上限、审批流程要求）"],
  "background": "需求产生的背景和动机（2-3 句话，包含触发事件）",
  "existing_workflow": "当前的工作流程描述（如何在没有该功能时完成工作）",
  "pain_points": ["当前痛点1", "当前痛点2"]
}}

会议纪要：
{minutes_text}"""

# 旧章节名映射（保留以兼容大纲输出）
_SECTION_NAMES_OLD = {
    "overview": "功能概述",
    "roles": "用户角色",
    "features": "功能清单",
    "stories": "用户故事",
    "boundaries": "边界条件与异常处理",
    "nonfunctional": "非功能需求",
}


class PRDGenService:
    """PRD 生成核心服务

    管理会话生命周期、LLM 调用、Prompt 组装、完备度检查。
    """

    # ── 基础方法 ──

    @staticmethod
    def _make_llm(api_key: str, base_url: str, model: str) -> LLMClient:
        """创建 LLM 客户端"""
        return LLMClient(api_key=api_key, base_url=base_url, model=model)

    @staticmethod
    def _build_system_prompt() -> str:
        """拼装 System Prompt"""
        return _SYSTEM_PROMPT_TEMPLATE

    @staticmethod
    def _parse_json_safe(text: str, default: dict | list) -> dict | list:
        """安全解析 JSON，失败返回默认值

        5 层递进容错（与 meeting_todo_service 相似）：
        1. 标准 json.loads
        2. 清理 ```json ... ``` 标记
        3. 容忍尾随逗号
        4. 截断修复（找到最后一个 } 或 ]）
        """
        if not text:
            return default

        # 1. 标准解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. 清理代码块标记
        cleaned = text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 3. 容忍尾随逗号
        for fix in (lambda s: s.replace(',\n}', '\n}').replace(',\n]', '\n]'),):
            try:
                return json.loads(fix(cleaned))
            except json.JSONDecodeError:
                continue

        # 4. 截断修复 — 找到最后一个 } 或 ]
        for end_char in ('}', ']'):
            pos = cleaned.rfind(end_char)
            if pos > 0:
                try:
                    return json.loads(cleaned[:pos + 1])
                except json.JSONDecodeError:
                    continue

        logger.warning(f'JSON 解析失败: {text[:200]}')
        return default

    @staticmethod
    def _build_collected_info_text(session: dict, current_section: str = '', rag_enabled: bool = True) -> str:
        """从 collected_info 和 user_input 构建信息文本（入 LLM Prompt）

        可选注入 RAG 参考片段（历史 PRD），降级时返回空串不影响生成。
        """
        parts = []

        user_input = session.get('user_input', '').strip()
        if user_input:
            parts.append(f'【用户原始需求】\n{user_input}')

        collected = json.loads(session.get('collected_info', '{}') or '{}')
        field_labels = {
            'featureOverview': '功能概述',
            'userRoles': '用户角色',
            'corePath': '核心操作路径',
            'boundaries': '边界条件',
            'inputOutput': '输入输出',
            'dependencies': '依赖模块',
        }
        for key, label in field_labels.items():
            val = collected.get(key, '')
            if val:
                parts.append(f'{label}: {val}')

        minutes = json.loads(session.get('minutes_extract', '{}') or '{}')
        if minutes.get('featurePoints'):
            parts.append(f'【会议提取】功能需求点: {", ".join(minutes["featurePoints"])}')
        if minutes.get('background'):
            parts.append(f'【会议提取】背景: {minutes["background"]}')

        # RAG 参考上下文（历史 PRD），降级空串
        if rag_enabled and current_section:
            rag_context = PRDGenService._retrieve_reference_context(session, current_section)
            if rag_context:
                parts.append(rag_context)

        return '\n\n'.join(parts) if parts else '（暂无补充信息）'

    @staticmethod
    def _query_kb_agent(question: str) -> list[dict]:
        """调用知识库非流式查询 /api/query，获取相关上下文片段

        返回 [{content, collection, score, metadata}, ...]。
        降级：微服务挂/超时 → 空列表。
        """
        if not (question or '').strip():
            return []
        try:
            resp = requests.post(
                f'{KB_BASE_URL}/api/query',
                json={'query': question.strip()[:500]},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('contexts', []) or []
        except requests.exceptions.ConnectionError:
            logger.warning('[PRDGen] KB 问答查询失败: 微服务未启动')
            return []
        except requests.exceptions.Timeout:
            logger.warning('[PRDGen] KB 问答查询超时')
            return []
        except Exception as e:
            logger.warning(f'[PRDGen] KB 问答查询异常: {e}')
            return []

    @staticmethod
    def _retrieve_reference_context(session: dict, current_section: str) -> str:
        """从知识库检索与当前 PRD 需求最相似的历史 PRD 片段（Few-shot 参考）

        调无矩2.0 /api/query/stream，collection=prd_history，取前 3 片段各截断 500 字。
        降级链路：
          - 微服务未启动 → 空串（日志 warning）
          - 无 prd_history 集合/无结果 → 空串（日志 info）
          - 检索异常 → 空串（日志 warning）
        无数据时不阻塞 PRD 生成，仅损失参考能力。
        """
        user_input = (session.get('user_input', '') or '').strip()
        section_name = _SECTION_NAMES.get(current_section, current_section)
        query = f'{user_input} {section_name}'.strip()[:200]

        if not query.strip():
            return ''

        try:
            resp = requests.post(
                f'{KB_BASE_URL}/api/query/stream',
                json={
                    'query': query,
                    'collections': [PRD_HISTORY_COLLECTION],
                    'top_k': 3,
                    'similarity_threshold': 0.5,
                    'page_size': 3,
                },
                timeout=15,
                stream=True,
            )
        except requests.exceptions.ConnectionError:
            logger.warning('[PRDGen] RAG 检索失败: 知识库服务未启动')
            return ''
        except requests.exceptions.Timeout:
            logger.warning('[PRDGen] RAG 检索超时')
            return ''
        except Exception as e:
            logger.warning(f'[PRDGen] RAG 检索异常: {e}')
            return ''

        # 解析 SSE 响应，提取 sources（事件格式与 chat.py 一致）
        sources = []
        try:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode('utf-8', errors='ignore')
                if not line.startswith('data: '):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                # 优先取 sources 事件；兜底取 token 累积中的 sources 字段
                if data.get('type') == 'sources' or 'sources' in data:
                    src = data.get('sources', [])
                    if src:
                        sources = src
        except Exception as e:
            logger.warning(f'[PRDGen] RAG SSE 解析异常: {e}')
            return ''

        if not sources:
            logger.info(f'[PRDGen] RAG 检索无结果: query="{query}"')
            return ''

        parts = ['【参考历史PRD片段】']
        for i, src in enumerate(sources[:3], 1):
            title = src.get('title', '未知PRD')
            content = (src.get('content', '') or '')[:500]
            score = src.get('score', '')
            score_str = f' (相似度: {score:.2f})' if isinstance(score, (int, float)) else ''
            parts.append(f'参考{i}：「{title}」{score_str}\n{content}')

        parts.append('')
        parts.append('⚠️ 以上为历史PRD参考，当前PRD应基于实际需求设计，不要盲目照搬。')
        logger.info(f'[PRDGen] RAG 检索到 {len(sources)} 个参考片段')
        return '\n\n'.join(parts)

    # ── 深度模式 Agent 2：平台上下文分析（调知识库图谱）──

    @staticmethod
    def _kb_graph_get(path: str, params: dict = None, timeout: int = 10) -> dict | None:
        """直连知识库图谱 API（不经 Flask 代理，供深度模式内部调用）

        降级：微服务挂/超时/异常 → None。
        """
        try:
            resp = requests.get(f'{KB_BASE_URL}/api/admin{path}', params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get('status') == 'success':
                return data.get('data')
            return None
        except requests.exceptions.ConnectionError:
            logger.warning('[PRDGen] 图谱 API 未连接（微服务未启动）')
            return None
        except requests.exceptions.Timeout:
            logger.warning(f'[PRDGen] 图谱 API 超时（>{timeout}s）: {path}')
            return None
        except Exception as e:
            logger.warning(f'[PRDGen] 图谱 API 异常 ({path}): {e}')
            return None

    @staticmethod
    def _match_module(user_input: str, modules: list[dict]) -> str | None:
        """从 12 模块清单中匹配与用户需求最相关的模块名

        策略：user_input 包含 module_name 的子串，或 module_name 的关键词（backend_keywords）
        出现在 user_input 中。多命中取 controller_count 最大的（数据最丰富）。
        """
        if not user_input or not modules:
            return None
        text = user_input
        candidates = []
        for m in modules:
            name = m.get('module_name', '')
            if name and name in text:
                candidates.append((m, len(name)))
            else:
                # backend_keywords 子串命中
                kws = m.get('backend_keywords', []) or []
                hit_kw = [kw for kw in kws if kw and kw in text]
                if hit_kw:
                    candidates.append((m, sum(len(k) for k in hit_kw) * 0.5))

        if not candidates:
            return None
        # 关键词命中权重*0.5 < 名称命中，优先名称命中；同权重取 controller_count 大
        candidates.sort(key=lambda x: (x[1], x[0].get('controller_count', 0)), reverse=True)
        return candidates[0][0].get('module_name')

    @staticmethod
    def _retrieve_platform_context(session: dict) -> str:
        """Agent 2 平台上下文分析（调知识库图谱）

        组装两部分：
          1. 平台架构快照（模块的 controllers/apis/frontend_pages/external_deps）
          2. 影响范围预警（incoming：谁依赖该模块的核心 controller）

        降级链路：
          - 微服务挂 → 空串（深度模式仍可跑，无图谱上下文）
          - 无匹配模块 → 提示"未匹配到平台模块，基于需求自由设计"
          - 无 controller → 跳过影响范围部分
          - impact 无 incoming → 影响范围空，不阻塞
        """
        user_input = (session.get('user_input', '') or '').strip()
        if not user_input:
            return ''
        # Agent1 feature_name 比 user_input 更结构化，辅助模块匹配
        import json as _json
        _arts = _json.loads(session.get('deep_artifacts', '{}') or '{}')
        _a1 = _arts.get('agent1', {}) or {}
        _feature = (_a1.get('requirements', {}) or {}).get('feature_name', '') or ''
        match_text = f'{user_input} {_feature}'.strip()

        # Step 1: 取 12 模块清单 + 匹配
        modules_data = PRDGenService._kb_graph_get('/modules')
        if not modules_data:
            logger.info('[PRDGen] Agent2 平台上下文: 微服务未启动，降级空串')
            return ''
        modules = modules_data.get('modules', [])
        module_name = PRDGenService._match_module(match_text, modules)
        if not module_name:
            return '【平台架构快照】\n未匹配到平台模块，基于需求自由设计。'

        # Step 2: 拿架构快照
        from urllib.parse import quote
        overview = PRDGenService._kb_graph_get(f'/modules/{quote(module_name, safe="")}')
        if not overview:
            return f'【平台架构快照】\n模块「{module_name}」详情获取失败，基于需求设计。'

        controllers = overview.get('controllers', []) or []
        apis = overview.get('apis', []) or []
        frontend_pages = overview.get('frontend_pages', []) or []
        external_deps = overview.get('external_deps', []) or []
        services = overview.get('services', []) or []

        parts = [f'【平台架构快照】模块「{module_name}」']
        parts.append(f'- Controllers: {len(controllers)} 个')
        if controllers:
            ctrl_names = [c.get('name', c.get('node_id', '')) for c in controllers[:8]]
            parts.append(f'  代表: {", ".join(n for n in ctrl_names if n)[:200]}')
        parts.append(f'- Services: {len(services)} 个')
        parts.append(f'- APIs: {len(apis)} 个')
        parts.append(f'- 前端页面: {len(frontend_pages)} 个')
        if external_deps:
            dep_names = [d.get('name', d.get('node_id', '')) for d in external_deps[:5]]
            parts.append(f'- 外部依赖: {", ".join(n for n in dep_names if n)[:150]}')

        # Step 3b: 查该模块的页面布局（design_layouts）
        layout_parts = []
        try:
            import requests as _req
            lay_resp = _req.get(f'{KB_BASE_URL}/api/admin/design-layouts', timeout=10)
            if lay_resp.ok:
                all_pages = lay_resp.json().get('data', {}).get('modules', {})
                # 模块名简写匹配: "模型训练" → all_pages 中找含 "training" 的 key
                matched_key = None
                for mk in all_pages:
                    if module_name[:4] in mk or mk[:4] in module_name:
                        matched_key = mk
                        break
                    # backend_keywords 匹配
                    for kw in (modules_data.get('modules', []) or []):
                        if kw.get('module_name') == module_name:
                            for bk in (kw.get('backend_keywords', []) or []):
                                if bk[:4].lower() in mk.lower():
                                    matched_key = mk
                                    break
                if matched_key:
                    pages = all_pages[matched_key]
                    layout_parts.append(f'\n【页面布局】模块「{module_name}」有 {len(pages)} 个页面:')
                    for p in pages:
                        comps = ', '.join(p.get('layout_components', []) or [])
                        layout_parts.append(f'  - {p.get("page_id","?")} [{p.get("page_type","?")}] 组件: [{comps}]')
                else:
                    # 展示全平台页面类型分布
                    type_counts = lay_resp.json().get('data', {}).get('page_type_counts', {})
                    layout_parts.append(f'\n【页面布局】全平台页面类型: {dict(type_counts)}')
        except Exception as _e:
            logger.warning(f'[PRDGen] 页面布局查询失败: {_e}')

        if layout_parts:
            parts.append('\n'.join(layout_parts))

        # Step 3: 拿影响范围（incoming：谁依赖该模块核心 controller）
        impact_text = ''
        if controllers:
            ctrl_node = controllers[0].get('node_id') or controllers[0].get('name', '')
            if ctrl_node:
                impact = PRDGenService._kb_graph_get(
                    '/graph/impact',
                    params={'node': ctrl_node, 'direction': 'incoming', 'depth': 3},
                )
                if impact:
                    impacted = impact.get('impacted', []) or []
                    summary = impact.get('summary_by_type', {}) or {}
                    candidates = impact.get('candidates', [])
                    if candidates:
                        # 名称多候选，列出全部供 Agent 2 / 人工二次确认
                        impact_text = f'\n\n【影响范围预警】节点「{ctrl_node}」匹配多候选，需二次确认: '
                        impact_text += ', '.join(c.get('name', '') for c in candidates[:5])
                    elif impacted:
                        impact_text = f'\n\n【影响范围预警】修改「{module_name}」会影响（incoming，谁依赖我）:'
                        impact_lines = []
                        for item in impacted[:10]:
                            node = item.get('node', {}) or {}
                            impact_lines.append(
                                f'  - [{node.get("node_type", "?")}] '
                                f'{node.get("name", "?")} (深度 {item.get("depth", "?")})'
                            )
                        impact_text += '\n' + '\n'.join(impact_lines)
                        if summary:
                            dist = ', '.join(f'{k}×{v}' for k, v in sorted(summary.items(), key=lambda x: -x[1])[:6])
                            impact_text += f'\n影响节点类型分布: {dist}'
                    else:
                        impact_text = f'\n\n【影响范围预警】模块「{module_name}」核心 controller 无 incoming 依赖（可能是叶子模块）。'

        parts.append('⚠️ 建议在 PRD 中覆盖上述下游影响，并考虑与已有模块的接口契约。')
        return '\n'.join(parts) + impact_text

    @staticmethod
    def _build_preceding_sections_text(session: dict, current_section: str) -> str:
        """按大纲顺序提取当前章节之前已生成的章节内容摘要

        用于注入章节生成 Prompt，确保：
        1. 新章节不自相矛盾
        2. 不重复已写过的内容
        3. 前后引用保持一致
        """
        outline = json.loads(session.get('outline', '[]') or '[]')
        contents = json.loads(session.get('section_contents', '{}') or '{}')

        preceding = []
        for section in outline:
            if section == current_section:
                break
            content = contents.get(section, '').strip()
            if content:
                section_name = _SECTION_NAMES.get(section, section)
                # 取前 150 字作为摘要
                summary = content[:150].replace('\n', ' ').strip()
                if len(content) > 150:
                    summary += '…'
                preceding.append(f'「{section_name}」：{summary}')

        if not preceding:
            return ''

        result = '【已生成的前序章节内容摘要】\n'
        result += '\n\n'.join(preceding)
        result += '\n\n⚠️ 注意：你正在撰写的章节必须与上述内容保持一致，不要重复上述章节已覆盖的内容。如需引用，用"如上一章所述"等表述。'
        return result

    # ── 会话管理 ──

    def create_session(self, mode: str, user_input: str = '') -> dict:
        """创建新会话"""
        return create_prd_session(mode, user_input)

    def get_session(self, session_id: str) -> dict | None:
        return get_prd_session(session_id)

    def update_session(self, session_id: str, **kwargs):
        return update_prd_session(session_id, **kwargs)

    # ── 信息完备度检查 ──

    @staticmethod
    def _get_missing_items(session: dict) -> list[str]:
        """获取缺失的信息项列表"""
        completed = json.loads(session.get('collected_info', '{}') or '{}').get('_completed_topics', [])
        all_topics = [t['topic'] for t in _QUESTION_TOPICS]
        return [t for t in all_topics if t not in completed]

    # ── 简单模式 ──

    def simple_generate(self, session_id: str, api_key: str, base_url: str, model: str,
                        rag_enabled: bool = True):
        """简单模式生成流程

        1. 生成大纲 → 存入 session
        2. 逐章节生成 → 每章节 section_complete 事件
        """
        session = self.get_session(session_id)
        if not session:
            yield sse_event('error', {'message': '会话不存在'})
            return

        llm = self._make_llm(api_key, base_url, model)

        # Step 1: 生成大纲
        yield sse_event('progress', {'step': 'outline', 'message': '正在分析需求、生成大纲...'})
        outline_text = llm.chat(
            system=self._build_system_prompt(),
            user=_OUTLINE_PROMPT.format(user_input=session.get('user_input', '')),
        )
        sections = self._parse_outline(outline_text)
        self.update_session(session_id, outline=json.dumps(sections, ensure_ascii=False), status='writing')
        yield sse_event('section_complete', {'section': 'outline', 'outline': sections})

        # Step 2: 逐章节生成（注入前序章节内容摘要，确保一致性和不重复）
        for section in sections:
            section_name = _SECTION_NAMES.get(section, section)
            yield sse_event('progress', {'step': section, 'message': f'正在生成章节「{section_name}」...'})

            collected_info = self._build_collected_info_text(
                session, current_section=section, rag_enabled=rag_enabled,
            )
            preceding_text = self._build_preceding_sections_text(session, section)
            full_context = collected_info
            if preceding_text:
                full_context += '\n\n' + preceding_text

            prompt = _SECTION_PROMPTS.get(section, '请撰写 PRD 的"{section_name}"章节。内容基于已收集的需求信息，不要臆造。使用 Markdown 格式。\n\n已收集的需求信息：{collected_info}')
            content = ''
            for chunk in llm.chat_stream(
                system=self._build_system_prompt(),
                user=prompt.format(collected_info=full_context) if '{collected_info}' in prompt else prompt + f'\n\n已收集的需求信息：{full_context}',
            ):
                content += chunk
                yield sse_event('progress', {'chunk': chunk, 'section': section})

            version_info = save_prd_version(session_id, section, content)
            self._save_section_to_session(session_id, section, content)
            yield sse_event('section_complete', {
                'section': section,
                'content': content,
                'versionId': version_info['id'],
            })

        self.update_session(session_id, status='done')
        yield sse_event('complete', {'sessionId': session_id})

    @staticmethod
    def _parse_outline(text: str) -> list[str]:
        """解析大纲 JSON"""
        result = PRDGenService._parse_json_safe(text, {'sections': list(_SECTION_NAMES.keys())})
        if isinstance(result, dict):
            sections = result.get('sections', [])
            if sections:
                return sections
        return list(_SECTION_NAMES.keys())

    # ── 中等模式 — 对话轮次 ──

    def _build_chat_collected_text(self, session: dict) -> str:
        """构建可读的收集信息文本"""
        collected = json.loads(session.get('collected_info', '{}') or '{}')
        completed = collected.get('_completed_topics', [])
        return f"已完成的话题：{', '.join(completed) if completed else '暂无'}"

    def start_chat(self, session_id: str, api_key: str, base_url: str, model: str) -> dict:
        """启动中等模式对话，LLM 生成第一个引导问题"""
        session = self.get_session(session_id)
        if not session:
            return {'error': '会话不存在'}

        llm = self._make_llm(api_key, base_url, model)
        user_input = session.get('user_input', '').strip()

        collected = {'_completed_topics': [], '_current_topic_idx': 0, '_topic_round_counts': {}}
        self.update_session(session_id, collected_info=collected)

        topic = _QUESTION_TOPICS[0]
        try:
            question_text = llm.chat(
                system='你是机器学习平台产品的需求分析助手，通过对话逐步收集 PRD 信息。每次只问一个问题，保持简洁具体。输出必须为严格 JSON 格式。',
                user=_QUESTION_PROMPT.format(
                    user_input=user_input or '（用户未提供文字描述）',
                    chat_history='（对话尚未开始）',
                    current_topic=topic['topic'],
                    current_guide=topic['guide'],
                    current_check=topic['check'],
                ),
            )
            result = self._parse_json_safe(question_text, {'status': 'continue', 'question': '请描述您当前遇到的问题是什么？', 'topic_done': False})
            question = result.get('question', '请描述您当前遇到的问题是什么？') if isinstance(result, dict) else '请描述您当前遇到的问题是什么？'
        except Exception:
            question = topic['guide'] + '。请描述一下。'

        add_chat_message(session_id, 'system', question, 1)

        return {
            'round': 1,
            'question': question,
            'status': 'chatting',
            'topic': topic['topic'],
        }

    def chat_round(self, session_id: str, answer: str, api_key: str, base_url: str, model: str) -> dict:
        """处理一轮对话——LLM 判断是否完成当前话题，代码层兜底防止卡住

        特殊规则：
        - 用户说"下一话题/继续/跳过"等关键词 → 强制推进，不给 LLM 判断
        """
        session = self.get_session(session_id)
        if not session:
            return {'error': '会话不存在'}

        llm = self._make_llm(api_key, base_url, model)
        round_num = session['current_round'] + 1

        add_chat_message(session_id, 'user', answer, round_num)

        collected = json.loads(session.get('collected_info', '{}') or '{}')
        completed_topics = collected.get('_completed_topics', [])
        current_idx = collected.get('_current_topic_idx', 0)
        topic_round_counts = collected.get('_topic_round_counts', {})

        current_topic_key = _QUESTION_TOPICS[current_idx]['topic'] if current_idx < len(_QUESTION_TOPICS) else None
        if current_topic_key:
            topic_round_counts[current_topic_key] = topic_round_counts.get(current_topic_key, 0) + 1

        messages = get_chat_messages(session_id)
        chat_history = '\n'.join(
            f"{'用户' if m['role'] == 'user' else '系统'}: {m['content']}"
            for m in messages[-10:]
        )

        user_input = session.get('user_input', '').strip()
        current_topic = _QUESTION_TOPICS[current_idx] if current_idx < len(_QUESTION_TOPICS) else _QUESTION_TOPICS[-1]
        rounds_on_current = topic_round_counts.get(current_topic['topic'], 0)

        # 代码层兜底：超过 3 轮强制推进
        force_advance = rounds_on_current >= 3

        # 关键词检测：用户说"下一话题/继续/跳过" → 强制推进
        next_topic_keyword = any(kw in answer for kw in _NEXT_TOPIC_KEYWORDS)
        if next_topic_keyword:
            force_advance = True

        # 即使按关键词强制推进，也尝试调用 LLM 获取下一话题的引导问题
        # 但如果 LLM 失败，用默认引导问题
        try:
            judgment = llm.chat(
                system='你是严格的产品需求分析助手。通过对话收集 PRD 信息，每轮只问一个问题。用户回答后判断是否可进入下一话题。输出必须为严格 JSON 格式。',
                user=_QUESTION_PROMPT.format(
                    user_input=user_input or '（用户未提供文字描述）',
                    chat_history=chat_history,
                    current_topic=current_topic['topic'],
                    current_guide=current_topic['guide'],
                    current_check=current_topic['check'],
                ),
            )
        except Exception:
            judgment = '{"status": "continue", "question": "请继续描述", "topic_done": false}'

        result = self._parse_json_safe(judgment, {'status': 'continue', 'question': '请进一步描述。', 'topic_done': False})

        status = result.get('status', 'continue') if isinstance(result, dict) else 'continue'
        topic_done = result.get('topic_done', False) if isinstance(result, dict) else False

        if force_advance:
            topic_done = True

        if topic_done and current_idx not in completed_topics:
            completed_topics.append(current_topic['topic'])
            current_idx += 1
            collected['_completed_topics'] = completed_topics
            collected['_current_topic_idx'] = current_idx

        collected['_topic_round_counts'] = topic_round_counts
        self.update_session(session_id, collected_info=collected, current_round=round_num)

        if status == 'complete' or current_idx >= len(_QUESTION_TOPICS):
            return {
                'round': round_num,
                'status': 'ready_for_outline',
                'reason': '已覆盖全部 7 个话题的信息',
            }

        next_topic = _QUESTION_TOPICS[current_idx] if current_idx < len(_QUESTION_TOPICS) else _QUESTION_TOPICS[-1]
        question = result.get('question', '请进一步描述。') if isinstance(result, dict) else '请进一步描述。'
        add_chat_message(session_id, 'system', question, round_num)

        return {
            'round': round_num,
            'question': question,
            'status': 'chatting',
            'topic': next_topic['topic'],
        }

    def rechat_topic(self, session_id: str, topic_name: str, api_key: str, base_url: str, model: str) -> dict:
        """重新进入某个已完成的话题，允许用户补充或修改之前的回答

        将该话题移出 completed_topics，_current_topic_idx 回退到该话题位置，
        并让 LLM 根据之前该话题的对话历史生成一个承上启下的引导问题。
        """
        session = self.get_session(session_id)
        if not session:
            return {'error': '会话不存在'}

        collected = json.loads(session.get('collected_info', '{}') or '{}')
        completed_topics = collected.get('_completed_topics', [])
        current_idx = collected.get('_current_topic_idx', 0)

        # 找到话题索引
        topic_idx = None
        for i, t in enumerate(_QUESTION_TOPICS):
            if t['topic'] == topic_name:
                topic_idx = i
                break

        if topic_idx is None:
            return {'error': f'话题 "{topic_name}" 不存在'}

        # 从 completed_topics 移除该话题
        if topic_name in completed_topics:
            completed_topics.remove(topic_name)

        # 把 current_idx 回退到该话题位置
        if topic_idx < current_idx:
            current_idx = topic_idx

        # 清理该话题之后标记完成的话题（因为回退到该话题后，后面的需要重新走）
        topics_to_remove = [t['topic'] for t in _QUESTION_TOPICS[topic_idx + 1:]]
        collected['_completed_topics'] = [t for t in completed_topics if t not in topics_to_remove]
        collected['_current_topic_idx'] = current_idx
        self.update_session(session_id, collected_info=collected)

        # 让 LLM 根据之前该话题的对话历史生成引导问题
        llm = self._make_llm(api_key, base_url, model)
        messages = get_chat_messages(session_id)
        chat_history = '\n'.join(
            f"{'用户' if m['role'] == 'user' else '系统'}: {m['content']}"
            for m in messages[-10:]
        )

        topic = _QUESTION_TOPICS[topic_idx]
        user_input = session.get('user_input', '').strip()

        try:
            question_text = llm.chat(
                system='你是机器学习平台产品的需求分析助手，通过对话收集 PRD 信息。用户想重新讨论一个话题，请根据之前的对话历史生成一个承上启下的引导问题。输出必须为严格 JSON 格式。',
                user=_QUESTION_PROMPT.format(
                    user_input=user_input or '（用户未提供文字描述）',
                    chat_history=chat_history,
                    current_topic=topic['topic'],
                    current_guide=topic['guide'],
                    current_check=topic['check'],
                ),
            )
            result = self._parse_json_safe(question_text, {'status': 'continue', 'question': topic['guide'] + '，请补充说明。', 'topic_done': False})
            question = result.get('question', topic['guide'] + '，请补充说明。') if isinstance(result, dict) else topic['guide'] + '，请补充说明。'
        except Exception:
            question = topic['guide'] + '，请补充说明。'

        add_chat_message(session_id, 'system', question, session['current_round'] + 1)

        return {
            'round': session['current_round'] + 1,
            'question': question,
            'status': 'chatting',
            'topic': topic['topic'],
        }

    # ── 大纲生成 ──

    def generate_outline(self, session_id: str, api_key: str, base_url: str, model: str) -> dict:
        """生成 PRD 大纲"""
        session = self.get_session(session_id)
        if not session:
            return {'error': '会话不存在'}

        llm = self._make_llm(api_key, base_url, model)
        outline_text = llm.chat(
            system=self._build_system_prompt(),
            user=_OUTLINE_PROMPT.format(user_input=session.get('user_input', '')),
        )
        parser = self._parse_json_safe(outline_text, {'sections': list(_SECTION_NAMES.keys())})
        sections = parser.get('sections', []) if isinstance(parser, dict) else parser
        self.update_session(session_id, outline=json.dumps(sections, ensure_ascii=False), status='writing')
        return {'outline': sections}

    # ── 章节流式生成 ──

    def generate_section(self, session_id: str, section: str, api_key: str, base_url: str, model: str,
                         rag_enabled: bool = True):
        """流式生成单个章节

        如果章节已存在，先自动保存版本快照再重新生成。
        注入前序章节内容摘要，确保一致性和不重复。

        Yields:
            SSE 事件字符串
        """
        session = self.get_session(session_id)
        if not session:
            yield sse_event('error', {'message': '会话不存在'})
            return

        llm = self._make_llm(api_key, base_url, model)
        collected_info = self._build_collected_info_text(
            session, current_section=section, rag_enabled=rag_enabled,
        )
        preceding_text = self._build_preceding_sections_text(session, section)
        section_name = _SECTION_NAMES.get(section, section)

        # 获取章节专用 Prompt 模板
        section_prompt_template = _SECTION_PROMPTS.get(section,
            '请撰写 PRD 的"{section_name}"章节。\n\n已收集的需求信息：\n{collected_info}')

        # 组装完整 Prompt：collected_info + 前序章节摘要
        full_context = collected_info
        if preceding_text:
            full_context += '\n\n' + preceding_text

        section_prompt = section_prompt_template.format(collected_info=full_context)

        # 检查是否已有内容 → 保存版本快照
        current_content = self._get_section_from_session(session, section)
        if current_content:
            save_prd_version(session_id, section, current_content)
            yield sse_event('progress', {'step': section, 'message': '已保存当前版本，正在重新生成...'})
        else:
            yield sse_event('progress', {'step': section, 'message': f'正在生成章节「{section_name}」...'})

        # 流式生成
        full_content = ''
        for chunk in llm.chat_stream(
            system=self._build_system_prompt(),
            user=section_prompt,
        ):
            full_content += chunk
            yield sse_event('progress', {'chunk': chunk, 'section': section})

        # 保存版本
        version_info = save_prd_version(session_id, section, full_content)
        self._save_section_to_session(session_id, section, full_content)

        yield sse_event('section_complete', {
            'section': section,
            'content': full_content,
            'versionId': version_info['id'],
        })

    def regenerate_section(self, session_id: str, section: str, api_key: str, base_url: str, model: str,
                           rag_enabled: bool = True):
        """重新生成章节（保存快照后生成）"""
        yield from self.generate_section(session_id, section, api_key, base_url, model, rag_enabled)

    # ── 章节内容存取辅助 ──

    @staticmethod
    def _get_section_from_session(session: dict, section: str) -> str:
        """从 session 的 section_contents 字段读取章节内容"""
        contents = json.loads(session.get('section_contents', '{}') or '{}')
        return contents.get(section, '')

    @staticmethod
    def _save_section_to_session(session_id: str, section: str, content: str):
        """保存章节内容到 session 的 section_contents 字段"""
        session = get_prd_session(session_id)
        if not session:
            return
        contents = json.loads(session.get('section_contents', '{}') or '{}')
        contents[section] = content
        update_prd_session(session_id, section_contents=contents)

    @staticmethod
    def update_section_content(session_id: str, section: str, content: str) -> dict:
        """用户手动编辑章节内容

        自动保存编辑前版本快照。
        """
        session = get_prd_session(session_id)
        if not session:
            return {'error': '会话不存在'}
        current = PRDGenService._get_section_from_session(session, section)
        if current:
            save_prd_version(session_id, section, current)
        PRDGenService._save_section_to_session(session_id, section, content)
        return {'ok': True}

    # ── 版本管理 ──

    def get_versions(self, session_id: str, section: str | None = None) -> list[dict]:
        """获取版本列表"""
        return get_prd_versions(session_id, section)

    def get_version_content(self, version_id: str) -> dict | None:
        """获取指定版本内容"""
        return get_prd_version_content(version_id)

    # ── 导出 ──

    def export_prd(self, session_id: str) -> str:
        """导出完整 PRD Markdown

        按大纲顺序拼接所有章节内容。
        """
        session = self.get_session(session_id)
        if not session:
            return '# PRD\n\n（会话不存在）'

        outline = json.loads(session.get('outline', '[]') or '[]')
        contents = json.loads(session.get('section_contents', '{}') or '{}')

        sections = []
        for section in outline:
            content = contents.get(section, '')
            if content:
                sections.append(content)

        if not sections:
            return '# PRD 草稿\n\n（内容尚未生成）'

        return '\n\n---\n\n'.join(sections)

    def export_to_feishu(self, session_id: str) -> dict:
        """将生成的 PRD 写入飞书文档

        复用 feishu_client.create_doc_xml + markdown_to_docxml。
        成功后保存 doc_url 到 session.feishu_doc_url。
        """
        from .feishu_client import create_doc_xml, markdown_to_docxml, LarkCliError

        session = self.get_session(session_id)
        if not session:
            return {'error': '会话不存在'}

        markdown = self.export_prd(session_id)
        if not markdown or markdown.startswith('# PRD\n\n（会话不存在）') or markdown.startswith('# PRD 草稿'):
            return {'error': 'PRD 内容尚未生成，请先完成章节生成'}

        user_input = (session.get('user_input', '') or '未命名PRD')[:30]
        title = f'PRD-{user_input}'

        try:
            content_xml = markdown_to_docxml(markdown, title)
            doc_url = create_doc_xml(title, content_xml)
        except LarkCliError as e:
            logger.warning(f'[PRDGen] 飞书文档创建失败: {e}')
            return {'error': f'飞书文档创建失败: {str(e)}'}
        except Exception as e:
            logger.warning(f'[PRDGen] 飞书导出异常: {e}')
            return {'error': f'飞书导出异常: {str(e)}'}

        if not doc_url:
            return {'error': '飞书文档创建成功但返回 URL 为空'}

        self.update_session(session_id, feishu_doc_url=doc_url)
        return {'url': doc_url, 'title': title}

    # ── 深度模式状态机（4 Agent + 6 校验器 + 3 人工闸口）──

    def deep_generate(self, session_id: str, api_key: str, base_url: str, model: str,
                      rag_enabled: bool = True):
        """深度模式 SSE 流式编排

        流水线：
          Agent1(萃取,flash) → V:Schema → [fail→Agent1] → Gate1(冲突确认)
          → Agent2(上下文,pro) → Gate2(影响确认)
          → Agent3(规格,pro) → V:Scope/Citation/Accept/Perm → [fail→Agent3] → Gate3(规格确认)
          → Agent4(撰写,flash) → V:Risk → done

        闸口用 threading.Event 挂起 generator，POST /deep/approve 唤醒。
        状态存 prd_sessions.deep_state + deep_artifacts。

        Yields:
            SSE 事件：
              progress / agent_complete / validation / gate / complete / error
        """
        from .deep_agents import agent1_extract_pass1, agent1_extract_pass2, agent2_analyze, agent3_spec, agent4_write
        from .validators import run_validators
        from .deep_gates import get_or_create_gate, get_gate_response, cleanup_session

        MAX_RETRY = 2  # 校验器回退上限

        session = self.get_session(session_id)
        if not session:
            yield sse_event('error', {'message': '会话不存在'})
            return

        user_input = session.get('user_input', '')
        artifacts = json.loads(session.get('deep_artifacts', '{}') or '{}')

        try:
            # ── Agent 1：需求萃取（双 pass：先问知识库再产出）──
            yield sse_event('progress', {
                'agent': 'agent1', 'step': 'agent1_pass1',
                'message': '需求萃取中（第 1 轮：初步分析 + 知识库查询）',
            })

            # 提前获取平台上下文（Agent1 Pass1 可据此判断是否需要问 KB）
            platform_context = self._retrieve_platform_context(session)

            pass1_out = agent1_extract_pass1(session, api_key, base_url, model, platform_context)
            questions = pass1_out.get('questions_to_kb', []) or []
            artifacts['agent1_pass1'] = pass1_out
            self.update_session(session_id, deep_artifacts=artifacts)
            yield sse_event('agent_complete', {
                'agent': 'agent1_pass1', 'data': pass1_out,
                'message': f'初步分析完成（{len(questions)} 个知识库问题待查询）',
            })

            # ── 问知识库（questions_to_kb→/api/query）──
            kb_answers_parts = []
            if questions:
                qs = [q.get('question', '') if isinstance(q, dict) else str(q) for q in questions]
                qs = [q for q in qs if q.strip()]
                yield sse_event('progress', {
                    'agent': 'agent1', 'step': 'agent1_kb_query',
                    'message': f'正在查询知识库（{len(qs)} 个问题）…',
                })
                for i, q in enumerate(qs):
                    contexts = self._query_kb_agent(q)
                    if contexts:
                        ctx_text = '\n'.join(
                            f'  [{c.get("collection","?")}][{c.get("score","0"):.2f}] {c.get("content","")[:500]}'
                            for c in contexts[:3]
                        )
                        kb_answers_parts.append(f'问题{i+1}: {q}\n回答:\n{ctx_text}')
                    else:
                        kb_answers_parts.append(f'问题{i+1}: {q}\n回答: （无相关结果）')
                yield sse_event('progress', {
                    'agent': 'agent1', 'step': 'agent1_pass2',
                    'message': '知识库查询完成，融合信息产出最终需求…',
                })

            kb_answers_text = '\n\n'.join(kb_answers_parts) if kb_answers_parts else ''

            retry = 0
            while retry <= MAX_RETRY:
                agent1_out = agent1_extract_pass2(session, api_key, base_url, model, kb_answers_text)
                artifacts['agent1'] = agent1_out
                self.update_session(session_id, deep_state='agent1_done', deep_artifacts=artifacts)
                yield sse_event('agent_complete', {
                    'agent': 'agent1', 'data': agent1_out,
                    'message': '需求萃取完成（含知识库参考）',
                })
                # V: Schema
                issues = run_validators('agent1', artifacts)
                errors = [i for i in issues if i['level'] == 'error']
                if errors:
                    yield sse_event('validation', {'stage': 'agent1', 'validator': 'schema', 'issues': errors})
                    if retry < MAX_RETRY:
                        retry += 1
                        yield sse_event('progress', {
                            'agent': 'agent1', 'step': 'agent1_retry',
                            'message': f'Schema 校验失败 {len(errors)} 项，回退 Agent1 重跑（{retry}/{MAX_RETRY}）',
                        })
                        continue
                break

            # ── Gate 1：需求萃取审核（始终显示，供用户确认/修改 Agent1 产出）──
            gate1 = get_or_create_gate(session_id, 'agent1_review')
            yield sse_event('gate', {
                'gate': 'agent1_review',
                'requirements': artifacts['agent1'].get('requirements', {}),
                'conflicts': artifacts['agent1'].get('conflicts', []) or [],
                'gaps': artifacts['agent1'].get('gaps', []) or [],
                'message': 'Agent 1 已萃取完成，请确认需求信息是否准确。可修改后继续。',
            })
            gate1.wait()
            resp = get_gate_response(session_id, 'agent1_review') or {}
            if not resp.get('approved'):
                yield sse_event('complete', {'sessionId': session_id, 'message': '用户在需求审核闸口驳回，深度模式终止'})
                return
            if resp.get('modifications'):
                artifacts['agent1']['_user_modifications'] = resp['modifications']
                artifacts.setdefault('user_fixes', []).append({'gate': 'agent1_review', 'content': resp['modifications']})
                self.update_session(session_id, deep_artifacts=artifacts)

            # ── Agent 2：上下文分析（调知识库图谱，降级空串）──
            yield sse_event('progress', {
                'agent': 'agent2', 'step': 'agent2',
                'message': 'Agent 2 上下文分析中…（平台图谱查询）',
            })
            user_fixes = artifacts.get('user_fixes', []) or []
            user_ctx = ('【用户修正】\n' + '\n'.join(
                '  [{0}]: {1}'.format(g.get('gate', ''), (g.get('content', '') or '')[:300])
                for g in user_fixes
            )) if user_fixes else ''
            agent2_out = agent2_analyze(session, artifacts['agent1'], api_key, base_url, model, user_ctx)
            artifacts['agent2'] = agent2_out
            self.update_session(session_id, deep_state='agent2_done', deep_artifacts=artifacts, status='writing')
            yield sse_event('agent_complete', {
                'agent': 'agent2', 'data': agent2_out,
                'message': 'Agent 2 上下文分析完成',
            })

            # ── Gate 2：影响范围确认（Agent2 之后）──
            impact_warnings = agent2_out.get('impact_warnings', []) or []
            if impact_warnings:
                gate2 = get_or_create_gate(session_id, 'impact')
                yield sse_event('gate', {
                    'gate': 'impact', 'impact_warnings': impact_warnings,
                    'message': '影响范围预警，请确认',
                })
                gate2.wait()
                resp = get_gate_response(session_id, 'impact') or {}
                if not resp.get('approved'):
                    yield sse_event('complete', {
                        'sessionId': session_id,
                        'message': '用户在影响闸口驳回，深度模式终止',
                    })
                    return
                if resp.get('modifications'):
                    artifacts['agent2']['_user_modifications'] = resp['modifications']
                    artifacts.setdefault('user_fixes', []).append({'gate': 'impact', 'content': resp['modifications']})
                    self.update_session(session_id, deep_artifacts=artifacts)

            # ── Agent 3：功能规格（pro）──
            yield sse_event('progress', {
                'agent': 'agent3', 'step': 'agent3',
                'message': 'Agent 3 功能规格定义中…',
            })
            user_fixes = artifacts.get('user_fixes', []) or []
            user_ctx = ('【用户修正】\n' + '\n'.join(
                '  [{0}]: {1}'.format(g.get('gate', ''), (g.get('content', '') or '')[:300])
                for g in user_fixes
            )) if user_fixes else ''
            retry = 0
            while retry <= MAX_RETRY:
                agent3_out = agent3_spec(session, artifacts['agent1'], artifacts['agent2'],
                                         api_key, base_url, model, user_ctx)
                artifacts['agent3'] = agent3_out
                self.update_session(session_id, deep_state='agent3_done', deep_artifacts=artifacts)
                yield sse_event('agent_complete', {
                    'agent': 'agent3', 'data': agent3_out,
                    'message': 'Agent 3 功能规格完成',
                })
                # V: Scope/Citation/Acceptance/Permission
                issues = run_validators('agent3', artifacts, user_input)
                errors = [i for i in issues if i['level'] == 'error']
                warns = [i for i in issues if i['level'] == 'warn']
                if warns:
                    yield sse_event('validation', {'stage': 'agent3', 'issues': warns})
                if errors:
                    yield sse_event('validation', {'stage': 'agent3', 'issues': errors, 'retry': True})
                    if retry < MAX_RETRY:
                        retry += 1
                        yield sse_event('progress', {
                            'agent': 'agent3', 'step': 'agent3_retry',
                            'message': f'校验失败 {len(errors)} 项，回退 Agent3（{retry}/{MAX_RETRY}）',
                        })
                        continue
                break

            # ── Gate 3：功能规格确认（Agent3 之后）──
            gate3 = get_or_create_gate(session_id, 'spec')
            yield sse_event('gate', {
                'gate': 'spec',
                'features': artifacts['agent3'].get('features', []),
                'message': '功能规格定义完成，请确认',
            })
            gate3.wait()
            resp = get_gate_response(session_id, 'spec') or {}
            if not resp.get('approved'):
                yield sse_event('complete', {
                    'sessionId': session_id,
                    'message': '用户在规格闸口驳回，深度模式终止',
                })
                return
            if resp.get('modifications'):
                artifacts['agent3']['_user_modifications'] = resp['modifications']
                artifacts.setdefault('user_fixes', []).append({'gate': 'spec', 'content': resp['modifications']})
                self.update_session(session_id, deep_artifacts=artifacts)

            # ── Agent 4：PRD 撰写（flash）──
            yield sse_event('progress', {
                'agent': 'agent4', 'step': 'agent4',
                'message': 'Agent 4 PRD 撰写中…',
            })
            agent4_out = agent4_write(session, artifacts, api_key, base_url, model, user_ctx)
            artifacts['agent4'] = agent4_out
            # PRD Markdown 存入 section_contents（复用导出/编辑能力）
            prd_md = agent4_out.get('prd_markdown', '')
            if prd_md:
                contents = json.loads(session.get('section_contents', '{}') or '{}')
                contents['deep_prd'] = prd_md
                self.update_session(
                    session_id,
                    deep_state='done', deep_artifacts=artifacts,
                    section_contents=contents, status='done',
                )
            else:
                self.update_session(session_id, deep_state='done', deep_artifacts=artifacts, status='done')
            yield sse_event('agent_complete', {
                'agent': 'agent4',
                'data': {
                    'prd_markdown': prd_md,
                    'spec': agent4_out.get('spec', {}),
                },
                'message': 'Agent 4 PRD 撰写完成',
            })

            # V: Risk
            risk_issues = run_validators('agent4', artifacts)
            if risk_issues:
                yield sse_event('validation', {'stage': 'agent4', 'issues': risk_issues})

            yield sse_event('complete', {
                'sessionId': session_id,
                'message': '深度模式完成（4 Agent + 3 闸口），可在 PRD 编辑面板点击"AI 增强原型"生成原型',
                'artifacts': list(artifacts.keys()),
                'has_prd': bool(prd_md),
            })

        finally:
            cleanup_session(session_id)

    # ── 飞书妙记解析 ──

    def parse_minutes(self, session_id: str, url: str, api_key: str, base_url: str, model: str) -> dict:
        """解析飞书妙记链接，提取需求要点

        复用 feishu_client 和 meeting_todo_service 的现有代码。
        """
        from .feishu_client import get_minute_info, get_transcript
        from .meeting_todo_service import parse_minutes_link

        minute_token = parse_minutes_link(url)
        if not minute_token:
            return {'status': 'error', 'message': '无效的妙记链接'}

        try:
            minute_info = get_minute_info(minute_token)
        except Exception as e:
            return {'status': 'error', 'message': f'获取妙记信息失败：{str(e)}'}

        try:
            transcript = get_transcript(minute_token)
        except Exception:
            transcript = ''

        if not transcript:
            return {'status': 'error', 'message': '无法获取妙记逐字稿，请确认妙记已完成转写'}

        # 限制长度防止超 Token
        if len(transcript) > 80000:
            transcript = transcript[:80000] + '\n...（截断）'

        llm = self._make_llm(api_key, base_url, model)
        result_text = llm.chat(
            system='你是机器学习平台的需求分析专家。',
            user=_MINUTES_EXTRACT_PROMPT.format(minutes_text=transcript),
        )
        extracted = self._parse_json_safe(result_text, {
            'featurePoints': [], 'stakeholders': [],
            'constraints': [], 'background': '',
        })

        if not isinstance(extracted, dict):
            extracted = {'featurePoints': [], 'stakeholders': [], 'constraints': [], 'background': ''}

        # 存入会话上下文
        self.update_session(session_id, minutes_extract=extracted)

        return {
            'status': 'success',
            'minuteTitle': (
                minute_info.get('data', {})
                .get('minute', {})
                .get('title', '')
            ),
            'extractedPoints': extracted,
        }

    # ── 文件上传 ──

    def handle_file_upload(self, session_id: str, file_storage, file_type: str) -> dict:
        """处理文件上传

        支持 .md / .txt / .docx，不超过 10MB。
        临时文件存入 /tmp/sessions/{session_id}/，长期文件存入 data/knowledge/permanent/
        """
        from werkzeug.utils import secure_filename

        filename = secure_filename(file_storage.filename or 'unnamed')
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.md', '.txt', '.docx'):
            return {'error': '不支持的文件格式，仅支持 .md / .txt / .docx'}

        # 大小校验
        file_storage.seek(0, os.SEEK_END)
        size = file_storage.tell()
        file_storage.seek(0)
        if size > 10 * 1024 * 1024:
            return {'error': '文件大小超过 10MB 限制'}

        # 存储路径
        if file_type == 'temporary':
            base_dir = f'/tmp/sessions/{session_id}'
        else:
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'data', 'knowledge', 'permanent', session_id,
            )
        os.makedirs(base_dir, exist_ok=True)
        save_path = os.path.join(base_dir, filename)
        file_storage.save(save_path)

        # 提取文本
        text_content = self._extract_text(file_storage, ext)

        # 存入数据库
        file_id = str(uuid.uuid4())
        save_prd_file(file_id, session_id, filename, file_type, save_path, text_content)

        return {
            'id': file_id,
            'filename': filename,
            'file_type': file_type,
            'text_preview': text_content[:500],
        }

    @staticmethod
    def _extract_text(file_storage, ext: str) -> str:
        """提取文件文本内容"""
        try:
            content = file_storage.read().decode('utf-8')
            return content
        except UnicodeDecodeError:
            if ext == '.docx':
                try:
                    import docx
                    doc = docx.Document(file_storage)
                    return '\n'.join(p.text for p in doc.paragraphs)
                except ImportError:
                    return '（需安装 python-docx 包以支持 .docx 文件）'
            return '（无法解析文件编码）'