from __future__ import annotations

from typing import Callable

from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore

ProgressCallback = Callable[[int, int, str], None]


def build_corpus_from_graph(
    graph: GraphStore,
    chroma: ChromaStore,
    *,
    on_progress: ProgressCallback | None = None,
) -> list[dict[str, str]]:
    corpus: list[dict[str, str]] = []
    files = graph.list_all_files()
    total = len(files)
    if on_progress:
        on_progress(0, total, f"构建检索语料 0/{total}")
    for i, f in enumerate(files):
        fid = f["file_id"]
        node = graph.get_file(fid) or {}
        text = (node.get("summary") or "") + " " + (node.get("name") or "")
        corpus.append({"file_id": fid, "name": node.get("name", ""), "text": text})
        if on_progress and (i % 800 == 0 or i + 1 == total):
            on_progress(i + 1, total, f"构建检索语料 {i + 1}/{total}")
    return corpus
