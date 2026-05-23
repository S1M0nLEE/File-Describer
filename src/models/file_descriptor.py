"""FileDescriptor node model."""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import hashlib


@dataclass
class FileDescriptor:
    id: str
    path: str
    name: str
    extension: str
    size: int
    modified_time: float
    created_time: float
    summary: str = ""
    ai_summary: str = ""
    file_embedding: List[float] = field(default_factory=list)
    status: str = "active"
    file_id: str = ""
    has_text: bool = True
    mime_type: str = ""
    content_text: str = ""

    @staticmethod
    def generate_id(file_path: str) -> str:
        normalized = file_path.replace("\\", "/")
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    @property
    def display_summary(self) -> str:
        return self.ai_summary or self.summary

    def to_neo4j_props(self) -> Dict[str, Any]:
        props = asdict(self)
        props.pop("file_embedding", None)
        props.pop("content_text", None)
        return props

    def to_chroma_metadata(self) -> Dict[str, Any]:
        return {
            "file_id": self.id,
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "size": self.size,
            "modified_time": self.modified_time,
            "status": self.status,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileDescriptor":
        return cls(
            id=data["id"],
            path=data["path"],
            name=data["name"],
            extension=data.get("extension", ""),
            size=data.get("size", 0),
            modified_time=data.get("modified_time", 0.0),
            created_time=data.get("created_time", 0.0),
            summary=data.get("summary", ""),
            ai_summary=data.get("ai_summary", ""),
            file_embedding=data.get("file_embedding", []),
            status=data.get("status", "active"),
            file_id=data.get("file_id", ""),
            has_text=data.get("has_text", True),
            mime_type=data.get("mime_type", ""),
            content_text=data.get("content_text", ""),
        )
