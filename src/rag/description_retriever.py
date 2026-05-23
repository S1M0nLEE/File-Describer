"""在节点 Description（summary / ai_summary）上快速召回，供 RAG 使用。"""
from __future__ import annotations

import heapq
import logging
import re
from typing import Any, Iterator

from src.api.path_scope import is_benchmark_path
from src.config import settings
from src.indexing.embedder import Embedder
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-z0-9_]{2,}", re.I)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text.lower())]


def _iter_node_props(graph: GraphStore) -> Iterator[tuple[str, dict[str, Any]]]:
    if hasattr(graph, "_nodes"):
        yield from graph._nodes.items()
        return
    for rec in graph.list_all_files():
        fid = rec.get("file_id")
        if not fid:
            continue
        props = graph.get_file(fid)
        if props:
            yield fid, props


def _node_description(props: dict[str, Any]) -> str:
    parts = [
        props.get("ai_summary") or "",
        props.get("summary") or "",
        props.get("name") or "",
    ]
    return "\n".join(p for p in parts if p and str(p).strip()).strip()


class DescriptionRetriever:
    """
    检索流程（对齐「Description 节点 + Top-K + API 理解」）：
    1. 在已索引节点的 description 文本上打分（不读磁盘原文）
    2. 可选 Chroma 文件级向量补充
    3. 合并排序，返回 top_k 个节点
    """

    def __init__(
        self,
        graph: GraphStore,
        chroma: ChromaStore,
        embedder: Embedder | None = None,
    ) -> None:
        self.graph = graph
        self.chroma = chroma
        self.embedder = embedder or Embedder.get()

    def retrieve(
        self,
        question: str,
        *,
        top_k: int | None = None,
        include_benchmark: bool = False,
    ) -> list[dict[str, Any]]:
        k = top_k or settings.rag_top_k
        tokens = _tokenize(question)
        q_lower = question.lower()
        pool_limit = int(getattr(settings, "rag_desc_pool", 800) or 800)

        semantic: dict[str, float] = {}
        primary = ""
        if tokens:
            long_tokens = [t for t in tokens if len(t) >= 4]
            primary = max(long_tokens, key=len) if long_tokens else tokens[0]

        use_semantic = self.chroma.is_healthy() and not primary
        if use_semantic:
            try:
                q_emb = self.embedder.embed(question)
                for h in self.chroma.search_files(q_emb, n_results=min(k * 4, 40)):
                    fid = h.get("file_id")
                    if fid:
                        semantic[fid] = float(h.get("similarity", 0))
            except Exception as e:
                logger.debug("Chroma 文件级检索跳过: %s", e)

        scored: list[tuple[float, str, dict[str, Any]]] = []
        scanned = 0
        for fid, props in _iter_node_props(self.graph):
            scanned += 1
            path = props.get("path") or ""
            path_l = path.lower()
            name_l = (props.get("name") or "").lower()
            if not include_benchmark and is_benchmark_path(path):
                continue
            if props.get("is_inside_archive"):
                continue

            if primary and primary not in path_l and primary not in name_l:
                if fid not in semantic:
                    continue

            desc = _node_description(props)
            if not desc and not path:
                continue

            blob = f"{path}\n{name_l}\n{desc.lower()}"
            if tokens and not any(t in blob for t in tokens):
                if fid not in semantic:
                    continue

            score = 0.0
            for t in tokens:
                if t in path.lower():
                    score += 4.0
                if t in name_l:
                    score += 2.5
                if t in desc.lower():
                    score += 1.0

            if "main" in q_lower or "入口" in question:
                if name_l in ("main.py", "__main__.py") or name_l.endswith("main.py"):
                    score += 6.0
                if "__main__" in path_l or "/cli/" in path_l.replace("\\", "/"):
                    score += 3.0

            if path_l.replace("\\", "/").endswith("uniflo/__main__.py"):
                score += 20.0
            elif "uniflo" in path_l and (
                name_l == "__main__.py" or "/uniflo/cli/" in path_l.replace("\\", "/")
            ):
                score += 10.0
            if "/raw_downloads/" in path_l or "\\raw_downloads\\" in path_l:
                score -= 8.0
            if "third_party" in path_l:
                score -= 2.0

            if fid in semantic:
                score += semantic[fid] * 8.0

            if score <= 0 and fid not in semantic:
                continue

            scored.append((score, fid, props))

        if len(scored) > pool_limit:
            scored = heapq.nlargest(pool_limit, scored, key=lambda x: x[0])

        top = heapq.nlargest(k, scored, key=lambda x: x[0])
        logger.info(
            "Description 检索: 扫描 %d 节点, 候选 %d, 返回 %d",
            scanned,
            len(scored),
            len(top),
        )

        out: list[dict[str, Any]] = []
        max_score = top[0][0] if top else 1.0
        for rank, (score, fid, props) in enumerate(top, start=1):
            desc = _node_description(props)
            out.append(
                {
                    "file_id": fid,
                    "path": props.get("path", ""),
                    "name": props.get("name", ""),
                    "description": desc,
                    "document": desc[: settings.rag_chunk_max_chars],
                    "similarity": round(score / max_score, 4),
                    "rank": rank,
                    "score": round(score, 3),
                    "source": "description",
                }
            )
        return out
