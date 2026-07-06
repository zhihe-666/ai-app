"""
meeting_todo_service.py — 会议TODO提取核心业务逻辑

工作流（对应 SKILL 五阶段）：
Phase 1: 妙记定位 — 解析链接 → 获取 minute_token
Phase 2: 内容提取 — 获取妙记信息 → 逐字稿
Phase 3: AI 分析 — LLM 提取待办事项
Phase 4: 人工校验 — 前端交互（本层不处理）
Phase 5: 文档生成 — 创建飞书文档
"""

import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Generator, Optional

from .feishu_client import (
    get_minute_info, get_transcript, search_user_by_name,
)
from .llm_client import LLMClient

logger = logging.getLogger(__name__)


# ── 常量 ──

_MAX_TRANSCRIPT_LENGTH = 100000


# ── 数据模型 ──

class TodoItem:
    def __init__(
        self,
        id: int,
        description: str,
        module: str = "",
        ddl: str = "",
        assignee: str = "",
        assignee_open_id: str = "",
        is_uncertain: bool = False,
        uncertainty_reason: str = "",
    ):
        self.id = id
        self.description = description
        self.module = module
        self.ddl = ddl
        self.assignee = assignee
        self.assignee_open_id = assignee_open_id
        self.is_uncertain = is_uncertain
        self.uncertainty_reason = uncertainty_reason

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "module": self.module,
            "ddl": self.ddl,
            "assignee": self.assignee,
            "assignee_open_id": self.assignee_open_id,
            "is_uncertain": self.is_uncertain,
            "uncertainty_reason": self.uncertainty_reason,
        }


class ModuleGroup:
    def __init__(self, name: str, todos: list[TodoItem]):
        self.name = name
        self.todos = todos

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "todos": [t.to_dict() for t in self.todos],
        }


class MeetingInfo:
    def __init__(self, title: str, time: str, minutes_link: str, minute_token: str,
                 create_time_ms: int = 0):
        self.title = title
        self.time = time
        self.minutes_link = minutes_link
        self.minute_token = minute_token
        self.create_time_ms = create_time_ms

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "time": self.time,
            "minutes_link": self.minutes_link,
            "minute_token": self.minute_token,
            "create_time_ms": self.create_time_ms,
        }


# ── 辅助函数 ──

_MINUTES_URL_PATTERN = re.compile(r'minutes/([a-zA-Z0-9]+)')


def parse_minutes_link(link: str) -> Optional[str]:
    """从妙记链接中提取 minute_token"""
    match = _MINUTES_URL_PATTERN.search(link)
    return match.group(1) if match else None


def format_timestamp(ts_ms: int) -> str:
    """将毫秒级时间戳格式化为可读日期"""
    dt = datetime.fromtimestamp(ts_ms / 1000)
    return dt.strftime('%Y-%m-%d %H:%M')


_WEEKDAYS_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def format_meeting_date_context(ts_ms: int) -> str:
    """生成会议日期上下文（年月日星期+周边日期参考），用于注入 LLM Prompt

    输出示例：
    "会议日期：2026年5月28日（周四）
     本周五：5月29日（周四+1）
     下周一：6月1日（周四+4）"
    """
    dt = datetime.fromtimestamp(ts_ms / 1000)
    y, m, d = dt.year, dt.month, dt.day
    wd_idx = dt.weekday()  # 0=周一
    wd_cn = _WEEKDAYS_CN[wd_idx]

    # 本周五
    days_to_friday = (4 - wd_idx) % 7  # 周五=4
    friday_dt = dt + timedelta(days=days_to_friday)
    # 下周一
    days_to_next_monday = (7 - wd_idx) % 7
    next_monday_dt = dt + timedelta(days=days_to_next_monday)

    lines = [
        f"会议日期：{y}年{m}月{d}日（{wd_cn}）",
        f"本周五：{friday_dt.month}月{friday_dt.day}日（{wd_cn}+{days_to_friday}）",
        f"下周一：{next_monday_dt.month}月{next_monday_dt.day}日（{wd_cn}+{days_to_next_monday}）",
    ]
    return "\n".join(lines)


