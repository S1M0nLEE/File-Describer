from __future__ import annotations

from pathlib import Path

import yaml


def _api_config() -> dict:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")) or {}
    return cfg.get("api", {})


def test_config_yaml_manual_load_disabled():
    assert _api_config().get("manual_load") is False


def test_config_yaml_preload_graph_enabled():
    assert _api_config().get("preload_graph") is True


def test_config_yaml_fast_startup_enabled():
    assert _api_config().get("fast_startup") is True
