"""
知识库管理 router — 代理到无矩2.0 FastAPI 微服务管理 API

所有接口代理到 http://localhost:8000/api/admin/*，统一响应格式：
    {"status": "success"|"error", "data": {...}, "error": "..."}
"""
import json
import logging
import os
from urllib.parse import quote

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


def _proxy_put(path: str, json_body: dict = None, timeout: int = _DEFAULT_TIMEOUT):
    """通用 PUT 代理"""
    try:
        resp = requests.put(f"{ADMIN_BASE}{path}", json=json_body, timeout=timeout)
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
    """导入文本内容到知识库

    对齐 T025 文档 4.5：POST /api/admin/import
    请求体可指定 collection（默认 manual_kb），metadata 可含 doc_type 等字段。
    注意：code_frontend 等系统 collection 不可手动导入（由同步流程维护）。
    """
    body = request.get_json(silent=True) or {}
    content = body.get("content", "")
    title = body.get("title", "")
    if not content or not title:
        return jsonify({"status": "error", "data": None, "error": "缺少 content 或 title 参数"}), 400

    payload = {
        "content": content,
        "title": title,
        "collection": body.get("collection", "manual_kb"),
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


# ── 9. 触发代码同步（3 模式）──────────────────────────────────────

@kb_manage_bp.route("/sync", methods=["POST"])
def trigger_sync():
    """触发知识库同步（T025 3 模式）

    Query 参数:
        mode (str): 同步模式 backend/frontend/full，默认 backend
        dry_run (bool): true=仅显示 diff 不写入（仅 backend 生效），默认 true

    非 dry_run 模式同步前自动创建快照，可用 GET /api/admin/snapshots 查看。
    """
    mode = request.args.get("mode", "backend")
    dry_run = request.args.get("dry_run", "true")
    # 仅 backend 模式支持 dry_run
    if mode == "backend":
        query = f"/sync?mode={mode}&dry_run={dry_run}"
    else:
        # frontend/full 不走 dry_run，直接真实同步
        query = f"/sync?mode={mode}"
    result = _proxy_post(query)
    return jsonify(result)


# ── 10. 轮询同步状态 ──────────────────────────────────────────────


@kb_manage_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """查看同步任务状态

    result_summary 含快照 ID（snapshot: xxx），可用于回退。
    """
    task_id = request.args.get("task_id", "")
    if not task_id:
        return jsonify({"status": "error", "data": None, "error": "缺少 task_id 参数"}), 400

    result = _proxy_get(f"/sync/status/{task_id}")
    return jsonify(result)


# ── 11. KB 快照与回退（T025 新增）──────────────────────────────────


@kb_manage_bp.route("/snapshots", methods=["POST"])
def create_snapshot():
    """手动创建 KB 快照（Chroma 9 collection + SQLite 5 表）

    Query 参数:
        reason (str): 创建原因，默认 manual
    """
    reason = request.args.get("reason", "manual")
    result = _proxy_post(f"/snapshots?reason={reason}")
    return jsonify(result)


@kb_manage_bp.route("/snapshots", methods=["GET"])
def list_snapshots():
    """列出所有快照（按时间倒序）"""
    result = _proxy_get("/snapshots")
    return jsonify(result)


@kb_manage_bp.route("/snapshots/<snapshot_id>", methods=["GET"])
def get_snapshot_detail(snapshot_id: str):
    """查看指定快照详情（含各 collection/表计数）"""
    result = _proxy_get(f"/snapshots/{snapshot_id}")
    return jsonify(result)


@kb_manage_bp.route("/rollback", methods=["POST"])
def rollback_snapshot():
    """一键回退到指定快照（危险操作）

    Query 参数:
        snapshot_id (str): 目标快照 ID
    """
    snapshot_id = request.args.get("snapshot_id", "")
    if not snapshot_id:
        return jsonify({"status": "error", "data": None, "error": "缺少 snapshot_id 参数"}), 400
    result = _proxy_post(f"/rollback?snapshot_id={snapshot_id}")
    return jsonify(result)


@kb_manage_bp.route("/snapshots/<snapshot_id>", methods=["DELETE"])
def delete_snapshot(snapshot_id: str):
    """删除指定快照"""
    result = _proxy_delete(f"/snapshots/{snapshot_id}")
    return jsonify(result)


# ── 12. 图谱查询（深度模式 Agent 2 数据源，KB_DEEP_MODE_PLAN Part A）──


@kb_manage_bp.route("/modules", methods=["GET"])
def list_platform_modules():
    """12 个业务模块清单 + 各模块节点计数（架构快照索引）

    供 PRD 深度模式 Agent 2 匹配功能关键词到平台模块。
    """
    result = _proxy_get("/modules")
    return jsonify(result)


@kb_manage_bp.route("/modules/<module_name>", methods=["GET"])
def get_platform_module(module_name: str):
    """单模块架构快照（controllers / apis / frontend_pages / external_deps）

    路径参数支持中文模块名（如「集群配置管理」），自动 URL 编码。
    """
    encoded = quote(module_name, safe="")
    result = _proxy_get(f"/modules/{encoded}")
    return jsonify(result)


@kb_manage_bp.route("/graph/impact", methods=["GET"])
def graph_impact():
    """定向影响范围分析（KB_DEEP_MODE_PLAN A1）

    Query 参数:
        node (str): 节点名称（模糊匹配，多候选返回全部）或 node_id（精确）
        direction (str): in/incoming=谁依赖我（改我谁受影响）；
                        out/outgoing=我改波及谁。默认 outgoing
        depth (int): BFS 深度上限，默认 5，最大 10
    """
    node = request.args.get("node", "")
    if not node:
        return jsonify({"status": "error", "data": None, "error": "缺少 node 参数"}), 400

    params = {
        "node": node,
        "direction": request.args.get("direction", "outgoing"),
        "depth": request.args.get("depth", 5, type=int),
    }
    result = _proxy_get("/graph/impact", params=params)
    return jsonify(result)


@kb_manage_bp.route("/graph/flow", methods=["GET"])
def graph_flow():
    """API 完整调用链（frontend_service → Controller → Service → Executor）

    Query 参数:
        api (str): API 入口节点名称或 node_id
    """
    api = request.args.get("api", "")
    if not api:
        return jsonify({"status": "error", "data": None, "error": "缺少 api 参数"}), 400

    result = _proxy_get("/graph/flow", params={"api": api})
    return jsonify(result)


@kb_manage_bp.route("/graph/node/<node_id>", methods=["GET"])
def graph_node_detail(node_id: str):
    """单个图谱节点详情（name / type / module / source_file）"""
    encoded = quote(node_id, safe="")
    result = _proxy_get(f"/graph/node/{encoded}")
    return jsonify(result)


# ── 13. 历史 PRD 管理（API_PRD.md）──


@kb_manage_bp.route("/prds", methods=["GET"])
def list_prds():
    """PRD 列表（分页 + 关键词 + 状态筛选）

    Query 参数: page, page_size, keyword, status
    """
    params = {
        "page": request.args.get("page", 1, type=int),
        "page_size": request.args.get("page_size", 20, type=int),
        "keyword": request.args.get("keyword", ""),
        "status": request.args.get("status", ""),
    }
    result = _proxy_get("/prds", params=params)
    return jsonify(result)


@kb_manage_bp.route("/prds", methods=["POST"])
def create_prd():
    """创建历史 PRD（入库 SQLite + 向量化 Chroma）"""
    body = request.get_json(silent=True) or {}
    title = body.get("title", "")
    if not title:
        return jsonify({"status": "error", "data": None, "error": "缺少 title 参数"}), 400
    result = _proxy_post("/prds", json_body=body)
    return jsonify(result)


@kb_manage_bp.route("/prds/<prd_id>", methods=["GET"])
def get_prd_detail(prd_id: str):
    """PRD 详情（含全文 content）"""
    result = _proxy_get(f"/prds/{prd_id}")
    return jsonify(result)


@kb_manage_bp.route("/prds/<prd_id>", methods=["PUT"])
def update_prd(prd_id: str):
    """更新 PRD（SQLite + Chroma 同步更新）"""
    body = request.get_json(silent=True) or {}
    result = _proxy_put(f"/prds/{prd_id}", json_body=body)
    return jsonify(result)


@kb_manage_bp.route("/prds/<prd_id>", methods=["DELETE"])
def delete_prd(prd_id: str):
    """删除 PRD（同步删 SQLite + Chroma 向量）"""
    result = _proxy_delete(f"/prds/{prd_id}")
    return jsonify(result)


@kb_manage_bp.route("/prds/search", methods=["POST"])
def search_prds():
    """语义搜索 PRD（基于 title+summary 向量匹配）"""
    query = request.args.get("query", "")
    top_k = request.args.get("top_k", 5, type=int)
    if not query:
        return jsonify({"status": "error", "data": None, "error": "缺少 query 参数"}), 400
    result = _proxy_post(f"/prds/search?query={quote(query)}&top_k={top_k}")
    return jsonify(result)


@kb_manage_bp.route("/design-layouts", methods=["GET"])
def get_design_layouts():
    """页面布局注册表（22 页，含页面类型/布局组件/浮层标记）"""
    result = _proxy_get("/design-layouts")
    return jsonify(result)


# ── 14. 组件注册表（API_PRD.md，代理微服务）──


@kb_manage_bp.route("/components/registry", methods=["GET"])
def get_component_registry():
    """组件注册表（606 组件，含 props/子组件/使用页面/复用度）

    代理到微服务 /api/admin/component-registry（API_PRD.md）。
    降级：微服务挂 → 503。
    """
    result = _proxy_get("/component-registry")
    return jsonify(result)