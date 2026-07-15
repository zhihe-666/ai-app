# backend/routers/code_analyze.py

import json
from datetime import datetime
from flask import Blueprint, Response, jsonify, request, stream_with_context, g

from services.code_analyze_service import CodeAnalyzeService, get_snapshot_info

code_analyze_bp = Blueprint('code_analyze', __name__)


@code_analyze_bp.route('/start', methods=['POST'])
def start_analysis():
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求体不能为空'}), 400

    required = ['start_time', 'end_time']
    for field in required:
        if field not in data:
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    repo_url = data.get('repo_url', '')
    branch = data.get('branch', 'master')
    frontend_paths = data.get('frontend_paths', [])
    start_time = data['start_time']
    end_time = data['end_time']
    git_token = data.get('git_token', '')
    # 兜底：请求体未传 git_token 时，用全局配置（inject_llm_config 注入的默认值）
    if not git_token:
        git_token = g.llm_config.get('git_token', '')

    service = CodeAnalyzeService()

    def generate():
        yield from service.analyze(
            repo_url=repo_url,
            branch=branch,
            frontend_paths=frontend_paths,
            start_time=start_time,
            end_time=end_time,
            git_token=git_token,
        )

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@code_analyze_bp.route('/status/<task_id>', methods=['GET'])
def get_status(task_id: str):
    return jsonify({
        'task_id': task_id,
        'status': 'running',
        'current_step': '',
        'step_index': 0,
        'total_steps': 8,
        'percentage': 0,
    })


@code_analyze_bp.route('/refresh-snapshot', methods=['POST'])
def refresh_snapshot():
    service = CodeAnalyzeService()

    def generate():
        yield f"event: progress\ndata: {json.dumps({'step': 'snapshot', 'message': '正在刷新知识快照...', 'percentage': 50})}\n\n"
        try:
            service._generate_snapshot()
            yield f"event: complete\ndata: {json.dumps({'section': 'complete', 'message': '知识快照刷新完成', 'llm_status': 'success'})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@code_analyze_bp.route('/snapshot', methods=['GET'])
def get_snapshot():
    info = get_snapshot_info()
    return jsonify(info)


@code_analyze_bp.route('/export/markdown', methods=['POST'])
def export_markdown():
    """Export analysis result as Markdown file."""
    data = request.get_json()
    result = data.get('result', {})

    lines = []
    lines.append("# 前端代码变更分析报告\n")
    lines.append(f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    summary = result.get('summary', {})
    if summary:
        lines.append(f"\n## 概览\n")
        lines.append(f"- Feature Groups: {summary.get('feature_groups', 0)}")
        lines.append(f"- 功能变更: {summary.get('functional_changes', 0)}")
        lines.append(f"- UI 变更: {summary.get('ui_changes', 0)}\n")

    new_features = result.get('new_features', [])
    if new_features:
        lines.append(f"\n## 新增功能 ({len(new_features)})\n")
        for f in new_features:
            lines.append(f"### {f.get('name', '未知变更')}")
            if f.get('confidence'):
                lines.append(f"> 置信度: {f['confidence']:.2f}")
            if f.get('description'):
                lines.append(f"\n{f['description']}\n")
            if f.get('evidence_files'):
                lines.append(f"\n证据文件：")
                for ef in f['evidence_files']:
                    lines.append(f"- `{ef}`")
            lines.append("")

    modified = result.get('modified_features', [])
    if modified:
        lines.append(f"\n## 功能修改 ({len(modified)})\n")
        for f in modified:
            lines.append(f"### {f.get('name', '未知修改')}")
            if f.get('description'):
                lines.append(f"\n{f['description']}\n")
            lines.append("")

    removed = result.get('removed_features', [])
    if removed:
        lines.append(f"\n## 功能下线 ({len(removed)})\n")
        for f in removed:
            lines.append(f"- {f.get('name', '未知')}")
            if f.get('description'):
                lines.append(f"  {f['description']}")
            lines.append("")

    ui_updates = result.get('ui_updates', [])
    if ui_updates:
        lines.append(f"\n## UI 更新 ({len(ui_updates)})\n")
        for u in ui_updates:
            lines.append(f"- {u}")

    markdown = '\n'.join(lines)

    from flask import Response as FlaskResponse
    return FlaskResponse(
        markdown,
        mimetype='text/markdown',
        headers={
            'Content-Disposition': 'attachment; filename=code-analyze-report.md',
            'Content-Type': 'text/markdown; charset=utf-8',
        }
    )


@code_analyze_bp.route('/export/feishu', methods=['POST'])
def export_feishu():
    """Export analysis result to Feishu document."""
    data = request.get_json()
    result = data.get('result', {})

    # Build Markdown first
    lines = []
    lines.append(f"# 前端代码变更分析报告\n")

    summary = result.get('summary', {})
    if summary:
        lines.append(f"\n## 概览\n")
        lines.append(f"- Feature Groups: {summary.get('feature_groups', 0)}")
        lines.append(f"- 功能变更: {summary.get('functional_changes', 0)}")
        lines.append(f"- UI 变更: {summary.get('ui_changes', 0)}\n")

    for key, title_str in [('new_features', '新增功能'), ('modified_features', '功能修改'), ('removed_features', '功能下线')]:
        items = result.get(key, [])
        if items:
            lines.append(f"\n## {title_str} ({len(items)})\n")
            for f in items:
                lines.append(f"### {f.get('name', '未知')}")
                if f.get('description'):
                    lines.append(f"\n{f['description']}\n")

    ui_updates = result.get('ui_updates', [])
    if ui_updates:
        lines.append(f"\n## UI 更新\n")
        for u in ui_updates:
            lines.append(f"- {u}\n")

    markdown = '\n'.join(lines)

    try:
        from services.feishu_client import create_doc_xml
        from datetime import datetime as dt
        title = f"代码变更分析报告 {dt.now().strftime('%Y%m%d_%H%M')}"

        # Build feishu docx XML: must start with <title> tag
        xml_parts = [f'<title>{title}</title>']
        for line in markdown.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('# ') or stripped.startswith('## '):
                text = stripped.lstrip('#').strip()
                xml_parts.append(f'<p><b>{text}</b></p>')
            elif stripped.startswith('### '):
                text = stripped[4:].strip()
                xml_parts.append(f'<p><b>{text}</b></p>')
            elif stripped.startswith('- '):
                text = stripped.lstrip('- ').strip()
                xml_parts.append(f'<p>• {text}</p>')
            elif stripped.startswith('> '):
                text = stripped.lstrip('> ').strip()
                xml_parts.append(f'<p><i>{text}</i></p>')
            else:
                xml_parts.append(f'<p>{stripped}</p>')

        content_xml = '\n'.join(xml_parts)
        doc_url = create_doc_xml(title, content_xml)
        if not doc_url:
            return jsonify({'success': False, 'error': '飞书文档创建成功但返回 URL 为空'}), 500
        return jsonify({'success': True, 'doc_url': doc_url})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
