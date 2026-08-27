"""意图解析与关系管线的补充 CI（不依赖网络）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.models.descriptor import FileDescriptor
from src.relations.content_relations import ReferencesParser
from src.relations.pipeline import DEFAULT_PIPELINE, RelationDiscoveryPipeline
from src.search.intent_parser import IntentParser


def _desc(name: str, path: str, *, ext: str, summary: str = "") -> FileDescriptor:
    return FileDescriptor(
        file_id=f"fid:{name}",
        path=path,
        name=name,
        extension=ext,
        size=100,
        created_time=datetime(2024, 1, 1),
        modified_time=datetime(2024, 1, 1),
        summary=summary,
    )


def test_intent_parser_extracts_extension_and_time():
    p = IntentParser().parse("上周修改的 python 代码")
    assert ".py" in p.extensions
    assert p.modified_after is not None
    assert p.keywords


def test_default_pipeline_has_core_parsers():
    names = {cls().name for cls in DEFAULT_PIPELINE}
    assert "metadata" in names
    assert "depends_on" in names
    assert "references" in names
    assert "version" in names
    assert len(DEFAULT_PIPELINE) >= 8


def test_references_parser_finds_file_link(tmp_path: Path):
    bib = tmp_path / "refs.bib"
    paper = tmp_path / "paper.md"
    bib.write_text("@article{a,title={t}}\n", encoding="utf-8")
    paper.write_text("see [bib](file://refs.bib)\n", encoding="utf-8")

    files = [
        _desc("refs.bib", str(bib.resolve()), ext=".bib"),
        _desc("paper.md", str(paper.resolve()), ext=".md"),
    ]
    edges = ReferencesParser().discover(files, None)
    assert any(e.rel_type == "REFERENCES" for e in edges)


def test_pipeline_instantiates():
    pipe = RelationDiscoveryPipeline()
    assert pipe.parsers
    assert all(hasattr(p, "discover") for p in pipe.parsers)
