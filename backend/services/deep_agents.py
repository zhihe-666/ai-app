"""
deep_agents.py — PRD 深度模式 4 Agent 节点

2a 阶段实现 Agent 1（需求萃取）+ Agent 2（上下文分析），Agent 3/4 留 2b。

每个 Agent = prompt + LLM 调用 + JSON 容错解析，接 artifacts state 返回新 state。
模型路由经 ModelRouter：
  - Agent 1: flash（协同模型，快、便宜）
  - Agent 2: pro（强推理，做影响范围/缺失依赖分析）

依赖：
  - services/llm_client.py — LLM 调用
  - services/model_router.py — 双模型路由
  - services/prd_gen_service.py — _retrieve_platform_context（调知识库图谱）
  - services/sse_helpers.py — SSE 事件（deep_generate 编排用）
"""
import logging

from .llm_client import LLMClient
from .model_router import ModelRouter
from .prd_gen_service import PRDGenService
from .sse_helpers import sse_event

logger = logging.getLogger(__name__)


# ── Agent 1：需求萃取（Pass 1 — 初步分析 + 问知识库）──

_AGENT1_PASS1_PROMPT = """你是资深产品需求分析专家。请从多源输入中萃取结构化需求信息，并主动向平台知识库提问了解平台现状。

## 你的核心能力
你可以通过 questions_to_kb 向平台知识库提问。知识库包含：代码知识图谱、平台架构文档、前端组件注册表、现有功能描述等。
**请务必主动提问**来确认平台当前已有的相关功能、页面、API 和流程，避免重复设计或忽略已有能力。

## 输入源
- 用户原始文字需求
- （可选）飞书妙记提取的功能点/干系人/约束/背景
- （可选）平台架构快照（你匹配到的已有功能模块，可能不完整）

## 你必须通过 questions_to_kb 了解的信息
针对用户需求，你必须主动查询以下方面：
1. **平台已有相关功能**：用户要的功能，平台目前是否有类似页面或功能？叫什么？在哪个模块？
2. **已有页面和组件**：平台是否有相关列表页、表单页、详情页？用了哪些前端组件？
3. **后台 API 和数据模型**：功能涉及的数据实体（如模型版本、配置项）在平台中是否有对应的 API 或数据表？
4. **现有流程**：平台当前的业务流程是什么（如配置变更流程、版本发布流程）？新增功能需要如何适配？

以上每方面至少提 1 个问题。

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "requirements": {{
    "feature_name": "功能名称（一句话）",
    "problem": "当前痛点（2-3 句，含数据/频率）",
    "solution_direction": "解决方案方向（2-3 句，不涉及实现细节）",
    "target_users": ["用户角色1", "用户角色2"],
    "core_features": ["核心功能点1", "核心功能点2"],
    "priorities": {{"P0": ["必须有的功能"], "P1": ["应该有的功能"]}}
  }},
  "conflicts": [
    {{"field": "冲突字段", "sources": ["来源1的值", "来源2的值"], "resolution": "建议如何解决"}}
  ],
  "gaps": ["信息缺口1", "信息缺口2"],
  "questions_to_kb": [
    {{"question": "向平台知识库提的具体可检索问题", "reason": "为什么需要这个问题"}}
  ]
}}

## 质量要求
- questions_to_kb 必须至少 2 个，覆盖"已有功能"和"页面/组件"两方面
- core_features 可独立开发、可测试
- priorities P0 不可为空
- 多源信息冲突时在 conflicts 中标出

## 多源输入
{multi_source_input}

## 平台架构快照（可能有）
{platform_context}"""


# ── Agent 1：需求萃取（Pass 2 — 融合 KB 答案产出最终版）──

