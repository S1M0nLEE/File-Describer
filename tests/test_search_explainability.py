"""检索可解释性字段形状（与 UI / 评测依赖一致）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def explain_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    chroma = data / "chroma"
    dataset = data / "dataset"
    dataset.mkdir(parents=True)
    chroma.mkdir(parents=True)

    monkeypatch.setenv("FILEKG_DATA_DIR", str(data))
    monkeypatch.setenv("FILEKG_CHROMA_DIR", str(chroma))
    monkeypatch.setenv("FILEKG_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("FILEKG_INDEX_FAST", "1")
    monkeypatch.setenv("FILEKG_VISUAL_ENABLED", "false")
    monkeypatch.setenv("FILEKG_MULTIMODAL_ENABLED", "false")

    (dataset / "实验数据.csv").write_text("id,v\n1,1\n", encoding="utf-8")
    (dataset / "data_processing.py").write_text(
        '"""处理实验数据"""\nDATA="实验数据.csv"\n',
        encoding="utf-8",
    )
    (dataset / "报告_v1.md").write_text("# 报告 v1\n", encoding="utf-8")
    (dataset / "报告_v2.md").write_text("# 报告 v2\n", encoding="utf-8")

    from src.config import reload_settings
    from src.indexing.embedder import Embedder

    reload_settings()
    Embedder.reset()
    yield dataset
    Embedder.reset()


@pytest.mark.e2e
def test_search_returns_explanation_fields(explain_env: Path):
    from src.indexing.builder import IndexBuilder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_stores

    builder = IndexBuilder()
    builder.build(explain_env, clear=True)

    graph, chroma = create_stores()
    if hasattr(graph, "ensure_loaded"):
        graph.ensure_loaded()
    engine = SearchEngine(graph, chroma, lazy_corpus=True)
    out = engine.search("实验数据", expand_graph=True)

    assert "results" in out
    assert "parsed" in out
    assert "seed_count" in out
    assert out["results"], "应至少返回一条结果"

    top = out["results"][0]
    assert "file_id" in top
    assert "score" in top
    # 可解释性：因子分与说明文本
    assert "factor_scores" in top or "explanation" in top
    if "factor_scores" in top:
        assert isinstance(top["factor_scores"], dict)
    if "explanation" in top:
        assert isinstance(top["explanation"], str)

    # 序列化稳定，供 API / 快照消费
    json.dumps(out, ensure_ascii=False, default=str)
