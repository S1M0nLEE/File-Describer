"""SIMILAR_TO relation via FAISS on file embeddings."""

from typing import List, Optional

import numpy as np

from src.config import Config, get_config
from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor


class SimilarToExtractor(RelationExtractor):
    relation_type = "SIMILAR_TO"

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        valid = [f for f in file_nodes if f.file_embedding]
        if len(valid) < 2:
            return []

        import faiss
        dim = len(valid[0].file_embedding)
        matrix = np.array([f.file_embedding for f in valid], dtype=np.float32)
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(dim)
        index.add(matrix)

        k = min(self.config.sim_topk + 1, len(valid))
        scores, indices = index.search(matrix, k)
        edges = []
        for i, src in enumerate(valid):
            for j, score in zip(indices[i], scores[i]):
                if j < 0 or j == i:
                    continue
                if float(score) < self.config.sim_threshold:
                    continue
                tgt = valid[int(j)]
                edges.append((
                    src.id, tgt.id, "SIMILAR_TO",
                    {"score": float(score)},
                ))
        return edges
