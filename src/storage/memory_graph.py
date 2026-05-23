from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import settings
from src.models.descriptor import FileDescriptor
from src.storage import graph_disk_cache

logger = logging.getLogger(__name__)


class MemoryGraphStore:
    """Neo4j 不可用时的本地 JSON 图存储（功能等价子集）。"""

    def __init__(self, path: Path | None = None, *, defer_load: bool = False) -> None:
        settings.ensure_dirs()
        self.path = path or (settings.data_dir / "graph_store.json")
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._loaded = not defer_load
        self._dirty = False
        if not defer_load:
            self._load()

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _ensure_loaded(self) -> None:
        self.ensure_loaded()

    def _load(self) -> None:
        if not self.path.exists():
            return
        if settings.api_disk_cache:
            cached = graph_disk_cache.try_load(self.path)
            if cached is not None:
                self._nodes, self._edges = cached
                self._dirty = False
                return
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return
            data = json.loads(raw)
            self._nodes = data.get("nodes", {})
            self._edges = data.get("edges", [])
            self._dirty = False
            if settings.api_disk_cache and self._nodes:
                graph_disk_cache.write(self.path, self._nodes, self._edges)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("图存储文件损坏，将重建: %s", e)
            self._nodes = {}
            self._edges = []

    def _save(self) -> None:
        self._ensure_loaded()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"nodes": self._nodes, "edges": self._edges},
            ensure_ascii=False,
            indent=2,
        )
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.path)
        if settings.api_disk_cache:
            graph_disk_cache.write(self.path, self._nodes, self._edges)
        self._dirty = False

    def close(self, *, persist: bool | None = None) -> None:
        self._ensure_loaded()
        if persist is None:
            persist = self._dirty
        if persist and self._dirty:
            self._save()

    def clear_all(self) -> None:
        self._ensure_loaded()
        self._nodes.clear()
        self._edges.clear()
        self._dirty = True
        self._save()
        if settings.api_disk_cache:
            graph_disk_cache.invalidate(self.path)

    def upsert_file(self, desc: FileDescriptor, *, persist: bool = False) -> None:
        self._ensure_loaded()
        self._nodes[desc.file_id] = desc.to_neo4j_props()
        self._dirty = True
        if persist:
            self._save()

    def upsert_files(self, descriptors: list[FileDescriptor]) -> None:
        self._ensure_loaded()
        for d in descriptors:
            self._nodes[d.file_id] = d.to_neo4j_props()
        self._dirty = True

    def create_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
        *,
        weight: float = 1.0,
        props: dict[str, Any] | None = None,
        symmetric: bool = False,
    ) -> None:
        self._ensure_loaded()
        edge = {
            "src": src_id,
            "type": rel_type,
            "dst": dst_id,
            "weight": weight,
            **(props or {}),
        }
        self._edges.append(edge)
        if symmetric:
            self._edges.append({**edge, "src": dst_id, "dst": src_id})
        self._dirty = True

    def flush(self) -> None:
        self._ensure_loaded()
        self._save()

    def create_symmetric_relation(
        self, a_id: str, rel_type: str, b_id: str, **kwargs: Any
    ) -> None:
        self.create_relation(a_id, rel_type, b_id, symmetric=True, **kwargs)

    def delete_file(self, file_id: str) -> None:
        self._ensure_loaded()
        self._dirty = True
        self._nodes.pop(file_id, None)
        self._edges = [
            e for e in self._edges if e["src"] != file_id and e["dst"] != file_id
        ]
        self._save()

    def update_path(self, file_id: str, new_path: str, new_name: str) -> None:
        self._ensure_loaded()
        if file_id in self._nodes:
            self._nodes[file_id]["path"] = new_path
            self._nodes[file_id]["name"] = new_name
            self._save()

    def get_neighbors(
        self,
        file_id: str,
        rel_types: list[str] | None = None,
        hops: int = 1,
    ) -> list[dict[str, Any]]:
        self._ensure_loaded()
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        frontier = {file_id}

        for _ in range(hops):
            next_frontier: set[str] = set()
            for fid in frontier:
                for e in self._edges:
                    if rel_types and e["type"] not in rel_types:
                        continue
                    other = None
                    direction_from = fid
                    if e["src"] == fid:
                        other = e["dst"]
                    elif e["dst"] == fid:
                        other = e["src"]
                        direction_from = fid
                    if not other or other == file_id:
                        continue
                    if other in seen:
                        continue
                    node = self._nodes.get(other)
                    if not node:
                        continue
                    seen.add(other)
                    next_frontier.add(other)
                    edge_props = {
                        k: e[k]
                        for k in (
                            "confidence",
                            "relation_subtype",
                            "relation_label",
                            "s_visual",
                            "s_text",
                            "s_doc",
                            "phash_dist",
                            "short_circuit",
                            "similarity",
                        )
                        if k in e
                    }
                    results.append(
                        {
                            "file_id": other,
                            "path": node.get("path", ""),
                            "name": node.get("name", ""),
                            "rel_type": e["type"],
                            "weight": e.get("weight", 1.0),
                            "from_id": direction_from,
                            "props": edge_props,
                        }
                    )
            frontier = next_frontier
        return results

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        self._ensure_loaded()
        return self._nodes.get(file_id)

    def patch_file(self, file_id: str, updates: dict[str, Any]) -> None:
        self._ensure_loaded()
        if file_id in self._nodes:
            self._nodes[file_id].update(updates)

    def set_file_status(self, file_id: str, status: str) -> None:
        self._ensure_loaded()
        if file_id in self._nodes:
            self._nodes[file_id]["status"] = status

    def count_relations_by_type(self) -> dict[str, int]:
        self._ensure_loaded()
        from collections import Counter

        return dict(Counter(e["type"] for e in self._edges))

    def list_all_files(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        return [
            {
                "file_id": fid,
                "path": n.get("path"),
                "name": n.get("name"),
                "status": n.get("status"),
                "modified_time": n.get("modified_time"),
            }
            for fid, n in self._nodes.items()
        ]

    def indexed_mtime_by_path(self, root: Path) -> dict[str, str]:
        """返回 root 下已索引文件的 path -> modified_time(iso)。"""
        self._ensure_loaded()
        root = root.resolve()
        out: dict[str, str] = {}
        for n in self._nodes.values():
            p = n.get("path")
            if not p:
                continue
            try:
                resolved = Path(p).resolve()
                if resolved.is_relative_to(root):
                    out[str(resolved)] = str(n.get("modified_time") or "")
            except (OSError, ValueError):
                continue
        return out

    def mark_dangling_relations(self, deleted_id: str) -> None:
        self._ensure_loaded()
        for e in self._edges:
            if e["dst"] == deleted_id:
                e["dangling"] = True
        self._save()
