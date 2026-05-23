#!/usr/bin/env python3
"""视觉融合消融与多跳命中率评测（发明说明第 6 章）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import reload_settings
from src.evaluation.visual_baselines import build_visual_ablation_baselines
from src.evaluation.visual_metrics import multihop_visual_hit_rate
from src.storage.factory import create_stores


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config_patent_full.yaml")
    p.add_argument("--dataset", default="filekg_main")
    p.add_argument("--variant", default="all", help="B0..B8 或 all")
    args = p.parse_args()

    reload_settings(ROOT / args.config)
    import os

    if args.variant != "all":
        os.environ["FILEKG_VISUAL_VARIANT"] = args.variant

    neo4j, chroma = create_stores()
    from src.search.engine import SearchEngine

    engine = SearchEngine(neo4j, chroma)
    baselines = build_visual_ablation_baselines(engine)

    qpath = ROOT / "data/evaluation/patent/visual_eval_queries.json"
    visual_q = json.loads(qpath.read_text(encoding="utf-8")).get("set_b_visual_dependent", [])

    print(f"视觉变体基线: {[b.name for b in baselines]}")
    print(f"视觉依赖查询: {len(visual_q)} 条（多跳指标需人工标注 relevant 后完整计算）")

    if visual_q:
        sample = visual_q[0]["query"]
        for b in baselines[:3]:
            hits = b.search(sample, k=5)
            print(f"  {b.name}: {len(hits)} hits, top={hits[0]['name'] if hits else '-'}")

    out = {
        "config": args.config,
        "dataset": args.dataset,
        "baselines": [b.name for b in baselines],
        "visual_query_count": len(visual_q),
        "pair_benchmark": json.loads(qpath.read_text(encoding="utf-8")).get(
            "pair_benchmark_spec"
        ),
        "note": "完整 MAP/多跳命中率请对 set_b 标注 GT 后接入 EvaluationRunner",
    }
    out_dir = ROOT / "data/evaluation/patent"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "visual_fusion_eval_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("已写入 data/evaluation/patent/visual_fusion_eval_summary.json")


if __name__ == "__main__":
    main()