_AGENT1_PASS2_PROMPT = """你是资深产品需求分析专家。现在你有了知识库补充信息，请产出最终版结构化需求。

## 输入源
- 用户原始需求 + 多源输入
{multi_source_input}

- 你提出的问题及知识库回答：
{kb_answers}

## 任务
基于以上信息，输出最终版结构化需求。你之前的初版需求 + KB 答案 → 修正补充 → 最终版。

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "requirements": {{
    "feature_name": "功能名称",
    "problem": "当前痛点",
    "solution_direction": "解决方案方向",
    "target_users": ["用户角色"],
    "core_features": ["核心功能点"],
    "priorities": {{"P0": ["必须有的"], "P1": ["应该有的"]}}
  }},
  "conflicts": [{{"field": "冲突字段", "sources": [], "resolution": "建议"}}],
  "gaps": ["信息缺口"]
}}

## 质量要求
- 引用 KB 答案时标注依据，不臆测
- 如果 KB 答案无帮助或微服务未启动，基于自身判断
- priorities P0 不可为空"""


# ── Agent 1：原始版 prompt（备用）──

_AGENT1_PROMPT = """你是资深产品需求分析专家。请从多源输入中萃取结构化需求信息。

## 输入源
- 用户原始文字需求
- （可选）飞书妙记提取的功能点/干系人/约束/背景
- （可选）上传文件的文本预览

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "requirements": {{
    "feature_name": "功能名称（一句话）",
    "problem": "当前痛点（2-3 句，含数据/频率）",
    "solution_direction": "解决方案方向（2-3 句，不涉及实现细节）",
    "target_users": ["用户角色1", "用户角色2"],
    "core_features": ["核心功能点1", "核心功能点2"],
    "priorities": {{"P0": ["必须有的功能"], "P1": ["应该有的功能"]}}
  }},
  "conflicts": [
    {{"field": "冲突字段", "sources": ["来源1的值", "来源2的值"], "resolution": "建议如何解决"}}
  ],
  "gaps": ["信息缺口1（如缺少性能指标基线）", "信息缺口2"]
}}

## 质量要求
- 多源信息冲突时，在 conflicts 中明确标出，不替用户决定
- 信息不完整时，在 gaps 中列出缺口，不臆造
- core_features 必须可独立开发、可测试
- priorities P0 不可为空

## 多源输入
{multi_source_input}"""


# ── Agent 2：上下文分析 prompt ──

_AGENT2_PROMPT = """你是平台架构分析专家。基于 Agent 1 萃取的需求 + 平台架构快照 + 影响范围，分析内部上下文。

## 输入
1. Agent 1 萃取的需求：
{agent1_requirements}

2. 平台架构快照 + 影响范围（从知识库图谱获取）：
{platform_context}

## 任务
1. 分析该需求与已有平台模块的关系（复用/扩展/新建）
2. 识别缺失依赖（需求隐含但未提及的依赖）
3. 基于影响范围，预警 PRD 必须覆盖的下游影响

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "platform_relationship": {{
    "relation_type": "reuse|extend|new",
    "related_modules": ["已有平台模块1", "已有平台模块2"],
    "rationale": "为什么是这种关系（2-3 句）"
  }},
  "missing_dependencies": [
    {{"dep": "缺失依赖名", "reason": "为什么需求隐含此依赖", "exists": true|false}}
  ],
  "impact_warnings": [
    {{"area": "影响区域", "warning": "PRD 必须覆盖的点", "priority": "P0|P1"}}
  ],
  "context_summary": "平台上下文总结（3-5 句，供 Agent 3 规格定义使用）"
}}

## 质量要求
- relation_type 基于架构快照的 controllers/services 实际存在情况判断，不臆测
- missing_dependencies 至少列 1 个（若无则 reason 填"需求自包含，无隐含依赖"，exists=true）
- impact_warnings 基于影响范围预警，不放大风险
- platform_context 为空时（微服务未启），relation_type="new"，context_summary 填"无平台上下文，基于需求自由设计"
"""


