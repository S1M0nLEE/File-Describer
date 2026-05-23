"""Pipeline package — import submodules directly to avoid circular imports."""

from .embedder import Embedder
from .scanner import FileScanner
from .text_extractor import TextExtractor
from .summarizer import Summarizer

__all__ = ["Embedder", "FileScanner", "TextExtractor", "Summarizer", "GraphBuilder"]


def __getattr__(name: str):
    if name == "GraphBuilder":
        from .graph_builder import GraphBuilder
        return GraphBuilder
    raise AttributeError(name)
