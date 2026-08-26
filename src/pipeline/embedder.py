"""Text embedding with sentence-transformers (BGE-small)."""

from typing import List, Optional, Union

import numpy as np

from src.config import Config


class Embedder:
  _instance: Optional["Embedder"] = None
  _model = None

  def __init__(self, config: Config):
    self.config = config
    self._model_name = config.embedding_model_name

  def _load_model(self):
    if Embedder._model is None:
      from sentence_transformers import SentenceTransformer
      Embedder._model = SentenceTransformer(self._model_name)
    return Embedder._model

  def encode(self, texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    model = self._load_model()
    single = isinstance(texts, str)
    inputs = [texts] if single else list(texts)
    inputs = [t or " " for t in inputs]
    vectors = model.encode(inputs, normalize_embeddings=True)
    if isinstance(vectors, np.ndarray):
      if single:
        return vectors[0].tolist()
      return [v.tolist() for v in vectors]
    return vectors[0].tolist() if single else [v.tolist() for v in vectors]

  @classmethod
  def reset_cache(cls):
    cls._model = None
    cls._instance = None