def _sse_event(event: str, data: dict) -> str:
    """生成 SSE 格式事件字符串"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── LLM 分析 ──

_TODO_EXTRACTION_PROMPT = """你是一个专业的会议纪要分析助手，擅长从会议逐字稿中提取待办事项。

## 核心原则
- 只提取有明确行动信号的待办事项
- 漏提和误提同等对待，都不能多
- DDL 准确与否影响不大，但待办提错影响大
- 不确定的标注 ⚠️

## 提取条件
必须同时满足两个条件才提取：
1. 有人说出要做什么（行动信号）
2. 有人认领或有明确指向（责任人信号）

## 明确排除（不要提取）
- 已完成的事项（"已经修了"、"搞定了"、"上线了"）
- 条件未触发的情况（"如果...就..."的条件不成立）
- 纯讨论/纯评价（"这个方案我觉得可以"）
- 纯事务性操作（"定个会议室"、"拉个群"）
- 一般性号召（"大家尽快修bug"）
- 讨论无结论
- 永久否决（明确说"不做"、"不需要"）

## 可以提取但注意
- "现在没排"/"后面再加" → 暂时搁置，提取（DDL写远期）
- "下个迭代" → 有后续计划，提取
- "找XX对一下" + 对方回应 → 对方回应=认领，提取
- "待定"但行动已明确 → 提取

## 模块划分
按事项类型动态归类：
- 技术类：技术问题修复、功能开发、性能优化
- 运营类：推广、演示、方案制定、用户引导
- 其他类：无法归入以上

## DDL 提取（⚠️ 必须输出具体日期，禁止模糊词）
会议日期见上方「会议日期上下文」。

- 明确日期（如"5月30号"、"下周一"）→ 直接换算为具体月日，如"5月30号"
- "今天" → 写成会议日期的具体月日+号，如"5月28号"
- "明天" → 会议日期次日，如"5月29号"
- "待会"/"等会"/"马上" → 当天，如"5月28号"
- "尽快"/"这周" → 结合会议日期写本周五，如"5月29号"
- "下周" → 写为"下周一"对应的具体日期加号，如"6月1号"
- "下个迭代" → 写为"下个迭代"
- **完全无时间表达 → 默认为会议当天，输出会议当天的具体日期（如"5月28号"）**

### ⚠️ 禁止输出：
- "今天"、"明天"、"这周"、"下周"等模糊词
- 空字符串（无时间表达时也必须输出会议当天日期）
- 必须输出具体月日格式，如"5月28号"

## 跟进人提取规则（关键 ⚠️）
### 核心原则：谁执行/谁被提及谁就是跟进人
逐字稿中每个发言段落以"姓名(英文名)"开头。**说话人不默认是跟进人，也不默认不是**——取决于语义。

### 判断矩阵（严格按此规则）
| 说话人说的话 | 跟进人 | 示例 |
|-------------|--------|------|
| "我来/我去/我负责/我看一下"（主动认领） | **说话人本人** | 思成："我来做配置初始化" → assignee=思成 |
| "你来做/你去处理"（指派某人） | **被指派的人** | → assignee=被指派者 |
| "找XX了解/找XX学一下/找XX问一下" | **说话人本人 + 被提及的XX** | 瘦子："找广智了解JVM参数" → assignee=**瘦子、广智** |
| "与XX/和XX/跟XX确认/对一下/沟通/对齐/同步"（协作类） | **说话人本人 + 被提及的XX** | 扉页："与瘦子对齐配置" → assignee=**扉页、瘦子** |
| "给XX验收/让XX看一下/提交给XX"（移交类） | **被提及的XX** | 思成："完成后给云锦验收" → assignee=云锦 |
| "我和XX一起/我和XX共同"（协作任务） | **说话人 + 被提及的XX 均需提取** | 思成："我和广智一起做TFS" → assignee=思成、广智 |
| 未明确提到任何人 | 留空（标注⚠️） | |

