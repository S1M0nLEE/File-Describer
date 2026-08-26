from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from src.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """本地 Ollama / Phi-3 等轻量模型客户端；不可用时由调用方降级。"""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or settings.llm_ollama_base).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout
        self._available: bool | None = None

    def is_available(self) -> bool:
        if not settings.llm_enabled:
            return False
        if self._available is not None:
            return self._available
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            self._available = r.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 256) -> str | None:
        if not self.is_available():
            return None
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.1},
        }
        if system:
            payload["system"] = system
        try:
            r = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            if r.status_code == 404:
                self._available = False
                return None
            r.raise_for_status()
            return (r.json().get("response") or "").strip()
        except Exception as e:
            logger.debug("Ollama 生成失败: %s", e)
            if "404" in str(e):
                self._available = False
            return None

    def generate_json(self, prompt: str, *, system: str = "") -> dict[str, Any] | None:
        text = self.generate(
            prompt + "\n\n仅输出合法 JSON，不要 markdown 代码块。",
            system=system or "你是查询解析助手，只输出 JSON。",
            max_tokens=400,
        )
        if not text:
            return None
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None
