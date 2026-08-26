from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.api.deps import RequireAuth, app_runtime
from src.api.schemas import LoadStartRequest
from src.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(_auth: RequireAuth):
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
        "auth_required": bool(settings.api_require_token and settings.api_token),
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


@router.get("/health/diagnostics")
async def health_diagnostics(_auth: RequireAuth, probe_network: bool = False):
    from src.api.diagnostics import run_diagnostics

    return run_diagnostics(probe_network=probe_network)


@router.get("/load/status")
async def load_status(_auth: RequireAuth):
    return app_runtime.load_status()


@router.post("/load/start")
async def load_start(req: LoadStartRequest, _auth: RequireAuth):
    st = app_runtime.load_status()
    if st.get("state") == "running" or st.get("load_running"):
        return {"started": False, "message": "正在加载中", **st}
    if st.get("graph_ready") and (not req.build_search or st.get("search_ready")):
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


@router.get("/config")
async def app_config(_auth: RequireAuth):
    return {
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "visual_enabled": settings.visual_enabled,
        "visual_fusion_mode": settings.visual_fusion_mode,
        "multimodal_enabled": settings.multimodal_enabled,
        "multimodal_vision_caption": settings.multimodal_vision_caption_enabled,
        "graph_hops": settings.graph_hops,
        "merge_near_duplicate_results": settings.visual_merge_near_duplicate_results,
        "rag_index_multimodal": settings.rag_index_multimodal,
        "auth_required": bool(settings.api_require_token and settings.api_token),
        "expose_full_paths": settings.api_expose_full_paths,
    }
