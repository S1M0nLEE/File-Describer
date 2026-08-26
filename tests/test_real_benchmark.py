"""真实公开 benchmark（HippoCamp）测试。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/benchmarks/hippocamp_adam_subset.json"
SNAPSHOT = ROOT / "docs/real_benchmark_snapshot.json"
HIPPO_FILES = ROOT / "data/benchmarks/hippocamp_adam/files"
HIPPO_ANNOT = ROOT / "data/benchmarks/annotations/hippocamp_adam.json"


def _basename_set(results: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in results:
        name = r.get("name") or Path(r.get("path", "")).name
        if name:
            out.add(name)
    return out


@pytest.mark.real_benchmark
def test_hippocamp_fixture_is_public_benchmark():
    assert FIXTURE.exists()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "huggingface.co" in data["source"]
    assert data["queries"]
    assert data["queries"][0]["direct"], "标注应含真实证据文件名"


@pytest.mark.real_benchmark
def test_real_benchmark_snapshot_no_user_paths():
    assert SNAPSHOT.exists(), "运行 python scripts/export_real_benchmark_metrics.py"
    text = SNAPSHOT.read_text(encoding="utf-8")
    assert "/Users/" not in text
    data = json.loads(text)
    assert data.get("benchmark_type") == "public_real"
    ids = {d["id"] for d in data["datasets"]}
    assert "hippocamp_adam" in ids


@pytest.mark.real_benchmark
def test_real_snapshot_hippocamp_adam_map_is_honest():
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    adam = next(d for d in data["datasets"] if d["id"] == "hippocamp_adam")
    # 来自 results_real/metrics.json，Fullset 344 文件；低于合成集 MAP 属正常
    assert 0.2 < adam["filekg_full"]["MAP@20"] < 0.6
    assert adam["queries"] >= 100
    assert adam["files"] >= 300


@pytest.mark.real_benchmark
@pytest.mark.slow
def test_hippocamp_subset_index_and_search():
    """在 HippoCamp Adam-Subset 真实文件上跑通索引+检索（需先下载）。"""
    if os.environ.get("FILEKG_RUN_REAL_BENCHMARK") != "1":
        pytest.skip("设置 FILEKG_RUN_REAL_BENCHMARK=1 并运行 download_hippocamp_subset.py")
    if not HIPPO_FILES.is_dir() or not any(HIPPO_FILES.rglob("*")):
        pytest.skip("缺少 data/benchmarks/hippocamp_adam/files，运行 scripts/download_hippocamp_subset.py")

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    q0 = fixture["queries"][0]

    os.environ.setdefault("FILEKG_INDEX_FAST", "1")
    os.environ.setdefault("FILEKG_VISUAL_ENABLED", "false")
    os.environ.setdefault("FILEKG_MULTIMODAL_ENABLED", "false")

    from src.config import reload_settings
    from src.indexing.builder import IndexBuilder
    from src.indexing.embedder import Embedder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_eval_stores

    reload_settings()
    Embedder.reset()

    graph, chroma = create_eval_stores("hippocamp_adam_test")
    builder = IndexBuilder(graph, chroma)
    builder.build(HIPPO_FILES, clear=True, max_files=80)

    if hasattr(graph, "ensure_loaded"):
        graph.ensure_loaded()
    engine = SearchEngine(graph, chroma, lazy_corpus=True)
    out = engine.search(q0["q"], expand_graph=True)
    results = out.get("results") or []
    assert results, "真实 benchmark 检索应返回结果"

    names = _basename_set(results)
    target = q0["direct"][0]
    # 真实嵌入下应能命中证据文件；hash 模式下仅断言 pipeline 不崩溃
    backend = Embedder.get().backend
    if backend != "hash":
        assert target in names or any(target.lower() in n.lower() for n in names)

    graph.close()
    Embedder.reset()
