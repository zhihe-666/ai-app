"""
Flask SSE 流式辅助模块

Flask 不直接支持 FastAPI 的 StreamingResponse，
通过 generator + Response(mimetype='text/event-stream') 实现 SSE。

用法:
    @app.route('/stream')
    def stream():
        def gen():
            yield sse_event('progress', {'step': 1})
            yield sse_event('complete', {'done': True})
        return sse_stream(gen)
"""

import json
from flask import Response, stream_with_context


def sse_event(event_type: str, data: dict) -> str:
    """生成 SSE 事件字符串"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_stream(generator_fn):
    """包装 generator 为 Flask SSE Response

    stream_with_context 确保每个 yield 立即 flush，不被 werkzeug 缓冲。
    不设置 direct_passthrough，让 flask 添加必要的传输头。
    """
    return Response(stream_with_context(generator_fn()), mimetype='text/event-stream')