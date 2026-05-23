from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

# 方案定义：意外发现应来自核心逻辑关系，而非目录/类型聚类
SERENDIPITY_RELATIONS = frozenset(
    {
        "DEPENDS_ON",
        "WORKFLOW_WITH",
        "REFERENCES",
        "HAS_VERSION",
        "IS_PREVIOUS_VERSION_OF",
        "VERSION_VARIANT",
        "CONTAINS",
        "IS_BACKUP_OF",
        "IS_TEMPORARY_OF",
        "BELONGS_TO_PROJECT",
    }
)

# 含目录/时间结构关系的间接发现（专利说明书中「多维关系」完整口径）
GRAPH_DISCOVERY_RELATIONS = SERENDIPITY_RELATIONS | frozenset(
    {"IN_FOLDER", "NEAR_IN_TIME", "SAME_TYPE"}
)

# 视觉依赖查询集：计入跨模态图边（发明说明 6.4.2 问题 8/10）
VISUAL_GRAPH_RELATIONS = GRAPH_DISCOVERY_RELATIONS | frozenset(
    {"VISUALLY_SIMILAR_TO", "NEAR_DUPLICATE"}
)


@dataclass
class QueryMetrics:
    query: str
    ap: float = 0.0
    p_at_k: float = 0.0
    r_at_k: float = 0.0
    ndcg_at_k: float = 0.0
    recall_direct: float = 0.0
    recall_indirect: float = 0.0
    serendipity: float = 0.0
    graph_discovery: float = 0.0
    explain_coverage: float = 0.0
    latency_ms: float = 0.0
    retrieved: list[str] = field(default_factory=list)
    relation_hits: dict[str, int] = field(default_factory=dict)


def _basename(path_or_name: str) -> str:
    return Path(path_or_name.replace("\\", "/")).name.lower()


def match_relevant(retrieved: str, target: str) -> bool:
    """严格匹配：仅比较文件名（不含路径子串误命中）。"""
    return _basename(retrieved) == _basename(target)


def relevant_set(direct: list[str], indirect: list[str]) -> tuple[set[str], set[str], set[str]]:
    d = set(direct)
    i = set(indirect)
    return d | i, d, i


def precision_at_k(retrieved: list[str], relevant: set[str], k: int = 20) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    hits = sum(1 for r in top if any(match_relevant(r, rel) for rel in relevant))
    return hits / k


def recall_at_k(retrieved: list[str], relevant: set[str], k: int = 20) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    found = 0
    for rel in relevant:
        if any(match_relevant(r, rel) for r in top):
            found += 1
    return found / len(relevant)


def recall_subset(retrieved: list[str], subset: set[str], k: int = 20) -> float:
    if not subset:
        return 0.0
    return recall_at_k(retrieved, subset, k)


def average_precision(retrieved: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, r in enumerate(retrieved, 1):
        if any(match_relevant(r, rel) for rel in relevant):
            hits += 1
            score += hits / i
    return score / len(relevant)


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int = 20) -> float:
    """NDCG@k：理想 DCG 为所有相关项排在最前。"""
    if not relevant:
        return 0.0

    def dcg(ranks: list[str]) -> float:
        s = 0.0
        for i, r in enumerate(ranks[:k], 1):
            if any(match_relevant(r, x) for x in relevant):
                s += 1.0 / math.log2(i + 1)
        return s

    n_rel = len(relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(n_rel, k) + 1))
    if ideal == 0:
        return 0.0
    return dcg(retrieved) / ideal


def serendipity_at_k(
    results_detail: list[dict],
    direct: set[str],
    indirect: set[str],
    k: int = 20,
) -> float:
    """
    修正定义：相关文件通过 SERENDIPITY_RELATIONS 中至少一种关系被召回，
    且该文件属于 indirect 标注，或虽为 direct 但非纯语义种子（有核心关系路径）。
    """
    all_rel = direct | indirect
    if not all_rel:
        return 0.0

    serendipitous = 0
    for rel in all_rel:
        for item in results_detail[:k]:
            if not match_relevant(item.get("name", ""), rel):
                continue
            paths = item.get("explanation_paths") or []
            core_paths = [p for p in paths if p.get("rel_type") in SERENDIPITY_RELATIONS]
            is_seed = item.get("is_seed", False)

            if rel in indirect and core_paths:
                serendipitous += 1
                break
            if rel in indirect and not is_seed and paths:
                serendipitous += 1
                break
            if rel in direct and core_paths:
                serendipitous += 1
                break
            break

    return serendipitous / len(all_rel)


def graph_discovery_at_k(
    results_detail: list[dict],
    direct: set[str],
    indirect: set[str],
    k: int = 20,
) -> float:
    """通过任意非纯语义图关系召回间接相关项的比例。"""
    all_rel = direct | indirect
    if not all_rel:
        return 0.0
    found = 0
    for rel in all_rel:
        for item in results_detail[:k]:
            if not match_relevant(item.get("name", ""), rel):
                continue
            paths = item.get("explanation_paths") or []
            if rel in indirect and paths:
                if any(p.get("rel_type") in GRAPH_DISCOVERY_RELATIONS for p in paths):
                    found += 1
                    break
            elif rel in direct and paths:
                found += 1
                break
            break
    return found / len(all_rel)


def explainability_coverage(
    results_detail: list[dict],
    direct: set[str],
    k: int = 20,
) -> float:
    """可解释：非种子命中须有核心关系路径；种子命中须为 direct 语义命中。"""
    if not results_detail[:k]:
        return 0.0
    explained = 0
    for item in results_detail[:k]:
        paths = item.get("explanation_paths") or []
        is_seed = item.get("is_seed", False)
        name = item.get("name", "")
        core_paths = [p for p in paths if p.get("rel_type") in SERENDIPITY_RELATIONS]

        if core_paths:
            explained += 1
        elif is_seed and any(match_relevant(name, d) for d in direct):
            explained += 1
        elif paths and any(p.get("rel_type") not in ("SIMILAR_TO",) for p in paths):
            explained += 1
    return explained / min(k, len(results_detail))


def aggregate(metrics: list[QueryMetrics]) -> dict[str, float]:
    if not metrics:
        return {}
    n = len(metrics)
    return {
        "MAP@20": sum(m.ap for m in metrics) / n,
        "P@20": sum(m.p_at_k for m in metrics) / n,
        "R@20": sum(m.r_at_k for m in metrics) / n,
        "NDCG@20": sum(m.ndcg_at_k for m in metrics) / n,
        "Recall_direct@20": sum(m.recall_direct for m in metrics) / n,
        "Recall_indirect@20": sum(m.recall_indirect for m in metrics) / n,
        "Serendipity@20": sum(m.serendipity for m in metrics) / n,
        "GraphDiscovery@20": sum(m.graph_discovery for m in metrics) / n,
        "Explainability@20": sum(m.explain_coverage for m in metrics) / n,
        "latency_ms_avg": sum(m.latency_ms for m in metrics) / n,
    }
