#!/usr/bin/env python3
"""文件移动 / file_id 鲁棒性实验（专利举证用）。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

RESULTS = ROOT / "data" / "evaluation" / "results_corrected_v2"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="filekg_main")
    parser.add_argument("--max-move", type=int, default=8)
    parser.add_argument("--results-dir", default="results_corrected_v2")
    args = parser.parse_args()

    from src.evaluation.robustness import run_robustness_test

    ds_path = ROOT / "data" / "benchmarks" / args.dataset
    gt_path = ROOT / "data" / "benchmarks" / "annotations" / f"{args.dataset}.json"
    out = ROOT / "data" / "evaluation" / args.results_dir / "robustness.json"

    result = run_robustness_test(
        ds_path,
        gt_path,
        max_move_files=args.max_move,
        output_path=out,
    )
    print(f"relation_retention_rate: {result['volume_file_id']['relation_retention_rate']}")
    print(f"已保存: {out}")


if __name__ == "__main__":
    main()
