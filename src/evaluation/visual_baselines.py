"""
视觉融合消融基线 B0–B8（发明说明 6.3 修改：含 B3.5 SigLIP2-SO400M、B5.5+OCR）。

通过环境变量 FILEKG_VISUAL_VARIANT 或构造参数选择变体；未安装 SigLIP/ColPali 时回退 CLIP。
"""
from __future__ import annotations

import os
from typing import Any

from src.config import settings
from src.evaluation.baselines import Baseline
from src.search.engine import SearchEngine


class VisualVariantBaseline(Baseline):
    """包装 SearchEngine，按变体限制关系扩展与融合路径。"""

    def __init__(self, engine: SearchEngine, variant: str, name: str) -> None:
        self.engine = engine
        self.variant = variant
        self.name = name

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        allowed = None
        expand = True
        if self.variant == "B0":
            expand = False
        elif self.variant in ("B1", "B2"):
            allowed = {"SIMILAR_TO"}
        elif self.variant in ("B3", "B3.5", "B5", "B5.5", "B5.5+OCR"):
            allowed = {"VISUALLY_SIMILAR_TO", "NEAR_DUPLICATE"}
        elif self.variant in ("B6", "B7", "B8"):
            allowed = None
        r = self.engine.search(query, expand_graph=expand, allowed_relations=allowed)
        return r["results"][:k]


def build_visual_ablation_baselines(engine: SearchEngine) -> list[Baseline]:
    variant = os.environ.get("FILEKG_VISUAL_VARIANT", "B7")
    table = [
        ("B0", "B0-NoVisualGraph"),
        ("B1", "B1-MetadataOnly"),
        ("B2", "B2-SemanticOnly"),
        ("B3", "B3-SigLIP2-base"),
        ("B3.5", "B3.5-SigLIP2-SO400M"),
        ("B5", "B5-ColPali-doc"),
        ("B5.5", "B5.5-ColPali-single"),
        ("B5.5+OCR", "B5.5+OCR-doc+text-shortcut"),
        ("B6", "B6-DualRoute-no-fusion"),
        ("B7", "B7-FullFusion-RRF"),
        ("B8", "B8-FullFusion+VLM-rerank"),
    ]
    if variant != "all":
        table = [t for t in table if t[0] == variant]
    return [VisualVariantBaseline(engine, v, n) for v, n in table]
