"""Query intent parsing: rules + optional Ollama."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import dateparser
import httpx

from src.config import Config, get_config


@dataclass
class ParsedQuery:
    raw: str
    keywords: List[str] = field(default_factory=list)
    extensions: List[str] = field(default_factory=list)
    datetime_range: Optional[Tuple[float, float]] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    status: Optional[str] = None
    semantic_text: str = ""

    def to_filters(self) -> Dict[str, Any]:
        f: Dict[str, Any] = {}
        if self.extensions:
            f["extension"] = {"$in": self.extensions}
        if self.status:
            f["status"] = self.status
        if self.datetime_range:
            f["modified_time"] = {
                "$gte": self.datetime_range[0],
                "$lte": self.datetime_range[1],
            }
        if self.min_size is not None:
            f["size"] = f.get("size", {})
            f["size"]["$gte"] = self.min_size
        if self.max_size is not None:
            f["size"] = f.get("size", {})
            f["size"]["$lte"] = self.max_size
        return f


EXT_PATTERN = re.compile(r"\.(py|pdf|docx?|txt|md|json|png|jpg|js|ts)\b", re.I)
SIZE_PATTERN = re.compile(r"(\d+)\s*(kb|mb|gb)?", re.I)
DATE_HINT = re.compile(r"(昨天|今天|上周|last week|yesterday|today|\d{4}[-/]\d{1,2})", re.I)


class QueryParser:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()

    def parse(self, query: str) -> ParsedQuery:
        pq = ParsedQuery(raw=query, semantic_text=query)
        pq.extensions = [f".{m.group(1).lower()}" for m in EXT_PATTERN.finditer(query)]

        for m in SIZE_PATTERN.finditer(query):
            val = int(m.group(1))
            unit = (m.group(2) or "b").lower()
            mult = {"kb": 1024, "mb": 1024**2, "gb": 1024**3}.get(unit, 1)
            if "大于" in query or ">" in query or "larger" in query.lower():
                pq.min_size = val * mult
            elif "小于" in query or "<" in query or "smaller" in query.lower():
                pq.max_size = val * mult

        if DATE_HINT.search(query):
            dt = dateparser.parse(query, languages=["zh", "en"])
            if dt:
                start = dt.replace(hour=0, minute=0, second=0).timestamp()
                end = dt.replace(hour=23, minute=59, second=59).timestamp()
                pq.datetime_range = (start, end)

        stop = {"的", "文件", "找", "搜索", "查询", "file", "find", "search"}
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", query)
        pq.keywords = [t for t in tokens if t.lower() not in stop and len(t) > 1]

        if self.config.use_llm_query_parse:
            llm = self._ollama_parse(query)
            if llm:
                pq.extensions = llm.get("extensions", pq.extensions)
                pq.keywords = llm.get("keywords", pq.keywords)
                pq.semantic_text = llm.get("semantic_text", query)

        if not pq.semantic_text.strip():
            pq.semantic_text = " ".join(pq.keywords) or query
        return pq

    def _ollama_parse(self, query: str) -> Dict[str, Any]:
        prompt = (
            "Parse file search query to JSON with keys: extensions (list), "
            f"keywords (list), semantic_text (string). Query: {query}"
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    f"{self.config.ollama_base_url}/api/generate",
                    json={"model": self.config.ollama_model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                text = resp.json().get("response", "")
                start, end = text.find("{"), text.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(text[start:end])
        except Exception:
            pass
        return {}
