"""BELONGS_TO_PROJECT relation from directory markers."""

import json
from pathlib import Path
from typing import Dict, List

from src.models.file_descriptor import FileDescriptor
from src.models.graph_entities import Project
from src.relations.base import RelationExtractor

MARKERS = ("package.json", "pyproject.toml", "setup.py", ".filekg_project.json")


class BelongsToProjectExtractor(RelationExtractor):
    relation_type = "BELONGS_TO_PROJECT"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        project_roots: Dict[str, str] = {}
        for f in file_nodes:
            if f.name in MARKERS:
                root = str(Path(f.path).parent).replace("\\", "/")
                name = self._project_name(f)
                project_roots[root] = name

        if not project_roots:
            common = self._infer_common_root(file_nodes)
            if common:
                project_roots[common] = Path(common).name

        edges = []
        for f in file_nodes:
            assigned = None
            for root, pname in sorted(project_roots.items(), key=lambda x: -len(x[0])):
                if f.path.startswith(root + "/") or f.path == root:
                    assigned = (root, pname)
                    break
            if assigned:
                root, pname = assigned
                pid = Project.generate_id(pname)
                edges.append((f.id, pid, "BELONGS_TO_PROJECT", {"project": pname, "root": root}))
        return edges

    @staticmethod
    def project_nodes(file_nodes: List[FileDescriptor]) -> List[Project]:
        extractor = BelongsToProjectExtractor()
        edges = extractor.discover(file_nodes)
        projects = {}
        for _, pid, _, props in edges:
            pname = props.get("project", "default")
            root = props.get("root", "")
            projects[pid] = Project(id=pid, name=pname, root_path=root)
        return list(projects.values())

    def _project_name(self, marker_file: FileDescriptor) -> str:
        if marker_file.name == ".filekg_project.json":
            try:
                data = json.loads(marker_file.content_text or "{}")
                return data.get("name", Path(marker_file.path).parent.name)
            except json.JSONDecodeError:
                pass
        if marker_file.name == "package.json":
            try:
                data = json.loads(marker_file.content_text or "{}")
                return data.get("name", Path(marker_file.path).parent.name)
            except json.JSONDecodeError:
                pass
        return Path(marker_file.path).parent.name

    def _infer_common_root(self, file_nodes: List[FileDescriptor]) -> str:
        if not file_nodes:
            return ""
        paths = [Path(f.path).parent for f in file_nodes]
        try:
            common = Path(*paths[0].parts)
            for p in paths[1:]:
                common_parts = []
                for a, b in zip(common.parts, p.parts):
                    if a == b:
                        common_parts.append(a)
                    else:
                        break
                common = Path(*common_parts) if common_parts else paths[0]
            return str(common).replace("\\", "/")
        except Exception:
            return str(paths[0]).replace("\\", "/")
