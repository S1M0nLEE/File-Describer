"""CONTAINS relation: archive/config listing or explicit containment keywords."""

import json
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Set

from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor

CONTAIN_KW = re.compile(r"(?:include|contains|embed)[s]?\s*[:=]\s*['\"]([^'\"]+)['\"]", re.I)


class ContainsExtractor(RelationExtractor):
    relation_type = "CONTAINS"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        by_name: Dict[str, FileDescriptor] = {f.name: f for f in file_nodes}
        by_rel: Dict[str, FileDescriptor] = {}
        for f in file_nodes:
            by_rel[Path(f.path).name] = f

        edges: List = []
        seen: Set[tuple] = set()

        for f in file_nodes:
            inner_names = self._listed_members(f)
            text = f.content_text or ""
            for m in CONTAIN_KW.finditer(text):
                inner_names.append(m.group(1))

            for name in inner_names:
                target = by_name.get(Path(name).name) or by_rel.get(Path(name).name)
                if target and target.id != f.id:
                    key = (f.id, target.id)
                    if key not in seen:
                        seen.add(key)
                        edges.append((f.id, target.id, "CONTAINS", {"member": name}))
        return edges

    def _listed_members(self, f: FileDescriptor) -> List[str]:
        path = Path(f.path)
        if path.suffix.lower() == ".zip" and path.is_file():
            try:
                with zipfile.ZipFile(path) as zf:
                    return [zi.filename for zi in zf.infolist() if not zi.is_dir()]
            except zipfile.BadZipFile:
                return []
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(f.content_text or "{}")
                if isinstance(data, dict) and "files" in data:
                    return list(data["files"])
            except json.JSONDecodeError:
                pass
        return []
