from __future__ import annotations

from src.api.diagnostics import run_diagnostics
from src.config import settings


def test_diagnostics_returns_structure():
    out = run_diagnostics(probe_network=False)
    assert "ok" in out
    assert "checks" in out
    assert isinstance(out["checks"], list)
    ids = {c["id"] for c in out["checks"]}
    assert "python" in ids
    assert "embedding" in ids
    assert "graph_index" in ids


def test_diagnostics_hash_backend_is_critical(monkeypatch):
    monkeypatch.setenv("FILEKG_EMBEDDING_BACKEND", "hash")
    from src.config import reload_settings
    from src.indexing.embedder import Embedder

    reload_settings()
    Embedder.reset()
    try:
        out = run_diagnostics(probe_network=False)
        emb = next(c for c in out["checks"] if c["id"] == "embedding")
        assert emb["severity"] == "critical"
        assert "hash" in emb["detail"]
        assert out["ok"] is False
    finally:
        monkeypatch.delenv("FILEKG_EMBEDDING_BACKEND", raising=False)
        reload_settings()
        Embedder.reset()


def test_diagnostics_api(client):
    r = client.get("/health/diagnostics")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body
    assert body.get("manual_load") is settings.api_manual_load
