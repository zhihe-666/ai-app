"""
飞书操作封装 — 通过 lark-cli subprocess 调用飞书 REST API

所有飞书操作（妙记、文档、搜索）集中在这一层。
调用方不需要关心 token 管理和 API 细节。

方案：使用 subprocess.run(['lark-cli', 'api', ...]) 代理所有飞书 Open API 请求。
lark-cli 自动管理 token 继承 keychain 权限，无需手动处理 Device Code Flow。
"""
import json
import logging
import os
import re
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

# lark-cli bot 配置目录（确保子进程继承正确身份）
_LARK_CONFIG_DIR = "/Users/admin/.dewuclaw/lark-cli-config/cli_aa847daba1bc1bb3"


class LarkCliError(Exception):
    """飞书 API 调用异常"""
    pass


def _fmt_ratio(v):
    """格式化占比字段：支持数值（int/float）和字符串（已带 %）"""
    if isinstance(v, (int, float)):
        return f"{v:.2f}%"
    return str(v) if v else "0%"


def _lark_env() -> dict:
    """返回注入 LARKSUITE_CLI_CONFIG_DIR 的环境变量副本"""
    env = os.environ.copy()
    env["LARKSUITE_CLI_CONFIG_DIR"] = _LARK_CONFIG_DIR
    return env


# ── 底层调用 ──


