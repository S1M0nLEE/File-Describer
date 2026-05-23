"""graph_store.json 的 pickle 磁盘缓存，加速重复加载。"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def graph_fingerprint(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    st = path.stat()
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size}


def pickle_path(json_path: Path) -> Path:
    return json_path.with_suffix(".pkl")


def meta_path(json_path: Path) -> Path:
    return json_path.with_suffix(".cache.meta.json")


def try_load(
    json_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    fp = graph_fingerprint(json_path)
    if fp is None:
        return None
    mpath = meta_path(json_path)
    ppath = pickle_path(json_path)
    if not mpath.exists() or not ppath.exists():
        return None
    try:
        meta = json.loads(mpath.read_text(encoding="utf-8"))
        if meta != fp:
            return None
        with ppath.open("rb") as f:
            data = pickle.load(f)
        nodes = data.get("nodes") or {}
        edges = data.get("edges") or []
        logger.info("图磁盘缓存命中: %d 节点 (%s)", len(nodes), ppath.name)
        return nodes, edges
    except Exception as e:
        logger.warning("读取图磁盘缓存失败，将回退 JSON: %s", e)
        return None


def write(
    json_path: Path,
    nodes: dict[str, Any],
    edges: list[dict[str, Any]],
) -> None:
    fp = graph_fingerprint(json_path)
    if fp is None:
        return
    ppath = pickle_path(json_path)
    mpath = meta_path(json_path)
    try:
        ppath.parent.mkdir(parents=True, exist_ok=True)
        tmp = ppath.with_suffix(".pkl.tmp")
        with tmp.open("wb") as f:
            pickle.dump({"nodes": nodes, "edges": edges}, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(ppath)
        mpath.write_text(json.dumps(fp), encoding="utf-8")
    except Exception as e:
        logger.warning("写入图磁盘缓存失败: %s", e)


def invalidate(json_path: Path) -> None:
    for p in (pickle_path(json_path), meta_path(json_path)):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
