"""[DEPRECATED] 旧版 API — 请使用 src.api.app。详见 legacy/README.md。"""

import warnings

warnings.warn(
    "src.api.main 已废弃，请使用 src.api.app (scripts/run_server.py)",
    DeprecationWarning,
    stacklevel=1,
)

"""FastAPI search API."""

import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.config import get_config
from src.pipeline.embedder import Embedder
from src.pipeline.graph_builder import GraphBuilder
from src.retrieval.graph_expander import GraphExpander
from src.retrieval.query_parser import QueryParser
from src.retrieval.ranker import Ranker
from src.retrieval.vector_search import VectorSearcher

logger = logging.getLogger(__name__)

_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    builder = GraphBuilder(cfg)
    builder.load_cache()
    _state["config"] = cfg
    _state["builder"] = builder
    _state["parser"] = QueryParser(cfg)
    _state["searcher"] = VectorSearcher(cfg)
    _state["searcher"].refresh()
    _state["expander"] = GraphExpander(cfg)
    _state["ranker"] = Ranker(cfg)
    _state["embedder"] = Embedder(cfg)
    yield
    builder.close()
    _state["expander"].close()


app = FastAPI(title="FileKG API", version="0.1.0", lifespan=lifespan)


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=20, ge=1, le=100)
    max_hops: int = Field(default=1, ge=0, le=3)


class SearchResultItem(BaseModel):
    file_id: str
    path: str
    name: str
    summary: str
    score: float
    vector_score: float
    graph_score: float
    reasoning_path: List[str]
    relation_types: List[str]


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    cfg = _state["config"]
    parser: QueryParser = _state["parser"]
    searcher: VectorSearcher = _state["searcher"]
    expander: GraphExpander = _state["expander"]
    ranker: Ranker = _state["ranker"]
    embedder: Embedder = _state["embedder"]
    builder: GraphBuilder = _state["builder"]

    parsed = parser.parse(req.query)
    filters = parsed.to_filters()
    qtext = parsed.semantic_text

    seeds_v = searcher.search(qtext, filters=filters, top_n=cfg.vector_seed_top_n)
    seeds = seeds_v
    if cfg.use_hybrid_seeds:
        try:
            from rank_bm25 import BM25Okapi
            cache = builder.load_cache()
            ids, docs = [], []
            for fid, f in cache.items():
                ids.append(fid)
                docs.append((f.display_summary or f.name or "").lower().split())
            if docs:
                bm25 = BM25Okapi(docs)
                scores = bm25.get_scores(qtext.lower().split())
                order = sorted(range(len(scores)), key=lambda i: -scores[i])
                seeds_b = [ids[i] for i in order[: cfg.bm25_seed_top_n]]
                seen = set()
                seeds = []
                for fid in seeds_v + seeds_b:
                    if fid not in seen:
                        seen.add(fid)
                        seeds.append(fid)
        except ImportError:
            pass

    hops = req.max_hops if req.max_hops > 0 else cfg.max_graph_hops
    expanded = expander.expand(seeds, max_hops=hops) if hops > 0 else []

    candidates = builder.load_cache()
    hard_filters = filters if cfg.metadata_filter_hard else {}
    vector_pool = searcher.search(
        qtext, filters=hard_filters, top_n=max(cfg.vector_seed_top_n, req.top_k * 8, 200)
    )
    subset = {fid: candidates[fid] for fid in vector_pool if fid in candidates}

    bm25_map = {}
    if cfg.use_hybrid_seeds and subset:
        try:
            from rank_bm25 import BM25Okapi
            ids = list(subset.keys())
            docs = [(subset[fid].display_summary or subset[fid].name or "").lower().split() for fid in ids]
            bm25 = BM25Okapi(docs)
            scores = bm25.get_scores(qtext.lower().split())
            mx = max(scores) if len(scores) else 1.0
            bm25_map = {ids[i]: float(scores[i]) / mx for i in range(len(ids)) if mx > 0}
        except ImportError:
            pass

    q_emb = embedder.encode(qtext)
    ranked = ranker.score_and_rank(
        q_emb, subset, seeds, expanded,
        parsed_keywords=parsed.keywords,
        top_k=req.top_k,
        bm25_scores=bm25_map,
        vector_seed_ids=seeds_v,
    )

    results = [
        SearchResultItem(
            file_id=r.file_id,
            path=r.path,
            name=r.name,
            summary=r.summary,
            score=round(r.score, 4),
            vector_score=round(r.vector_score, 4),
            graph_score=round(r.graph_score, 4),
            reasoning_path=r.reasoning_path,
            relation_types=r.relation_types,
        )
        for r in ranked
    ]
    return SearchResponse(query=req.query, results=results)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("src.api.main:app", host=host, port=port, reload=False)
