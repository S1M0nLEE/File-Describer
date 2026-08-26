from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api import runtime as app_runtime
from src.api.logging_config import RequestLoggingMiddleware, configure_logging
from src.api.routers import graph, health, indexing, rag, search
from src.api.routers import rag as rag_router
from src.config import settings

configure_logging()
logger = logging.getLogger(__name__)

static_dir = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    rag_router.stop_watcher()
    app_runtime.shutdown()


def create_app() -> FastAPI:
    application = FastAPI(
        title="个人文件知识图谱",
        description="基于可演化数字代理与多维度关系发现引擎的文件检索系统",
        version="1.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(RequestLoggingMiddleware)

    @application.exception_handler(app_runtime.GraphNotLoadedError)
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

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        rid = getattr(request.state, "request_id", "-")
        logger.exception("未处理异常 request_id=%s %s %s", rid, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误", "request_id": rid},
        )

    @application.get("/", response_class=HTMLResponse, tags=["ui"])
    async def home():
        index = static_dir / "index.html"
        if index.exists():
            return index.read_text(encoding="utf-8")
        return "<h1>个人文件知识图谱 API</h1><p>请访问 /docs</p>"

    application.include_router(health.router)
    application.include_router(search.router)
    application.include_router(indexing.router)
    application.include_router(graph.router)
    application.include_router(rag.router)

    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=static_dir), name="static")

    return application


app = create_app()
