from __future__ import annotations

import json
from pathlib import Path
from typing import Any as Neo4jStore

from src.models.descriptor import FileDescriptor
from src.relations.base import RelationEdge, RelationParser

_TAG_KEYWORDS = {
    "发票": "财务",
    "合同": "法务",
    "实验": "科研",
    "论文": "科研",
    "报销": "财务",
    "简历": "人事",
}


class ProjectRelationsParser(RelationParser):
    """方案 4.2.10：BELONGS_TO_PROJECT（.project 配置）与 TAGGED_WITH 自动推荐。"""

    name = "project_tags"

    def discover(
        self, descriptors: list[FileDescriptor], store: Neo4jStore
    ) -> list[RelationEdge]:
        edges: list[RelationEdge] = []
        project_roots = self._load_project_configs(descriptors)

        for d in descriptors:
            for root, pid in project_roots.items():
                if d.path.startswith(root):
                    edges.append(
                        RelationEdge(
                            d.file_id,
                            "BELONGS_TO_PROJECT",
                            f"project:{pid}",
                            weight=0.5,
                            props={"project_id": pid},
                        )
                    )
                    break

            for kw, tag in _TAG_KEYWORDS.items():
                if kw in d.name and tag not in (d.tags or []):
                    edges.append(
                        RelationEdge(
                            d.file_id,
                            "TAGGED_WITH",
                            f"tag:{tag}",
                            weight=0.4,
                            props={"tag": tag, "auto_suggested": True, "keyword": kw},
                        )
                    )
        return edges

    def _load_project_configs(
        self, descriptors: list[FileDescriptor]
    ) -> dict[str, str]:
        roots: dict[str, str] = {}
        seen_dirs: set[str] = set()
        for d in descriptors:
            parent = str(Path(d.path).parent)
            if parent in seen_dirs:
                continue
            seen_dirs.add(parent)
            cfg = Path(parent) / ".project"
            if not cfg.is_file():
                continue
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                pid = data.get("id") or data.get("name") or Path(parent).name
                roots[str(Path(parent).resolve())] = str(pid)
            except Exception:
                pass
        return roots
