from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    ARCHIVED = "ARCHIVED"
    DEPRECATED = "DEPRECATED"
    ERROR = "ERROR"
    GHOST = "GHOST"


class AccessLogEntry(BaseModel):
    query_hash: str
    relation_type: str | None = None
    hit_at: datetime = Field(default_factory=datetime.utcnow)


class FileDescriptor(BaseModel):
    """可演化文件数字代理节点。"""

    file_id: str
    path: str
    name: str
    extension: str
    size: int
    created_time: datetime
    modified_time: datetime
    mime_type: str | None = None

    summary: str = ""
    ai_summary: str = ""
    file_embedding: list[float] = Field(default_factory=list)
    visual_embedding: list[float] = Field(default_factory=list)
    media_kind: str = ""

    status: FileStatus = FileStatus.ACTIVE
    is_inside_archive: bool = False
    parent_archive_id: str | None = None

    indexed_time: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime | None = None
    access_log: list[AccessLogEntry] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)
    project_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def display_summary(self) -> str:
        return self.ai_summary or self.summary or self.name

    def to_neo4j_props(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "size": self.size,
            "created_time": self.created_time.isoformat(),
            "modified_time": self.modified_time.isoformat(),
            "mime_type": self.mime_type,
            "summary": self.summary,
            "ai_summary": self.ai_summary,
            "status": self.status.value,
            "is_inside_archive": self.is_inside_archive,
            "parent_archive_id": self.parent_archive_id,
            "indexed_time": self.indexed_time.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "tags": self.tags,
            "project_id": self.project_id,
        }
