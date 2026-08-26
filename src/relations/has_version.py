"""HAS_VERSION relation via filename patterns and content similarity."""

import re
from typing import Dict, List

from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor

VERSION_PATTERNS = [
    re.compile(r"(.+?)[_\-]v?(\d+(?:\.\d+)*)", re.I),
    re.compile(r"(.+?)[_\-](final|draft|rev\d+)", re.I),
    re.compile(r"(.+?)\s*\((\d+)\)", re.I),
]


class HasVersionExtractor(RelationExtractor):
    relation_type = "HAS_VERSION"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        groups: Dict[str, List[FileDescriptor]] = {}
        for f in file_nodes:
            base = self._base_name(f.name)
            if base:
                groups.setdefault(base, []).append(f)

        edges = []
        for base, group in groups.items():
            if len(group) < 2:
                continue
            group.sort(key=lambda x: x.modified_time)
            for i in range(len(group) - 1):
                older, newer = group[i], group[i + 1]
                sim = self._content_overlap(older, newer)
                edges.append((
                    newer.id, older.id, "HAS_VERSION",
                    {"base_name": base, "content_sim": sim},
                ))
        return edges

    def _base_name(self, name: str) -> str:
        stem = name.rsplit(".", 1)[0] if "." in name else name
        for pat in VERSION_PATTERNS:
            m = pat.match(stem)
            if m:
                return m.group(1).lower().strip("_- ")
        return stem.lower()

    def _content_overlap(self, a: FileDescriptor, b: FileDescriptor) -> float:
        ta = set((a.content_text or a.summary or "")[:500].split())
        tb = set((b.content_text or b.summary or "")[:500].split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta | tb), 1)
