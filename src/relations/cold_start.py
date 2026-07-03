"""冷启动渐进激活（规格 6.2）。"""
from __future__ import annotations

from src.config import settings

# 规格定义的 12 种核心关系
CORE_12 = frozenset(
    {
        "IN_FOLDER",
        "CONTAINS",
        "BELONGS_TO_PROJECT",
        "SIMILAR_TO",
        "SAME_TYPE",
        "HAS_VERSION",
        "DEPENDS_ON",
        "REFERENCES",
        "NEAR_IN_TIME",
        "WORKFLOW_WITH",
        "VISUALLY_SIMILAR_TO",
        "TAGGED_WITH",
    }
)

PARSER_RELATIONS: dict[str, set[str]] = {
    "metadata": {"IN_FOLDER", "CONTAINS", "SAME_TYPE", "NEAR_IN_TIME", "BELONGS_TO_PROJECT"},
    "depends_on": {"DEPENDS_ON"},
    "references": {"REFERENCES"},
    "contains": {"CONTAINS"},
    "version": {"HAS_VERSION"},
    "similar_to": {"SIMILAR_TO"},
    "workflow": {"WORKFLOW_WITH"},
    "visual_fusion": {"VISUALLY_SIMILAR_TO"},
    "project_tags": {"TAGGED_WITH", "BELONGS_TO_PROJECT"},
}


class ColdStartManager:
    """累计事件数达标后逐步启用行为类关系。"""

    _instance: ColdStartManager | None = None

    def __init__(self) -> None:
        self.event_count = 0
        self.enabled_relations: set[str] = {
            "IN_FOLDER",
            "CONTAINS",
            "BELONGS_TO_PROJECT",
            "SIMILAR_TO",
            "SAME_TYPE",
            "TAGGED_WITH",
            "DEPENDS_ON",
            "REFERENCES",
            "HAS_VERSION",
            "VISUALLY_SIMILAR_TO",
        }

    @classmethod
    def get(cls) -> ColdStartManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def on_file_event(self, n: int = 1) -> None:
        self.event_count += n
        near_threshold = int(getattr(settings, "cold_start_near_in_time_events", 50))
        wf_threshold = int(getattr(settings, "cold_start_workflow_events", 150))
        if self.event_count >= near_threshold:
            self.enabled_relations.add("NEAR_IN_TIME")
        if self.event_count >= wf_threshold:
            self.enabled_relations.add("WORKFLOW_WITH")

    def parser_enabled(self, parser_name: str) -> bool:
        rels = PARSER_RELATIONS.get(parser_name, set())
        if not rels:
            return True
        return bool(rels & self.enabled_relations)

    def relation_enabled(self, rel_type: str) -> bool:
        if rel_type not in CORE_12:
            return True
        return rel_type in self.enabled_relations
