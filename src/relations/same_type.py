"""SAME_TYPE relation between files with identical extension."""

from collections import defaultdict
from typing import List

from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor


class SameTypeExtractor(RelationExtractor):
    relation_type = "SAME_TYPE"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        by_ext: dict = defaultdict(list)
        for f in file_nodes:
            if f.extension:
                by_ext[f.extension].append(f)
        edges = []
        for ext, group in by_ext.items():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i + 1 : i + 4]:
                    edges.append((a.id, b.id, "SAME_TYPE", {"extension": ext}))
                    edges.append((b.id, a.id, "SAME_TYPE", {"extension": ext}))
        return edges
