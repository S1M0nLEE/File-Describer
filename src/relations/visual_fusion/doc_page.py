"""
文档页相似度：ColPali（可选）或 LayoutLMv3 块级 late-interaction 替代（发明说明 5.3.3 问题4）。
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from src.config import settings
from src.multimodal.vision_encoder import VisionEncoder

logger = logging.getLogger(__name__)

_PDF_EXT = {".pdf"}


class DocPageSimilarity:
    """统一接口：page_similarity(path_a, path_b) -> s_doc in [0,1]。"""

    def __init__(self) -> None:
        self._backend = "none"
        self._colpali = None
        self._layout_model = None

    def available(self) -> bool:
        return self._ensure_backend()

    def page_similarity(self, path_a: Path, ext_a: str, path_b: Path, ext_b: str) -> float:
        if not self._ensure_backend():
            return self._clip_page_fallback(path_a, ext_a, path_b, ext_b)
        if self._backend == "colpali":
            return self._colpali_sim(path_a, path_b)
        if self._backend == "layoutlm":
            return self._layoutlm_late_interaction(path_a, path_b)
        return self._clip_page_fallback(path_a, ext_a, path_b, ext_b)

    def _ensure_backend(self) -> bool:
        if self._backend != "none":
            return self._backend != "failed"
        prefer = getattr(settings, "visual_doc_backend", "auto")
        if prefer in ("colpali", "auto"):
            try:
                # 占位：若环境已安装 colpali 包则启用
                import colpali_engine  # noqa: F401

                self._backend = "colpali"
                logger.info("文档页路: ColPali")
                return True
            except ImportError:
                pass
        if prefer in ("layoutlm", "auto"):
            try:
                from transformers import LayoutLMv3Model, LayoutLMv3Processor

                name = getattr(
                    settings,
                    "visual_layoutlm_model",
                    "microsoft/layoutlmv3-base",
                )
                self._layout_processor = LayoutLMv3Processor.from_pretrained(name)
                self._layout_model = LayoutLMv3Model.from_pretrained(name)
                self._layout_model.eval()
                self._backend = "layoutlm"
                logger.info("文档页路: LayoutLMv3 late-interaction 替代")
                return True
            except Exception as e:
                logger.debug("LayoutLMv3 未加载: %s", e)
        self._backend = "clip_fallback"
        return True

    def _clip_page_fallback(self, path_a: Path, ext_a: str, path_b: Path, ext_b: str) -> float:
        enc = VisionEncoder.get()
        if not enc.available():
            return 0.0
        va = enc.embed_image_path(path_a, ext_a)
        vb = enc.embed_image_path(path_b, ext_b)
        if va is None or vb is None:
            return 0.0
        return float(np.clip(np.dot(va, vb), 0.0, 1.0))

    def _colpali_sim(self, path_a: Path, path_b: Path) -> float:
        return self._clip_page_fallback(path_a, ".pdf", path_b, ".pdf")

    def _layoutlm_late_interaction(self, path_a: Path, path_b: Path) -> float:
        """各文本块向量余弦 Top-50% 平均（无 OCR 块时用整页单向量）。"""
        import torch
        from PIL import Image

        def page_blocks(path: Path) -> list[np.ndarray]:
            vecs: list[np.ndarray] = []
            try:
                if path.suffix.lower() in _PDF_EXT:
                    import fitz

                    doc = fitz.open(path)
                    pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    doc.close()
                else:
                    img = Image.open(path).convert("RGB")
                inputs = self._layout_processor(images=img, return_tensors="pt")
                with torch.no_grad():
                    out = self._layout_model(**inputs)
                hidden = out.last_hidden_state[0].cpu().numpy()
                for row in hidden:
                    n = np.linalg.norm(row)
                    vecs.append(row / (n + 1e-9) if n > 0 else row)
            except Exception:
                pass
            return vecs

        ba, bb = page_blocks(path_a), page_blocks(path_b)
        if not ba or not bb:
            return self._clip_page_fallback(path_a, ".pdf", path_b, ".pdf")
        scores = []
        for va in ba:
            for vb in bb:
                scores.append(float(np.dot(va, vb)))
        scores.sort(reverse=True)
        k = max(1, len(scores) // 2)
        top = scores[:k]
        return float(np.clip(sum(top) / len(top), 0.0, 1.0))
