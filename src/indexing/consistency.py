from __future__ import annotations

import logging
from pathlib import Path

from src.indexing.file_id import get_file_id
from src.models.descriptor import FileStatus
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """方案 4.4.2：向量-图对账、GHOST 标记与自愈。"""

    def __init__(self, graph: GraphStore, chroma: ChromaStore | None) -> None:
        self.graph = graph
        self.chroma = chroma
        self.log: list[str] = []

    def run(self) -> dict[str, int]:
        stats = {"ghost": 0, "dangling_marked": 0, "vector_repaired": 0, "dead_edges": 0, "archived": 0, "rescanned": 0}

        graph_ids = set()
        for item in self.graph.list_all_files():
            fid = item["file_id"]
            graph_ids.add(fid)
            node = self.graph.get_file(fid) or item
            path = node.get("path", "")
            if not path or not Path(path).exists():
                if node.get("status") not in (FileStatus.ARCHIVED.value, FileStatus.GHOST.value):
                    self._archive_missing(fid, node)
                    stats["archived"] += 1
                    self.log.append(f"ARCHIVED: {fid} {path}")
                    continue
                if self._try_resolve_ghost(fid, path):
                    stats["ghost"] += 1
                    self.log.append(f"GHOST: {fid} {path}")
                else:
                    if hasattr(self.graph, "mark_dangling_relations"):
                        self.graph.mark_dangling_relations(fid)
                        stats["dangling_marked"] += 1

        if self.chroma:
            chroma_ids = set(self.chroma.list_file_ids())
            for fid in chroma_ids - graph_ids:
                self.chroma.delete_file(fid)
                stats["dead_edges"] += 1
                self.log.append(f"removed orphan vector: {fid}")
            for fid in graph_ids:
                node = self.graph.get_file(fid)
                if not node or node.get("status") == FileStatus.GHOST.value:
                    continue
                if fid not in chroma_ids and node.get("summary"):
                    try:
                        from src.indexing.scanner import build_descriptor

                        desc = build_descriptor(Path(node["path"]))
                        desc.file_id = fid
                        self.chroma.upsert_file(desc)
                        stats["vector_repaired"] += 1
                        self.log.append(f"repaired vector: {fid}")
                    except Exception as e:
                        self.log.append(f"vector repair failed {fid}: {e}")

        if hasattr(self.graph, "flush"):
            self.graph.flush()
        return stats

    def global_consistency_check(self, watch_roots: list[str] | None = None) -> dict[str, int]:
        """规格 5.4：图-向量-物理文件三方对齐。"""
        stats = self.run()
        if self.chroma:
            chroma_ids = set(self.chroma.list_file_ids())
            graph_ids = {f["file_id"] for f in self.graph.list_all_files()}
            for missing in chroma_ids - graph_ids:
                self.chroma.delete_file(missing)
                stats["dead_edges"] = stats.get("dead_edges", 0) + 1
            for fid in graph_ids - chroma_ids:
                node = self.graph.get_file(fid)
                if node and node.get("summary"):
                    try:
                        from src.indexing.scanner import build_descriptor

                        desc = build_descriptor(Path(node["path"]))
                        desc.file_id = fid
                        self.chroma.upsert_file(desc)
                        stats["vector_repaired"] = stats.get("vector_repaired", 0) + 1
                    except Exception:
                        pass
        if watch_roots:
            from src.indexing.builder import IndexBuilder

            builder = IndexBuilder(neo4j=self.graph, chroma=self.chroma)
            for root in watch_roots:
                root_p = Path(root)
                if not root_p.is_dir():
                    continue
                indexed_paths = {
                    (self.graph.get_file(f["file_id"]) or f).get("path")
                    for f in self.graph.list_all_files()
                }
                for fp in root_p.rglob("*"):
                    if fp.is_file() and str(fp.resolve()) not in indexed_paths:
                        try:
                            builder.index_single(fp)
                            stats["rescanned"] = stats.get("rescanned", 0) + 1
                        except Exception:
                            pass
        return stats

    def _archive_missing(self, fid: str, node: dict) -> None:
        updates = {"status": FileStatus.ARCHIVED.value, "path": None}
        if hasattr(self.graph, "_nodes") and fid in self.graph._nodes:
            self.graph._nodes[fid].update(updates)
        elif hasattr(self.graph, "patch_file"):
            self.graph.patch_file(fid, updates)

    def _try_resolve_ghost(self, fid: str, path: str) -> bool:
        if not path:
            self._mark_ghost(fid)
            return True
        p = Path(path)
        if p.exists():
            return False
        try:
            new_id = get_file_id(p, mode="volume")
        except Exception:
            new_id = None
        if new_id and new_id != fid and self.graph.get_file(new_id):
            return False
        self._mark_ghost(fid)
        return True

    def _mark_ghost(self, fid: str) -> None:
        if hasattr(self.graph, "_nodes") and fid in self.graph._nodes:
            self.graph._nodes[fid]["status"] = FileStatus.GHOST.value
        elif hasattr(self.graph, "set_file_status"):
            self.graph.set_file_status(fid, FileStatus.GHOST.value)
