from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.api.security import is_path_allowed, redact_path, validate_index_directory


def test_redact_path_hides_home_prefix():
    from pathlib import Path

    p = str(Path.home() / "Documents" / "secret.pdf")
    out = redact_path(p)
    assert out.startswith("~/")
    assert "secret.pdf" in out


def test_is_path_allowed_under_home():
    from pathlib import Path

    assert is_path_allowed(Path.home() / "Documents")


def test_is_path_allowed_rejects_system():
    assert not is_path_allowed("/etc/passwd")


def test_validate_index_directory_rejects_missing(tmp_path):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        validate_index_directory(str(tmp_path / "nope"))
    assert exc.value.status_code == 400


def test_api_token_required_when_configured(monkeypatch):
    monkeypatch.setenv("FILEKG_API_TOKEN", "secret-token")
    monkeypatch.setenv("FILEKG_API_REQUIRE_TOKEN", "true")
    from src.config import reload_settings

    reload_settings()
    from src.indexing.embedder import Embedder

    Embedder.reset()

    from src.api.app import create_app

    app = create_app()
    client = TestClient(app)
    r = client.post("/search", json={"query": "test"})
    assert r.status_code == 401
    r2 = client.post(
        "/search",
        json={"query": "test"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert r2.status_code in (200, 503)  # 503 if search not loaded in test mode

    monkeypatch.delenv("FILEKG_API_REQUIRE_TOKEN", raising=False)
    monkeypatch.delenv("FILEKG_API_TOKEN", raising=False)
    reload_settings()
    Embedder.reset()


def test_health_is_public_without_token(monkeypatch):
    monkeypatch.setenv("FILEKG_API_TOKEN", "secret-token")
    monkeypatch.setenv("FILEKG_API_REQUIRE_TOKEN", "true")
    from src.config import reload_settings

    reload_settings()
    from src.api.app import create_app

    client = TestClient(create_app())
    assert client.get("/health").status_code == 200

    monkeypatch.delenv("FILEKG_API_REQUIRE_TOKEN", raising=False)
    monkeypatch.delenv("FILEKG_API_TOKEN", raising=False)
    reload_settings()
