"""共享配置：默认 Access Token

从原始 skill 脚本动态读取，避免硬编码出错。
"""
import os
import re

# 原始 skill 脚本路径（容器内通常不存在，依赖环境变量 EP_TOKEN）
_SKILL_SCRIPT = os.environ.get(
    "AI_MEASURE_SCRIPT",
    "/Users/admin/.dewuclaw/workspaces/default/skills/ai-measure-query/scripts/ai_measure.py"
)


def _load_default_token():
    """从原始 skill 脚本中提取 ACCESS_TOKEN 默认值"""
    # 优先从环境变量读取
    env_token = os.environ.get("EP_TOKEN", "")
    if env_token:
        return env_token

    # 从 skill 脚本文件读取
    try:
        with open(_SKILL_SCRIPT, "r") as f:
            content = f.read()
        # 匹配 ACCESS_TOKEN = os.environ.get("EP_TOKEN", "....")
        m = re.search(r'os\.environ\.get\("EP_TOKEN",\s*"([A-F0-9]+)"\)', content)
        if m:
            return m.group(1)
    except Exception:
        pass

    return ""


DEFAULT_TOKEN = _load_default_token()
