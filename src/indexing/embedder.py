from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Literal

import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)

Backend = Literal["auto", "sentence_transformers", "fastembed", "hash"]


class Embedder:
    _instance: "Embedder | None" = None

    def __init__(self) -> None:
        self._backend: str | None = None
        self._st_model: Any = None
        self._fe_model: Any = None
        self._dim: int = settings.embedding_dim

    @classmethod
    def get(cls) -> "Embedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """切换后端或重建索引时重置单例。"""
        cls._instance = None

    @property
    def backend(self) -> str:
        self._ensure_loaded()
        return self._backend or "hash"

    @property
    def dimension(self) -> int:
        self._ensure_loaded()
        return self._dim

    def _preferred_backend(self) -> Backend:
        raw = os.environ.get("FILEKG_EMBEDDING_BACKEND") or getattr(
            settings, "embedding_backend", "auto"
        )
        return raw  # type: ignore[return-value]

    def _ensure_loaded(self) -> None:
        if self._backend is not None:
            return
        choice = self._preferred_backend()
        order: list[str]
        if choice == "auto":
            order = ["sentence_transformers", "fastembed", "hash"]
        else:
            order = [choice, "fastembed", "hash"] if choice != "hash" else ["hash"]

        for name in order:
            if name == "sentence_transformers" and self._try_sentence_transformers():
                return
            if name == "fastembed" and self._try_fastembed():
                return
        self._backend = "hash"
        logger.warning("所有嵌入后端不可用，使用哈希向量（仅适合联调）")

    def _try_sentence_transformers(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("加载 SentenceTransformer: %s", settings.embedding_model)
            self._st_model = SentenceTransformer(settings.embedding_model)
            get_dim = getattr(
                self._st_model, "get_embedding_dimension", None
            ) or getattr(self._st_model, "get_sentence_embedding_dimension", None)
            if get_dim:
                self._dim = int(get_dim())
            self._backend = "sentence_transformers"
            logger.info("嵌入后端就绪: sentence_transformers (dim=%s)", self._dim)
            return True
        except Exception as e:
            logger.debug("SentenceTransformer 不可用: %s", e)
            return False

    def _try_fastembed(self) -> bool:
        try:
            from fastembed import TextEmbedding

            model_name = settings.embedding_model
            # fastembed 使用 Qdrant 发布的 ONNX 权重
            fe_name = "BAAI/bge-small-zh-v1.5"
            if "bge" in model_name.lower() and "zh" in model_name.lower():
                fe_name = "BAAI/bge-small-zh-v1.5"
            elif "bge" in model_name.lower():
                fe_name = "BAAI/bge-small-en-v1.5"

            logger.info("加载 FastEmbed (ONNX): %s", fe_name)
            self._fe_model = TextEmbedding(model_name=fe_name)
            self._dim = 512
            self._backend = "fastembed"
            logger.info("嵌入后端就绪: fastembed (dim=%s)", self._dim)
            return True
        except Exception as e:
            logger.debug("FastEmbed 不可用: %s", e)
            return False

    def embed(self, text: str) -> list[float]:
        self._ensure_loaded()
        t = text or " "
        if self._backend == "sentence_transformers" and self._st_model:
            vec = self._st_model.encode(t, normalize_embeddings=True)
            out = vec.tolist()
            return self._maybe_project(out)
        if self._backend == "fastembed" and self._fe_model:
            vec = next(self._fe_model.embed([t]))
            return vec.tolist()
        return self._hash_embedding(t)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        if not texts:
            return []
        batch = [t or " " for t in texts]
        if self._backend == "sentence_transformers" and self._st_model:
            vecs = self._st_model.encode(batch, normalize_embeddings=True)
            return [self._maybe_project(v.tolist()) for v in vecs]
        if self._backend == "fastembed" and self._fe_model:
            return [v.tolist() for v in self._fe_model.embed(batch)]
        return [self._hash_embedding(t) for t in batch]

    def _maybe_project(self, vec: list[float]) -> list[float]:
        if not getattr(settings, "embedding_use_projection", True):
            return vec
        if len(vec) == settings.embedding_dim:
            return vec
        if len(vec) == getattr(settings, "embedding_raw_dim", 384):
            from src.indexing.projection import project_to_512

            return project_to_512(vec)
        return vec

    def _hash_embedding(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode()).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:8], "big"))
        v = rng.standard_normal(self._dim).astype(np.float32)
        v /= np.linalg.norm(v) + 1e-9
        return v.tolist()

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        denom = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-9
        return float(np.dot(va, vb) / denom)
