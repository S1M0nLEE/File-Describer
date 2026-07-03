"""内生解释生成（规格 4.3 / 论文 5.3）。"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from src.config import settings
from src.models.relationships import RELATION_LABELS_ZH

_BEHAVIOR_PRIORITY = (
    "WORKFLOW_WITH",
    "NEAR_IN_TIME",
    "DEPENDS_ON",
    "REFERENCES",
    "SIMILAR_TO",
    "IN_FOLDER",
    "CONTAINS",
    "BELONGS_TO_PROJECT",
    "VISUALLY_SIMILAR_TO",
    "SAME_TYPE",
    "HAS_VERSION",
    "TAGGED_WITH",
)


def weighted_centrality(node: dict, hit: Any, *, max_graph: float) -> float:
    gw = getattr(hit, "graph_weight", 0.0) if hit else 0.0
    if max_graph <= 0:
        return 0.0
    return min(1.0, gw / max_graph)


def days_since_last_access(node: dict) -> float:
    for key in ("last_accessed", "modified_time"):
        raw = node.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw))
            return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
        except Exception:
            continue
    return 365.0


def rule_match_score(query: str, node: dict) -> float:
    """文件名精确匹配 1.0，扩展名匹配 0.5。"""
    q = (query or "").strip().lower()
    name = (node.get("name") or "").lower()
    if not q:
        return 0.0
    if q == name or (q in name and len(q) >= 4):
        return 1.0
    ext = node.get("extension", "").lower()
    if ext and (q == ext.lstrip(".") or q.endswith(ext)):
        return 0.5
    return 0.0


def normalized_click_freq(node: dict, *, max_freq: float) -> float:
    logs = node.get("access_log") or []
    retrieved = sum(1 for e in logs if e.get("relation_type") or e.get("query_hash"))
    if max_freq <= 0:
        return 0.0
    return min(1.0, retrieved / max_freq)


def compute_factor_scores(
    query: str,
    node: dict,
    hit: Any,
    *,
    semantic: float,
    max_graph: float,
    max_freq: float,
) -> dict[str, float]:
    age = days_since_last_access(node)
    return {
        "semantic": settings.w_semantic * semantic,
        "centrality": settings.w_graph * weighted_centrality(node, hit, max_graph=max_graph),
        "recency": settings.w_time * math.exp(-settings.time_decay_lambda * age),
        "rule": settings.w_rule * rule_match_score(query, node),
        "frequency": settings.w_personal * normalized_click_freq(node, max_freq=max_freq),
    }


def _pick_related_name(store, hit: Any) -> tuple[str, str]:
    paths = getattr(hit, "paths", None) or []
    ordered = sorted(
        paths,
        key=lambda p: (
            _BEHAVIOR_PRIORITY.index(p.get("rel_type"))
            if p.get("rel_type") in _BEHAVIOR_PRIORITY
            else 99,
            -float(p.get("weight") or 0),
        ),
    )
    for p in ordered:
        rel = p.get("rel_type") or ""
        if rel in _BEHAVIOR_PRIORITY[:3]:
            fid = p.get("to_id") or p.get("file_id")
            if fid and store:
                nb = store.get_file(fid) or {}
                return rel, nb.get("name") or p.get("to_name") or fid
    if ordered:
        p = ordered[0]
        return p.get("rel_type") or "", p.get("to_name") or ""
    return "", ""


def generate_explanation(
    query: str,
    node: dict,
    hit: Any,
    factor_scores: dict[str, float],
    store=None,
) -> str:
    name = node.get("name") or node.get("path") or "该文件"
    ranked = sorted(factor_scores.items(), key=lambda x: x[1], reverse=True)
    top_factors = [k for k, v in ranked if v > 0][:2]
    primary = top_factors[0] if top_factors else "semantic"

    if primary == "centrality":
        rel, related = _pick_related_name(store, hit)
        if rel == "WORKFLOW_WITH" and related:
            return f"文件 {name} 被返回，因为它与高匹配文件 {related} 在工作流中频繁共同编辑。"
        if rel == "NEAR_IN_TIME" and related:
            return f"文件 {name} 被返回，因为它与您近期使用的 {related} 在同一时间段操作。"
        if rel == "SIMILAR_TO" and related:
            return f"文件 {name} 被返回，因为它与语义高度匹配的 {related} 内容相似。"
        if rel == "DEPENDS_ON" and related:
            return f"文件 {name} 被返回，因为它依赖或关联文件 {related}。"
        if rel == "REFERENCES" and related:
            return f"文件 {name} 被返回，因为它在文档中引用了 {related}。"
        if rel:
            label = RELATION_LABELS_ZH.get(rel, rel)
            if related:
                return f"文件 {name} 被返回，因为它通过「{label}」与 {related} 相关联。"
        return f"文件 {name} 在您的文件关系网络中处于关键关联位置。"

    if primary == "semantic":
        return f"文件 {name} 的文本内容与您的查询高度语义匹配。"

    if primary == "recency":
        return f"文件 {name} 是您近期频繁使用的文件，与当前任务相关性更高。"

    if primary == "rule":
        return f"文件 {name} 的文件名或类型与您的查询精确匹配。"

    if primary == "frequency":
        return f"文件 {name} 在您的历史检索与访问记录中出现频率较高。"

    return f"文件 {name} 综合匹配度最高，由语义、关联度与使用频率共同决定。"


def explanation_fidelity(factor_scores: dict[str, float], total_score: float, *, top_n_factors: int = 2) -> float:
    if total_score <= 0:
        return 0.0
    ranked = sorted(factor_scores.items(), key=lambda x: x[1], reverse=True)[:top_n_factors]
    attributed = sum(v for _, v in ranked)
    return round(min(1.0, attributed / total_score), 4)


def explainability_coverage(results: list[dict], *, k: int = 20) -> float:
    """ExplainCov：非纯语义匹配解释占比。"""
    top = results[:k]
    if not top:
        return 0.0
    covered = 0
    for r in top:
        expl = r.get("explanation") or ""
        paths = r.get("explanation_paths") or []
        if paths and not r.get("is_seed"):
            covered += 1
        elif expl and "语义匹配" not in expl and "精确匹配" not in expl:
            covered += 1
    return round(covered / len(top), 4)
