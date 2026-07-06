"""
知识库问答 router

将前端请求代理到无矩2.0 知识问答 API（FastAPI 微服务），
以 SSE 流式返回回答和引用来源。
"""
import json
import logging

import requests
from flask import Blueprint, Response, request, jsonify

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)

# 无矩2.0 知识问答服务地址
KB_BASE_URL = "http://localhost:8000"


def _sse_event(event_type: str, data: dict) -> str:
    """生成 SSE 事件字符串"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@chat_bp.route('/send', methods=['POST'])
def send_message():
    """发送问题 → 流式返回回答 + 引用（SSE 代理到无矩2.0）

    请求体:
        {"query": "问题内容"}

    响应（SSE 流）:
        data: {"type":"sources","sources":[...]}
        data: {"type":"token","content":"..."}
        data: {"type":"done"}
        data: {"type":"error","content":"..."}
    """
    body = request.get_json(silent=True) or {}
    query = body.get('query', '').strip()

    if not query:
        return jsonify({"error": "问题不能为空"}), 400

    def generate():
        try:
            resp = requests.post(
                f"{KB_BASE_URL}/api/query/stream",
                json={"query": query},
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            yield _sse_event("error", {
                "content": "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"
            })
            return
        except requests.exceptions.Timeout:
            yield _sse_event("error", {
                "content": "知识库服务响应超时，请稍后重试。"
            })
            return
        except requests.exceptions.RequestException as e:
            yield _sse_event("error", {
                "content": f"知识库服务请求失败: {str(e)}"
            })
            return

        # 逐行读取 SSE 流并转发（直接原样透传，保持 type/ sources/ token 字段不变）
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: ") or line.startswith("data:"):
                data_str = line[line.index(":")+1:].strip()
                if data_str == "[DONE]":
                    yield _sse_event("done", {})
                    return
                # 原样转发 data: {...}，不做二次封装
                yield f"{line}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_bp.route('/conversations', methods=['GET'])
def list_conversations():
    """获取历史对话列表（占位，后续可对接数据库）"""
    return jsonify({"conversations": []})


@chat_bp.route('/health', methods=['GET'])
def check_kb_health():
    """检查知识库服务连通性"""
    try:
        resp = requests.get(f"{KB_BASE_URL}/", timeout=5)
        return jsonify({
            "connected": resp.ok,
            "status_code": resp.status_code,
        })
    except Exception as e:
        return jsonify({
            "connected": False,
            "error": str(e),
        })
