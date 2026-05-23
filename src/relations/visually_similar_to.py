"""VISUALLY_SIMILAR_TO relation using CLIP on images."""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

from src.config import Config, get_config
from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor
from src.utils.helpers import is_image_extension


class VisuallySimilarToExtractor(RelationExtractor):
    relation_type = "VISUALLY_SIMILAR_TO"
    _clip_model = None
    _clip_processor = None

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        images = [f for f in file_nodes if is_image_extension(f.extension)]
        if len(images) < 2:
            return []

        embeddings = {}
        for f in images:
            emb = self._encode_image(f.path)
            if emb is not None:
                embeddings[f.id] = emb

        if len(embeddings) < 2:
            return []

        ids = list(embeddings.keys())
        matrix = np.array([embeddings[i] for i in ids], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
        matrix = matrix / norms
        sim = matrix @ matrix.T

        edges = []
        for i, sid in enumerate(ids):
            scores = [(j, sim[i, j]) for j in range(len(ids)) if j != i]
            scores.sort(key=lambda x: -x[1])
            for j, score in scores[: self.config.sim_topk]:
                if score < self.config.sim_threshold:
                    continue
                edges.append((sid, ids[j], "VISUALLY_SIMILAR_TO", {"score": float(score)}))
        return edges

    def _encode_image(self, path: str) -> Optional[np.ndarray]:
        try:
            from PIL import Image
            import torch
            model, processor = self._load_clip()
            image = Image.open(path).convert("RGB")
            inputs = processor(images=image, return_tensors="pt")
            with torch.no_grad():
                feats = model.get_image_features(**inputs)
            vec = feats[0].cpu().numpy()
            return vec / (np.linalg.norm(vec) + 1e-8)
        except Exception:
            return None

    def _load_clip(self):
        if VisuallySimilarToExtractor._clip_model is None:
            from transformers import CLIPModel, CLIPProcessor
            name = self.config.clip_model_name
            VisuallySimilarToExtractor._clip_model = CLIPModel.from_pretrained(name)
            VisuallySimilarToExtractor._clip_processor = CLIPProcessor.from_pretrained(name)
        return VisuallySimilarToExtractor._clip_model, VisuallySimilarToExtractor._clip_processor
