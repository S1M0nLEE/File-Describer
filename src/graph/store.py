"""Abstract graph storage backend."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set, Tuple

EdgeRow = Tuple[str, str, str, Dict[str, Any]]  # src, tgt, rel_type, props
ExpandRow = Tuple[str, str, List[str], int]  # seed_id, neighbor_id, rels, hops


class GraphStore(ABC):
    backend_name: str = "unknown"

    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def verify_connectivity(self) -> None:
        pass

    @abstractmethod
    def ensure_indexes(self) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def merge_node(self, label: str, node_id: str, props: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def write_relationships(self, edges: List[EdgeRow]) -> None:
        pass

    @abstractmethod
    def update_file_status(self, file_id: str, status: str) -> None:
        pass

    @abstractmethod
    def delete_file(self, file_id: str) -> None:
        pass

    @abstractmethod
    def expand_files(
        self,
        seed_ids: List[str],
        allowed_relations: Set[str],
        max_hops: int = 1,
        limit: int = 500,
    ) -> List[ExpandRow]:
        pass
