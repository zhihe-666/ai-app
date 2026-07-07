"""
LLM 调用封装 — OpenAI 兼容接口

三件套（API Key / Base URL / Model）从前端请求头传入：
- X-Api-Key
- X-Base-Url
- X-Model

不在代码或环境变量中硬编码（兜底方案除外）。
"""

import os
from typing import Optional
from openai import OpenAI


class LLMClient:
    """LLM 调用客户端

    Token / Base URL / Model 通过构造函数传入，不从环境变量读取。
    支持 OpenAI 兼容接口（OpenAI / DeepSeek / 通义千问 / 硅基流动等）。

    Usage:
        from flask import g
        client = LLMClient(**g.llm_config)
        answer = client.chat(system="...", user="...")
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ):
        """初始化 LLM 客户端

        Args:
            api_key: API Key（必填，由前端传入）
            base_url: 兼容接口地址，默认 https://api.openai.com/v1
            model: 模型名称，默认 gpt-4o
        """
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        seed: int | None = None,
    ) -> str:
        """通用 Chat 调用

        Args:
            system: System prompt
            user: User message
            temperature: 温度参数，默认 0.3（偏确定）
            max_tokens: 最大输出 token 数
            seed: 随机种子（设置后相同输入保证相同输出）

        Returns:
            LLM 回复文本

        Raises:
            Exception: API 调用失败
        """
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if seed is not None:
            kwargs["seed"] = seed
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def chat_stream(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        """流式 Chat 调用，逐 chunk yield 内容

        用于 SSE 流式场景，前端逐字展示生成内容。

        Args:
            system: System prompt
            user: User message
            temperature: 温度参数，默认 0.3
            max_tokens: 最大输出 token 数

        Yields:
            逐 token 内容字符串
        """
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in resp:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content