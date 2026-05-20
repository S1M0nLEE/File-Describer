"""REFERENCES relation from explicit path mentions in text."""

import re
from pathlib import Path
from typing import Dict, List, Set

from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor

PATH_REF = re.compile(
    r"""['"]([\w./\\\-]+\.(?:txt|md|py|js|json|pdf|docx|csv|yaml|yml))['"]""",
    re.I,
)


class ReferencesExtractor(RelationExtractor):
    relation_type = "REFERENCES"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        by_name: Dict[str, FileDescriptor] = {f.name: f for f in file_nodes}
        by_path: Dict[str, FileDescriptor] = {f.path: f for f in file_nodes}
        edges: List = []
        seen: Set[tuple] = set()

        for f in file_nodes:
            text = f.content_text or f.summary or ""
            base = Path(f.path).parent
            for m in PATH_REF.finditer(text):
                ref = m.group(1).replace("\\", "/")
                target = self._resolve(ref, base, by_name, by_path, file_nodes)
                if target and target.id != f.id:
                    key = (f.id, target.id)
                    if key not in seen:
                        seen.add(key)
                        edges.append((f.id, target.id, "REFERENCES", {"mention": ref}))
        return edges

    def _resolve(self, ref, base, by_name, by_path, all_files):
        candidates = [
            str((base / ref).resolve()).replace("\\", "/"),
            ref,
        ]
        for c in candidates:
            if c in by_path:
                return by_path[c]
        name = Path(ref).name
        return by_name.get(name)
