"""配置文件与评测 profile 可加载性（CI 防漂移）。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_CONFIGS = [
    "config.yaml",
    "config_tois_eval.yaml",
    "config_hippocamp_eval.yaml",
]


@pytest.mark.config_profile
@pytest.mark.parametrize("name", REQUIRED_CONFIGS)
def test_config_yaml_parses(name: str):
    path = ROOT / name
    assert path.exists(), f"缺少配置文件 {name}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "embeddings" in data or "search" in data


@pytest.mark.config_profile
def test_tois_eval_disables_visual_and_sets_search():
    data = yaml.safe_load((ROOT / "config_tois_eval.yaml").read_text(encoding="utf-8"))
    assert data.get("visual", {}).get("enabled") is False
    search = data.get("search") or {}
    assert "weights" in search
    assert search.get("graph_hops", 0) >= 1
    emb = data.get("embeddings") or {}
    assert emb.get("model_name")


@pytest.mark.config_profile
def test_settings_reload_with_tois_config(monkeypatch):
    monkeypatch.setenv("FILEKG_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("FILEKG_VISUAL_ENABLED", "false")

    from src.config import reload_settings
    from src.indexing.embedder import Embedder

    settings = reload_settings(ROOT / "config_tois_eval.yaml")
    Embedder.reset()
    assert settings is not None
    assert settings.visual_enabled is False
    Embedder.reset()
