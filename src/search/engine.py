from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from rank_bm25 import BM25Okapi

from src.behavior.collector import WorkflowCollector
from src.config import settings
from src.indexing.access_memory import AccessMemory
from src.search.corpus import build_corpus_from_graph
from src.search import corpus_cache
from src.indexing.embedder import Embedder
from src.search.graph_expander import GraphExpander
from src.search.intent_parser import IntentParser
from src.search.ranker import MultiFactorRanker, _tokenize
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)


class SearchEngine:
    def __init__(
        self,
        neo4j: GraphStore,
        chroma: ChromaStore,
        *,
        lazy_corpus: bool = False,
    ) -> None:
        self.neo4j = neo4j
        self.chroma = chroma
        self.intent = IntentParser()
        self.expander = GraphExpander(neo4j)
        self._corpus: list[dict[str, str]] | None = None
        self._bm25_bundle: tuple[Any, list[dict[str, str]], dict[str, int]] | None = None
        self.ranker = MultiFactorRanker(neo4j, chroma, bm25_bundle=None)
        if not lazy_corpus:
            self._init_corpus()
        self.embedder = Embedder.get()
        self._access = AccessMemory(neo4j)
        self._workflow = WorkflowCollector()

    def invalidate_corpus(self) -> None:
        self._corpus = None
        self._bm25_bundle = None
        self.ranker._bm25_bundle = None

    def _init_corpus(self, *, on_progress=None) -> None:
        if self._corpus is not None:
            return
        t0 = time.perf_counter()
        graph_path = getattr(self.neo4j, "path", None)
        if settings.api_disk_cache and graph_path is not None:
            cached = corpus_cache.try_load(graph_path, settings.data_dir)
            if cached is not None:
                self._corpus = cached
                if len(self._corpus) <= 25000:
                    self._bm25_bundle = self._build_bm25_bundle(self._corpus)
                else:
                    self._bm25_bundle = None
                self.ranker._bm25_bundle = self._bm25_bundle
                logger.info(
                    "检索语料从缓存恢复 %d 条 (%.1fs)",
                    len(self._corpus),
                    time.perf_counter() - t0,
                )
                return
        self._corpus = build_corpus_from_graph(
            self.neo4j, self.chroma, on_progress=on_progress
        )
        if len(self._corpus) <= 25000:
            self._bm25_bundle = self._build_bm25_bundle(self._corpus)
        else:
            logger.info("语料 %d 条，BM25 将在首次检索时构建", len(self._corpus))
            self._bm25_bundle = None
        self.ranker._bm25_bundle = self._bm25_bundle
        if settings.api_disk_cache and graph_path is not None:
            corpus_cache.write(graph_path, settings.data_dir, self._corpus)
        logger.info("检索语料就绪 %d 条 (%.1fs)", len(self._corpus), time.perf_counter() - t0)

    def _get_corpus(self) -> list[dict[str, str]]:
        if self._corpus is None:
            self._init_corpus()
        return self._corpus or []

    def _build_bm25_bundle(
        self, corpus: list[dict[str, str]]
    ) -> tuple[Any, list[dict[str, str]], dict[str, int]] | None:
        tokenized = [_tokenize(c["text"]) for c in corpus]
        if not tokenized:
            return None
        bm25 = BM25Okapi(tokenized)
        fid_map = {c["file_id"]: i for i, c in enumerate(corpus)}
        return bm25, corpus, fid_map

    def _ensure_bm25_bundle(self) -> tuple[Any, list[dict[str, str]], dict[str, int]] | None:
        if self._bm25_bundle is not None:
            return self._bm25_bundle
        corpus = self._get_corpus()
        if not corpus or len(corpus) > 25000:
            return None
        try:
            logger.info("构建 BM25 索引（%d 条）…", len(corpus))
            self._bm25_bundle = self._build_bm25_bundle(corpus)
            self.ranker._bm25_bundle = self._bm25_bundle
        except MemoryError:
            logger.warning("BM25 内存不足，将使用关键词扫描回退")
            self._bm25_bundle = None
        return self._bm25_bundle

    def _seeds_from_bm25(
        self, query: str, parsed: Any, *, n: int | None = None
    ) -> dict[str, dict]:
        bundle = self._ensure_bm25_bundle()
        if bundle:
            bm25, corpus, _fid_map = bundle
            scores = list(bm25.get_scores(_tokenize(parsed.keywords or query)))
            if scores:
                max_s = max(scores) or 1.0
                top_n = n or settings.seed_top_n
                seed_map: dict[str, dict] = {}
                for idx in sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )[:top_n]:
                    if scores[idx] <= 0:
                        break
                    fid = corpus[idx]["file_id"]
                    node = self.neo4j.get_file(fid)
                    if not node or node.get("is_inside_archive"):
                        continue
                    seed_map[fid] = {
                        "file_id": fid,
                        "path": node.get("path", ""),
                        "name": node.get("name", ""),
                        "similarity": float(scores[idx] / max_s),
                    }
                if seed_map:
                    return seed_map
        return self._seeds_from_keywords(query, parsed, n=n)

    def _seeds_from_keywords(
        self, query: str, parsed: Any, *, n: int | None = None
    ) -> dict[str, dict]:
        """大规模语料下的轻量回退（不构建 BM25 倒排）。"""
        kws = _tokenize(parsed.keywords or query)
        if not kws:
            return {}
        top_n = n or settings.seed_top_n
        ranked: list[tuple[int, str, dict]] = []
        for f in self.neo4j.list_all_files():
            fid = f.get("file_id")
            if not fid:
                continue
            node = self.neo4j.get_file(fid) or f
            if node.get("is_inside_archive"):
                continue
            text = (
                (node.get("name") or "")
                + " "
                + (node.get("summary") or "")
                + " "
                + (node.get("ai_summary") or "")
            ).lower()
            score = sum(1 for kw in kws if kw in text)
            if score > 0:
                ranked.append((score, fid, node))
        ranked.sort(key=lambda x: x[0], reverse=True)
        max_s = ranked[0][0] if ranked else 1
        seed_map: dict[str, dict] = {}
        for score, fid, node in ranked[:top_n]:
            seed_map[fid] = {
                "file_id": fid,
                "path": node.get("path", ""),
                "name": node.get("name", ""),
                "similarity": float(score / max_s),
            }
        return seed_map

    def search(
        self,
        query: str,
        *,
        expand_graph: bool = True,
        allowed_relations: set[str] | None = None,
        seed_file_id: str | None = None,
        hops: int | None = None,
    ) -> dict:
        parsed = self.intent.parse(query)
        query_emb = self.embedder.embed(parsed.keywords or query)

        chunk_hits = self.chroma.search_chunks(
            query_emb,
            n_results=settings.seed_top_n,
            where=parsed.chroma_where(),
        )

        seed_map: dict[str, dict] = {}
        for h in chunk_hits:
            fid = h["file_id"]
            if not fid:
                continue
            if fid not in seed_map or h["similarity"] > seed_map[fid]["similarity"]:
                seed_map[fid] = {
                    "file_id": fid,
                    "path": h.get("path", ""),
                    "name": h.get("name", ""),
                    "similarity": h["similarity"],
                }

        if not seed_map:
            file_hits = self.chroma.search_files(query_emb, n_results=settings.seed_top_n)
            for h in file_hits:
                meta = h.get("metadata") or {}
                seed_map[h["file_id"]] = {
                    "file_id": h["file_id"],
                    "path": meta.get("path", ""),
                    "name": meta.get("name", ""),
                    "similarity": h["similarity"],
                }

        if not seed_map:
            seed_map = self._seeds_from_bm25(query, parsed)

        if seed_file_id:
            node = self.neo4j.get_file(seed_file_id)
            if node:
                seed_map = {
                    seed_file_id: {
                        "file_id": seed_file_id,
                        "path": node.get("path", ""),
                        "name": node.get("name", ""),
                        "similarity": 1.0,
                    }
                }

        if settings.multimodal_enabled and settings.multimodal_fuse_visual_search:
            self._merge_visual_seeds(query, parsed, seed_map)

        seeds = list(seed_map.values())
        hop_n = hops if hops is not None else settings.graph_hops

        if expand_graph and seeds:
            graph_hits = self.expander.expand_seeds(
                seeds,
                hops=hop_n,
                allowed_relations=allowed_relations,
            )
        else:
            from src.search.graph_expander import GraphHit

            graph_hits = {
                s["file_id"]: GraphHit(
                    file_id=s["file_id"],
                    path=s.get("path", ""),
                    name=s.get("name", ""),
                    is_seed=True,
                    seed_similarity=s["similarity"],
                    graph_weight=1.0,
                )
                for s in seeds
            }

        ranked = self.ranker.rank(query, parsed, graph_hits, query_emb)
        ranked = self._inject_bm25_candidates(query, parsed, graph_hits, ranked)
        ranked = self._merge_near_duplicate_in_results(ranked)

        for r in ranked[:10]:
            rel = None
            paths = r.get("explanation_paths") or []
            if paths:
                rel = paths[0].get("rel_type")
            self._access.record_hit(r["file_id"], query, relation_type=rel)
            if r.get("path"):
                self._workflow.record_open(r["path"])

        return {
            "query": query,
            "parsed": {
                "keywords": parsed.keywords,
                "extensions": parsed.extensions,
                "modified_after": parsed.modified_after.isoformat()
                if parsed.modified_after
                else None,
            },
            "seed_count": len(seeds),
            "results": ranked,
            "graph_edges": self._build_graph_view(ranked),
        }

    def navigate_from(
        self, file_id: str, relation_type: str | None = None
    ) -> dict:
        rel_types = [relation_type] if relation_type else None
        neighbors = self.neo4j.get_neighbors(file_id, rel_types=rel_types)
        node = self.neo4j.get_file(file_id)
        return {
            "center": node,
            "neighbors": neighbors,
        }

    def search_along_relation(
        self,
        query: str,
        center_file_id: str,
        relation_type: str | None = None,
    ) -> dict:
        """方案 4.3.4：沿关系边二次导航检索。"""
        allowed = {relation_type} if relation_type else None
        return self.search(
            query,
            expand_graph=True,
            allowed_relations=allowed,
            seed_file_id=center_file_id,
            hops=settings.graph_hops,
        )

    def _merge_visual_seeds(
        self,
        query: str,
        parsed: Any,
        seed_map: dict[str, dict],
    ) -> None:
        from src.multimodal.vision_encoder import VisionEncoder

        enc = VisionEncoder.get()
        if not enc.available():
            return
        vq = parsed.keywords or query
        vec = enc.embed_text_query(vq)
        if vec is None:
            return
        for h in self.chroma.search_visual(
            vec.tolist(), n_results=settings.seed_top_n, where=parsed.chroma_where()
        ):
            fid = h["file_id"]
            if not fid:
                continue
            prev = seed_map.get(fid)
            sim = h["similarity"]
            if prev is None or sim > prev.get("similarity", 0):
                seed_map[fid] = {
                    "file_id": fid,
                    "path": h.get("path", ""),
                    "name": h.get("name", ""),
                    "similarity": sim,
                }

    def _inject_bm25_candidates(
        self,
        query: str,
        parsed: Any,
        graph_hits: dict,
        ranked: list[dict],
    ) -> list[dict]:
        """将 BM25 高分但未进入图扩展的候选并入（对标专利混合检索，保留 FileKG 路径）。"""
        bundle = getattr(self.ranker, "_bm25_bundle", None)
        if not bundle:
            return ranked
        bm25, corpus, fid_map = bundle
        from src.search.ranker import _tokenize

        scores = list(bm25.get_scores(_tokenize(parsed.keywords or query)))
        if not scores:
            return ranked
        max_s = max(scores) or 1.0
        seen = {r["file_id"] for r in ranked}
        extras: list[dict] = []
        for idx in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:25]:
            if scores[idx] <= 0:
                break
            fid = corpus[idx]["file_id"]
            if fid in seen:
                continue
            node = self.neo4j.get_file(fid)
            if not node or node.get("is_inside_archive"):
                continue
            path_l = (node.get("path") or "").replace("\\", "/").lower()
            if "/noise/" in path_l:
                continue
            hit = graph_hits.get(fid)
            extras.append(
                {
                    "file_id": fid,
                    "path": node.get("path", ""),
                    "name": node.get("name", ""),
                    "score": round(0.35 + 0.45 * (scores[idx] / max_s), 4),
                    "semantic_score": hit.seed_similarity if hit else 0.0,
                    "graph_weight": hit.graph_weight if hit else 0.0,
                    "time_decay": 0.5,
                    "rule_bonus": 0.0,
                    "bm25_score": round(scores[idx] / max_s, 4),
                    "is_seed": bool(hit and hit.is_seed),
                    "summary": node.get("ai_summary") or node.get("summary", ""),
                    "explanation_paths": (hit.paths[:3] if hit else []),
                }
            )
            seen.add(fid)
        merged = ranked + extras
        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged[: settings.result_top_n]

    def _merge_near_duplicate_in_results(self, ranked: list[dict]) -> list[dict]:
        """检索阶段合并 NEAR_DUPLICATE 呈现（图谱仍保留独立节点，发明说明 5.2.1）。"""
        if not settings.visual_merge_near_duplicate_results or not ranked:
            return ranked
        seen_dup: set[str] = set()
        out: list[dict] = []
        for r in ranked:
            fid = r.get("file_id")
            if fid in seen_dup:
                continue
            out.append(r)
            for nb in self.neo4j.get_neighbors(fid, hops=1):
                if nb.get("rel_type") == "NEAR_DUPLICATE":
                    seen_dup.add(nb.get("file_id", ""))
        return out

    def _build_graph_view(self, results: list[dict]) -> list[dict]:
        edges = []
        seen = set()
        for r in results[:10]:
            for p in r.get("explanation_paths", []):
                key = (p.get("from_id"), p.get("rel_type"), p.get("to_id"))
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "source": p.get("from_name") or p.get("from_id"),
                        "target": r.get("name"),
                        "relation": p.get("rel_label", p.get("rel_type")),
                    }
                )
        return edges
