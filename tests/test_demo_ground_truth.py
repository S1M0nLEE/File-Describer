"""Demo 数据集 ground_truth 标注 smoke（可复现，非合成 MAP 指标）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GT_PATH = ROOT / "data" / "dataset" / "ground_truth.json"


def _basename_set(results: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in results:
        name = r.get("name") or Path(r.get("path", "")).name
        if name:
            out.add(name)
    return out


def _targets_found(results: list[dict], targets: list[str]) -> bool:
    names = _basename_set(results)
    return any(t in names for t in targets)


@pytest.fixture
def demo_indexed(isolated_env, tmp_path, monkeypatch):
    """使用仓库内 generate_dataset 结构（若不存在则跳过）。"""
    if not GT_PATH.exists():
        pytest.skip("需先运行 python scripts/generate_dataset.py")

    import shutil

    src = ROOT / "data" / "dataset"
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            dest = isolated_env / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)

    monkeypatch.setenv("FILEKG_DATA_DIR", str(isolated_env.parent))
    monkeypatch.setenv("FILEKG_CHROMA_DIR", str(isolated_env.parent / "chroma"))
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

    from src.indexing.builder import IndexBuilder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_stores

    builder = IndexBuilder()
    builder.build(isolated_env, clear=True)

    graph, chroma = create_stores()
    if hasattr(graph, "ensure_loaded"):
        graph.ensure_loaded()
    engine = SearchEngine(graph, chroma, lazy_corpus=True)
    yield engine, isolated_env
    Embedder.reset()


@pytest.fixture
def isolated_env(tmp_path):
    d = tmp_path / "data" / "dataset"
    d.mkdir(parents=True)
    return d


@pytest.mark.e2e
def test_demo_ground_truth_queries_return_targets(demo_indexed):
    engine, _dataset = demo_indexed
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))

    hits = 0
    for item in gt.get("queries", []):
        q = item["q"]
        direct = item.get("direct") or []
        if not direct:
            continue
        out = engine.search(q, expand_graph=True)
        results = out.get("results") or []
        if _targets_found(results, direct):
            hits += 1

    # hash 嵌入下语义弱，至少应命中 1/3 条标注（通常 BM25/文件名可中）
    assert hits >= 1, "Demo ground_truth 查询应至少命中一条 direct 目标"


def test_ground_truth_file_valid():
    if not GT_PATH.exists():
        pytest.skip("需先运行 python scripts/generate_dataset.py")
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    assert len(gt.get("queries", [])) >= 3
