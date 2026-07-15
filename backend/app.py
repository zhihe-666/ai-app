import os
from flask import Flask, jsonify, g, request, send_from_directory
from flask_cors import CORS
from routers.meeting_todo import meeting_todo_bp
from routers.iteration_stats import iteration_stats_bp
from routers.ai_measure import ai_measure_bp
from routers.chat import chat_bp
from routers.kb_manage import kb_manage_bp
from routers.code_analyze import code_analyze_bp
from routers.prd_gen import prd_gen_bp
from services.auth_middleware import auth_bp, get_llm_config
from services.db import init_db, get_db, get_user_config

app = Flask(__name__)
CORS(app)

# 初始化数据库
init_db()

# 飞书操作：使用 lark-cli subprocess 方案，无需额外初始化


@app.teardown_appcontext
def close_db(exception):
    """请求结束时关闭数据库连接"""
    db = getattr(g, 'db', None)
    if db:
        db.close()


@app.before_request
def inject_llm_config():
    """在每个请求开始前注入 LLM 配置到 g 对象

    优先级：请求头 > 数据库 > 环境变量默认值（对方未配置时用本地默认）
    """
    g.llm_config = get_llm_config()
    # 如果请求头未携带 API Key，兜底使用数据库中的持久化配置
    if not g.llm_config.get('api_key'):
        saved = get_user_config()
        if saved:
            g.llm_config = {
                'api_key': saved.get('api_key', ''),
                'base_url': saved.get('base_url', 'https://api.openai.com/v1'),
                'model': saved.get('model', 'gpt-4o'),
                'git_token': saved.get('git_token', ''),
            }
    # 最后兜底：环境变量默认配置（对方未配置时也能用本地默认配置）
    if not g.llm_config.get('api_key'):
        g.llm_config = {
            'api_key': os.environ.get('DEFAULT_API_KEY', ''),
            'base_url': os.environ.get('DEFAULT_BASE_URL', 'https://api.openai.com/v1'),
            'model': os.environ.get('DEFAULT_MODEL', 'gpt-4o'),
            'git_token': os.environ.get('DEFAULT_GIT_TOKEN', os.environ.get('GIT_TOKEN', '')),
        }
    # Also inject git_token if present in header
    git_token = request.headers.get('X-Git-Token', '')
    if git_token:
        g.llm_config['git_token'] = git_token

# 注册 Blueprint
app.register_blueprint(meeting_todo_bp, url_prefix='/api/meeting-todo')
app.register_blueprint(iteration_stats_bp, url_prefix='/api/stats')
app.register_blueprint(ai_measure_bp, url_prefix='/api/ai-measure')
app.register_blueprint(chat_bp, url_prefix='/api/chat')
app.register_blueprint(kb_manage_bp, url_prefix='/api/kb-manage')
app.register_blueprint(code_analyze_bp, url_prefix='/api/code-analyze')
app.register_blueprint(prd_gen_bp)  # prd_gen_bp 自带 url_prefix=/api/prd
app.register_blueprint(auth_bp)  # auth_bp 自带 /api/auth/verify


@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "app": "AI 中控台",
        "version": "0.1.0",
    })


# ── 前端静态文件服务（生产环境，Docker 部署用）──
# 前端 dist 目录：项目根/frontend/dist（容器内 /app/frontend/dist）
_FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')


@app.route('/')
def serve_index():
    if os.path.exists(_FRONTEND_DIST):
        return send_from_directory(_FRONTEND_DIST, 'index.html')
    return jsonify({"error": "frontend not built"}), 404


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """Vite 构建产物，assets 目录下含 JS/CSS"""
    assets_dir = os.path.join(_FRONTEND_DIST, 'assets')
    if os.path.exists(assets_dir):
        return send_from_directory(assets_dir, filename)
    return jsonify({"error": "asset not found"}), 404


@app.route('/<path:path>')
def serve_spa(path):
    """SPA fallback：非 /api 路径回退到 index.html"""
    if path.startswith('api'):
        return jsonify({"error": "not found"}), 404
    full_path = os.path.join(_FRONTEND_DIST, path)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_from_directory(_FRONTEND_DIST, path)
    # SPA fallback
    if os.path.exists(_FRONTEND_DIST):
        return send_from_directory(_FRONTEND_DIST, 'index.html')
    return jsonify({"error": "frontend not built"}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)