def _lark_api(method: str, path: str, body: Optional[dict] = None,
              timeout: int = 60, as_user: bool = True) -> dict:
    """调用 lark-cli api 命令代理飞书 REST API

    Args:
        method: HTTP 方法（GET/POST/PATCH/DELETE）
        path: API 路径，如 /open-apis/minutes/v1/minutes/{token}
        body: 请求体 dict（可选，用于 POST/PATCH）
        timeout: 超时秒数
        as_user: 是否以用户身份调用（True=user, False=bot）

    Returns:
        解析后的 JSON dict（标准飞书 Open API 响应格式）

    Raises:
        LarkCliError: 调用失败时抛出
    """
    cmd = ['lark-cli', 'api', method, path, '--format', 'json']
    if not as_user:
        cmd.extend(['--as', 'bot'])

    stdin_data = None
    if body is not None:
        stdin_data = json.dumps(body, ensure_ascii=False)

    try:
        result = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_lark_env(),
        )
    except subprocess.TimeoutExpired:
        raise LarkCliError(f"飞书 API 调用超时（{timeout}s）: {method} {path}")
    except FileNotFoundError:
        raise LarkCliError("未找到 lark-cli 命令，请确认已安装并配置")

    if result.returncode != 0:
        err_msg = result.stderr[:500] if result.stderr else "未知错误"
        # 尝试解析结构化错误
        try:
            err_data = json.loads(result.stderr)
            err_detail = err_data.get('error', {})
            msg = err_detail.get('message', err_msg)
            code = err_detail.get('code', '')
            raise LarkCliError(f"飞书 API 错误 [{code}]: {msg}")
        except json.JSONDecodeError:
            raise LarkCliError(f"lark-cli 调用失败: {err_msg}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise LarkCliError(f"解析飞书 API 响应失败: {e}")


def _lark_api_get(path: str, **kwargs) -> dict:
    """GET 请求简写"""
    return _lark_api('GET', path, **kwargs)


def _lark_api_post(path: str, body: Optional[dict] = None, **kwargs) -> dict:
    """POST 请求简写"""
    return _lark_api('POST', path, body=body, **kwargs)


# ── 妙记 ──


def get_minute_info(minute_token: str) -> dict:
    """获取妙记基础信息

    GET /open-apis/minutes/v1/minutes/{minute_token}

    Args:
        minute_token: 妙记 token

    Returns:
        完整响应 dict（含 code/msg/data），与旧版兼容
    """
    path = f'/open-apis/minutes/v1/minutes/{minute_token}'
    return _lark_api_get(path)


def get_transcript(minute_token: str) -> str:
    """获取妙记逐字稿内容

    GET /open-apis/minutes/v1/minutes/{minute_token}/transcript

    lark-cli 将 text/plain 响应保存到本地文件，我们读取后返回字符串。

    Args:
        minute_token: 妙记 token

    Returns:
        逐字稿文本内容
    """
    import tempfile
    import os

    path = f'/open-apis/minutes/v1/minutes/{minute_token}/transcript'

    # lark-cli --output 只接受相对路径，cd 到临时目录再执行
    tmpdir = tempfile.mkdtemp()
    tmp_filename = f'_transcript_{minute_token}.txt'
    tmp_path = os.path.join(tmpdir, tmp_filename)

    cmd = ['lark-cli', 'api', 'GET', path, '--format', 'json',
           '--output', tmp_filename]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60,
            cwd=tmpdir, env=_lark_env(),
        )
        if result.returncode != 0:
            raise LarkCliError(f"获取逐字稿失败: {result.stderr[:500]}")

        # 读取保存的逐字稿文件
        with open(tmp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except subprocess.TimeoutExpired:
        raise LarkCliError("获取逐字稿超时")
    except FileNotFoundError:
        raise LarkCliError("未找到 lark-cli 命令")
    except LarkCliError:
        raise
    except Exception as e:
        raise LarkCliError(f"逐字稿读取失败: {e}")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def fetch_doc_markdown(doc_token: str) -> str:
    """获取飞书文档的原始内容

    GET /open-apis/docx/v1/documents/{doc_token}/raw_content

    Args:
        doc_token: 文档 token（如逐字稿文档）

    Returns:
        文档内容（字符串）
    """
    path = f'/open-apis/docx/v1/documents/{doc_token}/raw_content'
    data = _lark_api_get(path)
    content = data.get('data', {}).get('content', '')
    return content


def search_minutes(keyword: str, start_time: str = "",
                   end_time: str = "") -> list:
    """搜索妙记

    GET /open-apis/minutes/v1/minutes?query={keyword}&...

    Args:
        keyword: 搜索关键词
        start_time: 开始时间（可选，unix 时间戳 ms）
        end_time: 结束时间（可选）

    Returns:
        搜索结果列表（items 数组）
    """
    path = f'/open-apis/minutes/v1/minutes?query={keyword}'
    if start_time:
        path += f'&start_time={start_time}'
    if end_time:
        path += f'&end_time={end_time}'
    data = _lark_api_get(path)
    return data.get('data', {}).get('items', [])


# ── 文档创建 ──


def create_doc_xml(title: str, content_xml: str) -> str:
    """创建飞书文档（DocxXML 格式，支持表格）

    使用 lark-cli docs +create --api-version v2 --content @file.xml 创建文档。
    返回文档 URL。

    Args:
        title: 文档标题（备用，实际标题在 content_xml 的 <title> 中）
        content_xml: XML 格式的完整文档内容（含 <title> 标签）

    Returns:
        文档 URL
    """
    import tempfile
    import os

    # 将 XML 写入 CWD 下的临时文件（lark-cli 要求 --content @path 是相对路径）
    tmp_filename = f'_doc_content_{int(time.time()*1000)}.xml'
    tmp_filepath = os.path.join(os.getcwd(), tmp_filename)

    try:
        with open(tmp_filepath, 'w', encoding='utf-8') as f:
            f.write(content_xml)

        cmd = [
            'lark-cli', 'docs', '+create',
            '--api-version', 'v2',
            '--content', f'@{tmp_filename}',
            '--format', 'json',
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=30,
                env=_lark_env(),
            )
        except subprocess.TimeoutExpired:
            raise LarkCliError("创建飞书文档超时")
        except FileNotFoundError:
            raise LarkCliError("未找到 lark-cli 命令")

        if result.returncode != 0:
            err = result.stderr[:500] if result.stderr else "未知错误"
            raise LarkCliError(f"创建飞书文档失败: {err}")

        try:
            resp = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise LarkCliError(f"解析创建文档响应失败: {result.stdout[:200]}")

        # 解析文档信息
        data = resp.get('data', resp)
        doc = data.get('document', {})
        doc_token = doc.get('document_id', '')
        doc_url = doc.get('url', f"https://poizon.feishu.cn/docx/{doc_token}")

        logger.info(f"✅ 飞书文档已创建: {doc_url}")
        return doc_url
    finally:
        # 清理临时文件
        if os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)


