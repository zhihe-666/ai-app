"""
Skills 查询客户端

封装 skills.dewu-inc.com API 的直接 HTTP 调用。
token 为 None 时使用内置默认 token（与原始 skill 一致）。
"""
import logging
import os
from datetime import date as date_type
import concurrent.futures

import requests

from services.token_config import DEFAULT_TOKEN

logger = logging.getLogger(__name__)

SKILLS_URL = "https://skills.dewu-inc.com/v1/skills"

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def _call_with_timeout(fn, timeout_sec=70):
    """线程池执行 + 硬墙钟超时"""
    future = _executor.submit(fn)
    try:
        return future.result(timeout=timeout_sec)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f"API 调用超时（>{timeout_sec}s）")


class SkillsQueryClient:
    """封装 Skills 平台查询 API"""

    def __init__(self, token: str = None):
        self._token = token or DEFAULT_TOKEN
        self._headers = {
            "Accept": "application/json, text/plain, */*",
            "accessToken": self._token,
        }

    def query_skills(
        self,
        department: str = "算法平台",
        names: str = "",
        start_date: str = "",
        end_date: str = "",
        page_size: int = 200,
    ) -> dict:
        """查询部门 Skills 列表，全部拉取后按 updated_at 过滤

        API 本身不支持日期过滤参数，因此一次性拉取全部分页数据，
        在客户端按 updated_at 字段过滤。

        Returns:
            {"rows": [{"name", "author", "description", "call_count", "efficiency_minutes", "updated_at"}, ...],
             "total_count": int}
        """
        rows = []

        # 逐页拉取全部数据
        page = 1
        total_pages = 1
        while page <= total_pages:
            params = {
                "page": page,
                "page_size": page_size,
                "sort_by": "updated_at",
                "department": department,
            }
            resp = requests.get(SKILLS_URL, headers=self._headers, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            if isinstance(items, dict):
                for v in items.values():
                    if isinstance(v, list):
                        items = v
                        break

            if page == 1:
                total = data.get("total", 0)
                total_pages = max(1, (total + page_size - 1) // page_size)

            rows.extend(items)
            page += 1

        # 按 updated_at 客户端过滤
        if start_date or end_date:
            filtered = []
            for item in rows:
                ua = item.get("updated_at", "") or ""
                dt_str = ua[:10] if ua else ""
                if dt_str:
                    try:
                        from datetime import datetime as dt_cls
                        dt = dt_cls.strptime(dt_str, "%Y-%m-%d").date()
                        if start_date:
                            sd = dt_cls.strptime(start_date[:10], "%Y-%m-%d").date()
                            if dt < sd:
                                continue
                        if end_date:
                            ed = dt_cls.strptime(end_date[:10], "%Y-%m-%d").date()
                            if dt > ed:
                                continue
                    except ValueError:
                        pass
                filtered.append(item)
            rows = filtered

        # 按姓名或域账号过滤贡献人
        keywords = [k.strip() for k in names.split(",") if k.strip()] if names else []
        if keywords:
            filtered = []
            for item in rows:
                # username: 顶层 author 字段（域账号）
                username = str(item.get("author", ""))
                # name: author_info.name（中文名+英文名）
                author_info = item.get("author_info") or {}
                name = str(author_info.get("name", ""))
                if any(kw in name or kw in username for kw in keywords):
                    filtered.append(item)
            rows = filtered

        # 格式化为输出
        result_rows = []
        for r in rows:
            author_info = r.get("author_info") or {}
            author = author_info.get("name", "-")
            skill_name = r.get("name", "-")
            skill_id = r.get("id", "")
            url = f"https://skills.dewu-inc.com/skills/detail?id={skill_id}" if skill_id else ""
            description = r.get("description", "-") or "-"
            updated_at = r.get("updated_at", "-") or "-"
            call_count = r.get("usage_count", "-")     # 真实字段名 = usage_count
            efficiency = r.get("estimated_efficiency_time", "-")  # 真实字段名

            # Markdown 链接格式（写入飞书文档用）
            skill_link = f"[{skill_name}]({url})" if url else skill_name

            result_rows.append({
                "name": skill_name,
                "url": url,
                "skill_link": skill_link,
                "author": author,
                "description": description,
                "call_count": call_count,
                "efficiency_minutes": efficiency,
                "updated_at": updated_at,
            })

        # 按更新时间降序排列
        result_rows.sort(key=lambda r: r.get("updated_at", "") or "", reverse=True)

        return {"rows": result_rows, "total_count": len(result_rows)}