from flask import Flask, jsonify, g, request
from flask_cors import CORS
from routers.meeting_todo import meeting_todo_bp
from routers.iteration_stats import iteration_stats_bp
from routers.ai_measure import ai_measure_bp
from routers.chat import chat_bp
from routers.kb_manage import kb_manage_bp
from routers.code_analyze import code_analyze_bp
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

    优先从请求头/body读取（前端传入），兜底从数据库读取已保存配置。
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
app.register_blueprint(auth_bp)  # auth_bp 自带 /api/auth/verify


@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "app": "AI 中控台",
        "version": "0.1.0",
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)