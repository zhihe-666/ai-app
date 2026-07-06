#!/usr/bin/env python3
"""
Skills 数据查询脚本
查询指定部门的 skills 列表
"""

import argparse
import os
import requests

ACCESS_TOKEN = os.environ.get("EP_TOKEN", "")

URL = "https://skills.dewu-inc.com/v1/skills"

DEFAULT_DEPARTMENT = "算法平台"
DEFAULT_NAME       = ""


def parse_args():
    parser = argparse.ArgumentParser(description="查询 Skills 数据")
    parser.add_argument("--department", default=DEFAULT_DEPARTMENT, help=f"部门名称（默认：{DEFAULT_DEPARTMENT}）")
    parser.add_argument("--name",       default=DEFAULT_NAME,       help="过滤作者姓名关键字，多个用逗号分隔（默认：全部）")
    parser.add_argument("--page",       default=1,   type=int,      help="页码（默认：1）")
    parser.add_argument("--page-size",  default=100, type=int,      help="每页数量（默认：100）")
    return parser.parse_args()


def fetch_data(department, page, page_size):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "accessToken": ACCESS_TOKEN,
    }
    params = {
        "page":       page,
        "page_size":  page_size,
        "sort_by":    "updated_at",
        "department": department,
    }
    resp = requests.get(URL, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def filter_records(data, name_keyword):
    items = data.get("data", data) if isinstance(data.get("data"), list) else []

    # 兼容 data 为 dict 含 list 的情况
    if not items and isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                items = v
                break

    if not items:
        print("未找到 skills 列表，原始响应：")
        print(data)
        return []

    keywords = [k.strip() for k in name_keyword.split(",") if k.strip()]
    if not keywords:
        return items
    return [
        item for item in items
        if any(kw in str((item.get("author_info") or {}).get("name", "")) for kw in keywords)
    ]


def print_table(records, name_keyword):
    if not records:
        tip = f"「{name_keyword}」" if name_keyword else "该部门"
        print(f"未找到 {tip} 的 Skills 记录")
        return

    # 按作者聚合，保留插入顺序
    from collections import OrderedDict
    author_map = OrderedDict()
    for r in records:
        author_info = r.get("author_info") or {}
        author = author_info.get("name", "-")
        skill_name = r.get("name", "-")
        skill_id   = r.get("id", "")
        url = f"https://skills.dewu-inc.com/skills/detail?id={skill_id}" if skill_id else ""
        link = f"[{skill_name}]({url})" if url else skill_name
        author_map.setdefault(author, []).append(link)

    # 按作者名排序，拼接同一人的多个 skill
    # display_rows 用于列宽计算（纯文本），rows 用于实际输出（含超链接）
    rows = sorted(
        [[author, " / ".join(links)] for author, links in author_map.items()],
        key=lambda r: r[0]
    )
    # 纯文本版本用于列宽计算（去掉 markdown 链接语法，只保留文字部分）
    import re
    def strip_md_link(s):
        return re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', s)
    display_rows = [[strip_md_link(r[0]), strip_md_link(r[1])] for r in rows]

    col_author = "用户名"
    col_skills = "Skills"
    headers = [col_author, col_skills]
    col_widths = [max(len(h), max(len(r[i]) for r in display_rows)) for i, h in enumerate(headers)]

    def fmt_row(cells, display_cells):
        parts = []
        for i, (c, dc, w) in enumerate(zip(cells, display_cells, col_widths)):
            if i < len(headers) - 1:
                # 用显示宽度 padding，但输出含超链接的原始内容
                parts.append(c + " " * (w - len(dc)))
            else:
                parts.append(c)
        return "  ".join(parts)

    separator = "  ".join("-" * w for w in col_widths[:-1]) + "  " + "-" * col_widths[-1]
    print(fmt_row(headers, headers))
    print(separator)
    for row, drow in zip(rows, display_rows):
        print(fmt_row(row, drow))

    total_skills = sum(len(links) for links in author_map.values())
    print(f"\n共 {len(rows)} 人，{total_skills} 条 Skills")


def main():
    args = parse_args()
    if not ACCESS_TOKEN:
        print("错误：未设置环境变量 SKILLS_TOKEN")
        return
    print(f"查询 {args.department} 部门 Skills 数据（第 {args.page} 页，每页 {args.page_size} 条）...\n")
    data = fetch_data(args.department, args.page, args.page_size)
    records = filter_records(data, args.name)
    print_table(records, args.name)


if __name__ == "__main__":
    main()