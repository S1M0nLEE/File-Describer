"""端到端：临时目录索引 → 检索（不依赖预置 data/ 与真实嵌入模型）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
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
    monkeypatch.setenv("FILEKG_MULTIMODAL_VISUAL_INDEX_ENABLED", "false")
    monkeypatch.setenv("FILEKG_MULTIMODAL_FUSE_VISUAL_SEARCH", "false")

    from src.config import reload_settings
    from src.indexing.embedder import Embedder

    reload_settings()
    Embedder.reset()
    yield dataset
    Embedder.reset()


def _write_mini_dataset(root: Path) -> None:
    (root / "实验数据.csv").write_text("id,value\n1,0.95\n2,0.88\n", encoding="utf-8")
    (root / "data_processing.py").write_text(
        '"""处理实验数据"""\nimport csv\n\nDATA = "实验数据.csv"\n',
        encoding="utf-8",
    )
    (root / "论文终稿.pdf.md").write_text("# 论文终稿\n\n机器学习实验结果。\n", encoding="utf-8")
    gt = {
        "queries": [
            {"q": "实验数据", "direct": ["实验数据.csv"], "indirect": []},
            {"q": "处理实验数据的代码", "direct": ["data_processing.py"], "indirect": ["实验数据.csv"]},
        ]
    }
    (root / "ground_truth.json").write_text(json.dumps(gt, ensure_ascii=False), encoding="utf-8")


@pytest.mark.e2e
def test_index_and_search_pipeline(isolated_env: Path):
    _write_mini_dataset(isolated_env)

    from src.indexing.builder import IndexBuilder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_stores

    builder = IndexBuilder()
    result = builder.build(isolated_env, clear=True)
    assert result["file_count"] >= 3

    graph, chroma = create_stores()
    if hasattr(graph, "ensure_loaded"):
        graph.ensure_loaded()

    engine = SearchEngine(graph, chroma, lazy_corpus=True)
    out = engine.search("实验数据", expand_graph=True)
    assert "results" in out
    assert len(out["results"]) >= 1

    names = {r.get("name") or Path(r.get("path", "")).name for r in out["results"]}
    assert any("实验数据" in n for n in names)


@pytest.mark.e2e
def test_runtime_search_after_index(isolated_env: Path):
    """运行时：索引后 ensure_search 可检索。"""
    _write_mini_dataset(isolated_env)

    from src.api import runtime as app_runtime
    from src.indexing.builder import IndexBuilder

    builder = IndexBuilder()
    builder.build(isolated_env, clear=True)

    app_runtime.configure(manual_load=False, fast_startup=False)
    app_runtime.run_full_load(build_corpus=False, build_search=True)
    search = app_runtime.ensure_search()
    out = search.search("实验数据", expand_graph=True)
    assert out.get("results")
    app_runtime.shutdown()