# ── 多维表格 (Bitable) ──


def get_bitable_records(base_token: str, table_id: str) -> list:
    """获取多维表格所有记录（含 record_id 和字段值）

    使用 lark-cli base +record-list 获取记录列表。

    Args:
        base_token: Base Token
        table_id: 数据表 ID

    Returns:
        list of dict: [{
            "record_id": "recXXXXXX",
            "fields": { "项目名称": "...", "TL": "...", ... }
        }, ...]
    """
    cmd = [
        "lark-cli", "base", "+record-list",
        "--base-token", base_token,
        "--table-id", table_id,
        "--format", "json",
        "--limit", "200",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            env=_lark_env(),
        )
        if result.returncode != 0:
            raise LarkCliError(f"获取记录列表失败: {result.stderr[:500]}")

        resp = json.loads(result.stdout)
        data = resp.get("data", {})
        records = []
        field_names = data.get("fields", [])
        record_ids = data.get("record_id_list", [])
        values = data.get("data", [])

        for i, row in enumerate(values):
            if row is None or all(v is None for v in row if v is not None):
                continue
            record_id = record_ids[i] if i < len(record_ids) else ""
            fields = {}
            for j, field_name in enumerate(field_names):
                if j < len(row) and row[j] is not None:
                    fields[field_name] = row[j]
            records.append({"record_id": record_id, "fields": fields})

        return records
    except subprocess.TimeoutExpired:
        raise LarkCliError("获取记录列表超时")
    except FileNotFoundError:
        raise LarkCliError("未找到 lark-cli 命令")


def update_bitable_record(base_token: str, table_id: str,
                           record_id: str, stats: dict) -> dict:
    """更新多维表格单条记录的统计数字字段

    使用 lark-cli base +record-upsert 命令。

    只更新数字统计字段（项目名称和TL保持不动）：
        - 总需求数【完全排期】
        - 算法工程需求
        - AIcoding需求数
        - SDD需求数
        - 端到端需求数
        - AICoding需求占比  (text, e.g. "68.57%")
        - SDD需求占比       (text, e.g. "50.00%")

    Args:
        base_token: Base Token
        table_id: 数据表 ID
        record_id: 记录 ID
        stats: 统计数据 dict

    Returns:
        {"success": True} 或 抛出异常
    """
    update_data = {
        "总需求数【完全排期】": stats.get("total", 0),
        "算法工程需求": stats.get("engineering", 0),
        "AIcoding需求数": stats.get("aicoding", 0),
        "SDD需求数": stats.get("sdd", 0),
        "端到端需求数": stats.get("e2e", 0),
        "AICoding需求占比": _fmt_ratio(stats.get("aicoding_ratio", 0)),
        "SDD需求占比": _fmt_ratio(stats.get("sdd_ratio", 0)),
    }

    json_str = json.dumps(update_data, ensure_ascii=False)

    cmd = [
        "lark-cli", "base", "+record-upsert",
        "--base-token", base_token,
        "--table-id", table_id,
        "--record-id", record_id,
        "--json", json_str,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            env=_lark_env(),
        )
        if result.returncode != 0:
            raise LarkCliError(f"更新记录失败: {result.stderr[:500]}")
        return {"success": True}
    except subprocess.TimeoutExpired:
        raise LarkCliError("更新记录超时")
    except FileNotFoundError:
        raise LarkCliError("未找到 lark-cli 命令")


