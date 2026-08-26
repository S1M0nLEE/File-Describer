from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from src.api.deps import RequireAuth, app_runtime
from src.api.index_options import apply_index_multimodal
from src.api.schemas import IndexOptionsRequest, IndexRequest
from src.api.security import validate_index_directory
from src.config import settings
from src.indexing.builder import IndexBuilder

logger = logging.getLogger(__name__)
router = APIRouter(tags=["index"])


@router.post("/index")
async def index_directory(req: IndexRequest, _auth: RequireAuth):
    root = validate_index_directory(req.path)
    try:
        graph, chroma = app_runtime.ensure_graph_for_write()
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e

    mm = apply_index_multimodal(req.multimodal)
    if not mm:
        settings.llm_enabled = False
    builder = IndexBuilder(graph, chroma)

    def _run():
        return builder.build(root, clear=req.clear, max_files=req.max_files)

    result = await asyncio.to_thread(_run)
    result["multimodal"] = mm
    app_runtime.invalidate_search_corpus()
    return result


@router.get("/settings/index-options")
async def get_index_options(_auth: RequireAuth):
    mm = apply_index_multimodal(None)
    return {
        "multimodal": mm,
        "fast_index": not mm,
        "hint_off": "仅文本嵌入，速度快（默认）",
        "hint_on": "含图片/音视频多模态，速度慢",
    }


@router.post("/settings/index-options")
async def set_index_options(req: IndexOptionsRequest, _auth: RequireAuth):
    from src.api.index_options import persist_index_multimodal

    apply_index_multimodal(req.multimodal)
    if req.persist:
        persist_index_multimodal(req.multimodal)
    return {
        "multimodal": settings.rag_index_multimodal,
        "fast_index": not settings.rag_index_multimodal,
        "persisted": req.persist,
    }


@router.post("/consistency/check")
async def consistency_check(_auth: RequireAuth):
    try:
        graph, chroma = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e
    from src.indexing.consistency import ConsistencyChecker

    return await asyncio.to_thread(
        ConsistencyChecker(graph, chroma).global_consistency_check,
        settings.index_watch_roots or None,
    )


@router.post("/lifecycle/run")
async def lifecycle_run(_auth: RequireAuth):
    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e
    from src.indexing.lifecycle import LifecycleManager

    return await asyncio.to_thread(LifecycleManager(graph).run)
