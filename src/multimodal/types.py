from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MediaKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    OTHER = "other"


@dataclass
class ExtractedMedia:
    kind: MediaKind
    text: str = ""
    vision_caption: str = ""
    transcript: str = ""
    ocr_text: str = ""
    frame_captions: list[str] = field(default_factory=list)
    visual_embedding: list[float] | None = None
    tags: list[str] = field(default_factory=list)

    def searchable_text(self) -> str:
        parts = [p for p in (self.text, self.vision_caption, self.transcript, self.ocr_text) if p.strip()]
        if self.frame_captions:
            parts.append(" ".join(self.frame_captions[:8]))
        return "\n".join(parts).strip()
