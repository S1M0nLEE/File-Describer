"""检索语料磁盘缓存（与 graph_store.json 指纹绑定）。"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

from src.storage.graph_disk_cache import graph_fingerprint

logger = logging.getLogger(__name__)


def cache_paths(data_dir: Path) -> tuple[Path, Path]:
    base = data_dir / "search_corpus"
    return base.with_suffix(".pkl"), base.with_suffix(".meta.json")


def try_load(
    graph_json: Path,
    data_dir: Path,
) -> list[dict[str, str]] | None:
    fp = graph_fingerprint(graph_json)
    if fp is None:
        return None
    pkl, meta = cache_paths(data_dir)
    if not pkl.exists() or not meta.exists():
        return None
    try:
        stored = json.loads(meta.read_text(encoding="utf-8"))
        if stored != fp:
            return None
        with pkl.open("rb") as f:
            corpus = pickle.load(f)
        if not isinstance(corpus, list):
            return None
        logger.info("检索语料磁盘缓存命中: %d 条", len(corpus))
        return corpus
    except Exception as e:
        logger.warning("读取语料缓存失败: %s", e)
        return None


def write(
    graph_json: Path,
    data_dir: Path,
    corpus: list[dict[str, str]],
) -> None:
    fp = graph_fingerprint(graph_json)
    if fp is None:
        return
    pkl, meta = cache_paths(data_dir)
    try:
        tmp = pkl.with_suffix(".pkl.tmp")
        with tmp.open("wb") as f:
            pickle.dump(corpus, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(pkl)
        meta.write_text(json.dumps(fp), encoding="utf-8")
        logger.info("已写入检索语料缓存 (%d 条)", len(corpus))
    except Exception as e:
        logger.warning("写入语料缓存失败: %s", e)


def invalidate(data_dir: Path) -> None:
    pkl, meta = cache_paths(data_dir)
    for p in (pkl, meta):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