### 核心理解：找/与/和 类 = 说话人去协作，双方都涉及
- 说话人说"找XX了解XXX" → 说话人本身需要**主动去找**，所以说话人是跟进人；XX是知识提供方，也是跟进人
- 说话人说"与XX对齐XXX" → 说话人本身要**去对齐**，所以说话人是跟进人；XX是对齐对象，也是跟进人
- 但"给XX验收/让XX看" → 说话人本人已经完成了，移交给XX去验收，所以只有XX是跟进人

### ⚠️ 最容易漏的场景（特别注意）
以下场景中，**说话人本人 + 被提及人 都必须提取**：
- 云忻说"**与广智对齐**后端相关问题" → assignee=**云忻、广智**（云忻主动去找广智对齐，两人都参与）
- 思成说"**找广智了解**JVM参数" → assignee=**思成、广智**（思成要去找广智，两人都参与）
- 扉页说"**与瘦子对齐**配置" → assignee=**扉页、瘦子**（扉页和瘦子都需要做这件事）
- 大瘦子说"**和卡牌确认**版本号" → assignee=**大瘦子、卡牌**（两人都需要确认）

❌ 错误的输出：把上面任何一条的说话人去掉，只留被提及人
❌ 错误的输出：把上面任何一条的被提及人去掉，只留说话人

### 关键：只要句子中提到其他人名，就必须提取该人，不能漏

### 关键：只要句子中提到其他人名，就必须提取该人，不能漏
- "线下找广智了解JVM参数"→ 有"找广智"，广智就是跟进人
- "与瘦子对齐配置"→ 有"与瘦子"，瘦子就是跟进人
- "和云锦对一下"→ 有"和云锦"，云锦就是跟进人
- 即使动词是"了解""学习"等偏获取信息的词，**只要句中有"找XX"，XX就是跟进人**

### 多人协作（顿号分隔）
- 如果涉及多个被提及的人→全部用顿号"、"提取
- 示例："和广智、云锦确认"→ assignee=广智、云锦
- 说话人+被提及者时也全部提取：思成+"我和广智"→ assignee=思成、广智

### 简称→全称映射
- 说话人叫"大瘦子(Big Shou Zi)"，只说"瘦子"→ 输出"大瘦子"
- 语音识别错误（"云你"→"云锦"）→ 纠正为逐字稿中的完整姓名
- 参考"逐字稿中出现的说话人"列表

## 描述清洗规则（强制 ⚠️ 违反此规则视为错误输出）
**核心原则：跟进人提取后，描述中不能包含指向他们的"找人/协作"结构。**

### 具体规则
- **场景1：找人型** — 描述中有"找XX了解/找XX问/找XX对一下"且XX已被提取为跟进人 → 改为"了解/问/对一下"，**移除"找XX"**
  - ❌ "线下找广智了解JVM参数" + assignee=思成、广智 → ✅ "线下了解JVM参数"
- **场景2：协作型** — 描述中有"与XX对齐/和XX确认/与XX同步"且XX已被提取为跟进人 → 移除"与XX/和XX"，保留动作词
  - ❌ "与瘦子对齐配置" + assignee=扉页、瘦子 → ✅ "对齐配置"
  - ❌ "和云锦确认需求" + assignee=扉页、云锦 → ✅ "确认需求"
- **场景3：移交型** — 描述中有"给XX验收/提交给XX"且XX已被提取为跟进人 → 移除"给XX"，保留动作词
  - ❌ "完成后给云锦验收" + assignee=云锦 → ✅ "完成后验收"

### 识别技巧
1. 先写 assignee（判断谁该做），再写 description（描述做什么）
2. 写 description 时，把"找/与/和/给+人名"整块删掉
3. 保留技术术语和具体动作词，仅移除指向跟进人的人称结构
4. 如果删除后人称结构后语句不通顺，可适当调整语序（如"线下找广智了解"→"线下了解"）

## 输出格式

