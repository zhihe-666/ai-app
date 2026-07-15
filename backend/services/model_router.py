"""
model_router.py — 深度模式双模型路由

按 Agent 角色路由到不同模型:
  - Agent 1 / Agent 4: 协同模型（flash，快、便宜，做萃取/撰写）
  - Agent 2 / Agent 3: 强推理模型（pro，做上下文分析/功能规格，需深度推理）

简单/中等模式沿用用户配置的 model（随前端 LLMConfigProvider）。
深度模式 Agent 2/3 强制 pro，保证影响范围/规格推理质量。

优先级（深度模式 Agent）:
  1. MODEL_MAP 固定路由（Agent 2/3 强制 pro）
  2. 用户配置 model（Agent 1/4 用用户配置，无配置则 flash）
"""
import os


class ModelRouter:
    """深度模式模型路由"""

    # DeepSeek 模型 ID（OpenAI 兼容接口）
    MODEL_FLASH = 'deepseek-v4-flash'
    MODEL_PRO = 'deepseek-v4-pro'

    MODEL_MAP = {
        'simple': MODEL_FLASH,
        'medium': MODEL_FLASH,
        'deep_agent_1': MODEL_FLASH,
        'deep_agent_2': MODEL_PRO,
        'deep_agent_3': MODEL_PRO,
        'deep_agent_4': MODEL_FLASH,
    }

    # 强制 pro 的 Agent（不受用户配置覆盖）
    _FORCE_PRO = {'deep_agent_2', 'deep_agent_3'}

    @classmethod
    def get_model(cls, route_key: str, user_model: str = '') -> str:
        """获取指定路由的模型

        Args:
            route_key: 路由键（simple/medium/deep_agent_1..4）
            user_model: 用户在前端配置的模型（从 LLMConfigProvider 传入）

        Returns:
            模型名称字符串
        """
        if route_key in cls._FORCE_PRO:
            return cls.MODEL_MAP[route_key]

        if user_model:
            return user_model

        return cls.MODEL_MAP.get(route_key, cls.MODEL_FLASH)

    @classmethod
    def get_base_url(cls, route_key: str, user_base_url: str = '') -> str:
        """获取指定路由的 base_url

        Agent 2/3 用 DeepSeek 官方接口（pro 模型在 DeepSeek 域）。
        其余随用户配置。

        可通过 DEEPSEEK_BASE_URL 环境变量覆盖（与微服务共享同一配置）。
        """
        if route_key in cls._FORCE_PRO:
            return os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        return user_base_url or os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')

    @classmethod
    def get_api_key(cls, route_key: str, user_api_key: str = '') -> str:
        """获取指定路由的 api_key

        Agent 2/3 用 DeepSeek key（从 DEEPSEEK_API_KEY 环境变量）。
        其余随用户配置。
        """
        if route_key in cls._FORCE_PRO:
            return os.environ.get('DEEPSEEK_API_KEY', user_api_key)
        return user_api_key
