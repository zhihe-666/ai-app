#!/usr/bin/env python3
"""
AI 工具使用度量查询脚本
查询指定部门成员的 AI 编程工具使用数据
"""

import argparse
import os
import requests

ACCESS_TOKEN = os.environ.get("EP_TOKEN", "")

URL = "https://ep-copilot2.shizhuang-inc.com/v1/ai-tool-measure/drilldown"

DEFAULT_DEPARTMENT  = "算法平台"
DEFAULT_START_DATE  = "2026-03-01"
DEFAULT_END_DATE    = "2026-03-14"
DEFAULT_TOOL        = "Cursor,ClaudeCode(国内模型),ClaudeCode(国外模型)"
DEFAULT_TARGET_NAME = ""


def parse_args():
    parser = argparse.ArgumentParser(description="查询 AI 编程工具使用度量数据")
    parser.add_argument("--department",  default=DEFAULT_DEPARTMENT,  help=f"部门名称（默认：{DEFAULT_DEPARTMENT}）")
    parser.add_argument("--start-date",  default=DEFAULT_START_DATE,  help=f"开始日期 YYYY-MM-DD（默认：{DEFAULT_START_DATE}）")
    parser.add_argument("--end-date",    default=DEFAULT_END_DATE,    help=f"结束日期 YYYY-MM-DD（默认：{DEFAULT_END_DATE}）")
    parser.add_argument("--tool",        default=DEFAULT_TOOL,        help="工具列表，逗号分隔")
    parser.add_argument("--name",        default=DEFAULT_TARGET_NAME, help=f"过滤姓名关键字，多个用逗号分隔（默认：{DEFAULT_TARGET_NAME}）")
    return parser.parse_args()


def fetch_data(department, start_date, end_date, tool):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "accessToken": ACCESS_TOKEN,
    }
    params = {
        "dimension_type": "department",
        "dimension_value": department,
        "start_date": start_date,
        "end_date": end_date,
        "tool": tool,
    }
    resp = requests.get(URL, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def find_target(data, target_name):
    """从响应中找到匹配 target_name 的记录，支持逗号分隔多个关键字"""
    items = data.get("data", {}).get("users", [])

    if not items:
        print("未找到 users 列表，原始响应：")
        print(data)
        return []

    keywords = [k.strip() for k in target_name.split(",") if k.strip()]
    if not keywords:
        return items
    return [item for item in items if any(kw in str(item.get("name", "")) for kw in keywords)]


def print_table(records, target_name):
    if not records:
        print(f"未找到包含「{target_name}」的记录")
        return

    col_name     = "姓名"
    col_org      = "所属部门"
    col_activity = "活跃率"
    col_tokens   = "人均总Tokens(M)"
    col_code     = "AI生成代码占比"
    col_commit   = "AI Commit代码占比"

    rows = []
    for r in records:
        name          = r.get("name", "-")
        org_path      = r.get("org_path", "-")
        # org_path 格式：集团/得物/技术部/算法平台/xxx/xxx，取最后两级
        org_parts     = org_path.split("/")
        org_short     = "/".join(org_parts[-2:]) if len(org_parts) >= 2 else org_path
        activity      = r.get("activity_day_rate", None)
        total_tokens  = r.get("total_tokens", None)
        code_ratio    = r.get("code_ratio", None)
        commit_ratio  = r.get("commit_ratio", None)

        activity_str     = f"{float(activity):.1f}%" if activity is not None else "-"
        tokens_str       = f"{float(total_tokens)/1_000_000:.2f}M" if total_tokens is not None else "-"
        code_ratio_str   = f"{float(code_ratio):.1f}%" if code_ratio is not None else "-"
        commit_ratio_str = f"{float(commit_ratio):.1f}%" if commit_ratio is not None else "-"

        rows.append([name, org_short, activity_str, tokens_str, code_ratio_str, commit_ratio_str,
                     float(activity) if activity is not None else -1,
                     float(code_ratio) if code_ratio is not None else -1])

    # 排序：所属部门父级（升序）→ 活跃率（降序）→ AI生成代码占比（降序）
    # 部门取斜杠前的第一段，使同父级部门的成员归为一组
    rows.sort(key=lambda r: (r[1].split("/")[0], -r[6], -r[7]))
    # 去掉排序用的辅助列
    rows = [r[:6] for r in rows]

    headers = [col_name, col_org, col_activity, col_tokens, col_code, col_commit]
    col_widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt_row(cells):
        return "  ".join(c.ljust(w) for c, w in zip(cells, col_widths))

    separator = "  ".join("-" * w for w in col_widths)
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))


def main():
    args = parse_args()
    if not ACCESS_TOKEN:
        print("错误：未设置环境变量 EP_COPILOT_TOKEN")
        return
    print(f"查询 {args.department} 部门 {args.start_date} ~ {args.end_date} 数据...\n")
    data = fetch_data(args.department, args.start_date, args.end_date, args.tool)
    records = find_target(data, args.name)
    print_table(records, args.name)


if __name__ == "__main__":
    main()
