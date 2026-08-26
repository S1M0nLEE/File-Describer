"""HTTP 层集成测试：索引 + 检索。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app


@pytest.fixture
def api_client(isolated_env, tmp_path, monkeypatch):
    monkeypatch.setenv("FILEKG_API_MANUAL_LOAD", "false")
    from src.config import reload_settings
    from src.indexing.embedder import Embedder

    reload_settings()
    Embedder.reset()

    from src.config import settings

    monkeypatch.setattr(settings, "api_manual_load", False)
    monkeypatch.setattr(settings, "api_index_allow_roots", [str(tmp_path)])

    from src.api import runtime as app_runtime

    app_runtime.shutdown()
    app_runtime.configure(manual_load=False, fast_startup=False)

    with TestClient(create_app()) as client:
        yield client

    app_runtime.shutdown()
    Embedder.reset()


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    chroma = data / "chroma"
    dataset = data / "dataset"
    dataset.mkdir(parents=True)
    chroma.mkdir(parents=True)
    (dataset / "实验数据.csv").write_text("id,value\n1,0.95\n", encoding="utf-8")
    (dataset / "notes.md").write_text("# 实验数据说明\n", encoding="utf-8")

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


@pytest.mark.e2e
def test_http_index_and_search(api_client: TestClient, isolated_env):
    from src.api import runtime as app_runtime

    r_index = api_client.post(
        "/index",
        json={"path": str(isolated_env), "clear": True},
    )
    assert r_index.status_code == 200, r_index.text
    assert r_index.json().get("file_count", 0) >= 2

    app_runtime.run_full_load(build_corpus=False, build_search=True)

    r_search = api_client.post(
        "/search",
        json={"query": "实验数据", "expand_graph": True},
    )
    assert r_search.status_code == 200, r_search.text
    body = r_search.json()
    assert body.get("results")


def test_config_endpoint_fields(api_client: TestClient):
    r = api_client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "embedding_model" in data
    assert "visual_enabled" in data