def _build_agent1_input(session: dict) -> str:
    """组装 Agent 1 多源输入文本"""
    import json as _json

    parts = []
    user_input = (session.get('user_input', '') or '').strip()
    if user_input:
        parts.append(f'【文字需求】\n{user_input}')

    minutes = _json.loads(session.get('minutes_extract', '{}') or '{}')
    if minutes.get('featurePoints'):
        parts.append(f'【妙记提取-功能点】{", ".join(minutes["featurePoints"])}')
    if minutes.get('stakeholders'):
        parts.append(f'【妙记提取-干系人】{", ".join(minutes["stakeholders"])}')
    if minutes.get('constraints'):
        parts.append(f'【妙记提取-约束】{", ".join(minutes["constraints"])}')
    if minutes.get('background'):
        parts.append(f'【妙记提取-背景】{minutes["background"]}')

    # 文件预览（prd_files 表，text_content 截断）
    # 2a 暂不查文件表，留 2b 补；此处先占位
    if not parts:
        return '（无多源输入）'
    return '\n\n'.join(parts)


def agent1_extract(session: dict, api_key: str, base_url: str, model: str) -> dict:
    """Agent 1：需求萃取与澄清（单 pass 版，供兼容）

    用 flash 协同模型。
    """
    route = 'deep_agent_1'
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),
    )

    multi_input = _build_agent1_input(session)
    prompt = _AGENT1_PROMPT.format(multi_source_input=multi_input)

    try:
        result_text = llm.chat(
            system='你是资深产品需求分析专家。输出必须为严格 JSON 格式，不含其他内容。',
            user=prompt,
            temperature=0.2,
            max_tokens=4096,
            timeout=90,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent1 萃取失败: {e}')
        return {
            'error': f'Agent1 萃取失败: {str(e)}',
            'requirements': {},
            'conflicts': [],
            'gaps': ['需求萃取失败，需重试'],
        }

    parsed = PRDGenService._parse_json_safe(result_text, {
        'requirements': {}, 'conflicts': [], 'gaps': [],
    })
    if not isinstance(parsed, dict):
        parsed = {'requirements': {}, 'conflicts': [], 'gaps': ['JSON 解析失败']}
    return parsed


def agent1_extract_pass1(session: dict, api_key: str, base_url: str, model: str,
                         platform_context: str = '') -> dict:
    """Agent 1 Pass 1：初步分析 + 问知识库

    输出增加了 questions_to_kb 字段，供后端调知识库查询。
    平台上下文可选（_retrieve_platform_context 结果），降级空串。
    """
    route = 'deep_agent_1'
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),
    )

    multi_input = _build_agent1_input(session)
    ctx = platform_context or '（无平台上下文，基于需求自由设计）'
    prompt = _AGENT1_PASS1_PROMPT.format(multi_source_input=multi_input, platform_context=ctx)

    try:
        result_text = llm.chat(
            system='你是资深产品需求分析专家。输出必须为严格 JSON 格式，不含其他内容。',
            user=prompt,
            temperature=0.2,
            max_tokens=4096,
            timeout=90,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent1 Pass1 失败: {e}')
        return {'error': str(e), 'requirements': {}, 'conflicts': [], 'gaps': [], 'questions_to_kb': []}

    parsed = PRDGenService._parse_json_safe(result_text, {
        'requirements': {}, 'conflicts': [], 'gaps': [], 'questions_to_kb': [],
    })
    if not isinstance(parsed, dict):
        parsed = {'requirements': {}, 'conflicts': [], 'gaps': ['JSON 解析失败'], 'questions_to_kb': []}
    return parsed


def agent1_extract_pass2(session: dict, api_key: str, base_url: str, model: str,
                         kb_answers_text: str) -> dict:
    """Agent 1 Pass 2：融合 KB 答案产出最终版

    kb_answers_text: KB 查询结果拼接文本（pass1 的 questions → 各条答案）
    """
    route = 'deep_agent_1'
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),
    )

    multi_input = _build_agent1_input(session)
    kb_text = kb_answers_text or '（微服务未启动 / 无相关问题）'
    prompt = _AGENT1_PASS2_PROMPT.format(multi_source_input=multi_input, kb_answers=kb_text)

    try:
        result_text = llm.chat(
            system='你是资深产品需求分析专家。输出必须为严格 JSON 格式，不含其他内容。',
            user=prompt,
            temperature=0.2,
            max_tokens=4096,
            timeout=90,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent1 Pass2 失败: {e}')
        return {
            'error': f'Agent1 Pass2 失败: {str(e)}',
            'requirements': {}, 'conflicts': [], 'gaps': ['最终分析失败'],
        }

    parsed = PRDGenService._parse_json_safe(result_text, {
        'requirements': {}, 'conflicts': [], 'gaps': [],
    })
    if not isinstance(parsed, dict):
        parsed = {'requirements': {}, 'conflicts': [], 'gaps': ['JSON 解析失败']}
    return parsed


def agent2_analyze(session: dict, agent1_out: dict,
                   api_key: str, base_url: str, model: str,
                   user_context: str = '') -> dict:
    """Agent 2：内部上下文分析

    输入：Agent 1 输出 + _retrieve_platform_context（调知识库图谱）
    输出：{platform_relationship, missing_dependencies, impact_warnings, context_summary}
    用 pro 强推理模型。
    """
    import json as _json

    route = 'deep_agent_2'
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),  # 强制 pro
    )

    # 调知识库图谱组装平台上下文（降级空串）
    platform_context = PRDGenService._retrieve_platform_context(session)
    if not platform_context:
        platform_context = '（无平台上下文，微服务未启动或无匹配模块）'
    if user_context:
        platform_context += f'\n\n{user_context}'

    requirements = agent1_out.get('requirements', {}) if isinstance(agent1_out, dict) else {}
    prompt = _AGENT2_PROMPT.format(
        agent1_requirements=_json.dumps(requirements, ensure_ascii=False, indent=2),
        platform_context=platform_context,
    )

    try:
        result_text = llm.chat(
            system='你是平台架构分析专家。输出必须为严格 JSON 格式，不含其他内容。',
            user=prompt,
            temperature=0.3,
            max_tokens=4096,
            timeout=180,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent2 分析失败: {e}')
        return {
            'error': f'Agent2 分析失败: {str(e)}',
            'platform_relationship': {'relation_type': 'new', 'rationale': '分析失败，降级自由设计'},
            'missing_dependencies': [],
            'impact_warnings': [],
            'context_summary': '上下文分析失败，基于需求自由设计',
        }

    parsed = PRDGenService._parse_json_safe(result_text, {
        'platform_relationship': {},
        'missing_dependencies': [],
        'impact_warnings': [],
        'context_summary': '',
    })
    if not isinstance(parsed, dict):
        parsed = {'platform_relationship': {}, 'missing_dependencies': [], 'impact_warnings': [], 'context_summary': 'JSON 解析失败'}
    # 附带原始平台上下文，供前端展示
    parsed['_platform_context_raw'] = platform_context
    return parsed


# ── Agent 5：原型生成（结构化输出 + 平台布局复用）──

_AGENT5_PROMPT = """你是一个资深产品设计师。请基于 PRD 内容和平台现有页面布局，输出产品原型的结构化描述。

## 输入
1. PRD 完整内容：
{prd_markdown}

2. 功能规格 Spec：
{spec}

## 平台现有页面布局（参考结构，尽量复用）
{platform_layouts}

## 平台现有组件（参考使用）
{platform_components}

## 任务
1. 分析 PRD 的核心功能、数据实体、用户操作流程
2. **优先复用 platform_layouts 中的页面布局模式**（list/form/instance/dashboard）
3. **优先使用 platform_components 中的项目级/业务组件**（category=project/business）
4. 输出结构化页面描述，含真实的模拟数据

## 布局匹配指南
- 如果 PRD 需要数据列表 → 用 list 布局模式（DataTable + FilterBar + Space）
- 如果 PRD 需要表单 → 用 form 布局模式（Form + Form.Item + Space + Spin）
- 如果 PRD 需要详情/实例 → 用 instance 布局模式（Tabs + Card）
- 如果 PRD 需要仪表盘 → 用 dashboard 布局模式（DashboardHeader + Space）
- 混合需求 → 组合多种布局

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "title": "功能名称",
  "subtitle": "PRD 产品原型 · AI 基于平台组件生成",
  "nav": ["页面1", "页面2"],
  "sections": [
    {{
      "type": "stat_grid",
      "title": "概览统计",
      "items": [
        {{"label": "指标名", "value": "数值"}}
      ]
    }},
    {{
      "type": "table",
      "title": "数据列表",
      "columns": ["列名1", "列名2", "列名3"],
      "rows": [
        {{"列名1": "数据", "列名2": "数据", "列名3": "数据"}}
      ]
    }},
    {{
      "type": "badge_list",
      "title": "状态标签",
      "items": [
        {{"label": "状态名", "style": "badge-p0|badge-p1|badge-done|badge-progress"}}
      ]
    }},
    {{
      "type": "diff",
      "title": "差异对比",
      "rows": [
        {{"field": "字段", "old": "旧值", "new": "新值"}}
      ]
    }},
    {{
      "type": "form",
      "title": "表单",
      "fields": [
        {{"label": "字段", "type": "text|select", "placeholder": "...", "options": ["选项"]}}
      ]
    }},
    {{
      "type": "actions",
      "title": "操作",
      "buttons": [
        {{"label": "按钮", "style": "primary|default|danger"}}
      ]
    }},
    {{
      "type": "text",
      "title": "说明",
      "content": "描述"
    }}
  ]
}}

## 质量门禁（严格）
1. ✅ **必须**参考 platform_layouts 中的页面布局模式
2. ✅ **必须**参考 platform_components 中的组件名（特别是 project/business 组件）
3. ✅ **每个表格至少 3 条**真实模拟数据，不能空
4. ✅ stat_grid 覆盖核心度量（至少 3 项）
5. ✅ sections 至少 4 个区块，覆盖（概览+列表+操作+其他）
6. ❌ 禁止使用 PRD 中没有的功能
7. ❌ 禁止 section type 以外的键名"""


# ── Agent 3：功能规格定义 prompt（2b）──

_AGENT3_PROMPT = """你是资深产品规格定义专家。基于 Agent1 萃取需求 + Agent2 上下文分析，输出结构化功能规格书。

## 输入
1. Agent 1 需求：
{agent1_requirements}

2. Agent 2 上下文分析：
{agent2_context}

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "features": [
    {{
      "id": "F1",
      "name": "功能名称",
      "description": "功能描述（做什么）",
      "priority": "P0|P1|P2",
      "rationale": "为什么做（依据 Agent2 上下文，不臆造）",
      "acceptance_criteria": ["验收标准1（可测试）", "验收标准2"],
      "related_user_story": "US-001"
    }}
  ],
  "user_stories": [
    {{
      "id": "US-001",
      "story": "As a [角色], I want to [动作], So that [价值]",
      "priority": "P0|P1"
    }}
  ],
  "non_functional": {{
    "performance": "性能指标（含具体数值，如 p95<800ms）",
    "security": "安全/权限要求",
    "audit": "审计要求（如有）"
  }},
  "data_models": [
    {{"name": "数据实体名", "fields": ["字段1", "字段2"]}}
  ]
}}

## 质量要求
- 每个 feature 必须有 acceptance_criteria（可测试）
- rationale 必须基于 Agent2 上下文，引用 related_modules 或 missing_dependencies
- features 优先级与 Agent1 priorities.P0 对齐
- non_functional 性能有具体数值
- impact_warnings（Agent2）中 P0 项必须在 features 中覆盖"""


# ── Agent 4：PRD 撰写 prompt（2b）──

_AGENT4_PROMPT = """你是资深产品经理。基于 Agent1/2/3 产出，撰写完整 PRD + Machine-Readable Spec。

## 输入
1. Agent 1 需求：
{agent1_requirements}

2. Agent 2 上下文分析：
{agent2_context}

3. Agent 3 功能规格：
{agent3_spec}

## 任务
1. 撰写完整 PRD Markdown（按 9 章节结构：概述/背景/用户故事/需求/设计/技术/发布计划/开放问题/附录）
2. 输出 Machine-Readable Spec JSON（供前端原型生成 + 研发拆卡）

## 输出格式（严格 JSON，不要包含其他内容）
{{
  "prd_markdown": "# PRD: 功能名\\n\\n## 1. 功能概述\\n...（完整 9 章节 Markdown）",
  "spec": {{
    "feature": "功能名",
    "version": "1.0",
    "endpoints": [
      {{"path": "/api/xxx", "method": "POST", "auth": {{"required": true, "roles": ["role"]}}, "request": {{}}, "response": {{"200": {{}}}}}}
    ],
    "dataModels": [
      {{"name": "ModelName", "fields": [{{"name": "id", "type": "string", "required": true}}]}}
    ],
    "businessRules": ["业务规则1"],
    "uiSpec": [
      {{"component": "Table", "props": {{"columns": []}}, "label": "页面区块"}}
    ]
  }}
}}

## 质量要求
- PRD Markdown 完整 9 章节，每章质量门禁达标（精确/完整/可执行/结构化/数据驱动）
- spec.endpoints 基于功能需求，不臆造接口
- spec.uiSpec 优先用 antd 原生组件（Table/Form/Modal/Tabs/Select/Input），供 RenderEngine 渲染
- spec.businessRules 至少 1 条"""


def agent3_spec(session: dict, agent1_out: dict, agent2_out: dict,
                api_key: str, base_url: str, model: str,
                user_context: str = '') -> dict:
    """Agent 3：功能规格定义

    输入：Agent1 + Agent2 输出
    输出：{features, user_stories, non_functional, data_models}
    用 pro 强推理模型。
    """
    import json as _json

    route = 'deep_agent_3'
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),  # 强制 pro
    )

    requirements = agent1_out.get('requirements', {}) if isinstance(agent1_out, dict) else {}
    # Agent2 输出去掉原始图谱上下文（_platform_context_raw），只留分析结论
    agent2_clean = {k: v for k, v in (agent2_out or {}).items() if k != '_platform_context_raw'}
    if user_context:
        agent2_clean['_user_context'] = user_context

    prompt = _AGENT3_PROMPT.format(
        agent1_requirements=_json.dumps(requirements, ensure_ascii=False, indent=2),
        agent2_context=_json.dumps(agent2_clean, ensure_ascii=False, indent=2),
    )

    try:
        result_text = llm.chat(
            system='你是资深产品规格定义专家。输出必须为严格 JSON 格式，不含其他内容。',
            user=prompt,
            temperature=0.3,
            max_tokens=8192,
            timeout=240,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent3 规格失败: {e}')
        return {
            'error': f'Agent3 规格失败: {str(e)}',
            'features': [], 'user_stories': [], 'non_functional': {}, 'data_models': [],
        }

    parsed = PRDGenService._parse_json_safe(result_text, {
        'features': [], 'user_stories': [], 'non_functional': {}, 'data_models': [],
    })
    if not isinstance(parsed, dict):
        parsed = {'features': [], 'user_stories': [], 'non_functional': {}, 'data_models': []}
    return parsed


def agent4_write(session: dict, artifacts: dict,
                 api_key: str, base_url: str, model: str,
                 user_context: str = '') -> dict:
    """Agent 4：PRD 撰写与格式化

    输入：artifacts（agent1/agent2/agent3 全部产出）
    输出：{prd_markdown, spec}
    用 flash 协同模型，模板组装。
    """
    import json as _json

    route = 'deep_agent_4'
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),
    )

    agent1_req = artifacts.get('agent1', {}).get('requirements', {})
    agent2_clean = {k: v for k, v in (artifacts.get('agent2', {}) or {}).items() if k != '_platform_context_raw'}
    if user_context:
        agent2_clean['_user_context'] = user_context
    agent3 = artifacts.get('agent3', {})

    prompt = _AGENT4_PROMPT.format(
        agent1_requirements=_json.dumps(agent1_req, ensure_ascii=False, indent=2),
        agent2_context=_json.dumps(agent2_clean, ensure_ascii=False, indent=2),
        agent3_spec=_json.dumps(agent3, ensure_ascii=False, indent=2),
    )

    try:
        result_text = llm.chat(
            system='你是资深产品经理。输出必须为严格 JSON 格式，含 prd_markdown 和 spec 两字段，不含其他内容。',
            user=prompt,
            temperature=0.4,
            max_tokens=12288,
            timeout=180,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent4 撰写失败: {e}')
        return {
            'error': f'Agent4 撰写失败: {str(e)}',
            'prd_markdown': '# PRD\n\n（撰写失败，请重试）',
            'spec': {},
        }

    parsed = PRDGenService._parse_json_safe(result_text, {
        'prd_markdown': '', 'spec': {},
    })
    if not isinstance(parsed, dict):
        parsed = {'prd_markdown': result_text, 'spec': {}}
    # 确保 prd_markdown 非空
    if not parsed.get('prd_markdown'):
        parsed['prd_markdown'] = result_text
    return parsed


def agent5_prototype(session: dict, artifacts: dict,
                     api_key: str, base_url: str, model: str) -> dict:
    """Agent 5：原型生成（可选）

    基于最终 PRD + spec 生成增强版 uiSpec，供 RenderEngine / HTML 原型。
    用 flash 模型。
    """
    import json as _json

    route = 'deep_agent_1'  # flash
    llm = LLMClient(
        api_key=ModelRouter.get_api_key(route, api_key),
        base_url=ModelRouter.get_base_url(route, base_url),
        model=ModelRouter.get_model(route, model),
    )

    prd_md = artifacts.get('agent4', {}).get('prd_markdown', '') or ''
    spec = _json.dumps(artifacts.get('agent4', {}).get('spec', {}), ensure_ascii=False, indent=2)
    prd_preview = prd_md[:5000] if len(prd_md) > 5000 else prd_md

    # ── 加载平台数据：模块匹配 → 页面布局 → 组件列表 ──
    import os as _os
    import requests as _req
    _KB_BASE = 'http://localhost:8000'
    user_input = (session.get('user_input', '') or '') + ' ' + prd_preview[:500]

    layout_context = ''
    component_context = ''
    try:
        # 1. 取 12 模块清单，匹配模块
        mod_resp = _req.get(f'{_KB_BASE}/api/admin/modules', timeout=10)
        if mod_resp.ok:
            mod_data = mod_resp.json().get('data', {}).get('modules', [])
            matched_module = None
            for m in mod_data:
                name = m.get('module_name', '')
                kws = m.get('backend_keywords', []) or []
                if name and name in user_input:
                    matched_module = name
                    break
                for kw in kws:
                    if kw and kw in user_input:
                        matched_module = name
                        break
            if matched_module:
                layout_lines = [f'匹配模块: {matched_module}']
                # 2. 取 design_layouts，筛选该模块的页面
                lay_resp = _req.get(f'{_KB_BASE}/api/admin/design-layouts', timeout=10)
                if lay_resp.ok:
                    all_pages = lay_resp.json().get('data', {}).get('modules', {})
                    # 尝试匹配模块名简写：模型训练→modalTraining
                    mod_key_candidates = [matched_module]
                    for mk in all_pages:
                        if matched_module[:4] in mk or mk[:4] in matched_module:
                            mod_key_candidates.append(mk)
                    for mk in dict.fromkeys(mod_key_candidates):
                        pages = all_pages.get(mk, [])
                        if pages:
                            layout_lines.append(f'\n该模块有 {len(pages)} 个页面:')
                            for p in pages:
                                comps = ', '.join(p.get('layout_components', []) or [])
                                layout_lines.append(f'  - {p.get("page_id","?")} [{p.get("page_type","?")}] 组件: [{comps}]')
                            break
                    # 未命中则展示所有页面类型分布
                    if len(layout_lines) == 1:
                        type_counts = lay_resp.json().get('data', {}).get('page_type_counts', {})
                        most = ', '.join(lay_resp.json().get('data', {}).get('most_used_components', []))
                        layout_lines.append(f'\n平台页面类型分布: {type_counts}')
                        layout_lines.append(f'平台常用组件: {most}')
                layout_context = '\n'.join(layout_lines)

        # 3. 取 component_registry，按匹配模块筛选的页面筛选组件
        comps_resp = _req.get(f'{_KB_BASE}/api/admin/component-registry', timeout=10)
        if comps_resp.ok:
            reg = comps_resp.json().get('data', []) or []
            project_comps = [c for c in reg if c.get('category') == 'project']
            business_comps = sorted([c for c in reg if c.get('category') == 'business'], key=lambda x: -x.get('reuse_count', 0))
            lines = [f'共 {len(reg)} 个组件']
            lines.append(f'\n# 项目级封装组件（{len(project_comps)} 个）')
            for c in project_comps:
                props = ', '.join(f"{p['name']}: {p['type']}" for p in (c.get('props') or [])[:4])
                pages = ', '.join(c.get('used_in_pages', [])[:3])
                lines.append(f'- {c["name"]} props=[{props}] 用于={pages}')
            lines.append(f'\n# 常用业务组件（Top 15）')
            for c in business_comps[:15]:
                pages = ', '.join(c.get('used_in_pages', [])[:2])
                lines.append(f'- {c["name"]} (复用{c.get("reuse_count",0)}次) 用于={pages}')
            component_context = '\n'.join(lines)
    except Exception as e:
        logger.warning(f'[PRDGen] Agent5 加载平台数据失败: {e}')
        if not layout_context:
            layout_context = '（平台布局数据不可用）'
        if not component_context:
            component_context = '（组件注册表不可用）'

    prompt = _AGENT5_PROMPT.format(
        prd_markdown=prd_preview,
        spec=spec,
        platform_layouts=layout_context,
        platform_components=component_context,
    )

    try:
        result_text = llm.chat(
            system='你是一个资深产品设计师。输出必须为严格 JSON 格式，uiSpec 为 JSON 数组。',
            user=prompt,
            temperature=0.5,
            max_tokens=8192,
            timeout=180,
        )
    except Exception as e:
        logger.error(f'[PRDGen] Agent5 原型失败: {e}')
        return {'error': str(e), 'uiSpec': []}

    parsed = PRDGenService._parse_json_safe(result_text, {'sections': [], 'title': 'PRD 原型'})
    if not isinstance(parsed, dict):
        parsed = {'sections': [], 'title': 'PRD 原型'}
    # 用后端渲染器生成可靠 HTML
    try:
        from .prototype_renderer import render_prototype
        html = render_prototype(parsed)
        parsed['html'] = html
    except Exception as e:
        logger.error(f'[PRDGen] Agent5 原型渲染失败: {e}')
        parsed['html'] = '<html><body><h2>原型渲染失败</h2><p>' + str(e) + '</p></body></html>'
    return parsed

