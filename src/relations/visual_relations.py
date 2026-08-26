from __future__ import annotations

import logging
from typing import Any as Neo4jStore

from src.models.descriptor import FileDescriptor
from src.relations.base import RelationEdge, RelationParser
from src.relations.visual_fusion.fusion import VisualFusionDiscoverer

logger = logging.getLogger(__name__)


class VisualSimilarParser(RelationParser):
    """
    跨模态视觉相似关系：多模型融合发现（发明说明 5.2–5.4）。

    - VISUALLY_SIMILAR_TO：OCR / 文档页 / 视觉对齐三路 + 置信度真值表
    - NEAR_DUPLICATE：pHash 近重复（保留双节点，不删节点）
    """

    name = "visual_fusion"

    def __init__(self) -> None:
        self._discoverer = VisualFusionDiscoverer()

    def discover(
        self, descriptors: list[FileDescriptor], store: Neo4jStore
    ) -> list[RelationEdge]:
        return self._discoverer.discover(descriptors)
