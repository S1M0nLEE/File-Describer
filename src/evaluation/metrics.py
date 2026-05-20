"""IR and FileKG-specific evaluation metrics."""

import math
from typing import Dict, List, Set


def average_precision(relevant: Set[str], ranked: List[str], k: int = 20) -> float:
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, doc in enumerate(ranked[:k], 1):
        if doc in relevant:
            hits += 1
            score += hits / i
    return score / min(len(relevant), k)


def dcg(rels: List[int], k: int) -> float:
    s = 0.0
    for i, rel in enumerate(rels[:k]):
        s += rel / math.log2(i + 2)
    return s


def ndcg_at_k(relevant: Set[str], ranked: List[str], k: int = 20) -> float:
    gains = [1 if d in relevant else 0 for d in ranked[:k]]
    ideal = sorted(gains, reverse=True)
    idcg = dcg(ideal, k)
    if idcg == 0:
        return 0.0
    return dcg(gains, k) / idcg


def recall_at_k(relevant: Set[str], ranked: List[str], k: int = 20) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def r_indirect_at_k(
    relevant: Set[str],
    ranked: List[str],
    indirect: Set[str],
    k: int = 20,
) -> float:
    found = set(ranked[:k]) & (relevant | indirect)
    return len(found) / max(len(relevant), 1)


def indirect_recall_at_k(indirect: Set[str], ranked: List[str], k: int = 20) -> float:
    if not indirect:
        return 0.0
    return len(set(ranked[:k]) & indirect) / len(indirect)


def graph_discovery_at_k(
    ranked_ids: List[str],
    reasoning_map: Dict[str, List[str]],
    k: int = 20,
) -> float:
    if not ranked_ids:
        return 0.0
    count = sum(1 for fid in ranked_ids[:k] if len(reasoning_map.get(fid, [])) > 1)
    return count / min(k, len(ranked_ids))


def graph_only_discovery_at_k(
    ranked_ids: List[str],
    reasoning_map: Dict[str, List[str]],
    vector_top_k: Set[str],
    k: int = 20,
) -> float:
    """Top-K results found via graph expansion but not in vector-only top-K."""
    if not ranked_ids:
        return 0.0
    count = 0
    for fid in ranked_ids[:k]:
        if fid in vector_top_k:
            continue
        if len(reasoning_map.get(fid, [])) > 1:
            count += 1
    return count / min(k, len(ranked_ids))


def serendipity_at_k(
    ranked_ids: List[str],
    reasoning_map: Dict[str, List[str]],
    vector_top_k: Set[str],
    targets: Set[str],
    k: int = 20,
) -> float:
    """Relevant/indirect hits in top-K that are graph-discovered and outside vector top-K."""
    if not ranked_ids or not targets:
        return 0.0
    count = 0
    for fid in ranked_ids[:k]:
        if fid not in targets:
            continue
        if fid in vector_top_k:
            continue
        if len(reasoning_map.get(fid, [])) > 1:
            count += 1
    return count / min(k, len(ranked_ids))


def explain_coverage(
    reasoning_map: Dict[str, List[str]],
    ranked_ids: List[str],
    k: int = 20,
) -> float:
    if not ranked_ids:
        return 0.0
    explained = sum(
        1 for fid in ranked_ids[:k]
        if reasoning_map.get(fid) and len(reasoning_map[fid]) > 0
    )
    return explained / min(k, len(ranked_ids))


def path_fidelity_sample(
    reasoning_map: Dict[str, List[str]],
    ranked_ids: List[str],
    valid_edges: Set[tuple],
    k: int = 20,
    sample_n: int = 30,
) -> float:
    """Fraction of reasoning paths whose adjacent pairs match a known graph edge."""
    checked = 0
    valid = 0
    for fid in ranked_ids[:k]:
        path = reasoning_map.get(fid, [])
        if len(path) < 2:
            continue
        for i in range(len(path) - 1):
            if checked >= sample_n:
                break
            checked += 1
            if (path[i], path[i + 1]) in valid_edges or (path[i + 1], path[i]) in valid_edges:
                valid += 1
    if checked == 0:
        return 0.0
    return valid / checked


def robustness_ratio(before: float, after: float) -> float:
    if before <= 1e-9:
        return 1.0 if after <= 1e-9 else 0.0
    return min(1.0, after / before)
