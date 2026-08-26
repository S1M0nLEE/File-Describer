#!/usr/bin/env python3
"""从本地评测结果导出可提交的 metrics 快照（不含个人路径）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_RESULTS = ROOT / "data/evaluation/results_tois"
DEFAULT_OUT = ROOT / "docs/evaluation_snapshot.json"


def _sanitize_dataset_name(raw: str) -> str:
    p = Path(raw.replace("\\", "/"))
    name = p.name
    if name in ("filekg_main", "code_dependency", "personal_mixed"):
        return name
    for part in reversed(p.parts):
        if part in ("filekg_main", "code_dependency", "personal_mixed"):
            return part
    return name or "filekg_main"


def _load_filekg_metrics(metrics_path: Path) -> dict | None:
    if not metrics_path.exists():
        return None
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    fk = data.get("baselines", {}).get("FileKG-Full")
    if not fk:
        return None
    return {
        "dataset": data.get("dataset_id") or metrics_path.parent.name,
        "queries": data.get("query_count"),
        "files": data.get("file_count"),
        "filekg_full": {
            "MAP@20": round(float(fk.get("MAP@20", 0)), 4),
            "Serendipity@20": round(float(fk.get("Serendipity@20", 0)), 4),
            "Recall_indirect@20": round(float(fk.get("Recall_indirect@20", 0)), 4),
            "GraphDiscovery@20": round(float(fk.get("GraphDiscovery@20", 0)), 4),
        },
    }


def export_snapshot(results_dir: Path, out_path: Path) -> dict:
    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(results_dir.relative_to(ROOT)) if results_dir.is_relative_to(ROOT) else results_dir.name,
        "config_profile": "config_tois_eval.yaml",
        "eval_profile_env": "FILEKG_EVAL_PROFILE=tois_eval (recommended)",
        "reproduce": [
            "python scripts/generate_evaluation_benchmark.py --scale small",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_evaluation.py --dataset filekg_main",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_evaluation.py --dataset code_dependency",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_robustness.py --dataset filekg_main",
            "python scripts/export_public_metrics.py",
        ],
        "disclaimer": (
            "以下为合成基准上的离线评测结果（FileKG-Full），非第三方认证或生产环境 SLA。"
            "原始 report/metrics 在 data/evaluation/（gitignore），本文件为可审计摘要。"
        ),
        "metrics": [],
    }

    for ds in ("filekg_main", "code_dependency", "personal_mixed"):
        row = _load_filekg_metrics(results_dir / ds / "metrics.json")
        if row:
            out["metrics"].append(row)

    rb = results_dir / "robustness.json"
    if rb.exists():
        r = json.loads(rb.read_text(encoding="utf-8"))
        vol = r.get("volume_file_id") or {}
        path_id = r.get("path_based_id") or {}
        out["robustness"] = {
            "dataset": _sanitize_dataset_name(str(r.get("dataset", "filekg_main"))),
            "files_moved": r.get("files_moved"),
            "queries_evaluated": r.get("queries_evaluated"),
            "volume_file_id": {
                "relation_retention_rate": round(float(vol.get("relation_retention_rate", 0)), 4),
                "MAP@20_after_move": round(float(vol.get("MAP@20_after_move", 0)), 4),
            },
            "path_based_id": {
                "logical_relation_retention_rate": round(
                    float(path_id.get("logical_relation_retention_rate", 0)), 4
                ),
            },
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 docs/evaluation_snapshot.json")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.results_dir.exists():
        print(f"未找到评测目录: {args.results_dir}", file=sys.stderr)
        print("请先运行 docs/EVALUATION.md 中的复现命令。", file=sys.stderr)
        sys.exit(1)
    snap = export_snapshot(args.results_dir, args.out)
    print(f"已写入 {args.out}（{len(snap.get('metrics', []))} 个数据集）")


if __name__ == "__main__":
    main()
