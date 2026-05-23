"""视觉关系专项指标（发明说明 6.4.2 问题8/10）。"""
from __future__ import annotations

from src.evaluation.metrics import match_relevant
from src.storage.factory import GraphStore

VISUAL_RELATIONS = frozenset({"VISUALLY_SIMILAR_TO", "NEAR_DUPLICATE"})


def requires_visual_multihop(store: GraphStore, seed_ids: list[str], target_name: str) -> bool:
    """相关文件是否必须经 ≥2 跳且含 VISUALLY_SIMILAR_TO 边才能从某种子到达。"""
    target_nodes = []
    for fid in seed_ids:
        if _reachable_visual_multihop(store, fid, target_name, max_depth=4):
            return True
    return False


def _reachable_visual_multihop(
    store: GraphStore,
    start_id: str,
    target_name: str,
    *,
    max_depth: int,
) -> bool:
    from collections import deque

    q: deque[tuple[str, int, bool]] = deque([(start_id, 0, False)])
    seen = {start_id}
    while q:
        fid, depth, used_visual = q.popleft()
        if depth >= max_depth:
            continue
        node = store.get_file(fid)
        if node and match_relevant(node.get("name", ""), target_name):
            return used_visual and depth >= 1
        for nb in store.get_neighbors(fid, hops=1):
            nid = nb.get("file_id")
            if not nid or nid in seen:
                continue
            rel = nb.get("rel_type", "")
            seen.add(nid)
            vis = used_visual or rel == "VISUALLY_SIMILAR_TO"
            q.append((nid, depth + 1, vis))
    return False


def multihop_visual_hit_rate(
    results_detail: list[dict],
    *,
    visual_dependent_targets: list[dict],
    store: GraphStore,
    seed_file_ids: list[str],
    k: int = 20,
) -> float:
    """
    多跳路径命中率：仅统计必须通过 VISUALLY_SIMILAR_TO 多跳（≥2）才能到达的相关文件。
    基线无该边时恒为 0。
    """
    if not visual_dependent_targets:
        return 0.0
    need = []
    for t in visual_dependent_targets:
        name = t.get("name") or t.get("path", "")
        if requires_visual_multihop(store, seed_file_ids, name):
            need.append(name)
    if not need:
        return 0.0
    hits = 0
    top = results_detail[:k]
    for name in need:
        for item in top:
            if match_relevant(item.get("name", ""), name):
                paths = item.get("explanation_paths") or []
                if any(p.get("rel_type") in VISUAL_RELATIONS for p in paths):
                    hits += 1
                    break
                if item.get("is_seed"):
                    continue
    return hits / len(need)
