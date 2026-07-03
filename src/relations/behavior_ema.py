"""行为类关系 EMA 权重更新（规格 3.3：0.7*old + 0.3*current）。"""
from __future__ import annotations

from src.config import settings

BEHAVIOR_RELATIONS = frozenset({"NEAR_IN_TIME", "WORKFLOW_WITH"})


def ema_update(old_weight: float, current_weight: float, *, alpha: float | None = None) -> float:
    a = alpha if alpha is not None else float(getattr(settings, "vfe_relation_ema_alpha", 0.7))
    return a * old_weight + (1.0 - a) * current_weight


def apply_behavior_ema(store) -> int:
    """对图中行为类边做 EMA 平滑（若边含 current_weight 字段）。"""
    edges = getattr(store, "_edges", None)
    if not edges:
        return 0
    updated = 0
    for e in edges:
        rt = e.get("type")
        if rt not in BEHAVIOR_RELATIONS:
            continue
        current = e.get("current_weight")
        if current is None:
            continue
        old = float(e.get("weight", current))
        e["weight"] = round(ema_update(old, float(current)), 4)
        updated += 1
    if updated and hasattr(store, "flush"):
        store.flush()
    return updated


def upsert_behavior_edge(
    store,
    src: str,
    dst: str,
    rel_type: str,
    current_weight: float,
) -> None:
    """添加或更新行为边，保留 current_weight 供 EMA。"""
    if rel_type not in BEHAVIOR_RELATIONS:
        return
    edges = getattr(store, "_edges", None)
    if edges is None:
        return
    for e in edges:
        if (
            e.get("type") == rel_type
            and {e.get("src"), e.get("dst")} == {src, dst}
        ):
            e["current_weight"] = current_weight
            e["weight"] = ema_update(float(e.get("weight", current_weight)), current_weight)
            return
    edges.append(
        {
            "src": src,
            "dst": dst,
            "type": rel_type,
            "weight": current_weight,
            "current_weight": current_weight,
            "undirected": True,
        }
    )
