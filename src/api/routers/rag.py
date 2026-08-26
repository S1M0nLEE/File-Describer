from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.api.deps import RequireAuth, app_runtime
from src.api.index_options import apply_index_multimodal
from src.api.index_roots import resolve_rag_index_roots
from src.api.schemas import RagChatRequest, RagRetrieveRequest, TagRequest
from src.config import settings
from src.indexing.builder import IndexBuilder
from src.watcher.monitor import FileWatcher

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rag", "files", "admin"])

_watcher: FileWatcher | None = None


def get_watcher() -> FileWatcher | None:
    return _watcher


def stop_watcher() -> None:
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None


def _resolve_rag_top_k(top_k: int | None) -> int:
    if top_k is not None:
        return min(max(top_k, 1), settings.rag_top_k_max)
    return settings.rag_top_k


@router.get("/rag/status")
async def rag_status(_auth: RequireAuth):
    from src.llm.deepseek_client import DeepSeekClient

    indexed = 0
    chroma = app_runtime.get_chroma()
    if chroma is not None:
        try:
            indexed = len(chroma.list_file_ids())
        except Exception:
            pass
    client = DeepSeekClient()
    return {
        "deepseek_enabled": settings.deepseek_enabled,
        "deepseek_available": client.is_available(),
        "model": settings.deepseek_model,
        "indexed_files": indexed,
        "index_roots": settings.rag_index_roots,
        "default_top_k": settings.rag_top_k,
        "top_k_min": 1,
        "top_k_max": settings.rag_top_k_max,
        "hint": "首次使用请运行: python scripts/index_local_pc.py",
    }


@router.post("/rag/retrieve")
async def rag_retrieve(req: RagRetrieveRequest, _auth: RequireAuth):
    try:
        rag = app_runtime.ensure_rag()
    except Exception as e:
        raise HTTPException(503, "RAG 尚未就绪") from e
    k = _resolve_rag_top_k(req.top_k)

    def _run():
        nodes = rag.retrieve(req.question, top_k=k)
        return {
            "question": req.question,
            "top_k": k,
            "count": len(nodes),
            "nodes": nodes,
        }

    return await asyncio.to_thread(_run)


@router.post("/rag/chat")
async def rag_chat(req: RagChatRequest, _auth: RequireAuth):
    try:
        rag = app_runtime.ensure_rag()
    except Exception as e:
        raise HTTPException(503, "RAG 尚未就绪") from e
    k = _resolve_rag_top_k(req.top_k)
    if req.stream:

        def event_gen():
            result = rag.ask(req.question, history=req.history, stream=True, top_k=k)
            stream = result.get("stream")
            if stream is None:
                yield f"data: {json.dumps({'error': 'stream failed'}, ensure_ascii=False)}\n\n"
                return
            for piece in stream:
                yield f"data: {json.dumps({'text': piece}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': result.get('sources', [])}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    return await asyncio.to_thread(
        rag.ask, req.question, history=req.history, stream=False, top_k=k
    )


@router.post("/rag/index-local")
async def rag_index_local(
    _auth: RequireAuth,
    clear: bool = False,
    max_files: int | None = None,
    multimodal: bool | None = None,
):
    try:
        graph, chroma = app_runtime.ensure_graph_for_write()
    except Exception as e:
        raise HTTPException(503, "存储尚未就绪") from e
    mm = apply_index_multimodal(multimodal)
    if not mm:
        settings.llm_enabled = False
    expanded = resolve_rag_index_roots()
    builder = IndexBuilder(graph, chroma)
    cap = max_files or settings.rag_max_files_per_root

    def _run():
        results: list[dict[str, Any]] = []
        for i, root in enumerate(expanded):
            logger.info("RAG 索引: %s", root)
            stats = builder.build(root, clear=clear and i == 0, max_files=cap)
            results.append({"root": str(root), **stats})
        return {
            "roots": [str(p) for p in expanded],
            "multimodal": mm,
            "runs": results,
        }

    out = await asyncio.to_thread(_run)
    app_runtime.invalidate_search_corpus()
    return out


