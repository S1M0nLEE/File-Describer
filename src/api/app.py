from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api import runtime as app_runtime
from src.config import settings
from src.indexing.builder import IndexBuilder
from src.watcher.monitor import FileWatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_watcher: FileWatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher
    app_runtime.configure(
        fast_startup=settings.api_fast_startup,
        manual_load=settings.api_manual_load,
    )
    app_runtime.init_on_startup()
    preload = None
    if (
        settings.api_fast_startup
        and settings.api_preload_graph
        and not settings.api_manual_load
    ):
        preload = app_runtime.start_background_preload()
    heartbeat = app_runtime.start_heartbeat()
    yield
    if heartbeat and not heartbeat.done():
        heartbeat.cancel()
    if preload and not preload.done():
        preload.cancel()
    if _watcher:
        _watcher.stop()
    app_runtime.shutdown()


app = FastAPI(
    title="个人文件知识图谱",
    description="基于可演化数字代理与多维度关系发现引擎的文件检索系统",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(app_runtime.GraphNotLoadedError)
async def graph_not_loaded_handler(
    request: Request, exc: app_runtime.GraphNotLoadedError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
            "code": "graph_not_loaded",
            "load": app_runtime.load_status(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {exc}"},
    )

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


class IndexRequest(BaseModel):
    path: str
    clear: bool = False
    max_files: int | None = None
    multimodal: bool | None = None


class IndexOptionsRequest(BaseModel):
    multimodal: bool
    persist: bool = True


class SearchRequest(BaseModel):
    query: str
    expand_graph: bool = True


class TagRequest(BaseModel):
    file_id: str
    tag: str


class RagChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    stream: bool = False
    top_k: int | None = Field(
        None,
        ge=1,
        le=50,
        description="Description 检索并参与排序的节点数，默认读 config",
    )


class RagRetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(None, ge=1, le=50)


class LoadStartRequest(BaseModel):
    build_search: bool = Field(
        True, description="是否加载检索引擎与 RAG（推荐开启）"
    )
    build_corpus: bool = Field(
        False,
        description="是否构建全量 BM25 语料（13 万+ 文件时较慢，可稍后在首次检索时构建）",
    )


@app.get("/", response_class=HTMLResponse)
async def home():
    index = static_dir / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return "<h1>个人文件知识图谱 API</h1><p>请访问 /docs</p>"


@app.get("/health")
async def health():
    """轻量健康检查：不加载 BGE/CLIP，供前端轮询启动状态。"""
    s = app_runtime.status()
    out: dict[str, Any] = {
        "graph": s["graph_backend"],
        "graph_ready": s["graph_ready"],
        "chroma": s["graph_ready"],
        "search_ready": s["search_ready"],
        "rag_ready": s["rag_ready"],
        "fast_startup": s["fast_startup"],
        "loading": s["loading"],
        "phase": s["phase"],
        "error": s["error"],
        "embedding_model": settings.embedding_model,
        "visual_model": settings.visual_model,
        "deepseek_configured": bool(settings.deepseek_api_key),
        "manual_load": s.get("manual_load"),
        "load_running": s.get("load_running"),
        "load": s.get("load"),
    }
    if s["search_ready"]:
        from src.indexing.embedder import Embedder
        from src.multimodal.vision_encoder import VisionEncoder

        emb = Embedder.get()
        vis = VisionEncoder.get()
        out["embedding_backend"] = emb.backend
        out["embedding_dim"] = emb.dimension
        out["visual_encoder_ready"] = vis.available()
    else:
        out["embedding_backend"] = ""
        out["visual_encoder_ready"] = False
    out.update(
        {
            k: s[k]
            for k in (
                "disk_cache",
                "graph_warmed_at",
                "last_heartbeat_at",
                "last_heartbeat_indexed",
                "last_heartbeat_skipped",
                "heartbeat_running",
            )
            if k in s
        }
    )
    return out


@app.get("/load/status")
async def load_status():
    """全局索引加载进度（前端轮询）。"""
    return app_runtime.load_status()


@app.post("/load/start")
async def load_start(req: LoadStartRequest):
    """用户确认后启动后台加载，不阻塞 HTTP。"""
    st = app_runtime.load_status()
    if st.get("state") == "running" or st.get("load_running"):
        return {"started": False, "message": "正在加载中", **st}
    if st.get("graph_ready") and (
        not req.build_search or st.get("search_ready")
    ):
        return {"started": False, "message": "已加载", **st}
    ok = app_runtime.start_load_background(
        build_corpus=req.build_corpus,
        build_search=req.build_search,
    )
    return {
        "started": ok,
        "message": "已开始加载" if ok else "无法启动加载",
        **app_runtime.load_status(),
    }


@app.post("/admin/heartbeat")
async def trigger_heartbeat():
    """手动触发一次增量索引心跳（与定时任务相同逻辑）。"""
    if app_runtime.status().get("heartbeat_running"):
        raise HTTPException(409, "心跳任务正在执行中")
    from src.api.heartbeat import run_heartbeat_sync

    try:
        summary = await asyncio.to_thread(run_heartbeat_sync)
    except Exception as e:
        raise HTTPException(500, f"心跳失败: {e}") from e
    return summary


@app.get("/config")
async def app_config():
    return {
        "visual_enabled": settings.visual_enabled,
        "visual_fusion_mode": settings.visual_fusion_mode,
        "multimodal_enabled": settings.multimodal_enabled,
        "multimodal_vision_caption": settings.multimodal_vision_caption_enabled,
        "patent_visual_only": settings.patent_visual_only,
        "graph_hops": settings.graph_hops,
        "merge_near_duplicate_results": settings.visual_merge_near_duplicate_results,
        "rag_index_multimodal": settings.rag_index_multimodal,
    }


@app.get("/settings/index-options")
async def get_index_options():
    from src.api.index_options import apply_index_multimodal

    mm = apply_index_multimodal(None)
    return {
        "multimodal": mm,
        "fast_index": not mm,
        "hint_off": "仅文本 BGE，速度快（默认）",
        "hint_on": "含图片 moondream 描述、音视频转写，速度慢",
    }


@app.post("/settings/index-options")
async def set_index_options(req: IndexOptionsRequest):
    from src.api.index_options import apply_index_multimodal, persist_index_multimodal

    apply_index_multimodal(req.multimodal)
    if req.persist:
        persist_index_multimodal(req.multimodal)
    return {
        "multimodal": settings.rag_index_multimodal,
        "fast_index": not settings.rag_index_multimodal,
        "persisted": req.persist,
    }


@app.get("/graph/relations")
async def graph_relations():
    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    if hasattr(graph, "count_relations_by_type"):
        counts = graph.count_relations_by_type()
    else:
        counts = {}
    return {"relations": counts, "total_edges": sum(counts.values())}


@app.get("/graph/schema")
async def graph_schema():
    """关系类型图例：中文名、配色、扩展权重、边数量。"""
    from src.graph.relation_styles import relation_schema

    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
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


@app.get("/graph/subgraph")
async def graph_subgraph(
    center: str | None = Query(None, description="中心节点 file_id"),
    hops: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(80, ge=5, le=200),
    max_edges: int = Query(250, ge=10, le=500),
    relations: str | None = Query(None, description="逗号分隔的关系类型，空=全部"),
):
    """导出子图 JSON，供前端力导向图（类似 Neo4j Browser）。"""
    from src.graph.subgraph import export_subgraph

    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    rel_set: set[str] | None = None
    if relations:
        rel_set = {r.strip() for r in relations.split(",") if r.strip()}
    data = export_subgraph(
        graph,
        center_id=center,
        hops=hops,
        max_nodes=max_nodes,
        relation_types=rel_set,
        max_edges=max_edges,
    )
    return data


@app.get("/visual/sample-queries")
async def visual_sample_queries():
    path = settings.data_dir / "evaluation" / "patent" / "visual_eval_queries.json"
    if not path.exists():
        return {"queries": []}
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("set_b_visual_dependent") or []
    return {
        "queries": [{"id": q.get("id"), "text": q.get("query")} for q in items if q.get("query")]
    }


@app.post("/index")
async def index_directory(req: IndexRequest):
    try:
        graph, chroma = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    root = Path(req.path)
    if not root.is_dir():
        raise HTTPException(400, f"目录不存在: {req.path}")
    from src.api.index_options import apply_index_multimodal

    mm = apply_index_multimodal(req.multimodal)
    if not mm:
        settings.llm_enabled = False
    builder = IndexBuilder(graph, chroma)
    result = builder.build(root, clear=req.clear, max_files=req.max_files)
    result["multimodal"] = mm
    app_runtime.invalidate_search_corpus()
    return result


@app.post("/search")
async def search(req: SearchRequest):
    try:
        engine = app_runtime.ensure_search()
    except Exception as e:
        raise HTTPException(503, f"检索引擎加载失败: {e}") from e
    try:
        return engine.search(req.query, expand_graph=req.expand_graph)
    except Exception as e:
        logger.exception("检索失败")
        raise HTTPException(500, f"检索失败: {e}") from e


@app.get("/search")
async def search_get(
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
        raise HTTPException(503, f"检索引擎加载失败: {e}") from e
    allowed = None
    if visual_only:
        allowed = {"VISUALLY_SIMILAR_TO", "NEAR_DUPLICATE"}
    if seed_file_id and relation:
        return engine.search_along_relation(q, seed_file_id, relation)
    return engine.search(
        q,
        expand_graph=expand,
        seed_file_id=seed_file_id,
        hops=hops,
        allowed_relations=allowed,
    )


@app.post("/consistency/check")
async def consistency_check():
    try:
        graph, chroma = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    from src.indexing.consistency import ConsistencyChecker

    return ConsistencyChecker(graph, chroma).global_consistency_check(settings.index_watch_roots or None)


@app.post("/lifecycle/run")
async def lifecycle_run():
    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    from src.indexing.lifecycle import LifecycleManager

    return LifecycleManager(graph).run()


@app.post("/workflow/import-etw")
async def import_etw(path: str):
    from src.behavior.collector import WorkflowCollector

    n = WorkflowCollector().import_etw_csv(Path(path))
    return {"imported": n}


@app.get("/navigate/{file_id}")
async def navigate(file_id: str, relation: str | None = None):
    try:
        engine = app_runtime.ensure_search()
    except Exception as e:
        raise HTTPException(503, f"检索引擎加载失败: {e}") from e
    rel = relation
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
    return engine.navigate_from(file_id, rel)


@app.get("/stats")
async def stats():
    from src.api.path_scope import is_benchmark_path

    try:
        graph, chroma = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
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


@app.get("/files")
async def list_files(
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    scope: str = Query(
        "local",
        description="local=本机目录索引, benchmark=评测样例, all=全部",
    ),
):
    from src.api.path_scope import is_benchmark_path

    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    if scope not in ("local", "benchmark", "all"):
        raise HTTPException(400, "scope 须为 local | benchmark | all")
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
    page = files[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "scope": scope,
        "files": page,
    }


@app.post("/watch")
async def start_watch(paths: list[str]):
    global _watcher
    try:
        graph, chroma = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    builder = IndexBuilder(graph, chroma)
    _watcher = FileWatcher(paths, builder)
    _watcher.start(blocking=False)
    return {"watching": paths}


@app.post("/tags")
async def add_tag(req: TagRequest):
    try:
        graph, _ = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"图存储加载失败: {e}") from e
    graph.create_relation(req.file_id, "TAGGED_WITH", f"tag:{req.tag}", props={"tag": req.tag})
    return {"ok": True}


@app.get("/rag/status")
async def rag_status():
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


def _resolve_rag_top_k(top_k: int | None) -> int:
    if top_k is not None:
        return min(max(top_k, 1), settings.rag_top_k_max)
    return settings.rag_top_k


@app.post("/rag/retrieve")
async def rag_retrieve(req: RagRetrieveRequest):
    """仅做 Description 检索与排序，不调用 DeepSeek（用于预览 Top-K 节点）。"""
    try:
        rag = app_runtime.ensure_rag()
    except Exception as e:
        raise HTTPException(503, f"RAG 加载失败: {e}") from e
    k = _resolve_rag_top_k(req.top_k)
    nodes = rag.retrieve(req.question, top_k=k)
    return {
        "question": req.question,
        "top_k": k,
        "count": len(nodes),
        "nodes": nodes,
    }


@app.post("/rag/chat")
async def rag_chat(req: RagChatRequest):
    try:
        rag = app_runtime.ensure_rag()
    except Exception as e:
        raise HTTPException(503, f"RAG 加载失败: {e}") from e
    k = _resolve_rag_top_k(req.top_k)
    if req.stream:
        import json

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

    return rag.ask(req.question, history=req.history, stream=False, top_k=k)


@app.post("/rag/index-local")
async def rag_index_local(
    clear: bool = False,
    max_files: int | None = None,
    multimodal: bool | None = None,
):
    """按 config.yaml rag.index_roots 索引本机常用目录（后台任务式同步执行）。"""
    import os
    from src.api.index_options import apply_index_multimodal
    from src.indexing.builder import IndexBuilder

    try:
        graph, chroma = app_runtime.ensure_graph()
    except Exception as e:
        raise HTTPException(503, f"存储加载失败: {e}") from e
    mm = apply_index_multimodal(multimodal)
    if not mm:
        settings.llm_enabled = False
    roots = settings.rag_index_roots or []
    expanded: list[Path] = []
    for r in roots:
        p = Path(os.path.expandvars(r)).expanduser()
        if p.is_dir():
            expanded.append(p)
    if not expanded:
        home = Path.home()
        expanded = [home / "Documents", home / "Desktop", home / "Downloads"]
        expanded = [p for p in expanded if p.is_dir()]

    builder = IndexBuilder(graph, chroma)
    results: list[dict[str, Any]] = []
    cap = max_files or settings.rag_max_files_per_root
    for i, root in enumerate(expanded):
        logger.info("RAG 索引: %s", root)
        stats = builder.build(root, clear=clear and i == 0, max_files=cap)
        results.append({"root": str(root), **stats})
    app_runtime.invalidate_search_corpus()
    return {
        "roots": [str(p) for p in expanded],
        "multimodal": mm,
        "runs": results,
    }
