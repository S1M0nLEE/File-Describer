#!/usr/bin/env python3
"""从 results_extended 导出扩展专项 FileKG-Full 快照（不含个人路径）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "data/evaluation/results_extended"
DEFAULT_OUT = ROOT / "docs/extended_benchmark_snapshot.json"

DATASETS = (
    ("version_lineage", "版本链专项（HAS_VERSION）", ["HAS_VERSION", "IS_BACKUP_OF", "IS_PREVIOUS_VERSION_OF"]),
    ("office_workflow", "办公共现专项（WORKFLOW_WITH）", ["WORKFLOW_WITH", "NEAR_IN_TIME", "IN_FOLDER"]),
    ("doc_references", "文档引用专项（REFERENCES）", ["REFERENCES", "CONTAINS", "IN_FOLDER"]),
)


def _load(ds: str, results: Path) -> dict | None:
    path = results / ds / "metrics.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    fk = data.get("baselines", {}).get("FileKG-Full")
    if not fk:
        return None
    return {
        "files": data.get("file_count"),
        "queries": data.get("query_count"),
        "filekg_full": {
            "MAP@20": round(float(fk.get("MAP@20", 0)), 4),
            "Serendipity@20": round(float(fk.get("Serendipity@20", 0)), 4),
            "Recall_indirect@20": round(float(fk.get("Recall_indirect@20", 0)), 4),
            "GraphDiscovery@20": round(float(fk.get("GraphDiscovery@20", 0)), 4),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    datasets = []
    for ds_id, label, rels in DATASETS:
        row = _load(ds_id, args.results_dir)
        if not row:
            print(f"skip missing: {ds_id}", file=sys.stderr)
            continue
        datasets.append(
            {
                "id": ds_id,
                "label": label,
                "files": row["files"],
                "queries": row["queries"],
                "focus_relations": rels,
                "fixture": f"tests/fixtures/benchmarks/{ds_id}_subset.json",
                "filekg_full": row["filekg_full"],
            }
        )

    if len(datasets) != 3:
        raise SystemExit(f"expected 3 datasets, got {len(datasets)}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_type": "synthetic_extended",
        "source_dir": "data/evaluation/results_extended",
        "config_profile": "config_tois_eval.yaml",
        "eval_profile_env": "FILEKG_EVAL_PROFILE=tois_eval",
        "embedding": "BAAI/bge-small-zh-v1.5 (sentence_transformers)",
        "disclaimer": (
            "三项扩展合成专项上的 FileKG-Full 离线评测（tois_eval 口径）。"
            "原始 metrics 在 data/evaluation/results_extended/（gitignore），本文件为可审计摘要。"
        ),
        "reproduce": [
            "python scripts/generate_evaluation_benchmark.py --extended-only --clean",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_evaluation.py --dataset version_lineage --results-dir results_extended",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_evaluation.py --dataset office_workflow --results-dir results_extended",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_evaluation.py --dataset doc_references --results-dir results_extended",
            "python scripts/export_extended_metrics.py",
        ],
        "datasets": datasets,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    assert "/Users/" not in text and "C:\\\\Users" not in text and "JasonXu" not in text
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    for d in datasets:
        print(f"  {d['id']}: MAP@20={d['filekg_full']['MAP@20']}")


if __name__ == "__main__":
    main()
