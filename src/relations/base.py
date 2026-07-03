from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.descriptor import FileDescriptor
    from src.storage.memory_graph import MemoryGraphStore as Neo4jStore


@dataclass
class RelationEdge:
    src_id: str
    rel_type: str
    dst_id: str
    weight: float = 1.0
    symmetric: bool = False
    props: dict = field(default_factory=dict)


# Legacy aliases used by older extractor modules and __init__.py exports.
Edge = RelationEdge


class RelationParser(ABC):
    name: str = "base"
    enabled: bool = True

    @abstractmethod
    def discover(
        self,
        descriptors: list["FileDescriptor"],
        store: "Neo4jStore",
    ) -> list[RelationEdge]:
        ...

    def apply(self, edges: list[RelationEdge], store: "Neo4jStore") -> int:
        count = 0
        for e in edges:
            if e.symmetric:
                store.create_symmetric_relation(
                    e.src_id, e.rel_type, e.dst_id, weight=e.weight, props=e.props
                )
            else:
                store.create_relation(
                    e.src_id, e.rel_type, e.dst_id, weight=e.weight, props=e.props
                )
            count += 1
        return count


RelationExtractor = RelationParser
