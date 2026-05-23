from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Any

from rank_bm25 import BM25Okapi

from src.config import settings
from src.indexing.embedder import Embedder
from src.search.corpus import build_corpus_from_graph
from src.search.engine import SearchEngine
from src.search.intent_parser import IntentParser
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    chars = re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", text)
    return chars if chars else text.split()


class Baseline(ABC):
    name: str = "baseline"

    @abstractmethod
    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        ...

    def search_names(self, query: str, k: int = 20) -> list[str]:
        return [r.get("name", "") for r in self.search(query, k)]


class BM25Baseline(Baseline):
    name = "BM25"

    def __init__(self, corpus: list[dict[str, str]]) -> None:
        self._meta = corpus
        self._tokenized = [_tokenize(c["text"]) for c in corpus]
        self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            {
                "name": self._meta[i]["name"],
                "file_id": self._meta[i]["file_id"],
                "score": float(scores[i]),
                "explanation_paths": [],
                "is_seed": True,
            }
            for i in ranked
            if scores[i] > 0
        ]


class VectorOnlyBaseline(Baseline):
    name = "VectorOnly"

    def __init__(self, chroma: ChromaStore) -> None:
        self.chroma = chroma
        self.embedder = Embedder.get()

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        emb = self.embedder.embed(query)
        hits = self.chroma.search_chunks(emb, n_results=k * 2)
        seen: dict[str, dict] = {}
        for h in hits:
            fid = h.get("file_id")
            if not fid:
                continue
            if fid not in seen or h["similarity"] > seen[fid]["score"]:
                seen[fid] = {
                    "name": h.get("name", ""),
                    "file_id": fid,
                    "score": h["similarity"],
                    "explanation_paths": [],
                    "is_seed": True,
                }
        return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:k]


class VectorMetadataBaseline(Baseline):
    name = "Vector+Metadata"

    def __init__(self, chroma: ChromaStore) -> None:
        self.chroma = chroma
        self.embedder = Embedder.get()
        self.intent = IntentParser()

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        parsed = self.intent.parse(query)
        emb = self.embedder.embed(parsed.keywords or query)
        hits = self.chroma.search_chunks(
            emb, n_results=k * 2, where=parsed.chroma_where()
        )
        seen: dict[str, dict] = {}
        for h in hits:
            fid = h.get("file_id")
            if not fid:
                continue
            if fid not in seen or h["similarity"] > seen[fid]["score"]:
                seen[fid] = {
                    "name": h.get("name", ""),
                    "file_id": fid,
                    "score": h["similarity"],
                    "explanation_paths": [],
                    "is_seed": True,
                }
        return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:k]


class VectorSimilarOnlyBaseline(Baseline):
    name = "Vector+SIMILAR_TO"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(
            query, expand_graph=True, allowed_relations={"SIMILAR_TO"}
        )
        return r["results"][:k]


class FullKGBaseline(Baseline):
    name = "FileKG-Full"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(
            query, expand_graph=True, hops=settings.graph_hops
        )
        return r["results"][:k]


def build_baselines(
    graph: GraphStore,
    chroma: ChromaStore,
    engine: SearchEngine,
    corpus: list[dict[str, str]],
    *,
    include_patent_proxies: bool = True,
) -> list[Baseline]:
    from src.evaluation.patent_baselines import build_patent_baselines

    baselines: list[Baseline] = [
        BM25Baseline(corpus),
        VectorOnlyBaseline(chroma),
        VectorMetadataBaseline(chroma),
        VectorSimilarOnlyBaseline(engine),
    ]
    if include_patent_proxies:
        baselines.extend(build_patent_baselines(engine, chroma, corpus))
    baselines.append(FullKGBaseline(engine))
    return baselines


