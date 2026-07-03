from .base import Edge, RelationEdge, RelationExtractor, RelationParser

# Legacy extractor registry kept for src.pipeline.graph_builder compatibility.
ALL_EXTRACTORS: list[type] = []

__all__ = [
    "RelationParser",
    "RelationExtractor",
    "RelationEdge",
    "Edge",
    "ALL_EXTRACTORS",
]
