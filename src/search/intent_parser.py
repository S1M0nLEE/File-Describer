from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import dateparser


@dataclass
class ParsedQuery:
    raw: str
    keywords: str = ""
    extensions: list[str] = field(default_factory=list)
    modified_after: datetime | None = None
    modified_before: datetime | None = None
    min_size: int | None = None
    max_size: int | None = None
    project_id: str | None = None

    def chroma_where(self) -> dict | None:
        clauses: list[dict] = []
        if self.extensions:
            if len(self.extensions) == 1:
                clauses.append({"extension": self.extensions[0]})
            else:
                clauses.append({"extension": {"$in": self.extensions}})
        if len(clauses) == 1:
            return clauses[0]
        if len(clauses) > 1:
            return {"$and": clauses}
        return None


EXT_MAP = {
    "pdf": ".pdf",
    "word": ".docx",
    "docx": ".docx",
    "excel": ".xlsx",
    "xlsx": ".xlsx",
    "图片": ".png",
    "照片": ".jpg",
    "截图": ".png",
    "视频": ".mp4",
    "mp4": ".mp4",
    "音频": ".mp3",
    "mp3": ".mp3",
    "录音": ".wav",
    "png": ".png",
    "jpg": ".jpg",
    "jpeg": ".jpg",
    "python": ".py",
    "代码": ".py",
    "markdown": ".md",
    "md": ".md",
}


class IntentParser:
    def parse(self, query: str) -> ParsedQuery:
        parsed = ParsedQuery(raw=query)
        remaining = query

        for word, ext in EXT_MAP.items():
            if re.search(rf"\b{re.escape(word)}\b", remaining, re.I):
                if ext not in parsed.extensions:
                    parsed.extensions.append(ext)

        ext_dot = re.findall(r"\.\w{2,5}", remaining)
        for e in ext_dot:
            if e not in parsed.extensions:
                parsed.extensions.append(e.lower())

        time_patterns = [
            (r"上周|上星期", timedelta(days=7)),
            (r"昨天", timedelta(days=1)),
            (r"今天", timedelta(days=0)),
            (r"最近(\d+)天", None),
            (r"上个月", timedelta(days=30)),
        ]
        now = datetime.now()
        for pat, delta in time_patterns:
            m = re.search(pat, remaining)
            if m:
                if delta:
                    parsed.modified_after = now - delta
                elif m.lastindex:
                    days = int(m.group(1))
                    parsed.modified_after = now - timedelta(days=days)
                remaining = remaining[: m.start()] + remaining[m.end() :]

        for phrase in ["上周", "昨天", "今天", "上个月"]:
            dt = dateparser.parse(phrase, languages=["zh"])
            if phrase in query and dt:
                parsed.modified_after = dt

        parsed.keywords = re.sub(
            r"\b(pdf|word|docx|excel|png|jpg|python|markdown|md)\b",
            "",
            remaining,
            flags=re.I,
        ).strip()
        parsed.keywords = re.sub(
            r"(上周|昨天|今天|上个月|最近\d+天|的|文件|文档)",
            "",
            parsed.keywords,
        ).strip()
        if not parsed.keywords:
            parsed.keywords = query

        from src.llm.query_llm import augment_parsed_query

        return augment_parsed_query(query, parsed)
