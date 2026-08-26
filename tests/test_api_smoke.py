import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "graph" in body or "graph_ready" in body


def test_root_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_config_endpoint(client):
    r = client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "embedding_model" in data
    assert "visual_enabled" in data


def test_openapi_docs(client):
    r = client.get("/docs")
    assert r.status_code == 200