## 输出格式
以 JSON 格式输出，严格遵循以下结构（只输出 JSON，不要其他内容）：
{
  "module_groups": [
    {
      "name": "技术类-模块名",
      "todos": [
        {
          "description": "具体待办描述",
          "ddl": "5月28号 或 空字符串",
          "assignee": "跟进人姓名 或 空字符串",
          "is_uncertain": false,
          "uncertainty_reason": ""
        }
      ]
    }
  ]
}"""


def _ensure_valid_json(raw: str) -> str:
    """从 LLM 回复中提取并修复 JSON 字符串

    多层兜底策略（由简到繁）：
    第 1 层：标准 json.loads(strict=False)
    第 2 层：修复尾随逗号后重试
    第 3 层：json.JSONDecoder.raw_decode() 取解析到的部分
    第 4 层：重试 raw_decode + 截断残缺尾部

    关键原则：不预先删除 \\n、\\t、\\r（它们是 JSON 合法空白），
    只清理真正非法的字节（\\x00-\\x08、\\x0b、\\x0c、\\x0e-\\x1f、\\x7f）。
    """
    s = raw.strip()
    # 去掉 markdown 包裹
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    # 找到最外层 { … }
    start = s.find('{')
    end = s.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError("未找到有效的 JSON 对象")
    s = s[start:end+1]

    # 只清理真正非法字节（保留 \\n(0x0a)、\\t(0x09)、\\r(0x0d)）
    import re as _re
    s = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)

    # ── 第 1 层：标准解析 ──
    try:
        json.loads(s, strict=False)
        return s
    except json.JSONDecodeError:
        pass

    # ── 第 2 层：修复尾随逗号 ──
    s = _fix_trailing_commas(s)
    try:
        json.loads(s, strict=False)
        return s
    except json.JSONDecodeError:
        pass

    # ── 第 3 层：raw_decode 取能够解析的部分 ──
    try:
        decoder = json.JSONDecoder(strict=False)
        obj, pos = decoder.raw_decode(s)
        # 能解析出部分对象，将其序列化为标准 JSON
        repaired = json.dumps(obj, ensure_ascii=False)
        # 验证一下
        json.loads(repaired)
        return repaired
    except (json.JSONDecodeError, ValueError):
        pass

    # ── 第 4 层：逐字符裁尾，直到 raw_decode 能解析 ──
    # 常见场景：LLM 在 JSON 末尾多了一些不可解析的字符
    for cut_pos in range(len(s) - 1, start, -1):
        try:
            decoder = json.JSONDecoder(strict=False)
            obj, _ = decoder.raw_decode(s[:cut_pos])
            repaired = json.dumps(obj, ensure_ascii=False)
            json.loads(repaired)
            return repaired
        except (json.JSONDecodeError, ValueError):
            continue

    # 所有修复都失败，返回原始 cleaned（让上层报错）
    return s


def _fix_trailing_commas(s: str) -> str:
    """安全地移除 JSON 中尾随逗号（仅影响非字符串范围内）"""
    result = []
    in_string = False
    escape = False
    i = 0
    while i < len(s):
        ch = s[i]
        if escape:
            escape = False
            result.append(ch)
            i += 1
            continue
        if ch == '\\':
            escape = True
            result.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        if not in_string and ch == ',':
            # 看后面是否紧跟空白 + ] 或 }
            j = i + 1
            while j < len(s) and s[j] in ' \t\n\r':
                j += 1
            if j < len(s) and s[j] in ']}':
                # 尾随逗号：跳过逗号和空白，但保留 ] 或 }
                i = j
                # 不 continue，让循环处理当前的 ] 或 }
                continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _clean_description(description: str, assignee: str) -> str:
    """后端兜底清洗：从 description 中移除指向跟进人的前缀

    当 LLM 未正确执行描述清洗规则时，后端自动做安全清洗。
    处理模式：与XX/和XX/找XX/给XX/帮XX/替XX + 具体动作
    其中 XX 是 assignee 中包含的人名（支持顿号分隔多人）。

    支持模糊匹配：assignee="大瘦子" 也能匹配描述中的"瘦子"。
    """
    if not assignee or not description:
        return description

    # 拆分 assignee 中每个人名
    names = [n.strip() for n in assignee.split('、') if n.strip()]
    if not names:
        return description

    PREFIXES = ['与', '和', '找', '给', '帮', '替']

    def _strip_person(desc: str, name: str) -> str:
        """从 desc 中移除指向 name 的 '与/和/找/给/帮/替 + name' 结构"""
        # 生成要匹配的名字列表：精确名 + 所有可能简称（后缀子串，最少2字）
        search_names = [name]
        if len(name) > 2:
            for i in range(len(name) - 1, 1, -1):
                short = name[-i:]
                if len(short) >= 2:
                    search_names.append(short)
        # 去重但保持顺序
        seen = set()
        unique_names = []
        for n in search_names:
            if n not in seen:
                seen.add(n)
                unique_names.append(n)

        for p in PREFIXES:
            for try_name in unique_names:
                pattern = p + try_name
                idx = desc.find(pattern)
                while idx >= 0:
                    # 移除该部分
                    desc = desc[:idx] + desc[idx + len(pattern):]
                    desc = desc.lstrip('，,、　.')
                    idx = desc.find(pattern)

        return desc

    result = description
    for name in names:
        result = _strip_person(result, name)

    # 清理残余：多余逗号、首尾空白
    result = re.sub(r'[，,]\s*[，,]+', '，', result)
    result = result.strip('，, ')
    # 清理像 "完成后" 后面接空 → 如果只剩 "完成后" 但没动作了
    result = re.sub(r'^完成后[，,　\s]*', '', result)
    result = re.sub(r'^完成之后[，,　\s]*', '', result)
    result = result.strip('，, ')

    return result if result else description  # 不要返回空字符串


def _parse_llm_response(response: str) -> list[ModuleGroup]:
    """解析 LLM 返回的 JSON，转为 ModuleGroup 列表"""
    # 先记录原始响应前500字符用于调试
    logger.warning("LLM raw response (first 500): %s", response[:500])
    try:
        cleaned = _ensure_valid_json(response)
    except ValueError as e:
        logger.error("ensure_valid_json failed: %s, raw: %s", e, response[:300])
        raise
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("json.loads failed after _ensure_valid_json: %s, cleaned (first 500): %s",
                      e, cleaned[:500])
        raise
    module_groups = []
    todo_id = 1

    for mg in data.get("module_groups", []):
        todos = []
        for t in mg.get("todos", []):
            raw_desc = t.get("description", "")
            assignee = t.get("assignee", "")
            description = _clean_description(raw_desc, assignee)
            todos.append(TodoItem(
                id=todo_id,
                description=description,
                module=mg.get("name", "其他"),
                ddl=t.get("ddl", ""),
                assignee=t.get("assignee", ""),
                is_uncertain=t.get("is_uncertain", False),
                uncertainty_reason=t.get("uncertainty_reason", ""),
            ))
            todo_id += 1
        if todos:
            module_groups.append(ModuleGroup(
                name=mg.get("name", "其他"),
                todos=todos,
            ))

    return module_groups


def llm_extract_todos(
    api_key: str,
    base_url: str,
    model: str,
    transcript: str,
    meeting_info: MeetingInfo,
    create_time_ms: int = 0,
) -> list[ModuleGroup]:
    """调用 LLM 从逐字稿中提取待办事项

    Args:
        create_time_ms: 妙记创建时间（毫秒时间戳），用于生成会议日期上下文
    """
    client = LLMClient(api_key=api_key, base_url=base_url, model=model)

    # 入参净化：清除可能导致 LLM 输出 JSON 损坏的控制字符
    safe_transcript = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', transcript)

    # 生成会议日期上下文
    date_context = format_meeting_date_context(create_time_ms) if create_time_ms else ""
    # 提取逐字稿中所有说话人，帮助 LLM 做简称→全称映射
    speaker_names = set()
    for line in safe_transcript.split('\n'):
        m = re.match(r'^([\u4e00-\u9fff\w]+)\([^)]+\)', line)
        if m:
            speaker_names.add(m.group(1))
    speaker_list = "、".join(sorted(speaker_names))
    user_message = (
        f"会议信息：\n"
        f"标题：{meeting_info.title}\n"
        f"时间：{meeting_info.time}\n"
        f"\n{date_context}\n\n"
        f"逐字稿中出现的说话人（完整姓名）：{speaker_list}\n\n"
        f"以下是会议逐字稿内容，请提取待办事项：\n\n"
        f"{safe_transcript}"
    )

    response = client.chat(
        system=_TODO_EXTRACTION_PROMPT,
        user=user_message,
        temperature=0.0,
        max_tokens=8192,
    )

    return _parse_llm_response(response)


# ── 跟进人匹配 ──


def match_assignee_open_id(name: str) -> dict:
    """将跟进人姓名匹配为 open_id

    调用 lark-cli contact +search-user 查询，
    返回 {'open_id': str, 'name': str} 或 {'open_id': '', 'name': name}

    Args:
        name: 跟进人姓名/花名

    Returns:
        {'open_id': str, 'name': str}
    """
    if not name:
        return {'open_id': '', 'name': ''}

    result = search_user_by_name(name)
    if result:
        return result
    logger.warning(f"未找到用户: {name}")
    return {'open_id': '', 'name': name}


def _format_time_for_doc(time_str: str) -> str:
    """将 '2026-05-28 11:00' 转为 '5月28日 11:00'"""
    try:
        dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
        return f"{dt.month}月{dt.day}日 {dt.strftime('%H:%M')}"
    except ValueError:
        return time_str


# ── 文档模板（XML 格式，符合 SKILL 规范） ──

def _xml_escape(text: str) -> str:
    """转义 XML 特殊字符"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text


