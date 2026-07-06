#!/usr/bin/env python3
"""
部门维度 AI 覆盖聚合统计
按 org_path 最小部门聚合，返回：AI覆盖人数、活跃人数、活跃占比、人均Tokens
"""

import argparse
import os
import requests
from collections import defaultdict

ACCESS_TOKEN = os.environ.get("EP_TOKEN", "")

URL = "https://ep-copilot2.shizhuang-inc.com/v1/ai-tool-measure/drilldown"

DEFAULT_DEPARTMENT  = "算法平台"
DEFAULT_START_DATE  = "2026-03-01"
DEFAULT_END_DATE    = "2026-03-14"
DEFAULT_TOOL        = "Cursor,ClaudeCode(国内模型),ClaudeCode(国外模型)"


def parse_args():
    parser = argparse.ArgumentParser(description="按最小部门聚合 AI 使用统计")
    parser.add_argument("--department",            default=DEFAULT_DEPARTMENT, help=f"部门名称（默认：{DEFAULT_DEPARTMENT}）")
    parser.add_argument("--start-date",            default=DEFAULT_START_DATE, help=f"开始日期 YYYY-MM-DD（默认：{DEFAULT_START_DATE}）")
    parser.add_argument("--end-date",              default=DEFAULT_END_DATE,   help=f"结束日期 YYYY-MM-DD（默认：{DEFAULT_END_DATE}）")
    parser.add_argument("--tool",                  default=DEFAULT_TOOL,       help="工具列表，逗号分隔")
    parser.add_argument("--second-department",     default="",                 help="二级部门过滤关键字，对应 second_department_name（可选）")
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


def get_dept_name(org_path, second_dept_filter):
    """
    有 second_dept_filter 时：取 org_path 中该节点的下一段（-1 级）；
    若该节点已是最后一段（人直接挂在该层），则取自身。
    无 second_dept_filter 时：取 org_path 最后一段。
    """
    parts = [p.strip() for p in org_path.split("/") if p.strip()]
    if not parts:
        return org_path
    if not second_dept_filter:
        return parts[-1]
    try:
        idx = parts.index(second_dept_filter)
        return parts[idx + 1] if idx + 1 < len(parts) else parts[idx]
    except ValueError:
        return parts[-1]


def is_active(user):
    """活跃判定：activity_day_rate >= 40 或 consumption >= 3000"""
    activity = user.get("activity_day_rate")
    consumption = user.get("consumption")
    try:
        if activity is not None and float(activity) >= 40:
            return True
    except (ValueError, TypeError):
        pass
    try:
        if consumption is not None and float(consumption) >= 3000:
            return True
    except (ValueError, TypeError):
        pass
    return False


def aggregate(users, second_dept_filter):
    """
    只统计 platform 包含 ClaudeCode 的记录（AI覆盖人员）。
    按最小部门聚合：AI覆盖人数、活跃人数、人均Tokens。
    """
    # 若有 second_department 过滤，先筛选
    if second_dept_filter:
        users = [u for u in users if second_dept_filter in u.get("second_department_name", "")]

    # 只保留 platform 含 ClaudeCode 的记录
    covered = [u for u in users if "ClaudeCode" in str(u.get("platform", ""))]

    # 按最小部门聚合
    dept_map = defaultdict(lambda: {"covered": 0, "active": 0, "tokens_sum": 0.0})
    for u in covered:
        dept = get_dept_name(u.get("org_path", ""), second_dept_filter)
        dept_map[dept]["covered"] += 1
        if is_active(u):
            dept_map[dept]["active"] += 1
        total_tokens = u.get("total_tokens") or 0
        try:
            dept_map[dept]["tokens_sum"] += float(total_tokens)
        except (ValueError, TypeError):
            pass

    return dept_map


def print_table(dept_map):
    if not dept_map:
        print("无数据")
        return

    col_dept     = "部门"
    col_covered  = "AI覆盖人数"
    col_active   = "活跃人数"
    col_ratio    = "活跃占比"
    col_tokens   = "人均总Tokens(M)"

    rows = []
    for dept, stats in dept_map.items():
        covered = stats["covered"]
        active  = stats["active"]
        ratio   = active / covered * 100 if covered > 0 else 0.0
        avg_tok = stats["tokens_sum"] / covered / 1_000_000 if covered > 0 else 0.0
        rows.append([dept, str(covered), str(active), f"{ratio:.1f}%", f"{avg_tok:.2f}M"])

    # 按部门名升序排列
    rows.sort(key=lambda r: r[0])

    headers = [col_dept, col_covered, col_active, col_ratio, col_tokens]
    col_widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt_row(cells):
        return "  ".join(c.ljust(w) for c, w in zip(cells, col_widths))

    separator = "  ".join("-" * w for w in col_widths)
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))

    # 汇总行
    total_covered = sum(stats["covered"] for stats in dept_map.values())
    total_active  = sum(stats["active"]   for stats in dept_map.values())
    total_ratio   = total_active / total_covered * 100 if total_covered > 0 else 0.0
    total_tokens  = sum(stats["tokens_sum"] for stats in dept_map.values())
    avg_tokens    = total_tokens / total_covered / 1_000_000 if total_covered > 0 else 0.0
    print(separator)
    print(fmt_row(["合计", str(total_covered), str(total_active), f"{total_ratio:.1f}%", f"{avg_tokens:.2f}M"]))


def main():
    args = parse_args()
    if not ACCESS_TOKEN:
        print("错误：未设置环境变量 EP_TOKEN")
        return

    second_filter = args.second_department.strip()
    filter_desc = f"（二级部门过滤：{second_filter}）" if second_filter else ""
    print(f"查询 {args.department} 部门 {args.start_date} ~ {args.end_date} 部门维度聚合数据{filter_desc}...\n")

    data = fetch_data(args.department, args.start_date, args.end_date, args.tool)
    users = data.get("data", {}).get("users", [])
    if not users:
        print("未获取到数据，原始响应：")
        print(data)
        return

    dept_map = aggregate(users, second_filter)
    print_table(dept_map)


if __name__ == "__main__":
    main()