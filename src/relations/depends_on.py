"""DEPENDS_ON relation from import/require statements."""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set

from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor

JS_IMPORT = re.compile(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]""")
CONFIG_REF = re.compile(r"""['"]([\w./\-]+\.(?:py|js|ts|json|yaml|yml))['"]""")


class DependsOnExtractor(RelationExtractor):
    relation_type = "DEPENDS_ON"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        path_by_name: Dict[str, FileDescriptor] = {}
        path_by_stem: Dict[str, FileDescriptor] = {}
        for f in file_nodes:
            path_by_name[f.name] = f
            path_by_stem[Path(f.path).stem] = f

        edges: List = []
        seen: Set[tuple] = set()
        for f in file_nodes:
            refs = self._extract_refs(f)
            base_dir = Path(f.path).parent
            for ref in refs:
                target = self._resolve_ref(ref, base_dir, path_by_name, path_by_stem, file_nodes)
                if target and target.id != f.id:
                    key = (f.id, target.id)
                    if key not in seen:
                        seen.add(key)
                        edges.append((f.id, target.id, "DEPENDS_ON", {"ref": ref}))
        return edges

    def _extract_refs(self, f: FileDescriptor) -> Set[str]:
        text = f.content_text or ""
        refs: Set[str] = set()
        ext = f.extension.lower()
        if ext == ".py":
            refs.update(self._python_imports(text))
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            refs.update(m.group(1) for m in JS_IMPORT.finditer(text))
        elif ext in (".json", ".yaml", ".yml", ".cfg", ".ini"):
            refs.update(m.group(1) for m in CONFIG_REF.finditer(text))
        return refs

    def _python_imports(self, text: str) -> Set[str]:
        refs: Set[str] = set()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return refs
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    refs.add(alias.name.split(".")[0] + ".py")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    refs.add(node.module.replace(".", "/") + ".py")
        return refs

    def _resolve_ref(
        self, ref, base_dir, path_by_name, path_by_stem, all_files
    ) -> FileDescriptor | None:
        ref_path = Path(ref)
        candidates = [
            base_dir / ref,
            base_dir / ref_path.name,
            base_dir / (ref_path.stem + ".py"),
        ]
        for c in candidates:
            norm = str(c.resolve()).replace("\\", "/")
            for f in all_files:
                if f.path == norm or f.name == c.name:
                    return f
        stem = ref_path.stem
        if stem in path_by_stem:
            return path_by_stem[stem]
        name = ref_path.name
        return path_by_name.get(name)
