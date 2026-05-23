"""关系类型：中文标签、配色、图扩展权重（供前端图谱与 API 使用）。"""
from __future__ import annotations

from src.config import settings
from src.models.relationships import RELATION_LABELS_ZH

# Neo4j Browser 风格区分色（按关系语义分组）
RELATION_COLORS: dict[str, str] = {
    "IN_FOLDER": "#64748b",
    "SAME_TYPE": "#94a3b8",
    "SIMILAR_TO": "#4f8cff",
    "HAS_VERSION": "#a78bfa",
    "IS_PREVIOUS_VERSION_OF": "#c4b5fd",
    "VERSION_VARIANT": "#ddd6fe",
    "DEPENDS_ON": "#f97316",
    "REFERENCES": "#22d3ee",
    "CONTAINS": "#14b8a6",
    "NEAR_IN_TIME": "#fbbf24",
    "WORKFLOW_WITH": "#ec4899",
    "VISUALLY_SIMILAR_TO": "#8b5cf6",
    "NEAR_DUPLICATE": "#f43f5e",
    "IS_TEMPORARY_OF": "#71717a",
    "IS_BACKUP_OF": "#78716c",
    "BELONGS_TO_PROJECT": "#10b981",
    "TAGGED_WITH": "#06b6d4",
}

# 展示顺序：元数据 → 内容 → 行为 → 视觉 → 其它
RELATION_ORDER: list[str] = [
    "IN_FOLDER",
    "SAME_TYPE",
    "NEAR_IN_TIME",
    "BELONGS_TO_PROJECT",
    "TAGGED_WITH",
    "SIMILAR_TO",
    "DEPENDS_ON",
    "REFERENCES",
    "CONTAINS",
    "HAS_VERSION",
    "IS_PREVIOUS_VERSION_OF",
    "VERSION_VARIANT",
    "WORKFLOW_WITH",
    "VISUALLY_SIMILAR_TO",
    "NEAR_DUPLICATE",
    "IS_TEMPORARY_OF",
    "IS_BACKUP_OF",
]

DEFAULT_COLOR = "#6b7280"


def relation_schema(counts: dict[str, int] | None = None) -> list[dict]:
    """返回前端图例与筛选器用的关系元数据。"""
    weights = settings.relation_weights or {}
    counts = counts or {}
    known = set(RELATION_ORDER) | set(RELATION_LABELS_ZH.keys())
    for extra in counts:
        known.add(extra)
    ordered: list[str] = [r for r in RELATION_ORDER if r in known]
    for r in sorted(known):
        if r not in ordered:
            ordered.append(r)
    out: list[dict] = []
    for rel in ordered:
        out.append(
            {
                "type": rel,
                "label_zh": RELATION_LABELS_ZH.get(rel, rel),
                "color": RELATION_COLORS.get(rel, DEFAULT_COLOR),
                "weight": float(weights.get(rel, 0.5)),
                "count": int(counts.get(rel, 0)),
            }
        )
    return out