def batch_update_bitable(base_token: str, table_id: str,
                          records_data: list) -> dict:
    """批量更新多维表格

    Args:
        base_token: Base Token
        table_id: 数据表 ID
        records_data: list of {"record_id": str, "stats": dict}

    Returns:
        {"success": bool, "updated": int, "errors": list}
    """
    updated = 0
    errors = []
    for item in records_data:
        try:
            update_bitable_record(
                base_token, table_id,
                item["record_id"], item["stats"],
            )
            updated += 1
        except Exception as e:
            errors.append({"record_id": item.get("record_id"), "error": str(e)})

    return {
        "success": len(errors) == 0,
        "updated": updated,
        "errors": errors,
    }


def create_bitable_record(base_token: str, table_id: str, stats: dict) -> dict:
    """在多维表格中新建一条记录（用于自动创建"合计"行）

    使用 lark-cli base +record-batch-create 命令。

    Args:
        base_token: Base Token
        table_id: 数据表 ID
        stats: 统计数据 dict（字段格式与 update_bitable_record 一致）

    Returns:
        {"success": True, "record_id": str}
    """
    # aicoding_ratio / sdd_ratio 可能是数值或带 "%" 的字符串
    # 去掉了 local _fmt_ratio (已提升到模块级别)
    fields = [
        "项目名称",
        "TL",
        "总需求数【完全排期】",
        "算法工程需求",
        "AIcoding需求数",
        "SDD需求数",
        "端到端需求数",
        "AICoding需求占比",
        "SDD需求占比",
    ]

    row = [
        stats.get("project_name", "合计"),
        stats.get("tl", ""),
        stats.get("total", 0),
        stats.get("engineering", 0),
        stats.get("aicoding", 0),
        stats.get("sdd", 0),
        stats.get("e2e", 0),
        _fmt_ratio(stats.get("aicoding_ratio", "")),
        _fmt_ratio(stats.get("sdd_ratio", "")),
    ]

    payload = {"fields": fields, "rows": [row]}
    json_str = json.dumps(payload, ensure_ascii=False)

    cmd = [
        "lark-cli", "base", "+record-batch-create",
        "--base-token", base_token,
        "--table-id", table_id,
        "--json", json_str,
        "--as", "user",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            env=_lark_env(),
        )
        if result.returncode != 0:
            raise LarkCliError(f"创建记录失败: {result.stderr[:500]}")
        resp = json.loads(result.stdout)
        records = resp.get("data", {}).get("records", [])
        record_id = records[0].get("record_id", "") if records else ""
        return {"success": True, "record_id": record_id}
    except subprocess.TimeoutExpired:
        raise LarkCliError("创建记录超时")
    except FileNotFoundError:
        raise LarkCliError("未找到 lark-cli 命令")


def search_user_by_name(name: str) -> dict | None:
    """通过姓名搜索飞书用户，返回 {open_id, name}

    lark-cli contact +search-user --query '{name}' --page-size 5 --as user

    Args:
        name: 用户姓名（支持中文名/英文名/花名）

    Returns:
        {'open_id': str, 'name': str} 或 None（未找到）
    """
    cmd = [
        'lark-cli', 'contact', '+search-user',
        '--query', name,
        '--page-size', '5',
        '--format', 'json',
        '--as', 'user',
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=15,
            env=_lark_env(),
        )
        if result.returncode != 0:
            return None
        resp = json.loads(result.stdout)
        # 新版本 +search-user 返回 data.users，不是 data.items
        users = resp.get('data', {}).get('users', [])
        if not users:
            return None
        # 取第一个匹配结果
        user = users[0]
        return {
            'open_id': user.get('open_id', ''),
            'name': user.get('localized_name', '') or user.get('name', '') or user.get('nickname', ''),
        }
    except Exception:
        return None