def _build_doc_xml(
    meeting_info: MeetingInfo,
    module_groups: list[ModuleGroup],
    create_time_ms: int = 0,
) -> str:
    """构建飞书文档 XML 内容（符合 SKILL 文档模板规范）

    使用 <ol> + <cite> 格式，而非简单表格。
    模板参考：references/document-template.xml
    """
    meeting_date = meeting_info.time[:10] if meeting_info.time else "未知日期"

    # 标题：会议纪要-{MM-DD} | {会议主题}
    # 避免重复：妙记标题已含 "MM-DD |" 前缀时不再重复
    mmdd = meeting_date[5:7] + '-' + meeting_date[8:10]
    safe_title = _xml_escape(meeting_info.title)
    if safe_title.startswith(mmdd + ' | '):
        title = f"会议纪要-{safe_title}"
    else:
        title = f"会议纪要-{mmdd} | {safe_title}"

    # 格式化时间
    time_display = _format_time_for_doc(meeting_info.time)

    parts = [f'<title>{title}</title>']
    parts.append('<h1 seq="auto">会议日程</h1>')
    parts.append('<table>')
    parts.append('  <colgroup><col/><col/></colgroup>')
    parts.append('  <tbody>')
    parts.append(f'    <tr><td><p><b>会议主题</b></p></td><td><p>{safe_title}</p></td></tr>')
    parts.append(f'    <tr><td><p><b>会议时间</b></p></td><td><p>{time_display} (GMT+8)</p></td></tr>')
    parts.append(f'    <tr><td><p><b>飞书妙记链接</b></p></td><td><p>{_xml_escape(meeting_info.minutes_link)}</p></td></tr>')
    parts.append('  </tbody>')
    parts.append('</table>')
    parts.append('<p></p>')
    parts.append('<h1 seq="auto">会议纪要</h1>')
    parts.append('<table>')
    parts.append('  <colgroup><col/><col/><col/></colgroup>')
    parts.append('  <tbody>')
    parts.append('    <tr><td colspan="3"><ol>')

    # 每个模块一层 <li>，内嵌 <ol>
    module_seq = 1
    for mg in module_groups:
        parts.append(f'      <li seq="{module_seq}">{_xml_escape(mg.name)}<ol>')
        module_seq += 1

        todo_seq = 1
        for todo in mg.todos:
            desc = todo.description
            if todo.is_uncertain:
                desc = f"⚠️ {desc}（{todo.uncertainty_reason}）"
            safe_desc = _xml_escape(desc)

            # DDL
            ddl_part = ""
            if todo.ddl:
                ddl_part = f"，DDL：{_xml_escape(todo.ddl)}"

            # @人 — 用 <cite> 标签，支持多人
            if todo.assignee_open_id and todo.assignee:
                assignee_names = todo.assignee.split("、")
                assignee_oids = todo.assignee_open_id.split("、")
                cite_parts = ""
                for idx, name_part in enumerate(assignee_names):
                    name_part = name_part.strip()
                    oid = assignee_oids[idx].strip() if idx < len(assignee_oids) else ""
                    if not name_part:
                        continue
                    safe_name = _xml_escape(name_part)
                    cite_parts += f'<cite type="user" user-id="{oid}" user-name="{safe_name}"></cite>'
            elif todo.assignee and not todo.assignee_open_id:
                assignee_names = todo.assignee.split("、")
                cite_parts = ""
                for name_part in assignee_names:
                    name_part = name_part.strip()
                    if not name_part:
                        continue
                    safe_name = _xml_escape(name_part)
                    cite_parts += f'<cite type="user" user-id="" user-name="{safe_name}"></cite>'

            parts.append(f'        <li seq="{todo_seq}">{safe_desc}{ddl_part}{cite_parts}</li>')
            todo_seq += 1

        parts.append('      </ol></li>')

    parts.append('    </ol></td></tr>')
    parts.append('  </tbody>')
    parts.append('</table>')
    parts.append('<p></p>')
    return '\n'.join(parts)


