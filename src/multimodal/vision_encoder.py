"""可插拔视觉编码器（默认 CLIP，本地 HF 路径或缓存）。"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_PDF_EXT = {".pdf"}


class VisionEncoder:
    _instance: VisionEncoder | None = None

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._text_model = None
        self._text_processor = None

    @classmethod
    def get(cls) -> VisionEncoder:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def available(self) -> bool:
        return self._load()

    def _feature_vector(self, output) -> np.ndarray:
        import torch

        if hasattr(output, "pooler_output") and output.pooler_output is not None:
            tensor = output.pooler_output[0]
        elif isinstance(output, torch.Tensor):
            tensor = output[0] if output.ndim > 1 else output
        else:
            tensor = torch.as_tensor(output).reshape(-1)
        vec = tensor.detach().cpu().numpy().astype(np.float32)
        n = np.linalg.norm(vec)
        return vec / (n + 1e-9) if n > 0 else vec

    def embed_image_path(self, path: Path, ext: str) -> np.ndarray | None:
        if not self._load():
            return None
        try:
            import torch
            from PIL import Image

            if ext in _IMAGE_EXT:
                img = Image.open(path).convert("RGB")
            elif ext in _PDF_EXT:
                import fitz

                doc = fitz.open(path)
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
            else:
                return None
            inputs = self._processor(images=img, return_tensors="pt")
            with torch.no_grad():
                feats = self._model.get_image_features(**inputs)
            return self._feature_vector(feats)
        except Exception as e:
            logger.debug("embed_image_path %s: %s", path, e)
            return None

    def embed_pil(self, img) -> np.ndarray | None:
        if not self._load():
            return None
        try:
            import torch

            inputs = self._processor(images=img.convert("RGB"), return_tensors="pt")
            with torch.no_grad():
                feats = self._model.get_image_features(**inputs)
            return self._feature_vector(feats)
        except Exception:
            return None

    def embed_text_query(self, text: str) -> np.ndarray | None:
        if not text.strip() or not self._load():
            return None
        try:
            import torch

            inputs = self._processor(text=[text], return_tensors="pt", padding=True)
            with torch.no_grad():
                feats = self._model.get_text_features(**inputs)
            return self._feature_vector(feats)
        except Exception:
            return None

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if not (
            settings.visual_enabled
            or settings.multimodal_visual_index_enabled
            or settings.multimodal_fuse_visual_search
        ):
            return False
        try:
            from transformers import CLIPModel, CLIPProcessor

            name = settings.visual_model
            local = Path(name)
            if local.is_dir():
                self._processor = CLIPProcessor.from_pretrained(str(local))
                self._model = CLIPModel.from_pretrained(str(local))
            else:
                self._processor = CLIPProcessor.from_pretrained(name)
                self._model = CLIPModel.from_pretrained(name)
            self._model.eval()
            logger.info("视觉编码器已加载: %s", name)
            return True
        except Exception as e:
            logger.info("视觉编码器未加载（可选 torch+transformers）: %s", e)
            return False
