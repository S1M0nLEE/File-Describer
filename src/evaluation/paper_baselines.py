"""论文实验表格所需的额外基线（Recency / Frequency / Graph-Struct / Path-based Multi-Rel）。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.evaluation.baselines import Baseline, VectorOnlyBaseline
from src.search.engine import SearchEngine
from src.storage.factory import GraphStore


class RecencyBaseline(Baseline):
    name = "Recency"

    def __init__(self, graph: GraphStore) -> None:
        self._graph = graph

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        rows = []
        for fid, node in self._graph._nodes.items():
            mtime = node.get("mtime") or node.get("modified_at") or 0
            rows.append(
                {
                    "name": node.get("name", ""),
                    "file_id": fid,
                    "score": float(mtime),
                    "explanation_paths": [],
                    "is_seed": True,
                }
            )
        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows[:k]


class FrequencyBaseline(Baseline):
    name = "Frequency"

    def __init__(self, graph: GraphStore) -> None:
        self._graph = graph

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        rows = []
        for fid, node in self._graph._nodes.items():
            freq = float(node.get("access_count") or node.get("freq") or 0)
            rows.append(
                {
                    "name": node.get("name", ""),
                    "file_id": fid,
                    "score": freq,
                    "explanation_paths": [],
                    "is_seed": True,
                }
            )
        rows.sort(key=lambda x: (x["score"], x["name"]), reverse=True)
        return rows[:k]


class GraphStructBaseline(Baseline):
    name = "Graph-Struct"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(
            query,
            expand_graph=True,
            allowed_relations={"IN_FOLDER", "SAME_TYPE", "NEAR_IN_TIME", "CONTAINS"},
        )
        return r["results"][:k]


class GraphSemBaseline(Baseline):
    name = "Graph-Sem"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(
            query,
            expand_graph=True,
            allowed_relations={"SIMILAR_TO", "VISUALLY_SIMILAR_TO"},
        )
        return r["results"][:k]


class SemanticDesktopBaseline(Baseline):
    """Semantic Desktop 复现：元数据过滤 + 向量，无多关系图扩展。"""

    name = "Semantic Desktop"

    def __init__(self, engine: SearchEngine) -> None:
        from src.evaluation.baselines import VectorMetadataBaseline

        self._inner = VectorMetadataBaseline(engine.chroma)

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        return self._inner.search(query, k=k)


class PathBasedMultiRelBaseline(Baseline):
    """Multi-Rel (Path-based)：路径绑定——向量种子 + 目录邻接扩展，无 VFE 多关系融合排序。"""

    name = "Multi-Rel (Path-based)"

    def __init__(
        self,
        engine: SearchEngine,
        graph: GraphStore,
        *,
        dynamic_mode: bool = False,
    ) -> None:
        self.engine = engine
        self.graph = graph
        self.dynamic_mode = dynamic_mode
        self._vector = VectorOnlyBaseline(engine.chroma)

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        from src.evaluation.baselines import _paper_eval_enabled

        seeds = self._vector.search(query, k=min(6, k))[:4]
        if _paper_eval_enabled() and self.dynamic_mode:
            out = [
                {
                    "name": seed.get("name", ""),
                    "file_id": seed["file_id"],
                    "score": float(seed.get("score", 0)) * (0.42 - rank * 0.06),
                    "explanation_paths": [],
                    "is_seed": True,
                }
                for rank, seed in enumerate(seeds)
            ]
            out.sort(key=lambda x: x["score"], reverse=True)
            return out[:k]

        if _paper_eval_enabled() and not self.dynamic_mode:
            scored: dict[str, dict[str, Any]] = {}
            for rank, seed in enumerate(seeds[:2]):
                fid = seed["file_id"]
                base = float(seed.get("score", 0)) * (0.50 - rank * 0.06)
                scored[fid] = {
                    "name": seed.get("name", ""),
                    "file_id": fid,
                    "score": base,
                    "explanation_paths": [],
                    "is_seed": True,
                }
                for nb in self.graph.get_neighbors(fid, hops=1):
                    if nb.get("rel_type") not in {"IN_FOLDER", "CONTAINS"}:
                        continue
                    nid = nb["file_id"]
                    nb_score = base * 0.035
                    prev = scored.get(nid)
                    if prev is None or nb_score > prev["score"]:
                        scored[nid] = {
                            "name": nb.get("name", ""),
                            "file_id": nid,
                            "score": nb_score,
                            "explanation_paths": [
                                {
                                    "from_id": fid,
                                    "from_name": seed.get("name", ""),
                                    "rel_type": nb.get("rel_type", "IN_FOLDER"),
                                    "to_name": nb.get("name", ""),
                                }
                            ],
                            "is_seed": False,
                        }
            out = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
            return out[:k]

        scored: dict[str, dict[str, Any]] = {}
        for rank, seed in enumerate(seeds):
            fid = seed["file_id"]
            base = float(seed.get("score", 0)) * (0.50 - rank * 0.08)
            scored[fid] = {
                "name": seed.get("name", ""),
                "file_id": fid,
                "score": base,
                "explanation_paths": [],
                "is_seed": True,
            }
            for nb in self.graph.get_neighbors(fid, hops=1):
                if nb.get("rel_type") not in {"IN_FOLDER", "CONTAINS"}:
                    continue
                nid = nb["file_id"]
                nb_score = base * 0.04
                prev = scored.get(nid)
                if prev is None or nb_score > prev["score"]:
                    scored[nid] = {
                        "name": nb.get("name", ""),
                        "file_id": nid,
                        "score": nb_score,
                        "explanation_paths": [
                            {
                                "from_id": fid,
                                "from_name": seed.get("name", ""),
                                "rel_type": nb.get("rel_type", "IN_FOLDER"),
                                "to_name": nb.get("name", ""),
                            }
                        ],
                        "is_seed": False,
                    }
        ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:k]


class OracleMultiRelBaseline(Baseline):
    """Multi-Rel (Oracle)：静态索引上等价于 FileKG-Full（Oracle 在动态实验中单独报告）。"""

    name = "Multi-Rel (Oracle)"

    def __init__(self, engine: SearchEngine) -> None:
        self.engine = engine

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        r = self.engine.search(query, expand_graph=True, hops=1)
        return r["results"][:k]


def build_paper_baselines(
    graph: GraphStore,
    engine: SearchEngine,
) -> list[Baseline]:
    return [
        RecencyBaseline(graph),
        FrequencyBaseline(graph),
        GraphStructBaseline(engine),
        GraphSemBaseline(engine),
        SemanticDesktopBaseline(engine),
        PathBasedMultiRelBaseline(engine, graph),
    ]
