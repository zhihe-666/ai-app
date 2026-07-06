#!/usr/bin/env python3
"""
AI 编程度量查询客户端

完全照搬原始 skill (ai-measure-query/scripts/ai_measure.py) 的数据获取逻辑。
- URL: https://ep-copilot2.shizhuang-inc.com/v1/ai-tool-measure/drilldown
- dimension_value 直接传 department 参数值（如 "技术部"）
- names 不传给 API，返回后本地过滤
- token 使用 os.environ.get("EP_TOKEN", DEFAULT) 方式
"""
import os
import logging
import time
import concurrent.futures

import requests

from services.token_config import DEFAULT_TOKEN

logger = logging.getLogger(__name__)

# API 地址（与原始 skill 一致）
DRILLDOWN_URL = "https://ep-copilot2.shizhuang-inc.com/v1/ai-tool-measure/drilldown"
SKILLS_URL = "https://skills.dewu-inc.com/v1/skills"
DEFAULT_TOOL = "Cursor,ClaudeCode(国内模型),ClaudeCode(国外模型)"


def _parse_rate(v):
    """解析活跃率，返回 (float, is_null)"""
    if v is None:
        return (0.0, True)
    if isinstance(v, str) and v.strip() in ("-", "", "None"):
        return (0.0, True)
    try:
        return (float(v), False)
    except (ValueError, TypeError):
        return (0.0, True)


def _to_float(v):
    """安全转 float"""
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


# 每次 drilldown API 调用的硬超时（总墙钟时间，非字节间隔）
_HARD_TIMEOUT_SECONDS = 120


def _run_with_timeout(func, args, timeout=_HARD_TIMEOUT_SECONDS):
    """使用线程池执行函数，施加硬墙钟超时

    requests timeout 只控制两次字节到达间的间隔，无法防止
    服务端慢传导致无限等待。此函数确保总耗时不超过 timeout 秒。
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"API 调用超时（>{timeout}s）")


class AiMeasureClient:
    def __init__(self, token=None):
        self._token = token or DEFAULT_TOKEN

    def _fetch_drilldown(self, department, start_date, end_date, tool=DEFAULT_TOOL):
        """调用 drilldown API，含 2 次自动重试抵御瞬时错误"""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "accessToken": self._token,
        }
        params = {
            "dimension_type": "department",
            "dimension_value": department,
            "start_date": start_date,
            "end_date": end_date,
            "tool": tool,
        }
        logger.info(f"drilldown API: dept={department} {start_date}~{end_date}")

        def _do_request():
            last_exc = None
            for attempt in range(3):  # 最多 3 次尝试
                try:
                    resp = requests.get(DRILLDOWN_URL, headers=headers, params=params,
                                        timeout=min(180, _HARD_TIMEOUT_SECONDS + 10))
                    resp.raise_for_status()
                    return resp.json()
                except requests.RequestException as e:
                    last_exc = e
                    if attempt < 2:
                        wait = (attempt + 1) * 2  # 退避: 2s, 4s
                        logger.warning(f"drilldown 重试 {attempt+1}/2 (等待{wait}s): {e}")
                        import time
                        time.sleep(wait)
            raise last_exc

        return _run_with_timeout(_do_request, ())

    def query_drilldown(self, department, start_date, end_date, names="", tool=DEFAULT_TOOL):
        """查询度量数据并按 department/names 过滤"""
        data = self._fetch_drilldown(department, start_date, end_date, tool)
        users = data.get("data", {}).get("users", [])
        logger.info(f"  API 返回 {len(users)} 人")

        # names 本地过滤（与原始 skill find_target 一致）
        keywords = [k.strip() for k in names.split(",") if k.strip()] if names else []
        if keywords:
            users = [u for u in users
                     if any(kw in str(u.get("name", "")) or kw in str(u.get("username", ""))
                            for kw in keywords)]
            logger.info(f"  过滤后 {len(users)} 人")

        rows = []
        for u in users:
            org_path = u.get("org_path", "")
            org_parts = org_path.split("/")
            org_short = "/".join(org_parts[-2:]) if len(org_parts) >= 2 else org_path
            activity_rate, activity_null = _parse_rate(u.get("activity_day_rate"))

            rows.append({
                "name": u.get("name", "-"),
                "username": u.get("username", ""),
                "department": org_short,
                "org_path": org_path,
                "department_name": u.get("department_name", ""),
                "activity_rate": activity_rate,
                "activity_rate_null": activity_null,
                "tokens_m": round(_to_float(u.get("total_tokens")) / 1_000_000, 1),
                "tokens_raw": _to_float(u.get("total_tokens")),
                "code_ratio": _to_float(u.get("code_ratio")),
                "commit_ratio": _to_float(u.get("commit_ratio")),
                "consumption": _to_float(u.get("consumption")),
            })

        return {"rows": rows}

    def query_all_pilot_data(self, department, start_date, end_date, names=""):
        return self.query_drilldown(department, start_date, end_date, names)

    def query_active_rate(self, department, start_date, end_date, names=""):
        return self.query_drilldown(department, start_date, end_date, names)

    def query_inactive(self, department, start_date, end_date, names=""):
        return self.query_drilldown(department, start_date, end_date, names)

    def test_connection(self):
        """测试连接，返回用户数"""
        data = self._fetch_drilldown("技术部", "2026-06-12", "2026-06-26")
        return data.get("data", {}).get("user_count", 0)
