"""公开指标快照与 README 声明一致（防止文档与数据漂移）。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "evaluation_snapshot.json"


def test_snapshot_exists_and_has_metrics():
    assert SNAPSHOT.exists(), "运行 python scripts/export_public_metrics.py 生成快照"
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data.get("metrics"), "快照应含至少一个数据集"
    assert data.get("disclaimer")
    assert "config_tois_eval" in data.get("config_profile", "")


def test_snapshot_no_absolute_user_paths():
    text = SNAPSHOT.read_text(encoding="utf-8")
    assert "/Users/" not in text
    assert "/Desktop/" not in text
    assert "FILEKG/data" not in text


def test_readme_headline_metrics_match_snapshot():
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    by_ds = {m["dataset"]: m for m in data["metrics"]}

    main = by_ds["filekg_main"]["filekg_full"]
    code = by_ds["code_dependency"]["filekg_full"]
    rob = data["robustness"]["volume_file_id"]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    # 精确值或四舍五入展示均需在 README 中可找到
    assert "0.691" in readme or f"{main['MAP@20']:.3f}" in readme
    assert "0.522" in readme or f"{code['Serendipity@20']:.3f}" in readme
    assert "97.85" in readme or "9785" in readme or "0.9785" in readme

    assert abs(main["MAP@20"] - 0.6906) < 0.002
    assert abs(code["Serendipity@20"] - 0.5222) < 0.002
    assert abs(rob["relation_retention_rate"] - 0.9785) < 0.0001


def test_robustness_logical_retention_documented():
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    logical = data["robustness"]["path_based_id"]["logical_relation_retention_rate"]
    assert 0.9 < logical < 1.0
