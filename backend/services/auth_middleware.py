"""
全局 LLM 配置管理 — 后端中间件 + 验证接口

前端每次请求携带三个请求头：
- X-Api-Key:    API Key（必填）
- X-Base-Url:   Base URL（可选，有默认值）
- X-Model:      Model 名称（可选，有默认值）

后端 LLMClient 从请求头读取这些参数，不依赖环境变量。
"""

from flask import request, g, jsonify, Blueprint
import os
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from services.db import init_db, get_user_config, save_user_config, get_repo_cache, save_repo_cache

auth_bp = Blueprint('auth', __name__)

# 常见 LLM Provider 预设
PROVIDER_PRESETS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
    },
    "siliconflow": {
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1"],
    },
}


def get_llm_config() -> dict:
    """从当前请求中提取 LLM 三件套

    Returns:
        dict: {"api_key": str, "base_url": str, "model": str}
    """
    config = {
        "api_key": request.headers.get('X-Api-Key', ''),
        "base_url": request.headers.get('X-Base-Url', 'https://api.openai.com/v1'),
        "model": request.headers.get('X-Model', 'gpt-4o'),
    }
    # 如果请求体也有，优先用请求体覆盖（用于验证接口）
    if request.is_json:
        body = request.get_json(silent=True) or {}
        config["api_key"] = body.get("api_key") or config["api_key"]
        config["base_url"] = body.get("base_url") or config["base_url"]
        config["model"] = body.get("model") or config["model"]

    g.llm_config = config
    return config


@auth_bp.route('/api/auth/presets', methods=['GET'])
def get_presets():
    """返回 LLM Provider 预设列表，供前端下拉选择"""
    return jsonify({"presets": PROVIDER_PRESETS})


@auth_bp.route('/api/auth/verify', methods=['POST'])
def verify_config():
    """验证 LLM 配置是否可用

    用提供的 API Key + Base URL 调一次模型列表接口来验证。
    """
    config = get_llm_config()

    if not config["api_key"]:
        return jsonify({"valid": False, "message": "API Key 为空"})

    if OpenAI is None:
        return jsonify({"valid": True, "message": "openai 库未安装，跳过验证"})

    try:
        client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        client.models.list()
        return jsonify({
            "valid": True,
            "message": f"配置有效 · {config['model']} · {config['base_url']}",
            "config": config,
        })
    except Exception as e:
        return jsonify({"valid": False, "message": f"验证失败: {str(e)[:200]}"})


@auth_bp.route('/api/auth/config', methods=['GET'])
def get_config():
    """获取已保存的 LLM 配置 + Git Token"""
    saved = get_user_config()
    if saved:
        return jsonify({
            "configured": True,
            "provider_name": saved.get("provider_name", ""),
            "base_url": saved.get("base_url", ""),
            "model": saved.get("model", ""),
            "api_key": saved.get("api_key", ""),
            "git_token": saved.get("git_token", ""),
        })
    return jsonify({"configured": False})


@auth_bp.route('/api/auth/config', methods=['POST'])
def save_config():
    """保存 LLM 配置 + Git Token 到数据库"""
    body = request.get_json(silent=True) or {}
    provider_name = body.get("provider_name", "")
    api_key = body.get("api_key", "")
    base_url = body.get("base_url", "")
    model = body.get("model", "")
    git_token = body.get("git_token", "")

    if not api_key:
        return jsonify({"error": "API Key 为空"}), 400

    saved = save_user_config(provider_name, api_key, base_url, model, git_token)
    return jsonify({
        "saved": True,
        "provider_name": saved["provider_name"],
        "base_url": saved["base_url"],
        "model": saved["model"],
        "git_token": saved["git_token"],
    })


# ── 仓库配置缓存 ──


@auth_bp.route('/api/auth/repo-cache', methods=['GET'])
def get_repo_cache_endpoint():
    """获取指定仓库的缓存配置"""
    repo_url = request.args.get('repo_url', '')
    if not repo_url:
        return jsonify({"cached": False}), 200
    cached = get_repo_cache(repo_url)
    if cached:
        return jsonify({"cached": True, "repo_url": cached["repo_url"], "branch": cached["branch"], "frontend_paths": cached.get("frontend_paths", [])})
    return jsonify({"cached": False})


@auth_bp.route('/api/auth/repo-cache', methods=['POST'])
def save_repo_cache_endpoint():
    """保存仓库配置到缓存"""
    body = request.get_json(silent=True) or {}
    repo_url = body.get("repo_url", "")
    branch = body.get("branch", "master")
    frontend_paths = body.get("frontend_paths", [])
    if not repo_url:
        return jsonify({"error": "repo_url 为空"}), 400
    save_repo_cache(repo_url, branch, frontend_paths)
    return jsonify({"saved": True, "repo_url": repo_url, "branch": branch})