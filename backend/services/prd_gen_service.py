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

from .db import (
    create_prd_session, get_prd_session, update_prd_session,
    save_prd_version, get_prd_versions, get_prd_version_content,
    add_chat_message, get_chat_messages,
    save_prd_file, get_prd_files, get_prd_file,
)
from .llm_client import LLMClient
from .sse_helpers import sse_event

logger = logging.getLogger(__name__)


# ── Prompt 模板 ──

_SYSTEM_PROMPT_TEMPLATE = """你是机器学习平台的产品需求文档撰写助手。"""

_OUTLINE_PROMPT = """请根据以下需求描述，生成 PRD 大纲（仅返回章节列表，JSON 格式）。

输出格式（严格 JSON，不要包含其他内容）：
{{
  "sections": ["overview", "background", "stories", "requirements", "design", "technical", "rollout", "questions", "appendix"]
}}

章节说明：
- overview: 功能概述（问题陈述 + 解决方案 + 成功指标）
- background: 背景与上下文（为什么现在做、战略对齐）
- stories: 用户故事（3-7 条，含验收标准）
- requirements: 需求（功能 P0/P1/P2 + 非功能）
- design: 设计与体验（关键流程、边界状态）
- technical: 技术考虑（依赖、风险）
- rollout: 分阶段发布计划
- questions: 开放问题
- appendix: 附录

需求描述：
{user_input}"""

# 9 个章节，每节带"好"的标准说明
_SECTION_PROMPTS = {
    "overview": """请撰写 PRD 的「功能概述」章节。必须包含以下 3 个子节：

## 1. 问题陈述
从用户视角描述当前遇到的痛点，2-3 句话，包含具体数据。

## 2. 解决方案
高层次的方案描述，2-3 句话。

## 3. 成功指标
| 指标 | 当前基线 | 目标值 | 衡量时间 |
|---|---|---|---|
| 采用率 | | | |
| 核心效果 | | | |
| 业务影响 | | | |
| 防护指标 | | | |

- 每个指标必须有基线值（当前是多少），没有基线就不能算指标
- 至少包含一个防护指标（"什么不能变差"）
- 指标必须与功能行为直接相关

已收集的需求信息：
{collected_info}""",

    "background": """请撰写 PRD 的「背景与上下文」章节。必须包含：

## 1. 为什么现在做
触发事件——下降的指标、竞争对手动作、战略押注、合同到期等。

## 2. 战略对齐
引述相关的团队/公司目标。

## 3. 研究总结
3-5 个关键发现，附样本量和来源。

已收集的需求信息：
{collected_info}""",

    "stories": """请撰写 PRD 的「用户故事」章节。要求：
- 3-7 条用户故事，格式：As a [用户角色], I want to [动作] so that [收益]
- 每条故事必须有可测试的验收标准
- 按优先级排列

已收集的需求信息：
{collected_info}""",

    "requirements": """请撰写 PRD 的「需求」章节。必须包含：

## 功能需求
| ID | 需求描述 | 优先级 |
|---|---|---|
| F1 | | P0/P1/P2 |

P0 = 必须要有，P1 = 应该有，P2 = 可以有

## 非功能需求
- 性能：具体数值，如 p95 加载 < 800ms
- 安全/隐私：涉及的数据、访问规则
- 可访问性：标准，如 WCAG 2.2 AA

已收集的需求信息：
{collected_info}""",

    "design": """请撰写 PRD 的「设计与体验」章节。要求：
- 关键用户流程描述
- 错误状态、空状态、加载状态的处理
- 边界情况说明

已收集的需求信息：
{collected_info}""",

    "technical": """请撰写 PRD 的「技术考虑」章节。要求：
- 依赖的系统/模块/团队
- 风险与缓解措施
- 不需要写实现细节（那是技术方案的事）

已收集的需求信息：
{collected_info}""",

    "rollout": """请撰写 PRD 的「分阶段发布计划」章节。要求：
| 阶段 | 范围 | 进入下一阶段的门禁 |
|---|---|---|
| MVP | | |
| 阶段 2 | | |

已收集的需求信息：
{collected_info}""",

    "questions": """请撰写 PRD 的「开放问题」章节。以表格形式列出：
| 问题 | 负责人 | 需要决策时间 |
|---|---|---|

已收集的需求信息：
{collected_info}""",

    "appendix": """请撰写 PRD 的「附录」章节。包含：
- 相关参考链接
- 相关文档
- 竞品分析笔记

已收集的需求信息：
{collected_info}""",
}

