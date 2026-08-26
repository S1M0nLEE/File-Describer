#!/usr/bin/env python3
"""从本地 results_real 导出真实 benchmark 指标快照（可提交仓库）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_RESULTS = ROOT / "data/evaluation/results_real"
DEFAULT_OUT = ROOT / "docs/real_benchmark_snapshot.json"

BENCHMARKS = (
    ("hippocamp_adam", "HippoCamp Adam (HF MMMem-org/HippoCamp)"),
    ("hippocamp_bei", "HippoCamp Bei"),
    ("hippocamp_victoria", "HippoCamp Victoria"),
    ("real_github_repos", "GitHub 开源仓库聚合"),
)


def _sanitize_dataset_id(raw: str) -> str:
    name = Path(str(raw).replace("\\", "/")).name
    for bid, _ in BENCHMARKS:
        if bid in str(raw):
            return bid
    return name or "unknown"


def export_snapshot(results_dir: Path, out_path: Path) -> dict:
    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": "data/evaluation/results_real",
        "benchmark_type": "public_real",
        "disclaimer": (
            "真实公开数据集上的离线评测（HippoCamp / GitHub 等），非合成 filekg_main。"
            "完整 metrics 在 data/evaluation/results_real/（gitignore）。"
        ),
        "reproduce": [
            "python scripts/download_real_benchmarks.py --hippocamp --subset",
            "FILEKG_CONFIG=config_tois_eval.yaml FILEKG_EVAL_PROFILE=tois_eval "
            "python scripts/run_evaluation.py --registry real --dataset hippocamp_adam --output results_real",
            "python scripts/export_real_benchmark_metrics.py",
        ],
        "datasets": [],
    }

    for ds_id, label in BENCHMARKS:
        p = results_dir / ds_id / "metrics.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        fk = data.get("baselines", {}).get("FileKG-Full", {})
        if not fk:
            continue
        out["datasets"].append(
            {
                "id": ds_id,
                "label": label,
                "files": data.get("file_count"),
                "queries": data.get("query_count"),
                "filekg_full": {
                    "MAP@20": round(float(fk.get("MAP@20", 0)), 4),
                    "NDCG@20": round(float(fk.get("NDCG@20", 0)), 4),
                    "Recall_indirect@20": round(float(fk.get("Recall_indirect@20", 0)), 4),
                    "Serendipity@20": round(float(fk.get("Serendipity@20", 0)), 4),
                    "GraphDiscovery@20": round(float(fk.get("GraphDiscovery@20", 0)), 4),
                },
                "query_leakage_ratio": round(float(data.get("query_leakage_ratio", 0)), 4),
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.results_dir.exists():
        print(f"未找到 {args.results_dir}，请先运行真实 benchmark 评测。", file=sys.stderr)
        sys.exit(1)
    snap = export_snapshot(args.results_dir, args.out)
    print(f"已写入 {args.out}（{len(snap['datasets'])} 个真实数据集）")


if __name__ == "__main__":
    main()