def _build_old_table_doc_xml(
    meeting_info: MeetingInfo,
    module_groups: list[ModuleGroup],
) -> str:
    """旧的表格格式文档模板（备用）"""
    meeting_date = meeting_info.time[:10] if meeting_info.time else "未知日期"
    title = f"会议纪要-{meeting_date.replace('-', '')} | {meeting_info.title}"

    parts = [f'<title>{title}</title>']
    parts.append('<h1 seq="auto">会议日程</h1>')
    parts.append('<table>')
    parts.append(f'  <tr><th><p>会议主题</p></th><td><p>{meeting_info.title}</p></td></tr>')
    parts.append(f'  <tr><th><p>时间</p></th><td><p>{meeting_info.time}</p></td></tr>')
    parts.append(f'  <tr><th><p>妙记链接</p></th><td><p>{meeting_info.minutes_link}</p></td></tr>')
    parts.append('</table>')
    parts.append('<p></p>')
    parts.append('<h1 seq="auto">会议纪要</h1>')
    parts.append('<table>')
    parts.append('  <tr><th><p>模块</p></th><th><p>待办事项</p></th><th><p>DDL</p></th><th><p>跟进人</p></th></tr>')
    for mg in module_groups:
        for todo in mg.todos:
            desc = todo.description
            if todo.is_uncertain:
                desc = f"⚠️ {desc}（{todo.uncertainty_reason}）"
            ddl_cell = todo.ddl or ""
            assignee_cell = todo.assignee or ""
            parts.append(
                f'  <tr><td><p>{mg.name}</p></td>'
                f'<td><p>{desc}</p></td>'
                f'<td><p>{ddl_cell}</p></td>'
                f'<td><p>{assignee_cell}</p></td></tr>'
            )
    parts.append('</table>')
    return '\n'.join(parts)


