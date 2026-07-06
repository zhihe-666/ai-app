"""
数据模型定义

Flask 无自动验证，所有请求参数通过 dataclass 做结构化封装。
路由中通过 parse_json() 或 parse_form() 解析请求体后转为模型实例。

用法:
    @router.route('/example', methods=['POST'])
    def example():
        req = MeetingTodoExtractRequest(**request.get_json())
        # req.link, req.minute_token ...
"""

from dataclasses import dataclass, field
from typing import Optional


# ── 会议 TODO ──


@dataclass
class MeetingTodoExtractRequest:
    """妙记链接 → 提取待办"""
    link: str = ""
    minute_token: str = ""           # 可选，直接传入 token 跳过解析


@dataclass
class MeetingDocGenerateRequest:
    """确认后的待办 → 生成飞书文档"""
    meeting_title: str = ""
    meeting_time: str = ""
    paragraphs: list = field(default_factory=list)       # 逐字稿段落
    todos: list = field(default_factory=list)            # 待办列表
    transcript_paragraphs: list = field(default_factory=list)  # 逐字稿文本列表


# ── 迭代统计 ──


@dataclass
class IterStatsCrawlRequest:
    """自动爬取 iwork"""
    version: str = "5.94"
    projects: list = field(default_factory=list)
    iwork_cookie: Optional[str] = None


# ── 数据报告 ──


@dataclass
class ReportGenerateRequest:
    """生成数据报告"""
    access_token: str = ""
    pilot_names: str = ""            # 逗号分隔
    start_date: str = ""
    end_date: str = ""
    sections: list = field(default_factory=list)   # ["active_rate", "inactive", "skills", "tl_usage"]


@dataclass
class ReportWriteRequest:
    """写入飞书文档"""
    title: str = ""
    content: str = ""                # Markdown


# ── 问答 ──


@dataclass
class ChatRequest:
    """发送问题"""
    message: str = ""
    conversation_id: Optional[str] = None


# ── 通用 ──


@dataclass
class TokenVerifyRequest:
    """验证 Token 是否有效"""
    token: str = ""