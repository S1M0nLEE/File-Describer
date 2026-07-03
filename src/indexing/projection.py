"""384 维文本嵌入 → 512 维投影（规格 7.1，与 CLIP 对齐）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from src.config import settings

_PROJ: np.ndarray | None = None


def projection_matrix(raw_dim: int = 384, out_dim: int = 512) -> np.ndarray:
    global _PROJ
    if _PROJ is not None and _PROJ.shape == (raw_dim, out_dim):
        return _PROJ

    cache = Path(settings.data_dir) / f"projection_{raw_dim}_{out_dim}.npy"
    if cache.is_file():
        _PROJ = np.load(cache)
        return _PROJ

    seed = int.from_bytes(hashlib.sha256(b"filekg-minilm-coco-proj").digest()[:8], "big")
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((raw_dim, out_dim)).astype(np.float32)
    w /= np.sqrt(raw_dim)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, w)
    _PROJ = w
    return _PROJ


def project_to_512(vec: list[float] | np.ndarray) -> list[float]:
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    raw_dim = int(getattr(settings, "embedding_raw_dim", 384))
    out_dim = int(getattr(settings, "embedding_dim", 512))
    if v.size == out_dim:
        n = np.linalg.norm(v)
        return (v / (n + 1e-9)).tolist()
    if v.size != raw_dim:
        if v.size > out_dim:
            v = v[:out_dim]
        else:
            v = np.pad(v, (0, out_dim - v.size))
    w = projection_matrix(raw_dim, out_dim)
    out = v @ w
    n = np.linalg.norm(out)
    if n > 0:
        out = out / n
    return out.tolist()


def project_batch(vecs: list[list[float]]) -> list[list[float]]:
    return [project_to_512(v) for v in vecs]
