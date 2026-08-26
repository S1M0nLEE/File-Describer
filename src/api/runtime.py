"""API 运行时：手动加载、进度上报、进程内缓存、后台心跳。"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from src.api.heartbeat import _iso_now, manifest_snapshot, run_heartbeat_sync, write_manifest
from src.api.load_progress import (
    make_corpus_callback,
    reset_idle,
    set_done,
    set_error,
    set_running,
)
from src.api.load_progress import (
    snapshot as load_progress_snapshot,
)
from src.config import settings
from src.search import corpus_cache
from src.search.engine import SearchEngine
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore, create_graph_store
from src.storage.graph_disk_cache import graph_fingerprint

logger = logging.getLogger(__name__)


class GraphNotLoadedError(RuntimeError):
    """手动加载模式下，图/检索尚未初始化。"""


_lock = threading.Lock()
_load_lock = threading.Lock()
_phase: str = "idle"
_error: str | None = None
_graph: GraphStore | None = None
_chroma: ChromaStore | None = None
_search: SearchEngine | None = None
_rag: Any = None
_graph_backend: str = "unknown"
_fast_startup: bool = True
_manual_load: bool = False
_load_thread: threading.Thread | None = None
_load_running: bool = False
_preload_task: asyncio.Task | None = None
_heartbeat_task: asyncio.Task | None = None
_heartbeat_running: bool = False


def configure(
    *,
    fast_startup: bool | None = None,
    manual_load: bool | None = None,
) -> None:
    global _fast_startup, _manual_load
    if fast_startup is not None:
        _fast_startup = fast_startup
    if manual_load is not None:
        _manual_load = manual_load


def status() -> dict[str, Any]:
    manifest = manifest_snapshot()
    hb = manifest.get("last_heartbeat") or {}
    lp = load_progress_snapshot()
    return {
        "fast_startup": _fast_startup,
        "manual_load": _manual_load,
        "phase": _phase,
        "graph_ready": _graph is not None,
        "search_ready": _search is not None,
        "rag_ready": _rag is not None,
        "loading": _load_running or _phase in ("graph", "search") or _heartbeat_running,
        "load_running": _load_running,
        "heartbeat_running": _heartbeat_running,
        "error": _error,
        "graph_backend": _graph_backend,
        "disk_cache": settings.api_disk_cache,
        "graph_warmed_at": manifest.get("graph_warmed_at"),
        "last_heartbeat_at": manifest.get("last_heartbeat_at"),
        "last_heartbeat_indexed": hb.get("indexed_new"),
        "last_heartbeat_skipped": hb.get("skipped_unchanged"),
        "load": lp,
    }


def graph_backend() -> str:
    return _graph_backend


def get_graph() -> GraphStore | None:
    return _graph


def get_chroma() -> ChromaStore | None:
    return _chroma


def get_search() -> SearchEngine | None:
    return _search


def get_rag() -> Any:
    return _rag


def load_status() -> dict[str, Any]:
    s = status()
    return {
        **load_progress_snapshot(),
        "graph_ready": s["graph_ready"],
        "search_ready": s["search_ready"],
        "manual_load": s["manual_load"],
        "load_running": _load_running,
    }


def invalidate_search_corpus() -> None:
    global _search
    corpus_cache.invalidate(settings.data_dir)
    if _search is not None:
        _search.invalidate_corpus()
    logger.info("检索语料缓存已失效，下次检索将按最新图重建")


def _record_graph_warmed(graph: GraphStore) -> None:
    path = getattr(graph, "path", None)
    fp = graph_fingerprint(path) if path else None
    write_manifest(graph_warmed_at=_iso_now(), graph_fingerprint=fp)


def _load_graph_unlocked() -> tuple[GraphStore, ChromaStore]:
    global _graph, _chroma, _graph_backend, _phase, _error
    set_running("graph", "正在加载图存储（JSON / 磁盘缓存）…", 8)
    t0 = time.perf_counter()
    graph = create_graph_store(defer_load=True)
    if hasattr(graph, "ensure_loaded"):
        graph.ensure_loaded()
    set_running("chroma", "正在连接向量库 Chroma…", 48)
    chroma = ChromaStore()
    _graph = graph
    _chroma = chroma
    _graph_backend = type(graph).__name__
    _phase = "ready" if _search is not None else "idle"
    _error = None
    _record_graph_warmed(graph)
    logger.info("图存储已加载 (%s, %.1fs)", _graph_backend, time.perf_counter() - t0)
    set_running("chroma", "向量库已连接", 52)
    return _graph, _chroma


def _load_search_unlocked(*, build_corpus: bool = False) -> SearchEngine:
    global _search, _rag, _phase, _error
    graph, chroma = _load_graph_unlocked() if _graph is None else (_graph, _chroma)
    assert graph is not None and chroma is not None
    _phase = "search"
    set_running("search", "正在初始化检索引擎与嵌入模型…", 58)
    t0 = time.perf_counter()
    search = SearchEngine(graph, chroma, lazy_corpus=True)
    from src.rag.pipeline import RagPipeline

    rag = RagPipeline(graph, chroma, search)
    _search = search
    _rag = rag
    if build_corpus:
        set_running("corpus", "正在构建检索语料（文件较多时较慢）…", 75)
        search._init_corpus(on_progress=make_corpus_callback())
    _phase = "ready"
    write_manifest(search_warmed_at=_iso_now())
    logger.info("检索引擎已就绪 (%.1fs)", time.perf_counter() - t0)
    set_running("search", "检索引擎已就绪", 92)
    return _search


def run_full_load(*, build_corpus: bool = False, build_search: bool = True) -> None:
    """同步执行完整加载（在线程池中调用）。"""
    global _error
    try:
        set_running("start", "开始加载全局索引…", 2)
        if build_search:
            _load_search_unlocked(build_corpus=build_corpus)
        else:
            _load_graph_unlocked()
        set_done()
    except Exception as e:
        _error = str(e)
        _phase = "error"
        set_error(str(e))
        logger.exception("全局加载失败")
        raise


def start_load_background(
    *,
    build_corpus: bool = False,
    build_search: bool = True,
) -> bool:
    """启动后台加载线程；若已在加载或已就绪则返回 False。"""
    global _load_thread, _load_running
    if _graph is not None and _search is not None and not build_corpus:
        set_done("全局索引已在内存中")
        return False
    with _load_lock:
        if _load_running:
            return False
        _load_running = True

        def _worker() -> None:
            global _load_running
            try:
                if build_search and _search is None:
                    run_full_load(build_corpus=build_corpus, build_search=True)
                elif _graph is None:
                    run_full_load(build_corpus=False, build_search=False)
                elif build_corpus and _search is not None:
                    set_running("corpus", "正在构建检索语料…", 75)
                    _search._init_corpus(on_progress=make_corpus_callback())
                    set_done()
                else:
                    set_done()
            except Exception:
                pass
            finally:
                _load_running = False

        _load_thread = threading.Thread(target=_worker, name="filekg-load", daemon=True)
        _load_thread.start()
        return True


def init_on_startup() -> None:
    settings.ensure_dirs()
    if _manual_load:
        reset_idle()
        logger.info("手动加载模式：服务已启动，等待用户在前端确认加载全局索引")
        return
    if not _fast_startup:
        run_full_load(build_corpus=False, build_search=True)
        logger.info("完整启动：图与检索已就绪 (%s)", _graph_backend)
        return
    # 非手动 + 快速启动：后台加载图与检索，HTTP 立即可用
    started = start_load_background(build_corpus=False, build_search=True)
    if started:
        logger.info("快速启动：HTTP 已就绪，后台加载全局索引中…")
    elif _graph is not None and _search is not None:
        logger.info("快速启动：索引已在内存中 (%s)", _graph_backend)
    else:
        logger.info("快速启动：HTTP 已就绪（非手动模式）")


def ensure_graph() -> tuple[GraphStore, ChromaStore]:
    if _graph is not None and _chroma is not None:
        return _graph, _chroma
    if _manual_load:
        raise GraphNotLoadedError("请先在界面中加载全局索引")
    with _lock:
        if _graph is not None and _chroma is not None:
            return _graph, _chroma
        return _load_graph_unlocked()


def ensure_graph_for_write() -> tuple[GraphStore, ChromaStore]:
    """写入/索引类 API：允许在手动模式下懒加载图（不要求先加载检索引擎）。"""
    if _graph is not None and _chroma is not None:
        return _graph, _chroma
    with _lock:
        if _graph is not None and _chroma is not None:
            return _graph, _chroma
        return _load_graph_unlocked()


def ensure_search() -> SearchEngine:
    if _search is not None:
        return _search
    if _manual_load:
        raise GraphNotLoadedError("请先在界面中加载全局索引（含检索引擎）")
    with _lock:
        if _search is not None:
            return _search
        return _load_search_unlocked(build_corpus=False)


def ensure_rag() -> Any:
    ensure_search()
    return _rag


def shutdown() -> None:
    global _graph, _chroma, _search, _rag, _phase, _load_running
    _load_running = False
    if _graph:
        try:
            persist = settings.api_persist_on_shutdown
            if hasattr(_graph, "close"):
                _graph.close(persist=persist)
            elif persist:
                _graph.close()
        except Exception:
            pass
    _graph = None
    _chroma = None
    _search = None
    _rag = None
    _phase = "idle"
    reset_idle()


async def preload_graph_background(delay_s: float = 0.3) -> None:
    if _manual_load or not _fast_startup or _graph is not None:
        return
    await asyncio.sleep(delay_s)
    if _graph is not None:
        return
    try:
        await asyncio.to_thread(_load_graph_unlocked)
        logger.info("后台预加载图存储完成")
    except Exception:
        logger.warning("后台预加载图存储失败")


def start_background_preload() -> asyncio.Task | None:
    global _preload_task
    if _manual_load or not _fast_startup:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    _preload_task = loop.create_task(preload_graph_background())
    return _preload_task


async def _heartbeat_loop() -> None:
    global _heartbeat_running
    interval = max(60, settings.api_heartbeat_interval_minutes * 60)
    await asyncio.sleep(settings.api_heartbeat_initial_delay_seconds)
    while True:
        if _manual_load and _graph is None:
            await asyncio.sleep(interval)
            continue
        _heartbeat_running = True
        try:
            await asyncio.to_thread(run_heartbeat_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("定时心跳失败")
        finally:
            _heartbeat_running = False
        await asyncio.sleep(interval)


def start_heartbeat() -> asyncio.Task | None:
    global _heartbeat_task
    if not settings.api_heartbeat_enabled:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    _heartbeat_task = loop.create_task(_heartbeat_loop())
    logger.info(
        "索引心跳已配置（每 %d 分钟；手动模式下需先加载全局索引）",
        settings.api_heartbeat_interval_minutes,
    )
    return _heartbeat_task