_SECTION_NAMES = {
    "overview": "功能概述",
    "background": "背景与上下文",
    "stories": "用户故事",
    "requirements": "需求",
    "design": "设计与体验",
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

_QUESTION_PROMPT = """你是机器学习平台产品的需求分析助手，正在通过多轮对话收集 PRD 所需信息。

## 用户原始需求
{user_input}

## 对话历史（完整记录，包含之前所有问答）
{chat_history}

## 当前引导话题
当前话题：{current_topic}
引导说明：{current_guide}
完成标准：{current_check}

## 你应该继续追问还是进入下一话题？

### 继续追问的条件：
- 当前话题的信息还不够充分，用户只回答了部分内容，需要补充更多细节
- 用户回答比较模糊，可以进一步澄清

### 进入下一话题的条件：
- 当前话题的信息已经收集得比较充分，可以进入下一话题
- 用户明确说"不知道"或"没有"——不再追问，推进到下一话题

**重要规则：**
1. 每个话题应进行 2-3 轮对话，充分收集信息后再进入下一话题
2. 每一轮只问一个问题，一次只聚焦一个话题
3. 不要问与 PRD 功能需求无关的问题（如公司战略、团队目标、组织架构等）
4. 参考对话历史，不要重复问已经回答过的问题
5. 如果用户回答中说"不知道"或"没有"，视为该话题已覆盖，进入下一话题
6. 当信息足够充分时，及时进入下一话题，不要过度追问

## 输出格式
返回严格 JSON，不要包含其他内容：

如果继续追问当前话题：
{{"status": "continue", "question": "针对当前话题的追问（简洁、具体，聚焦细节补充）", "topic_done": false, "reason": "为什么还需要追问"}}

如果当前话题已足够，进入下一话题：
{{"status": "continue", "question": "下一话题的引导问题（结合历史，承上启下）", "topic_done": true, "items_covered": ["已覆盖的话题名称1", "已覆盖的话题名称2"]}}

如果所有 7 个话题都已覆盖：
{{"status": "complete", "reason": "全部 7 个话题已收集完毕", "items_covered": ["话题1", "话题2", "话题3", "话题4", "话题5", "话题6", "话题7"]}}"""

_MINUTES_EXTRACT_PROMPT = """你是机器学习平台的需求分析助手。请从以下飞书会议纪要中提取与产品功能需求相关的信息。

会议纪要：
{minutes_text}

请提取以下信息，以 JSON 格式返回（不要包含其他内容）：
{{
  "featurePoints": ["功能需求点1", "功能需求点2"],
  "stakeholders": ["涉及的干系人/角色"],
  "constraints": ["约束条件/限制"],
  "background": "需求产生的背景和动机"
}}"""

_SECTION_NAMES = {
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
    def _build_collected_info_text(session: dict) -> str:
        """从 collected_info 和 user_input 构建信息文本（入 LLM Prompt）"""
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

        return '\n\n'.join(parts) if parts else '（暂无补充信息）'

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

    def simple_generate(self, session_id: str, api_key: str, base_url: str, model: str):
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

        # Step 2: 逐章节生成
        collected_info = self._build_collected_info_text(session)
        for section in sections:
            section_name = _SECTION_NAMES.get(section, section)
            yield sse_event('progress', {'step': section, 'message': f'正在生成章节「{section_name}」...'})

            prompt = _SECTION_PROMPTS.get(section, '请撰写 PRD 的"{section_name}"章节。内容基于已收集的需求信息，不要臆造。使用 Markdown 格式。\n\n已收集的需求信息：{collected_info}')
            content = ''
            for chunk in llm.chat_stream(
                system=self._build_system_prompt(),
                user=prompt.format(collected_info=collected_info) if '{collected_info}' in prompt else prompt + f'\n\n已收集的需求信息：{collected_info}',
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
        """处理一轮对话——LLM 判断是否完成当前话题，代码层兜底防止卡住"""
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

        # 代码层兜底：超过 3 轮强制推进（给 LLM 2-3 轮空间，防止过度追问）
        force_advance = rounds_on_current >= 3

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

    def generate_section(self, session_id: str, section: str, api_key: str, base_url: str, model: str):
        """流式生成单个章节

        如果章节已存在，先自动保存版本快照再重新生成。

        Yields:
            SSE 事件字符串
        """
        session = self.get_session(session_id)
        if not session:
            yield sse_event('error', {'message': '会话不存在'})
            return

        llm = self._make_llm(api_key, base_url, model)
        collected_info = self._build_collected_info_text(session)
        section_name = _SECTION_NAMES.get(section, section)

        # 获取章节专用 Prompt 模板
        section_prompt = _SECTION_PROMPTS.get(section,
            '请撰写 PRD 的"{section_name}"章节。\n\n已收集的需求信息：\n{collected_info}')

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
            user=section_prompt.format(collected_info=collected_info),
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

    def regenerate_section(self, session_id: str, section: str, api_key: str, base_url: str, model: str):
        """重新生成章节（保存快照后生成）"""
        yield from self.generate_section(session_id, section, api_key, base_url, model)

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
            system='你是机器学习平台的需求分析助手。',
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
