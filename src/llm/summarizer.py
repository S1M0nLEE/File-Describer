from __future__ import annotations

import logging

from src.llm.client import OllamaClient

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是个人文件助手。根据给定文件名与正文片段，用中文写一句不超过50字的概括，"
    "不要引号、不要列表、不要前缀。"
)


def generate_ai_summary(name: str, text: str, *, rule_fallback: str) -> str:
    """方案 4.1.1：Phi-3-mini 一句话摘要；失败则用规则摘要。"""
    snippet = (text or "")[:2000].replace("\n", " ").strip()
    if not snippet and not name:
        return rule_fallback[:50]

    client = OllamaClient()
    if not client.is_available():
        return rule_fallback[:50]

    prompt = f"文件名：{name}\n\n正文片段：\n{snippet[:1800]}"
    out = client.generate(prompt, system=_SYSTEM, max_tokens=80)
    if out:
        out = out.replace("\n", " ").strip()[:50]
        if len(out) >= 4:
            return out
    return rule_fallback[:50]
