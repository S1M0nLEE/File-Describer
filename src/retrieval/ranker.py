"""Multi-factor ranking: vector-primary with bounded graph/metadata/BM25 boosts."""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np

from src.config import Config, get_config
from src.models.file_descriptor import FileDescriptor
from src.retrieval.graph_expander import ExpandedNode


@dataclass
class ScoredFile:
    file_id: str
    path: str = ""
    name: str = ""
    summary: str = ""
    score: float = 0.0
    vector_score: float = 0.0
    graph_score: float = 0.0
    time_score: float = 0.0
    rule_score: float = 0.0
    bm25_score: float = 0.0
    reasoning_path: List[str] = field(default_factory=list)
    relation_types: List[str] = field(default_factory=list)


class Ranker:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()

    def score_and_rank(
        self,
        query_emb: List[float],
        candidates: Dict[str, FileDescriptor],
        seed_ids: List[str],
        expanded: List[ExpandedNode],
        parsed_keywords: Optional[List[str]] = None,
        top_k: int = 20,
        bm25_scores: Optional[Dict[str, float]] = None,
        vector_seed_ids: Optional[List[str]] = None,
    ) -> List[ScoredFile]:
        seed_set = set(seed_ids)
        vector_seeds = set(vector_seed_ids or seed_ids)
        expand_map = {e.file_id: e for e in expanded}
        keywords = [k.lower() for k in (parsed_keywords or []) if len(k) > 1]
        now = time.time()
        bm25_scores = bm25_scores or {}

        q = np.array(query_emb, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-8)

        scored: List[ScoredFile] = []
        for fid, f in candidates.items():
            if not f.file_embedding:
                continue
            v = np.array(f.file_embedding, dtype=np.float32)
            v = v / (np.linalg.norm(v) + 1e-8)
            vector_score = float(np.dot(q, v))

            exp = expand_map.get(fid)
            graph_score = 0.0
            if exp and len(exp.reasoning_path) > 1 and vector_score >= self.config.min_graph_expand_vector:
                graph_score = exp.graph_weight * vector_score
                if fid not in vector_seeds:
                    graph_score += self.config.graph_discovery_boost

            age_days = max(0.0, (now - f.modified_time) / 86400.0)
            time_score = math.exp(-age_days / 30.0)

            text = (f.display_summary + " " + f.name + " " + f.path).lower()
            rule_score = min(1.0, sum(0.2 for kw in keywords if kw in text))
            bm25_score = float(bm25_scores.get(fid, 0.0))

            aux = (
                self.config.beta * graph_score
                + self.config.gamma * time_score
                + self.config.delta * rule_score
                + self.config.bm25_fusion_weight * bm25_score * vector_score
            )
            if fid in vector_seeds and self.config.seed_boost > 0:
                aux += self.config.seed_boost * vector_score

            aux = min(self.config.max_aux_boost, aux)
            total = self.config.alpha * vector_score + aux

            path = exp.reasoning_path if exp else ([fid] if fid in seed_set else [])
            scored.append(ScoredFile(
                file_id=fid,
                path=f.path,
                name=f.name,
                summary=f.display_summary,
                score=total,
                vector_score=vector_score,
                graph_score=graph_score,
                time_score=time_score,
                rule_score=rule_score,
                bm25_score=bm25_score,
                reasoning_path=path,
                relation_types=exp.relation_types if exp else [],
            ))

        scored.sort(key=lambda x: (-x.score, -x.vector_score))
        return scored[:top_k]
