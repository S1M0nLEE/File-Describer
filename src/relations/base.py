"""Base class for relation extractors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from src.models.file_descriptor import FileDescriptor

Edge = Tuple[str, str, str, Dict[str, Any]]


class RelationExtractor(ABC):
    relation_type: str = ""

    @abstractmethod
    def discover(self, file_nodes: List[FileDescriptor]) -> List[Edge]:
        pass