# ── 核心 SSE 流程 ──

def extract_todos_flow(
    link: str,
    api_key: str,
    base_url: str,
    model: str,
) -> Generator[str, None, None]:
    """
    完整提取流程 — 以 SSE 事件流形式产出

    事件顺序：
      1. progress  → step 1: 获取妙记信息
      2. progress  → step 2: 提取逐字稿
      3. section_complete → transcript_ready（含逐字稿内容）
      4. progress  → step 3: AI 分析
      5. complete  → 最终结果（含待办事项）
      6. error     → 出错时 emit
    """
    # Phase 1: 解析链接
    minute_token = parse_minutes_link(link)
    if not minute_token:
        yield _sse_event("error", {"message": "无效的妙记链接，请检查链接格式"})
        return

    yield _sse_event("progress", {"step": 1, "message": "正在获取妙记信息..."})

    # Phase 2: 获取妙记信息
    try:
        minute_info = get_minute_info(minute_token)
    except Exception as e:
        yield _sse_event("error", {"message": f"获取妙记失败：{str(e)}"})
        return

    data = minute_info.get("data", {})
    minute = data.get("minute", data)
    title = minute.get("title", "未知会议")
    create_time = minute.get("create_time", "")

    create_time_ms = int(create_time) if create_time else 0

    meeting_info = MeetingInfo(
        title=title,
        time=format_timestamp(create_time_ms) if create_time else "",
        minutes_link=link,
        minute_token=minute_token,
        create_time_ms=create_time_ms,
    )

    # 获取逐字稿（直连 transcript 端点）
    yield _sse_event("progress", {"step": 2, "message": "正在提取逐字稿..."})

    try:
        transcript = get_transcript(minute_token)
    except Exception as e:
        yield _sse_event("error", {"message": f"获取逐字稿失败：{str(e)}"})
        return

    # 截取过长内容
    if len(transcript) > _MAX_TRANSCRIPT_LENGTH:
        transcript = transcript[:_MAX_TRANSCRIPT_LENGTH] + "\n\n...（逐字稿过长，已截取前 10 万字）"

    # 发送逐字稿给前端
    yield _sse_event("section_complete", {
        "step": "transcript_ready",
        "data": {
            "meeting_info": meeting_info.to_dict(),
            "content": transcript,
        }
    })

    # Phase 3: LLM 分析（最多重试 3 次）
    yield _sse_event("progress", {"step": 3, "message": "AI 正在分析待办事项..."})

    module_groups = None
    last_error = None
    for attempt in range(3):
        try:
            module_groups = llm_extract_todos(
                api_key=api_key,
                base_url=base_url,
                model=model,
                transcript=transcript,
                meeting_info=meeting_info,
                create_time_ms=create_time_ms,
            )
            break
        except Exception as e:
            last_error = e
            if attempt < 2:
                logger.warning(f"LLM 第 {attempt + 1} 次调用 JSON 解析失败，重试中... ({e})")
            else:
                logger.error(f"LLM 连续 3 次调用均失败: {e}")
                yield _sse_event("error", {"message": f"AI 分析失败（连续 3 次）: {str(e)}"})
                return

    # 完成
    yield _sse_event("complete", {
        "step": "todos_ready",
        "data": {
            "meeting_info": meeting_info.to_dict(),
            "module_groups": [mg.to_dict() for mg in module_groups],
        }
    })


