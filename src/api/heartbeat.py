"""后台心跳：增量检查本机索引目录，更新图与向量，不重启服务。"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from src.api.index_roots import resolve_rag_index_roots
from src.config import settings
from src.indexing.builder import IndexBuilder

logger = logging.getLogger(__name__)

MANIFEST_PATH = settings.data_dir / "runtime_manifest.json"


def _read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_manifest(**updates: Any) -> dict[str, Any]:
    data = _read_manifest()
    data.update(updates)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST_PATH)
    return data


def manifest_snapshot() -> dict[str, Any]:
    return _read_manifest()


def run_heartbeat_sync() -> dict[str, Any]:
    """在线程池中执行：增量扫描 index_roots，跳过未变更文件。"""
    from src.api import runtime as app_runtime

    t0 = time.perf_counter()
    graph, chroma = app_runtime.ensure_graph()
    roots = resolve_rag_index_roots()
    if not roots:
        summary = {
            "ok": True,
            "roots": [],
            "message": "未配置 index_roots",
            "duration_s": round(time.perf_counter() - t0, 2),
        }
        write_manifest(
            last_heartbeat_at=_iso_now(),
            last_heartbeat=summary,
        )
        return summary

    prev = os.environ.get("FILEKG_INDEX_FAST")
    os.environ["FILEKG_INDEX_FAST"] = "1"
    builder = IndexBuilder(graph, chroma)
    runs: list[dict[str, Any]] = []
    total_new = 0
    total_updated = 0
    total_skipped = 0
    try:
        for root in roots:
            try:
                stats = builder.build(
                    root,
                    resume=True,
                    skip_relations=settings.api_heartbeat_skip_relations,
                    lightweight=True,
                )
                runs.append(stats)
                total_new += int(stats.get("indexed_new") or stats.get("file_count") or 0)
                total_skipped += int(stats.get("skipped_unchanged") or 0)
                total_updated += int(stats.get("updated") or 0)
            except Exception as e:
                logger.exception("心跳索引失败: %s", root)
                runs.append({"root": str(root), "error": str(e)})
    finally:
        if prev is None:
            os.environ.pop("FILEKG_INDEX_FAST", None)
        else:
            os.environ["FILEKG_INDEX_FAST"] = prev

    if total_new > 0 or total_updated > 0:
        app_runtime.invalidate_search_corpus()

    summary = {
        "ok": True,
        "roots": [str(r) for r in roots],
        "indexed_new": total_new,
        "skipped_unchanged": total_skipped,
        "updated": total_updated,
        "runs": runs,
        "duration_s": round(time.perf_counter() - t0, 2),
    }
    write_manifest(
        last_heartbeat_at=_iso_now(),
        last_heartbeat=summary,
        graph_warmed_at=_iso_now(),
    )
    logger.info(
        "心跳完成: 新增/更新写入 %d，跳过未变更 %d (%.1fs)",
        total_new,
        total_skipped,
        summary["duration_s"],
    )
    return summary


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
