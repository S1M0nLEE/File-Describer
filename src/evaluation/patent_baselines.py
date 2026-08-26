"""代表性专利方案的检索代理基线（同基准、同指标可比）。"""
from __future__ import annotations

from typing import Any

from src.evaluation.baselines import Baseline, _tokenize
from src.indexing.embedder import Embedder
from src.search.engine import SearchEngine
from src.search.intent_parser import IntentParser
from src.storage.chroma_store import ChromaStore


class PatentIFlytekBaseline(Baseline):
    """科大讯飞 CN121981233A：强约束 KG 检索 ≈ 元数据过滤 + 向量 + 关键词融合（无多关系图扩展）。"""

    name = "Patent-IFlytek-KG"

    def __init__(self, chroma: ChromaStore, corpus_meta: list[dict[str, str]]) -> None:
        self.chroma = chroma
        self.embedder = Embedder.get()
        self.intent = IntentParser()
        from rank_bm25 import BM25Okapi

        self._meta = corpus_meta
        self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in corpus_meta])
        self._fid_to_idx = {c["file_id"]: i for i, c in enumerate(corpus_meta)}

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        parsed = self.intent.parse(query)
        emb = self.embedder.embed(parsed.keywords or query)
        vec_hits = self.chroma.search_chunks(
            emb, n_results=k * 3, where=parsed.chroma_where()
        )
        bm25_scores = self._bm25.get_scores(_tokenize(parsed.keywords or query))
        merged: dict[str, float] = {}
        for h in vec_hits:
            fid = h.get("file_id")
            if fid:
                merged[fid] = max(merged.get(fid, 0), h["similarity"] * 0.55)
        for i, s in enumerate(bm25_scores):
            if s <= 0:
                continue
            fid = self._meta[i]["file_id"]
            merged[fid] = merged.get(fid, 0) + (s / (max(bm25_scores) or 1)) * 0.45
        ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)[:k]
        name_map = {c["file_id"]: c["name"] for c in self._meta}
        return [
            {
                "name": name_map.get(fid, ""),
                "file_id": fid,
                "score": sc,
                "explanation_paths": [],
                "is_seed": True,
            }
            for fid, sc in ranked
        ]


class PatentInspurBaseline(Baseline):
    """浪潮 CN120493935A：KG+RAG ≈ 向量召回 + BM25 重排（无图路径、无可解释边）。"""

    name = "Patent-Inspur-RAG"

    def __init__(self, chroma: ChromaStore, corpus_meta: list[dict[str, str]]) -> None:
        self.chroma = chroma
        self.embedder = Embedder.get()
        from rank_bm25 import BM25Okapi

        self._meta = corpus_meta
        self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in corpus_meta])

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        emb = self.embedder.embed(query)
        hits = self.chroma.search_chunks(emb, n_results=k * 4)
        seen: dict[str, dict] = {}
        for h in hits:
            fid = h.get("file_id")
            if not fid:
                continue
            if fid not in seen or h["similarity"] > seen[fid]["_vec"]:
                seen[fid] = {
                    "name": h.get("name", ""),
                    "file_id": fid,
                    "_vec": h["similarity"],
                }
        bm25 = list(self._bm25.get_scores(_tokenize(query)))
        max_b = max(bm25) if bm25 else 1.0
        out = []
        for fid, item in seen.items():
            idx = next((i for i, c in enumerate(self._meta) if c["file_id"] == fid), None)
            b = (bm25[idx] / max_b) if idx is not None and max_b > 0 else 0
            out.append(
                {
                    "name": item["name"],
                    "file_id": fid,
                    "score": 0.4 * item["_vec"] + 0.6 * b,
                    "explanation_paths": [],
                    "is_seed": True,
                }
            )
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:k]


class PatentMicrosoftBaseline(Baseline):
    """微软 US12405821B2：行为序列 ≈ 仅 WORKFLOW_WITH 图扩展。"""

    name = "Patent-MS-ActionSeq"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(
            query, expand_graph=True, allowed_relations={"WORKFLOW_WITH"}
        )
        return r["results"][:k]


class PatentSnapBaseline(Baseline):
    """Snap US2025/0259463：视觉/相似 ≈ SIMILAR_TO + VISUALLY_SIMILAR_TO 扩展。"""

    name = "Patent-Snap-Visual"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(
            query,
            expand_graph=True,
            allowed_relations={"SIMILAR_TO", "VISUALLY_SIMILAR_TO"},
        )
        return r["results"][:k]


def build_patent_baselines(
    engine: SearchEngine,
    chroma: ChromaStore,
    corpus: list[dict[str, str]],
) -> list[Baseline]:
    return [
        PatentIFlytekBaseline(chroma, corpus),
        PatentInspurBaseline(chroma, corpus),
        PatentMicrosoftBaseline(engine),
        PatentSnapBaseline(engine),
    ]
