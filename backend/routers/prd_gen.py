"""
prd_gen.py — PRD 智能生成 API 路由

接口：
  POST   /api/prd/sessions                        — 创建会话
  POST   /api/prd/sessions/{id}/simple-generate   — 简单模式 SSE 生成
  POST   /api/prd/sessions/{id}/chat              — 中等模式对话
  GET    /api/prd/sessions/{id}/completeness      — 查询完备度
  POST   /api/prd/sessions/{id}/outline           — 生成大纲
  POST   /api/prd/sessions/{id}/sections/{section}/generate    — 章节 SSE 生成
  PUT    /api/prd/sessions/{id}/sections/{section}             — 编辑章节
  POST   /api/prd/sessions/{id}/sections/{section}/regenerate  — 重新生成
  GET    /api/prd/sessions/{id}/versions          — 版本列表
  GET    /api/prd/sessions/{id}/versions/{vid}    — 版本内容
  GET    /api/prd/sessions/{id}/export            — 导出 PRD (Content-Disposition)
  POST   /api/prd/files/upload                    — 上传文件
  POST   /api/prd/sessions/{id}/minutes           — 妙记解析
"""

from flask import Blueprint, request, Response, g

from services.prd_gen_service import PRDGenService
from services.sse_helpers import sse_event, sse_stream

prd_gen_bp = Blueprint('prd_gen', __name__, url_prefix='/api/prd')
service = PRDGenService()


def _get_llm_config() -> dict:
    """获取 LLM 配置（从请求头 / g 对象）"""
    cfg = getattr(g, 'llm_config', {})
    return {
        'api_key': cfg.get('api_key', ''),
        'base_url': cfg.get('base_url', 'https://api.openai.com/v1'),
        'model': cfg.get('model', 'gpt-4o'),
    }


def _sse_error(message: str):
    """构造 SSE 错误响应"""
    return sse_stream(lambda: iter([sse_event('error', {'message': message})]))


# ── 1. 创建会话 ──


@prd_gen_bp.route('/sessions', methods=['POST'])
def create_session():
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'simple')
    user_input = data.get('userInput', '')

    if mode not in ('simple', 'medium'):
        return {'error': '无效的模式，仅支持 simple / medium'}, 400

    session = service.create_session(mode, user_input)
    if not session:
        return {'error': '创建会话失败'}, 500

    return {
        'sessionId': session['id'],
        'mode': session['mode'],
        'status': session['status'],
    }


# ── 2. 简单模式 SSE 生成 ──


@prd_gen_bp.route('/sessions/<id>/simple-generate', methods=['POST'])
def simple_generate(id):
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return _sse_error('请先配置 LLM API Key')

    def generate():
        yield from service.simple_generate(id, cfg['api_key'], cfg['base_url'], cfg['model'])

    return sse_stream(generate)


# ── 3. 中等模式对话 ──


@prd_gen_bp.route('/sessions/<id>/start-chat', methods=['POST'])
def start_chat(id):
    """启动中等模式对话，返回第一个引导问题"""
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return {'error': '请先配置 LLM API Key'}, 400

    result = service.start_chat(id, cfg['api_key'], cfg['base_url'], cfg['model'])
    if 'error' in result:
        return result, 404 if result.get('error') == '会话不存在' else 400
    return result


@prd_gen_bp.route('/sessions/<id>/chat', methods=['POST'])
def chat_round(id):
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return {'error': '请先配置 LLM API Key'}, 400

    data = request.get_json(silent=True) or {}
    answer = data.get('answer', '')

    if not answer:
        return {'error': '请提供回答内容'}, 400

    result = service.chat_round(id, answer, cfg['api_key'], cfg['base_url'], cfg['model'])
    if 'error' in result:
        return result, 404 if result.get('error') == '会话不存在' else 400

    return result


# ── 4. 查询完备度 ──


@prd_gen_bp.route('/sessions/<id>/completeness', methods=['GET'])
def get_completeness(id):
    session = service.get_session(id)
    if not session:
        return {'error': '会话不存在'}, 404

    completeness = service._check_completeness(session)
    missing_items = service._get_missing_items(session)

    return {
        'completeness': completeness,
        'missingItems': missing_items,
    }


