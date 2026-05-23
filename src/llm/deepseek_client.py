"""DeepSeek API（OpenAI SDK 兼容）。"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from src.config import settings

logger = logging.getLogger(__name__)


class DeepSeekClient:
    def __init__(self) -> None:
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not settings.deepseek_api_key:
            return None
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
            return self._client
        except ImportError:
            logger.warning("请安装 openai: pip install openai")
            return None

    def is_available(self) -> bool:
        return bool(settings.deepseek_enabled and settings.deepseek_api_key and self._ensure_client())

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> str | Iterator[str]:
        client = self._ensure_client()
        if not client:
            raise RuntimeError("DeepSeek 未配置或 openai 未安装")

        kwargs: dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": messages,
            "stream": stream,
            "temperature": settings.deepseek_temperature,
            "max_tokens": settings.deepseek_max_tokens,
        }
        if settings.deepseek_reasoning_effort:
            kwargs["reasoning_effort"] = settings.deepseek_reasoning_effort
        if settings.deepseek_thinking_enabled:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        if stream:
            return self._stream_chat(client, kwargs)
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        return (msg.content or "").strip()

    def _stream_chat(self, client, kwargs: dict[str, Any]) -> Iterator[str]:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
