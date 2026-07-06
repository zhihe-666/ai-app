"""
知识库管理 router — 代理到无矩2.0 FastAPI 微服务管理 API

所有接口代理到 http://localhost:8000/api/admin/*，统一响应格式：
    {"status": "success"|"error", "data": {...}, "error": "..."}
"""
import json
import logging

import requests
from flask import Blueprint, Response, request, jsonify

logger = logging.getLogger(__name__)

kb_manage_bp = Blueprint("kb_manage", __name__)

# 无矩2.0 管理 API 基地址
ADMIN_BASE = "http://localhost:8000/api/admin"
# 通用请求超时（非 SSE 接口，30s 足够）
_DEFAULT_TIMEOUT = 30


def _proxy_get(path: str, params: dict = None, timeout: int = _DEFAULT_TIMEOUT):
    """通用 GET 代理"""
    try:
        resp = requests.get(f"{ADMIN_BASE}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"status": "error", "data": None, "error": "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"}
    except requests.exceptions.Timeout:
        return {"status": "error", "data": None, "error": f"知识库服务响应超时（>{timeout}s）。"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "data": None, "error": f"请求失败: {str(e)}"}


def _proxy_post(path: str, json_body: dict = None, timeout: int = _DEFAULT_TIMEOUT):
    """通用 POST 代理"""
    try:
        resp = requests.post(f"{ADMIN_BASE}{path}", json=json_body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"status": "error", "data": None, "error": "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"}
    except requests.exceptions.Timeout:
        return {"status": "error", "data": None, "error": f"知识库服务响应超时（>{timeout}s）。"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "data": None, "error": f"请求失败: {str(e)}"}


def _proxy_delete(path: str, json_body: dict = None, timeout: int = _DEFAULT_TIMEOUT):
    """通用 DELETE 代理"""
    try:
        resp = requests.delete(f"{ADMIN_BASE}{path}", json=json_body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"status": "error", "data": None, "error": "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"}
    except requests.exceptions.Timeout:
        return {"status": "error", "data": None, "error": f"知识库服务响应超时（>{timeout}s）。"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "data": None, "error": f"请求失败: {str(e)}"}


def _proxy_files(path: str, files: dict, data: dict, timeout: int = _DEFAULT_TIMEOUT):
    """通用文件上传代理"""
    try:
        resp = requests.post(f"{ADMIN_BASE}{path}", files=files, data=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"status": "error", "data": None, "error": "无法连接到知识库服务（localhost:8000），请确认无矩2.0 已启动。"}
    except requests.exceptions.Timeout:
        return {"status": "error", "data": None, "error": f"知识库服务响应超时（>{timeout}s）。"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "data": None, "error": f"请求失败: {str(e)}"}


# ── 1. 知识库概览 ──────────────────────────────────────────────


@kb_manage_bp.route("/collections", methods=["GET"])
def get_collections():
    """查看所有 collection 的文档数、类型和同步状态"""
    result = _proxy_get("/collections")
    return jsonify(result)


# ── 2. 浏览集合内容 ─────────────────────────────────────────────


@kb_manage_bp.route("/browse", methods=["GET"])
def browse_collection():
    """分页浏览指定 collection 的文档列表"""
    collection = request.args.get("collection", "")
    if not collection:
        return jsonify({"status": "error", "data": None, "error": "缺少 collection 参数"}), 400

    params = {
        "page": request.args.get("page", 1, type=int),
        "page_size": request.args.get("page_size", 20, type=int),
        "keyword": request.args.get("keyword", ""),
    }
    result = _proxy_get(f"/{collection}/browse", params=params)
    return jsonify(result)


# ── 3. 查看单条文档全文 ─────────────────────────────────────────


@kb_manage_bp.route("/doc", methods=["GET"])
def get_document():
    """查看单条文档全文"""
    collection = request.args.get("collection", "")
    doc_id = request.args.get("doc_id", "")
    if not collection or not doc_id:
        return jsonify({"status": "error", "data": None, "error": "缺少 collection 或 doc_id 参数"}), 400

    result = _proxy_get(f"/{collection}/doc/{doc_id}")
    return jsonify(result)


# ── 4. SQLite 数据库/表结构 ──────────────────────────────────────


@kb_manage_bp.route("/sqlite/tables", methods=["GET"])
def get_sqlite_tables():
    """列出所有 SQLite 数据库和表"""
    result = _proxy_get("/sqlite/tables")
    return jsonify(result)


@kb_manage_bp.route("/sqlite/table", methods=["GET"])
def get_sqlite_table():
    """查看指定 SQLite 表的内容"""
    db_name = request.args.get("db_name", "")
    table_name = request.args.get("table_name", "")
    if not db_name or not table_name:
        return jsonify({"status": "error", "data": None, "error": "缺少 db_name 或 table_name 参数"}), 400

    params = {
        "page": request.args.get("page", 1, type=int),
        "page_size": request.args.get("page_size", 20, type=int),
    }
    result = _proxy_get(f"/sqlite/{db_name}/{table_name}", params=params)
    return jsonify(result)


# ── 6. 导入文档（文本）─────────────────────────────────────────────


@kb_manage_bp.route("/import", methods=["POST"])
def import_text():
    """导入文本内容到 manual_kb"""
    body = request.get_json(silent=True) or {}
    content = body.get("content", "")
    title = body.get("title", "")
    if not content or not title:
        return jsonify({"status": "error", "data": None, "error": "缺少 content 或 title 参数"}), 400

    payload = {
        "content": content,
        "title": title,
        "collection": "manual_kb",
    }
    if body.get("metadata"):
        payload["metadata"] = body["metadata"]

    result = _proxy_post("/import", json_body=payload)
    return jsonify(result)


# ── 7. 导入文档（文件上传）────────────────────────────────────────


@kb_manage_bp.route("/import/file", methods=["POST"])
def import_file():
    """上传文件导入 manual_kb"""
    if "file" not in request.files:
        return jsonify({"status": "error", "data": None, "error": "缺少 file 字段"}), 400

    file = request.files["file"]
    files = {"file": (file.filename, file.stream, file.content_type)}
    data = {}
    if request.form.get("title"):
        data["title"] = request.form["title"]
    if request.form.get("metadata"):
        data["metadata"] = request.form["metadata"]

    result = _proxy_files("/import/file", files=files, data=data)
    return jsonify(result)


# ── 8. 删除文档 ────────────────────────────────────────────────


@kb_manage_bp.route("/delete", methods=["DELETE"])
def delete_document():
    """删除指定文档"""
    body = request.get_json(silent=True) or {}
    collection = body.get("collection", "")
    doc_id = body.get("doc_id", "")
    if not collection or not doc_id:
        return jsonify({"status": "error", "data": None, "error": "缺少 collection 或 doc_id 参数"}), 400

    result = _proxy_delete(f"/{collection}/doc/{doc_id}")
    return jsonify(result)


# ── 9. 触发代码同步 ────────────────────────────────────────────────


@kb_manage_bp.route("/sync", methods=["POST"])
def trigger_sync():
    """触发后台代码同步

    Query 参数:
        dry_run (bool): true=预览差异, false=实际同步
        rebuild_core (bool): 是否重建核心KB（tech/ops/business）
        rebuild_wiki (bool): 是否重建 Wiki KB
    """
    dry_run = request.args.get("dry_run", "true")
    rebuild_core = request.args.get("rebuild_core", "false")
    rebuild_wiki = request.args.get("rebuild_wiki", "false")
    query = f"/sync?dry_run={dry_run}&rebuild_core={rebuild_core}&rebuild_wiki={rebuild_wiki}"
    result = _proxy_post(query)
    return jsonify(result)


# ── 10. 轮询同步状态 ──────────────────────────────────────────────


@kb_manage_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """查看同步任务状态"""
    task_id = request.args.get("task_id", "")
    if not task_id:
        return jsonify({"status": "error", "data": None, "error": "缺少 task_id 参数"}), 400

    result = _proxy_get(f"/sync/status/{task_id}")
    return jsonify(result)