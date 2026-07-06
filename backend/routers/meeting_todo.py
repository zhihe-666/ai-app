"""
会议 TODO 提取 — API 路由

接口：
  POST /api/meeting-todo/extract    — SSE 流式提取（输入妙记链接 → 流式返回逐字稿/待办）
  POST /api/meeting-todo/generate   — 生成飞书文档（参数：meeting_info + module_groups）
  POST /api/meeting-todo/search     — 搜索妙记（参数：keyword）
"""

from flask import Blueprint, request, Response, g

from services.meeting_todo_service import (
    extract_todos_flow, parse_minutes_link,
    MeetingInfo, TodoItem, ModuleGroup,
    generate_meeting_doc, _sse_event,
    format_timestamp,
)
from services.feishu_client import (
    get_minute_info, search_minutes, get_transcript,
)

meeting_todo_bp = Blueprint('meeting_todo', __name__)


@meeting_todo_bp.route('/extract', methods=['POST'])
def extract():
    """SSE 流式提取待办事项

    请求体：{ "link": "https://poizon.feishu.cn/minutes/xxx" }
    响应：SSE 事件流
    """
    data = request.get_json(silent=True) or {}
    link = data.get('link', '')
    if not link:
        return Response(
            _sse_event("error", {"message": "请提供妙记链接"}),
            mimetype='text/event-stream',
        )

    llm_config = getattr(g, 'llm_config', {})
    api_key = llm_config.get('api_key', '')
    base_url = llm_config.get('base_url', '')
    model = llm_config.get('model', '')

    if not api_key:
        return Response(
            _sse_event("error", {"message": "请先配置 LLM API Key"}),
            mimetype='text/event-stream',
        )

    def generate():
        yield from extract_todos_flow(link, api_key, base_url, model)

    return Response(generate(), mimetype='text/event-stream')


@meeting_todo_bp.route('/generate', methods=['POST'])
def generate_doc():
    """生成会议纪要飞书文档

    请求体：
    {
        "meeting_info": { ... },
        "module_groups": [ { "name": "...", "todos": [...] } ]
    }
    响应：{ "url": "https://...feishu.cn/docx/xxx" }
    """
    data = request.get_json(silent=True) or {}

    meeting_data = data.get('meeting_info', {})
    module_data = data.get('module_groups', [])

    if not meeting_data or not module_data:
        return {"error": "缺少必要参数"}, 400

    meeting_info = MeetingInfo(
        title=meeting_data.get('title', ''),
        time=meeting_data.get('time', ''),
        minutes_link=meeting_data.get('minutes_link', ''),
        minute_token=meeting_data.get('minute_token', ''),
    )

    create_time_ms = meeting_data.get('create_time_ms', 0)

    module_groups = []
    for mg in module_data:
        todos = []
        for t in mg.get('todos', []):
            todos.append(TodoItem(
                id=t.get('id', 0),
                description=t.get('description', ''),
                module=t.get('module', mg.get('name', '')),
                ddl=t.get('ddl', ''),
                assignee=t.get('assignee', ''),
                assignee_open_id=t.get('assignee_open_id', ''),
                is_uncertain=t.get('is_uncertain', False),
                uncertainty_reason=t.get('uncertainty_reason', ''),
            ))
        module_groups.append(ModuleGroup(name=mg.get('name', '其他'), todos=todos))

    try:
        doc_url = generate_meeting_doc(meeting_info, module_groups, create_time_ms)
        return {"url": doc_url, "message": "文档创建成功"}
    except Exception as e:
        return {"error": f"文档创建失败：{str(e)}"}, 500


@meeting_todo_bp.route('/search', methods=['POST'])
def search():
    """搜索飞书妙记

    请求体：{ "keyword": "周会" }
    响应：{ "results": [ { "title": "...", "url": "...", "time": "..." } ] }
    """
    data = request.get_json(silent=True) or {}
    keyword = data.get('keyword', '')
    if not keyword:
        return {"error": "请提供搜索关键词"}, 400

    try:
        results = search_minutes(keyword)
        return {"results": results}
    except Exception as e:
        return {"error": f"搜索失败：{str(e)}"}, 500


@meeting_todo_bp.route('/preview', methods=['POST'])
def preview_transcript():
    """预览妙记内容（获取妙记信息和逐字稿概述，不调 LLM）

    请求体：{ "link": "https://poizon.feishu.cn/minutes/xxx" }
    响应：{ "meeting_info": {...}, "transcript_preview": "..." }
    """
    data = request.get_json(silent=True) or {}
    link = data.get('link', '')
    if not link:
        return {"error": "请提供妙记链接"}, 400

    minute_token = parse_minutes_link(link)
    if not minute_token:
        return {"error": "无效的妙记链接"}, 400

    try:
        minute_info = get_minute_info(minute_token)
        data = minute_info.get("data", {})
        minute = data.get("minute", data)
        title = minute.get("title", "未知会议")
        create_time = minute.get("create_time", "")

        meeting_info = MeetingInfo(
            title=title,
            time=format_timestamp(int(create_time)) if create_time else "",
            minutes_link=link,
            minute_token=minute_token,
        )

        transcript_preview = ""
        has_transcript = False
        try:
            transcript = get_transcript(minute_token)
            if transcript:
                has_transcript = True
                transcript_preview = transcript[:2000] + "..." if len(transcript) > 2000 else transcript
        except Exception:
            pass

        return {
            "meeting_info": meeting_info.to_dict(),
            "transcript_preview": transcript_preview,
            "has_transcript": has_transcript,
        }
    except Exception as e:
        return {"error": f"获取妙记信息失败：{str(e)}"}, 500