# ── 5. 生成大纲 ──


@prd_gen_bp.route('/sessions/<id>/outline', methods=['POST'])
def generate_outline(id):
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return {'error': '请先配置 LLM API Key'}, 400

    result = service.generate_outline(id, cfg['api_key'], cfg['base_url'], cfg['model'])
    if 'error' in result:
        return result, 404
    return result


# ── 6. 章节 SSE 生成 ──


@prd_gen_bp.route('/sessions/<id>/sections/<section>/generate', methods=['POST'])
def generate_section(id, section):
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return _sse_error('请先配置 LLM API Key')

    def generate():
        yield from service.generate_section(id, section, cfg['api_key'], cfg['base_url'], cfg['model'])

    return sse_stream(generate)


# ── 7. 编辑章节 ──


@prd_gen_bp.route('/sessions/<id>/sections/<section>', methods=['PUT'])
def update_section(id, section):
    data = request.get_json(silent=True) or {}
    content = data.get('content', '')

    if not content:
        return {'error': '内容不能为空'}, 400

    result = service.update_section_content(id, section, content)
    if 'error' in result:
        return result, 404
    return result


# ── 8. 重新生成章节 ──


@prd_gen_bp.route('/sessions/<id>/sections/<section>/regenerate', methods=['POST'])
def regenerate_section(id, section):
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return _sse_error('请先配置 LLM API Key')

    def generate():
        yield from service.regenerate_section(id, section, cfg['api_key'], cfg['base_url'], cfg['model'])

    return sse_stream(generate)


# ── 9. 版本列表 ──


@prd_gen_bp.route('/sessions/<id>/versions', methods=['GET'])
def get_versions(id):
    section = request.args.get('section', None)
    versions = service.get_versions(id, section)
    return {'versions': versions}


# ── 10. 版本内容 ──


@prd_gen_bp.route('/sessions/<id>/versions/<vid>', methods=['GET'])
def get_version_content(id, vid):
    version = service.get_version_content(vid)
    if not version:
        return {'error': '版本不存在'}, 404
    return {
        'id': version['id'],
        'session_id': version['session_id'],
        'section': version['section'],
        'content': version['content'],
        'version_num': version['version_num'],
        'created_at': version['created_at'],
    }


# ── 11. 导出 PRD ──


@prd_gen_bp.route('/sessions/<id>/export', methods=['GET'])
def export_prd(id):
    """导出 PRD 为 Markdown 文件（GET 请求）"""
    session = service.get_session(id)
    if not session:
        return {'error': '会话不存在'}, 404

    markdown = service.export_prd(id)
    user_input = (session.get('user_input', '') or 'untitled')[:20]
    safe_name = ''.join(c for c in user_input if c.isalnum() or c in ' _-').strip() or 'prd'

    return Response(
        markdown,
        mimetype='text/markdown',
        headers={'Content-Disposition': f'attachment; filename="PRD-{safe_name}.md"'},
    )


# ── 12. 文件上传 ──


@prd_gen_bp.route('/files/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return {'error': '请选择文件'}, 400

    file = request.files['file']
    file_type = request.form.get('file_type', 'temporary')
    session_id = request.form.get('session_id', '')

    if not session_id:
        return {'error': '缺少 session_id'}, 400

    if not file.filename:
        return {'error': '文件名为空'}, 400

    result = service.handle_file_upload(session_id, file, file_type)
    if 'error' in result:
        return result, 400
    return result


# ── 13. 妙记解析 ──


@prd_gen_bp.route('/sessions/<id>/minutes', methods=['POST'])
def parse_minutes(id):
    cfg = _get_llm_config()
    if not cfg['api_key']:
        return {'error': '请先配置 LLM API Key'}, 400

    data = request.get_json(silent=True) or {}
    url = data.get('url', '')

    if not url:
        return {'error': '请提供妙记链接'}, 400

    result = service.parse_minutes(id, url, cfg['api_key'], cfg['base_url'], cfg['model'])
    return result
