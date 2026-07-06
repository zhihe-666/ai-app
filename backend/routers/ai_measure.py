"""
AI 编程数据报告 router

提供三个接口:
  POST /api/ai-measure/test-token     → 测试 Token 连通性
  POST /api/ai-measure/generate       → 流式生成报告（SSE）
  POST /api/ai-measure/write-to-feishu → 写入飞书文档
"""
import json
import logging
import re
import time
from threading import Timer

from flask import Blueprint, jsonify, request, Response

from services.report_generator import ReportGenerator, SECTION_CONFIGS, get_pilot_names, save_pilot_names, DEFAULT_PILOT_NAMES, get_tl_names, save_tl_names, DEFAULT_TL_NAMES
from services.sse_helpers import sse_event, sse_stream

logger = logging.getLogger(__name__)

ai_measure_bp = Blueprint('ai_measure', __name__)


@ai_measure_bp.route('/test-token', methods=['POST'])
def test_token():
    """测试 Token 连通性（不传 token 时使用内置默认 token）"""
    body = request.get_json(silent=True) or {}
    access_token = body.get('access_token', '') or None  # None → 用默认

    try:
        from services.ai_measure_client import AiMeasureClient
        client = AiMeasureClient(token=access_token)
        count = client.test_connection()
        return jsonify({"ok": True, "message": f"Token 有效，共找到 {count} 名成员"})
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "403" in error_msg or "Unauthorized" in error_msg:
            return jsonify({"ok": False, "message": "Token 无效或未授权"})
        return jsonify({"ok": False, "message": f"连接失败: {error_msg}"})


@ai_measure_bp.route('/pilot-names', methods=['GET'])
def get_pilot_names_route():
    """获取当前试点人员名单"""
    names = get_pilot_names()
    return jsonify({"names": names})


@ai_measure_bp.route('/pilot-names', methods=['POST'])
def save_pilot_names_route():
    """保存试点人员名单"""
    body = request.get_json(silent=True) or {}
    names = body.get('names', '')
    if not names:
        return jsonify({"ok": False, "message": "名单不能为空"}), 400
    save_pilot_names(names)
    return jsonify({"ok": True, "message": "试点人员名单已保存"})


@ai_measure_bp.route('/tl-names', methods=['GET'])
def get_tl_names_route():
    """获取当前 TL 名单"""
    names = get_tl_names()
    return jsonify({"names": names})


@ai_measure_bp.route('/tl-names', methods=['POST'])
def save_tl_names_route():
    """保存 TL 名单"""
    body = request.get_json(silent=True) or {}
    names = body.get('names', '')
    if not names:
        return jsonify({"ok": False, "message": "名单不能为空"}), 400
    save_tl_names(names)
    return jsonify({"ok": True, "message": "TL 名单已保存"})


@ai_measure_bp.route('/generate', methods=['POST'])
def generate_report():
    """配置参数 → 流式生成报告（SSE）"""
    body = request.get_json(silent=True) or {}
    access_token = body.get('access_token', '') or None  # None → 用默认
    pilot_names = body.get('pilot_names', '') or get_pilot_names()
    start_date = body.get('start_date', '')
    end_date = body.get('end_date', '')
    sections = body.get('sections', ['active_rate', 'inactive', 'skills', 'tl_usage'])

    if not start_date or not end_date:
        return jsonify({"error": "请选择时间范围"}), 400

    def generate():
        generator = ReportGenerator(token=access_token)
        report_parts = [
            f"# 算法平台 AI 编程周报（{start_date} ~ {end_date}）\n"
        ]
        sections_completed = 0

        for section_id, section_title, _, _ in SECTION_CONFIGS:
            if section_id not in sections:
                continue

            yield sse_event("progress", {
                "section": section_id,
                "status": "running",
                "message": f"正在查询「{section_title}」...",
            })

            try:
                data = generator.query_section(section_id, pilot_names, start_date, end_date)
                rows = data.get("rows", [])
                error = data.get("error")

                if error:
                    yield sse_event("section_error", {
                        "section": section_id,
                        "title": section_title,
                        "message": f"查询失败: {error}",
                    })
                    continue

                section_md = generator.format_section_markdown(section_id, section_title, data)
                report_parts.append(section_md)
                sections_completed += 1

                yield sse_event("section_complete", {
                    "section": section_id,
                    "title": section_title,
                    "row_count": len(rows),
                    "rows": rows,
                    "markdown": section_md,
                })
            except Exception as e:
                logger.error(f"查询 section {section_id} 异常: {e}")
                yield sse_event("section_error", {
                    "section": section_id,
                    "title": section_title,
                    "message": f"查询异常: {str(e)}",
                })
                continue

        full_report = "\n\n".join(report_parts)
        yield sse_event("complete", {
            "report_markdown": full_report,
            "sections_completed": sections_completed,
            "total_sections": len([s for s in sections if s in [c[0] for c in SECTION_CONFIGS]]),
        })

    return sse_stream(generate)


