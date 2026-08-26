from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import RequireAuth, app_runtime
from src.config import settings
from src.graph.relation_styles import relation_schema
from src.graph.subgraph import export_subgraph

router = APIRouter(tags=["graph"])


@router.get("/graph/relations")
async def graph_relations(_auth: RequireAuth):
    def _run():
        graph, _ = app_runtime.ensure_graph()
        counts = (
            graph.count_relations_by_type()
            if hasattr(graph, "count_relations_by_type")
            else {}
        )
        return {"relations": counts, "total_edges": sum(counts.values())}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e


@router.get("/graph/schema")
async def graph_schema(_auth: RequireAuth):
    def _run():
        graph, _ = app_runtime.ensure_graph()
        counts = (
            graph.count_relations_by_type()
            if hasattr(graph, "count_relations_by_type")
            else {}
        )
        return {
            "relations": relation_schema(counts),
            "total_edges": sum(counts.values()),
            "relation_weights": settings.relation_weights or {},
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e


@router.get("/graph/subgraph")
async def graph_subgraph(
    _auth: RequireAuth,
    center: str | None = Query(None, description="中心节点 file_id"),
    hops: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(80, ge=5, le=200),
    max_edges: int = Query(250, ge=10, le=500),
    relations: str | None = Query(None, description="逗号分隔的关系类型"),
):
    rel_set: set[str] | None = None
    if relations:
        rel_set = {r.strip() for r in relations.split(",") if r.strip()}

    def _run():
        graph, _ = app_runtime.ensure_graph()
        return export_subgraph(
            graph,
            center_id=center,
            hops=hops,
            max_nodes=max_nodes,
            relation_types=rel_set,
            max_edges=max_edges,
        )

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e


@router.get("/visual/sample-queries")
async def visual_sample_queries(_auth: RequireAuth):
    path = settings.data_dir / "evaluation" / "patent" / "visual_eval_queries.json"
    if not path.exists():
        return {"queries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("set_b_visual_dependent") or []
    return {
        "queries": [{"id": q.get("id"), "text": q.get("query")} for q in items if q.get("query")]
    }
