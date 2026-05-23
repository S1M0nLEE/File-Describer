"""感知哈希与 NEAR_DUPLICATE 边（发明说明 5.2.1 修改：不删节点，建边保留双方）。"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def compute_phash(path: Path) -> int | None:
    try:
        from PIL import Image

        img = Image.open(path).convert("L").resize((32, 32), Image.Resampling.LANCZOS)
        pixels = np.array(img, dtype=np.float32)
        dct = np.fft.fft2(pixels)
        dct_low = dct[:8, :8]
        med = np.median(dct_low.real)
        bits = (dct_low.real > med).flatten()
        val = 0
        for b in bits[:64]:
            val = (val << 1) | int(b)
        return val
    except Exception as e:
        logger.debug("phash %s: %s", path, e)
        return None


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def discover_near_duplicate_edges(
    file_phashes: dict[str, tuple[Path, int]],
) -> list[tuple[str, str, int]]:
    """返回 (id_a, id_b, hamming) 列表；双方均保留参与后续向量化。"""
    t = int(getattr(settings, "visual_phash_threshold", 6))
    ids = list(file_phashes.keys())
    pairs: list[tuple[str, str, int]] = []
    for i, fid_a in enumerate(ids):
        _, ha = file_phashes[fid_a]
        for fid_b in ids[i + 1 :]:
            _, hb = file_phashes[fid_b]
            d = hamming_distance(ha, hb)
            if d <= t:
                pairs.append((fid_a, fid_b, d))
    return pairs