@ai_measure_bp.route('/write-to-feishu', methods=['POST'])
def write_to_feishu():
    """将报告写入飞书文档（DocxXML 格式，支持表格）"""
    body = request.get_json(silent=True) or {}
    title = body.get('title', 'AI 编程周报')
    content_md = body.get('content', '')

    if not content_md:
        return jsonify({"error": "报告内容为空"}), 400

    try:
        from services.feishu_client import create_doc_xml

        # 将 Markdown 转换为 lark-doc XML（标准 HTML 标签子集）
        xml_body = _md_to_docx_xml(title, content_md)
        doc_key = create_doc_xml(xml_body)

        return jsonify({
            "ok": True,
            "doc_key": doc_key,
            "url": f"https://poizon.feishu.cn/docx/{doc_key}",
        })
    except Exception as e:
        logger.error(f"写入飞书文档失败: {e}")
        return jsonify({"error": f"写入失败: {str(e)}"}), 500


# ── Markdown → lark-doc XML 转换 ──────────────────────────────

def _is_table_separator(line: str) -> bool:
    """检测 Markdown 表格分隔行，如 '|---|---|---|' 或 '| :--- | :--- |'"""
    stripped = line.replace("|", "").replace(" ", "").replace("-", "").replace(":", "")
    return stripped == "" and "|" in line


def _md_link_to_html(text: str) -> str:
    """将 Markdown 链接 [text](url) 转为 HTML <a href='url'>text</a>"""
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)


def _cell_md_to_html(text: str) -> str:
    """转换单元格内容中的 Markdown 链接"""
    text = text.strip()
    return _md_link_to_html(text)


def _md_to_docx_xml(title: str, content: str) -> str:
    """将 Markdown 内容转换为 lark-doc XML 格式（标准 HTML 标签子集）"""
    lines = content.split("\n")
    parts = [f'<docx xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main">']
    parts.append(f'<title>{title}</title>')

    i = 0
    while i < len(lines):
        line = lines[i]

        # H1
        if line.startswith("# "):
            parts.append(f'<h1>{line[2:]}</h1>')
            i += 1
            continue

        # H2
        if line.startswith("## "):
            parts.append(f'<h2>{line[3:]}</h2>')
            i += 1
            continue

        # 表格检测
        if line.startswith("|"):
            # 收集表格行
            table_rows = []
            header_done = False
            j = i
            while j < len(lines):
                if lines[j].startswith("|"):
                    if _is_table_separator(lines[j]):
                        header_done = True
                        j += 1
                        continue
                    cells = [c.strip() for c in lines[j].strip().split("|")[1:-1]]
                    if header_done:
                        table_rows.append(("<tr>", cells))
                    else:
                        table_rows.insert(0, ("<tr>", cells))
                        header_done = False
                    j += 1
                else:
                    break

            if table_rows:
                parts.append('<table>')
                for _, cells in table_rows:
                    parts.append('<tr>')
                    for cell in cells:
                        parts.append(f'<td>{_cell_md_to_html(cell)}</td>')
                    parts.append('</tr>')
                parts.append('</table>')
                i = j
                continue

        # 空行
        if line.strip() == "":
            i += 1
            continue

        # 普通段落
        parts.append(f'<p>{_md_link_to_html(line)}</p>')
        i += 1

    parts.append('</docx>')
    return "\n".join(parts)
