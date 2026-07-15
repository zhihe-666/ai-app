"""
知识库问答 router

将前端请求代理到无矩2.0 知识问答 API（FastAPI 微服务），
以 SSE 流式返回回答和引用来源。流式结束后保存历史到 SQLite。
"""
import json
import logging

import requests
from flask import Blueprint, Response, request, jsonify

from services.db import (
    save_chat_session, list_chat_sessions, get_chat_session,
    delete_chat_session, clear_chat_sessions,
)

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

    流式结束后将完整 answer + sources 保存到 chat_sessions 表。

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
        full_answer_parts = []
        collected_sources = []
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

        # 逐行读取 SSE 流并转发（原样透传 type/sources/token）
        # 同时累积 answer 和 sources，流结束后存历史
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: ") or line.startswith("data:"):
                data_str = line[line.index(":")+1:].strip()
                if data_str == "[DONE]":
                    # 流结束，保存历史
                    full_answer = "".join(full_answer_parts)
                    try:
                        save_chat_session(query, full_answer, collected_sources)
                    except Exception as e:
                        logger.warning(f"[Chat] 保存历史失败: {e}")
                    yield _sse_event("done", {})
                    return
                # 解析事件，累积 answer/sources
                try:
                    event = json.loads(data_str)
                    etype = event.get("type", "")
                    if etype == "sources":
                        collected_sources = event.get("sources", []) or []
                    elif etype == "token":
                        full_answer_parts.append(event.get("content", ""))
                except json.JSONDecodeError:
                    pass
                # 原样转发
                yield f"{line}\n\n"

        # 流自然结束（无 [DONE]），也保存
        full_answer = "".join(full_answer_parts)
        try:
            save_chat_session(query, full_answer, collected_sources)
        except Exception as e:
            logger.warning(f"[Chat] 保存历史失败: {e}")

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_bp.route('/query', methods=['POST'])
def query_contexts():
    """非流式查询 → 返回检索到的 contexts（用于中控台自管 LLM）

    对齐 T025 文档 2.2：POST /api/query
    """
    body = request.get_json(silent=True) or {}
    query = body.get('query', '').strip()

    if not query:
        return jsonify({"error": "查询不能为空"}), 400

    try:
        resp = requests.post(
            f"{KB_BASE_URL}/api/query",
            json={"query": query},
            timeout=60,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"
        }), 502
    except requests.exceptions.Timeout:
        return jsonify({"error": "知识库服务响应超时，请稍后重试。"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"知识库服务请求失败: {str(e)}"}), 502


# ── 问答历史 CRUD ──


@chat_bp.route('/conversations', methods=['GET'])
def list_conversations():
    """获取问答历史列表（按时间倒序）"""
    limit = request.args.get('limit', 50, type=int)
    sessions = list_chat_sessions(limit=limit)
    return jsonify({"conversations": sessions})


@chat_bp.route('/conversations/<session_id>', methods=['GET'])
def get_conversation(session_id: str):
    """获取单条问答历史详情（含完整 answer 和 sources）"""
    session = get_chat_session(session_id)
    if not session:
        return jsonify({"error": "历史记录不存在"}), 404
    return jsonify(session)


@chat_bp.route('/conversations/<session_id>', methods=['DELETE'])
def delete_conversation(session_id: str):
    """删除单条问答历史"""
    ok = delete_chat_session(session_id)
    if not ok:
        return jsonify({"error": "历史记录不存在"}), 404
    return jsonify({"deleted": session_id})


@chat_bp.route('/conversations', methods=['DELETE'])
def clear_conversations():
    """清空所有问答历史"""
    count = clear_chat_sessions()
    return jsonify({"deleted_count": count})


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
