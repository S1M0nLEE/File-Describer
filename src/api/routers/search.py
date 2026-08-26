from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import RequireAuth, app_runtime
from src.api.schemas import SearchRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])


@router.post("/search")
async def search(req: SearchRequest, _auth: RequireAuth):
    try:
        engine = app_runtime.ensure_search()
    except Exception as e:
        raise HTTPException(503, "检索引擎尚未就绪") from e
    try:
        return await asyncio.to_thread(
            engine.search, req.query, expand_graph=req.expand_graph
        )
    except Exception as e:
        logger.exception("检索失败")
        raise HTTPException(500, "检索失败，请查看服务日志") from e


@router.get("/search")
async def search_get(
    _auth: RequireAuth,
    q: str = Query(..., min_length=1),
    expand: bool = True,
    seed_file_id: str | None = None,
    hops: int | None = None,
    relation: str | None = None,
    visual_only: bool = False,
):
    try:
        engine = app_runtime.ensure_search()
    except Exception as e:
        raise HTTPException(503, "检索引擎尚未就绪") from e
    allowed = None
    if visual_only:
        allowed = {"VISUALLY_SIMILAR_TO", "NEAR_DUPLICATE"}

    def _run():
        if seed_file_id and relation:
            return engine.search_along_relation(q, seed_file_id, relation)
        return engine.search(
            q,
            expand_graph=expand,
            seed_file_id=seed_file_id,
            hops=hops,
            allowed_relations=allowed,
        )

    return await asyncio.to_thread(_run)


@router.get("/navigate/{file_id}")
async def navigate(file_id: str, _auth: RequireAuth, relation: str | None = None):
    try:
        engine = app_runtime.ensure_search()
    except Exception as e:
        raise HTTPException(503, "检索引擎尚未就绪") from e

    def _run():
        if relation and "," in relation:
            rels = [r.strip() for r in relation.split(",") if r.strip()]
            node = engine.neo4j.get_file(file_id)
            neighbors: list[dict] = []
            seen: set[str] = set()
            for r in rels:
                for nb in engine.neo4j.get_neighbors(file_id, rel_types=[r]):
                    key = nb.get("file_id")
                    if key and key not in seen:
                        seen.add(key)
                        neighbors.append(nb)
            return {"center": node, "neighbors": neighbors}
        return engine.navigate_from(file_id, relation)

    return await asyncio.to_thread(_run)