@router.get("/files")
async def list_files(
    _auth: RequireAuth,
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    scope: str = Query("local", description="local | benchmark | all"),
):
    from src.api.path_scope import is_benchmark_path
    from src.api.security import redact_file_record

    if scope not in ("local", "benchmark", "all"):
        raise HTTPException(400, "scope 须为 local | benchmark | all")

    def _run():
        graph, _ = app_runtime.ensure_graph()
        files = graph.list_all_files()
        if scope == "local":
            files = [f for f in files if not is_benchmark_path(f.get("path"))]
        elif scope == "benchmark":
            files = [f for f in files if is_benchmark_path(f.get("path"))]
        if q:
            needle = q.lower()
            files = [
                f
                for f in files
                if needle in (f.get("name") or "").lower()
                or needle in (f.get("path") or "").lower()
            ]
        files.sort(key=lambda f: f.get("modified_time") or "", reverse=True)
        total = len(files)
        page = [redact_file_record(f) for f in files[offset : offset + limit]]
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "scope": scope,
            "files": page,
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e


@router.get("/stats")
async def stats(_auth: RequireAuth):
    from src.api.path_scope import is_benchmark_path

    def _run():
        graph, chroma = app_runtime.ensure_graph()
        files = graph.list_all_files()
        rel_counts = (
            graph.count_relations_by_type()
            if hasattr(graph, "count_relations_by_type")
            else {}
        )
        benchmark_n = sum(1 for f in files if is_benchmark_path(f.get("path")))
        chroma_ok = chroma.is_healthy() if hasattr(chroma, "is_healthy") else True
        return {
            "file_count": len(files),
            "local_file_count": len(files) - benchmark_n,
            "benchmark_file_count": benchmark_n,
            "chroma_healthy": chroma_ok,
            "graph_backend": app_runtime.graph_backend(),
            "multimodal_enabled": settings.multimodal_enabled,
            "visual_enabled": settings.visual_enabled,
            "visual_edges": rel_counts.get("VISUALLY_SIMILAR_TO", 0),
            "near_duplicate_edges": rel_counts.get("NEAR_DUPLICATE", 0),
            "relation_types": len(rel_counts),
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e


@router.post("/watch")
async def start_watch(paths: list[str], _auth: RequireAuth):
    global _watcher
    from src.api.security import validate_index_directory

    validated = [str(validate_index_directory(p)) for p in paths]
    try:
        graph, chroma = app_runtime.ensure_graph_for_write()
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e
    builder = IndexBuilder(graph, chroma)
    if _watcher:
        _watcher.stop()
    _watcher = FileWatcher(validated, builder)
    _watcher.start(blocking=False)
    return {"watching": validated}


@router.post("/tags")
async def add_tag(req: TagRequest, _auth: RequireAuth):
    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, "图存储尚未就绪") from e

    def _run():
        graph.create_relation(
            req.file_id, "TAGGED_WITH", f"tag:{req.tag}", props={"tag": req.tag}
        )
        return {"ok": True}

    return await asyncio.to_thread(_run)


@router.post("/workflow/import-etw")
async def import_etw(path: str, _auth: RequireAuth):
    from src.api.security import validate_readable_file
    from src.behavior.collector import WorkflowCollector

    csv_path = validate_readable_file(path)

    def _run():
        n = WorkflowCollector().import_etw_csv(csv_path)
        return {"imported": n}

    return await asyncio.to_thread(_run)


@router.post("/admin/heartbeat")
async def trigger_heartbeat(_auth: RequireAuth):
    if app_runtime.status().get("heartbeat_running"):
        raise HTTPException(409, "心跳任务正在执行中")
    from src.api.heartbeat import run_heartbeat_sync

    try:
        summary = await asyncio.to_thread(run_heartbeat_sync)
    except Exception as e:
        logger.exception("心跳失败")
        raise HTTPException(500, "心跳失败，请查看服务日志") from e
    return summary
