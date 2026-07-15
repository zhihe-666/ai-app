"""
prototype_renderer.py — 产品原型 HTML 渲染器

Agent5 输出结构化数据（标题、区块列表、表格数据、按钮等），
此模块将其渲染为可靠、自包含的 HTML 页面（纯 CSS，无外部 JS 依赖）。
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 样式模板 ──
_CSS = """body{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;color:#333}
.header{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:16px 32px}
.header h1{margin:0;font-size:20px;font-weight:600}
.header .sub{font-size:13px;opacity:.85;margin-top:4px}
.content{max-width:1200px;margin:0 auto;padding:20px}
.card{background:#fff;border-radius:8px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card-title{font-size:15px;font-weight:600;color:#1a1a1a;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #eee}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f8f9ff;color:#1a1a1a;font-weight:600;padding:10px 12px;text-align:left;border-bottom:2px solid #e8eaff}
td{padding:10px 12px;border-bottom:1px solid #f0f0f0}
tr:hover{background:#fafafa}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:500}
.badge-p0{background:#fff1f0;color:#cf1322}
.badge-p1{background:#fff7e6;color:#d46b08}
.badge-done{background:#f6ffed;color:#389e0d}
.badge-progress{background:#e6f7ff;color:#096dd9}
.status-bar{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}
.stat-item{background:#fff;border-radius:8px;padding:16px 20px;flex:1;min-width:160px;box-shadow:0 1px 3px rgba(0,0,0,.08);text-align:center}
.stat-value{font-size:28px;font-weight:700;color:#6366f1}
.stat-label{font-size:12px;color:#999;margin-top:4px}
.btn{display:inline-block;padding:6px 16px;border-radius:6px;font-size:13px;font-weight:500;cursor:pointer;border:none;margin-right:8px;margin-bottom:8px}
.btn-primary{background:#6366f1;color:#fff}
.btn-default{background:#fff;color:#333;border:1px solid #d9d9d9}
.btn-danger{background:#ff4d4f;color:#fff}
.section{margin-bottom:16px}
.diff{display:flex;gap:16px;flex-wrap:wrap}
.diff-col{flex:1;min-width:200px;background:#fafafa;border-radius:6px;padding:12px}
.diff-col h4{margin:0 0 8px;font-size:13px;color:#666}
.nav{background:#fff;border-bottom:1px solid #e8e8e8;padding:0 32px;display:flex;gap:0}
.nav a{padding:12px 20px;font-size:13px;color:#666;text-decoration:none;border-bottom:2px solid transparent}
.nav a.active{color:#6366f1;border-bottom-color:#6366f1;font-weight:600}
.nav a:hover{color:#6366f1}
.breadcrumb{font-size:12px;color:#999;margin-bottom:12px}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:12px;color:#666;margin-bottom:4px}
.form-group input,.form-group select{width:100%;padding:6px 10px;border:1px solid #d9d9d9;border-radius:6px;font-size:13px;box-sizing:border-box}
.footer{text-align:center;padding:16px;font-size:12px;color:#bbb}
@media(max-width:768px){.status-bar{flex-direction:column}.diff{flex-direction:column}.header{padding:12px 16px}.content{padding:12px}}
"""


def _render_section(section: dict) -> str:
    """渲染单个区块"""
    typ = section.get("type", "card")
    title = section.get("title", "")
    parts = []

    if title:
        parts.append(f'<div class="card-title">{_e(title)}</div>')

    if typ == "table":
        columns = section.get("columns", [])
        rows = section.get("rows", [])
        parts.append('<table><thead><tr>')
        for col in columns:
            parts.append(f'<th>{_e(col)}</th>')
        parts.append('</tr></thead><tbody>')
        for row in rows:
            parts.append('<tr>')
            for col in columns:
                val = row.get(col, row.get(col.lower(), ''))
                parts.append(f'<td>{_e(str(val))}</td>')
            parts.append('</tr>')
        parts.append('</tbody></table>')

    elif typ == "stat_grid":
        items = section.get("items", [])
        parts.append('<div class="status-bar">')
        for item in items:
            parts.append(
                f'<div class="stat-item">'
                f'<div class="stat-value">{_e(str(item.get("value", "")))}</div>'
                f'<div class="stat-label">{_e(item.get("label", ""))}</div>'
                f'</div>'
            )
        parts.append('</div>')

    elif typ == "diff":
        rows = section.get("rows", [])
        parts.append('<div class="diff">')
        parts.append('<div class="diff-col"><h4>旧值</h4>')
        for r in rows:
            parts.append(f'<div style="margin-bottom:4px;font-size:12px"><b>{_e(r.get("field",""))}</b>: {_e(r.get("old",""))}</div>')
        parts.append('</div>')
        parts.append('<div class="diff-col"><h4>新值</h4>')
        for r in rows:
            parts.append(f'<div style="margin-bottom:4px;font-size:12px"><b>{_e(r.get("field",""))}</b>: {_e(r.get("new",""))}</div>')
        parts.append('</div>')
        parts.append('</div>')

    elif typ == "badge_list":
        items = section.get("items", [])
        parts.append('<div style="display:flex;flex-wrap:wrap;gap:8px">')
        for item in items:
            badge_cls = item.get("style", "badge-p0") or "badge-p0"
            parts.append(f'<span class="badge {badge_cls}">{_e(item.get("label",""))}</span>')
        parts.append('</div>')

    elif typ == "form":
        fields = section.get("fields", [])
        parts.append('<div>')
        for f in fields:
            parts.append(f'<div class="form-group"><label>{_e(f.get("label",""))}</label>')
            if f.get("type") == "select":
                opts = f.get("options", [])
                parts.append(f'<select><option>{"</option><option>".join(opts)}</option></select>')
            else:
                parts.append(f'<input type="text" placeholder="{_e(f.get("placeholder",""))}" />')
            parts.append('</div>')
        parts.append('</div>')

    elif typ == "actions":
        buttons = section.get("buttons", [])
        parts.append('<div>')
        for b in buttons:
            btn_cls = f'btn btn-{b.get("style", "default")}'
            parts.append(f'<button class="{btn_cls}">{_e(b.get("label",""))}</button>')
        parts.append('</div>')

    elif typ == "text":
        parts.append(f'<p style="font-size:13px;line-height:1.8;color:#555">{_e(section.get("content",""))}</p>')

    result = '\n'.join(parts)
    return f'<div class="card">\n{result}\n</div>' if title or typ != "card" else f'<div class="card">\n{result}\n</div>'


def render_prototype(data: dict) -> str:
    """渲染完整 HTML 原型

    data 结构:
      {
        "title": "功能名",
        "subtitle": "PRD 产品原型",
        "nav": ["版本列表", "审计日志", ...], (可选)
        "sections": [
          {"type": "table"|"stat_grid"|"diff"|"badge_list"|"form"|"actions"|"text",
           "title": "...",
           ...}
        ]
      }
    """
    title = data.get("title", "PRD 产品原型")
    subtitle = data.get("subtitle", "PRD 产品原型 · AI 生成")

    sections_html = []
    for sec in data.get("sections", []):
        try:
            sections_html.append(_render_section(sec))
        except Exception as e:
            logger.warning(f'[PrototypeRenderer] section 渲染失败: {e}')
            sections_html.append(f'<div class="card"><div class="card-title">{_e(str(e))}</div></div>')

    nav_html = ''
    nav_items = data.get("nav", [])
    if nav_items:
        nav_html = '<div class="nav">' + ''.join(
            f'<a href="#" class="active" if i==0 else ""{_e(item)}</a>' for i, item in enumerate(nav_items)
        ) + '</div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{_e(title)} — 产品原型</title>
<style>{_CSS}</style>
</head>
<body>

<div class="header">
  <h1>{_e(title)}</h1>
  <div class="sub">{_e(subtitle)}</div>
</div>

{nav_html}

<div class="content">
  {'\\n'.join(sections_html)}
</div>

<div class="footer">产品原型 · AI 生成</div>
</body>
</html>"""
    return html


def _e(text: str) -> str:
    """HTML 转义"""
    if not isinstance(text, str):
        text = str(text)
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
