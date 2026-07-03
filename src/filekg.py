"""FileKG 统一门面 API（规格 7.3）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import settings
from src.indexing.builder import IndexBuilder
from src.indexing.consistency import ConsistencyChecker
from src.search.engine import SearchEngine
from src.storage.factory import create_stores
from src.watcher.monitor import FileWatcher


@dataclass
class SearchResult:
    vfe_id: str
    path: str
    name: str
    score: float
    explanation: str
    fidelity: float
    factor_scores: dict[str, float]
    explanation_paths: list[dict]


class FileKG:
    """论文/规格对齐的高层 API。"""

    def __init__(self) -> None:
        self.graph, self.chroma = create_stores()
        self.builder = IndexBuilder(neo4j=self.graph, chroma=self.chroma)
        self.search_engine = SearchEngine(self.graph, self.chroma)
        self._watcher: FileWatcher | None = None

    def index_file(self, path: str | Path) -> str:
        path = Path(path)
        from src.indexing.file_id import get_file_id

        self.builder.index_single(path)
        try:
            return get_file_id(path, mode=getattr(self.builder, "_id_mode", "volume"))
        except Exception:
            return ""

    def handle_event(self, event: dict[str, Any]) -> None:
        """处理文件系统事件：Create/Modify/Delete/Move。"""
        etype = (event.get("type") or "").lower()
        path = event.get("path") or event.get("file_path")
        if not path:
            return
        if etype in ("create", "created"):
            self.builder.index_single(path)
        elif etype in ("modify", "modified"):
            self.builder.index_single(path)
        elif etype in ("delete", "deleted"):
            from src.models.descriptor import FileStatus

            try:
                from src.indexing.file_id import get_file_id

                fid = get_file_id(path)
            except Exception:
                return
            if hasattr(self.graph, "patch_file"):
                self.graph.patch_file(fid, {"status": FileStatus.ARCHIVED.value, "path": None})
        elif etype in ("move", "moved"):
            dest = event.get("dest_path") or event.get("new_path")
            if dest:
                self.builder.relocate_file(path, dest)

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        out = self.search_engine.search(query)
        results: list[SearchResult] = []
        limit = top_k or settings.result_top_n
        for r in out.get("results", [])[:limit]:
            results.append(
                SearchResult(
                    vfe_id=r.get("file_id", ""),
                    path=r.get("path", ""),
                    name=r.get("name", ""),
                    score=float(r.get("score", 0)),
                    explanation=r.get("explanation", ""),
                    fidelity=float(r.get("fidelity", 0)),
                    factor_scores=r.get("factor_scores") or {},
                    explanation_paths=r.get("explanation_paths") or [],
                )
            )
        return results

    def get_subgraph(self, vfe_id: str, hops: int = 1) -> dict:
        return self.search_engine.navigate_from(vfe_id)

    def update_tags(self, vfe_id: str, tags: list[str]) -> None:
        node = self.graph.get_file(vfe_id)
        if not node:
            return
        merged = list(dict.fromkeys((node.get("tags") or []) + tags))
        if hasattr(self.graph, "patch_file"):
            self.graph.patch_file(vfe_id, {"tags": merged})
        for tag in tags:
            if hasattr(self.graph, "add_tag_edge"):
                self.graph.add_tag_edge(vfe_id, tag)

    def run_consistency_check(self, *, watch_roots: list[str] | None = None) -> dict:
        checker = ConsistencyChecker(self.graph, self.chroma)
        return checker.global_consistency_check(watch_roots or settings.index_watch_roots)

    def start_watch(self, roots: list[str] | None = None) -> None:
        self._watcher = FileWatcher(roots or settings.index_watch_roots, self.builder)
        self._watcher.start(blocking=False)

    def close(self) -> None:
        if self._watcher:
            self._watcher.stop()
        if hasattr(self.graph, "close"):
            self.graph.close()
