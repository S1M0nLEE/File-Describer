from __future__ import annotations

import logging
from datetime import datetime

from src.llm.client import OllamaClient
from src.search.intent_parser import EXT_MAP, ParsedQuery

logger = logging.getLogger(__name__)


def augment_parsed_query(query: str, parsed: ParsedQuery) -> ParsedQuery:
    """方案 4.3.1：规则优先，复杂修饰由 LLM 输出 JSON 条件。"""
    if _rules_sufficient(parsed):
        return parsed

    client = OllamaClient()
    if not client.is_available():
        return parsed

    data = client.generate_json(
        f'用户查询："{query}"\n'
        '输出 JSON 字段：keywords(string), extensions(list 如 [".pdf"]), '
        'modified_after(ISO8601 或 null), modified_before(ISO8601 或 null), '
        'min_size(int|null), max_size(int|null), project_id(string|null)。',
        system="解析中文文件检索意图，仅 JSON。",
    )
    if not data:
        return parsed

    if data.get("keywords"):
        parsed.keywords = str(data["keywords"]).strip()
    for ext in data.get("extensions") or []:
        e = ext if str(ext).startswith(".") else EXT_MAP.get(str(ext).lower(), f".{ext}")
        if e not in parsed.extensions:
            parsed.extensions.append(e)
    for key in ("modified_after", "modified_before"):
        val = data.get(key)
        if val:
            try:
                dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                setattr(parsed, key, dt.replace(tzinfo=None) if dt.tzinfo else dt)
            except ValueError:
                pass
    if data.get("min_size") is not None:
        parsed.min_size = int(data["min_size"])
    if data.get("max_size") is not None:
        parsed.max_size = int(data["max_size"])
    if data.get("project_id"):
        parsed.project_id = str(data["project_id"])
    return parsed


def _rules_sufficient(parsed: ParsedQuery) -> bool:
    has_time = parsed.modified_after or parsed.modified_before
    has_ext = bool(parsed.extensions)
    kw = (parsed.keywords or "").strip()
    if has_time and has_ext:
        return True
    if has_ext and len(kw) >= 2:
        return True
    return False
