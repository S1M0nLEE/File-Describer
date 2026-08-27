"""扩展合成 benchmark（version_lineage / office_workflow / doc_references）。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "extended_benchmark_snapshot.json"
FIXTURES = {
    "version_lineage": ROOT / "tests/fixtures/benchmarks/version_lineage_subset.json",
    "office_workflow": ROOT / "tests/fixtures/benchmarks/office_workflow_subset.json",
    "doc_references": ROOT / "tests/fixtures/benchmarks/doc_references_subset.json",
}


def _load_gen():
    path = ROOT / "scripts" / "generate_evaluation_benchmark.py"
    spec = importlib.util.spec_from_file_location("gen_eval_bench", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.extended_benchmark
def test_extended_snapshot_schema():
    assert SNAPSHOT.exists(), "缺少 docs/extended_benchmark_snapshot.json"
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data.get("benchmark_type") == "synthetic_extended"
    assert data.get("disclaimer")
    ids = {d["id"] for d in data["datasets"]}
    assert ids == set(FIXTURES)


@pytest.mark.extended_benchmark
@pytest.mark.parametrize("dataset_id,path", list(FIXTURES.items()))
def test_extended_fixture_has_public_queries(dataset_id: str, path: Path):
    assert path.exists(), f"缺少 fixture: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["dataset"] == dataset_id
    assert data["source"] == "synthetic_extended"
    assert data.get("focus_relations"), "应声明关注的关系类型"
    assert len(data["queries"]) >= 3
    for q in data["queries"]:
        assert q.get("q")
        assert q.get("direct"), "每条查询应有 direct 标注"


@pytest.mark.extended_benchmark
def test_extended_snapshot_no_user_paths():
    text = SNAPSHOT.read_text(encoding="utf-8")
    assert "/Users/" not in text
    assert "C:\\\\Users" not in text


@pytest.mark.extended_benchmark
@pytest.mark.e2e
def test_extended_benchmarks_index_and_search_smoke(tmp_path, monkeypatch):
    """生成三项扩展集并跑通索引+检索（hash 嵌入，CI 冒烟）。"""
    data = tmp_path / "data"
    chroma = data / "chroma"
    data.mkdir(parents=True)
    chroma.mkdir(parents=True)

    monkeypatch.setenv("FILEKG_DATA_DIR", str(data))
    monkeypatch.setenv("FILEKG_CHROMA_DIR", str(chroma))
    monkeypatch.setenv("FILEKG_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("FILEKG_INDEX_FAST", "1")
    monkeypatch.setenv("FILEKG_VISUAL_ENABLED", "false")
    monkeypatch.setenv("FILEKG_MULTIMODAL_ENABLED", "false")

    gen = _load_gen()
    monkeypatch.setattr(gen, "BENCH", data / "benchmarks")
    monkeypatch.setattr(gen, "ANNOT", data / "benchmarks" / "annotations")
    monkeypatch.setattr(gen, "ROOT", tmp_path)

    stats = gen.build_extended_benchmarks(clean=True)
    assert {s["id"] for s in stats} == set(FIXTURES)

    from src.config import reload_settings
    from src.indexing.builder import IndexBuilder
    from src.indexing.embedder import Embedder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_eval_stores

    reload_settings()
    Embedder.reset()

    for s in stats:
        ds_id = s["id"]
        ds_path = gen.BENCH / ds_id
        assert ds_path.is_dir()
        annot = gen.ANNOT / f"{ds_id}.json"
        gt = json.loads(annot.read_text(encoding="utf-8"))
        assert len(gt["queries"]) >= 8

        graph, chroma_store = create_eval_stores(f"ext_{ds_id}")
        builder = IndexBuilder(graph, chroma_store)
        info = builder.build(ds_path, clear=True)
        assert info["file_count"] >= 8

        if hasattr(graph, "ensure_loaded"):
            graph.ensure_loaded()
        engine = SearchEngine(graph, chroma_store, lazy_corpus=True)
        q0 = gt["queries"][0]["q"]
        out = engine.search(q0, expand_graph=True)
        assert out.get("results"), f"{ds_id} 检索应返回结果"
        graph.close()

    Embedder.reset()