# ── 文档生成 ──

def generate_meeting_doc(
    meeting_info: MeetingInfo,
    module_groups: list[ModuleGroup],
    create_time_ms: int = 0,
) -> str:
    """生成会议纪要飞书文档，返回文档 URL

    在生成文档前，自动匹配所有跟进人的 open_id。
    使用 XML 格式创建飞书文档（符合 SKILL 文档模板规范）

    Args:
        meeting_info: 会议信息
        module_groups: 模块化的待办列表
        create_time_ms: 妙记创建时间（毫秒时间戳），用于生成日期上下文

    Returns:
        文档 URL
    """
    # Step 1: 匹配所有跟进人的 open_id（支持多人，"、"分隔）
    for mg in module_groups:
        for todo in mg.todos:
            if todo.assignee and not todo.assignee_open_id:
                names = [n.strip() for n in todo.assignee.split("、") if n.strip()]
                matched_names = []
                matched_oids = []
                for name in names:
                    user_info = match_assignee_open_id(name)
                    matched_oids.append(user_info.get('open_id', ''))
                    matched_names.append(user_info.get('name') or name)
                todo.assignee_open_id = "、".join(matched_oids)
                todo.assignee = "、".join(matched_names)

    meeting_date = meeting_info.time[:10] if meeting_info.time else "未知日期"
    mmdd = meeting_date[5:7] + '-' + meeting_date[8:10]
    title = f"会议纪要-{mmdd} | {meeting_info.title}"
    xml_content = _build_doc_xml(meeting_info, module_groups, create_time_ms)

    # 用 XML 格式创建文档
    from .feishu_client import create_doc_xml
    doc_url = create_doc_xml(title, xml_content)
    return doc_url