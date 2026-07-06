#!/usr/bin/env python3
"""
不活跃人员明细查询
过滤试点名单（PILOT_USERNAMES），列出不活跃成员（activity_day_rate < 40% 且 consumption < 3000）
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

# 试点名单（对应接口 username 字段）
PILOT_USERNAMES = [

]


def parse_args():
    parser = argparse.ArgumentParser(description="查询不活跃人员明细")
    parser.add_argument("--department",  default=DEFAULT_DEPARTMENT, help=f"部门名称（默认：{DEFAULT_DEPARTMENT}）")
    parser.add_argument("--start-date",  default=DEFAULT_START_DATE, help=f"开始日期 YYYY-MM-DD（默认：{DEFAULT_START_DATE}）")
    parser.add_argument("--end-date",    default=DEFAULT_END_DATE,   help=f"结束日期 YYYY-MM-DD（默认：{DEFAULT_END_DATE}）")
    parser.add_argument("--tool",        default=DEFAULT_TOOL,       help="工具列表，逗号分隔")
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


def get_sub_dept(org_path, second_dept_filter):
    """
    有 second_dept_filter 时：取 org_path 中该节点的下一段作为子部门；
    若该节点已是最后一段，则取自身。
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


def print_table(rows):
    if not rows:
        print("无不活跃人员")
        return

    headers = ["姓名", "部门", "是否活跃", "活跃率", "AI生成代码占比", "AI Commit代码占比"]
    col_widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt_row(cells):
        return "  ".join(c.ljust(w) for c, w in zip(cells, col_widths))

    separator = "  ".join("-" * w for w in col_widths)
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))
    print(f"\n共 {len(rows)} 人")


def main():
    args = parse_args()
    if not ACCESS_TOKEN:
        print("错误：未设置环境变量 EP_TOKEN")
        return

    print(f"查询 {args.department} 部门 {args.start_date} ~ {args.end_date} 试点名单不活跃人员明细...\n")
    print(f"试点名单（{len(PILOT_USERNAMES)} 人）：{', '.join(PILOT_USERNAMES)}\n")

    data = fetch_data(args.department, args.start_date, args.end_date, args.tool)
    users = data.get("data", {}).get("users", [])
    if not users:
        print("未获取到数据，原始响应：")
        print(data)
        return

    # 只保留试点名单中的成员
    pilot_set = set(PILOT_USERNAMES)
    covered = [u for u in users if u.get("username", "") in pilot_set]

    rows = []
    for u in covered:
        if is_active(u):
            continue

        name     = u.get("name", "-")
        dept     = get_sub_dept(u.get("org_path", ""), "")
        activity = u.get("activity_day_rate")
        code     = u.get("code_ratio")
        commit   = u.get("commit_ratio")

        activity_str = f"{float(activity):.1f}%" if activity is not None else "-"
        code_str     = f"{float(code):.1f}%"     if code     is not None else "-"
        commit_str   = f"{float(commit):.1f}%"   if commit   is not None else "-"

        rows.append([name, dept, "否", activity_str, code_str, commit_str])

    # 按部门升序，同部门内按活跃率升序
    def activity_val(s):
        try:
            return -float(s.rstrip("%"))
        except ValueError:
            return 1  # "-" 排在最后

    rows.sort(key=lambda r: (r[1], activity_val(r[3])))

    print_table(rows)


if __name__ == "__main__":
    main()
