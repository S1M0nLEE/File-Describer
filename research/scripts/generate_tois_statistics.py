#!/usr/bin/env python3
"""聚合 TOIS 实验统计量，供论文回填与正文同步。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pct_change(full: float, variant: float) -> float:
    if not full:
        return 0.0
    return (full - variant) / full * 100


def build_stats(results_dir: str) -> dict:
    base = ROOT / "data" / "evaluation" / results_dir
    data_path = ROOT / "data" / "evaluation" / "paper_experiment_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}

    stats: dict = {"results_dir": results_dir, "datasets": {}, "comparisons": {}, "ablation_deltas": {}}

    core_baselines = ["BM25", "VectorOnly", "Vector+Metadata", "Vector+SIMILAR_TO"]
    for ds_id in ("filekg_main", "personal_mixed", "code_dependency"):
        mpath = base / ds_id / "metrics.json"
        if not mpath.exists():
            continue
        m = json.loads(mpath.read_text(encoding="utf-8"))
        fk = m["baselines"]["FileKG-Full"]
        stats["datasets"][ds_id] = {
            "filekg_map": fk["MAP@20"],
            "filekg_sdr": fk["Serendipity@20"],
            "filekg_ndcg": fk["NDCG@20"],
            "query_count": m.get("query_count"),
            "statistical_test": m.get("statistical_tests", {}).get("filekg_vs_best_baseline_ap", {}),
        }
        best_core = max(core_baselines, key=lambda b: m["baselines"].get(b, {}).get("MAP@20", 0))
        stats["comparisons"][ds_id] = {
            "best_core_baseline": best_core,
            "best_core_map": m["baselines"][best_core]["MAP@20"],
            "filekg_beats_core": fk["MAP@20"] > m["baselines"][best_core]["MAP@20"],
            "delta_map": fk["MAP@20"] - m["baselines"][best_core]["MAP@20"],
        }

    pm = data.get("datasets", {}).get("personal_mixed", {}).get("baselines", {})
    pb = data.get("paper_baselines", {}).get("personal_mixed", {})
    fk_map = pm.get("FileKG-Full", {}).get("MAP@20", 0)
    path_map = pb.get("Multi-Rel (Path-based)", {}).get("MAP@20", 0)
    stats["vfe"] = {
        "filekg_map": fk_map,
        "path_map": path_map,
        "path_map_measured": pb.get("Multi-Rel (Path-based)", {}).get("MAP@20_measured", path_map),
        "lift_pct": (fk_map - path_map) / path_map * 100 if path_map else 0.0,
    }

    ab = {a["variant"]: a for a in data.get("ablation", {}).get("ablations", [])}
    full = ab.get("完整方案", {})
    for key, label in (("禁用 SIMILAR_TO", "similar_to"), ("禁用 WORKFLOW_WITH", "workflow_with")):
        v = ab.get(key, {})
        stats["ablation_deltas"][label] = {
            "map_drop_pct": _pct_change(full.get("MAP@20", 0), v.get("MAP@20", 0)),
            "sdr_drop_pct": _pct_change(full.get("Serendipity@20", 0), v.get("Serendipity@20", 0)),
            "full_map": full.get("MAP@20"),
            "variant_map": v.get("MAP@20"),
            "full_sdr": full.get("Serendipity@20"),
            "variant_sdr": v.get("Serendipity@20"),
        }

    mpath = base / "personal_mixed" / "metrics.json"
    if mpath.exists():
        m = json.loads(mpath.read_text(encoding="utf-8"))
        fk_pq = m.get("per_query", {}).get("FileKG-Full", [])
        n = len(fk_pq)
        gsize = max(1, n // 3)
        groups = []
        for i in range(3):
            chunk = fk_pq[i * gsize : (i + 1) * gsize if i < 2 else n]
            groups.append(
                {
                    "map": _mean([r["ap"] for r in chunk]),
                    "sdr": _mean([r.get("serendipity", 0) for r in chunk]),
                    "queries": len(chunk),
                }
            )
        stats["personal_query_groups"] = groups

    out = base / "tois_statistics.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results_tois")
    args = parser.parse_args()
    stats = build_stats(args.results_dir)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
