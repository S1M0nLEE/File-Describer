from __future__ import annotations

import logging
from typing import Any as Neo4jStore
from typing import Callable

from src.models.descriptor import FileDescriptor
from src.relations.base import RelationParser
from src.relations.content_relations import (
    ContainsParser,
    DependsOnParser,
    ReferencesParser,
    SimilarToParser,
    WeakFileParser,
)
from src.relations.metadata_relations import MetadataRelationsParser
from src.relations.project_relations import ProjectRelationsParser
from src.relations.version_relations import VersionRelationsParser
from src.relations.visual_relations import VisualSimilarParser
from src.relations.workflow_relations import WorkflowParser

logger = logging.getLogger(__name__)

# 方案 4.2.11：元数据 -> 内容解析 -> 语义 -> 行为/跨模态 -> 弱文件 -> 项目标签
DEFAULT_PIPELINE: list[type[RelationParser]] = [
    MetadataRelationsParser,
    DependsOnParser,
    ReferencesParser,
    ContainsParser,
    VersionRelationsParser,
    SimilarToParser,
    WorkflowParser,
    VisualSimilarParser,
    WeakFileParser,
    ProjectRelationsParser,
]


class RelationDiscoveryPipeline:
    """关系发现管线：元数据 -> 内容解析 -> 语义 -> 行为。"""

    def __init__(
        self,
        parsers: list[RelationParser] | None = None,
        on_progress: Callable[[str, int], None] | None = None,
    ) -> None:
        self.parsers = parsers or [cls() for cls in DEFAULT_PIPELINE]
        self.on_progress = on_progress

    def run(
        self,
        descriptors: list[FileDescriptor],
        store: Neo4jStore,
    ) -> dict[str, int]:
        import os

        from src.relations.behavior_ema import apply_behavior_ema
        from src.relations.cold_start import ColdStartManager

        stats: dict[str, int] = {}
        fast = os.environ.get("FILEKG_INDEX_FAST", "").lower() in ("1", "true", "yes")
        skip_heavy = fast and len(descriptors) > 5000
        cs = ColdStartManager.get()
        cs.on_file_event(len(descriptors))
        for parser in self.parsers:
            if not parser.enabled:
                continue

            if not cs.parser_enabled(parser.name):
                logger.info("冷启动：跳过 %s", parser.name)
                continue
            if skip_heavy and parser.name in ("visual_fusion", "similar_to"):
                logger.info("快速批量索引：跳过 %s", parser.name)
                continue
            logger.info("运行关系解析器: %s", parser.name)
            edges = parser.discover(descriptors, store)
            count = parser.apply(edges, store)
            stats[parser.name] = count
            if self.on_progress:
                self.on_progress(parser.name, count)
            logger.info("  -> 建立 %d 条边", count)
        apply_behavior_ema(store)
        return stats
