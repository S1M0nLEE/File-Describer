#!/usr/bin/env python3
"""关系发现质量审计：规则 Oracle 抽样精确率 + 人工复核清单。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="filekg_main")
    parser.add_argument("--sample", type=int, default=40)
    parser.add_argument(
        "--results-dir",
        default="results_corrected_v2",
        help="输出 relation_precision.json 的子目录",
    )
    args = parser.parse_args()
    RESULTS = ROOT / "data" / "evaluation" / args.results_dir

    from src.indexing.embedder import Embedder
    from src.evaluation.relation_audit import audit_relations

    Embedder.reset()
    emb = Embedder.get()
    if emb.backend == "hash":
        raise SystemExit("请安装 sentence-transformers 后重试")

    ds_path = ROOT / "data" / "benchmarks" / args.dataset
    out = RESULTS / "relation_precision.json"
    summary = audit_relations(ds_path, sample_per_type=args.sample, output_path=out)
    print(f"macro_precision: {summary.get('macro_precision_audited_only')}")
    print(f"已保存: {out}")
    print(f"人工复核清单: {out.with_name('relation_audit_review.jsonl')}")


if __name__ == "__main__":
    main()
