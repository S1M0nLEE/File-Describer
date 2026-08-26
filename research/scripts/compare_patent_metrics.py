#!/usr/bin/env python3
"""对比 FileKG-Full 与专利代理基线，输出胜负表。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "data" / "evaluation" / "results_patent_compare"
METRICS = [
    "MAP@20",
    "NDCG@20",
    "Recall@20",
    "Recall_indirect@20",
    "GraphDiscovery@20",
    "Explainability@20",
    "Serendipity@20",
]
PATENTS = [
    "Patent-IFlytek-KG",
    "Patent-Inspur-RAG",
    "Patent-MS-ActionSeq",
    "Patent-Snap-Visual",
]
FILEKG = "FileKG-Full"


def load_summary(ds_id: str, results: Path) -> dict:
    p = results / ds_id / "metrics.json"
    if not p.exists():
        raise SystemExit(f"缺少 {p}，请先运行 run_evaluation.py")
    return json.loads(p.read_text(encoding="utf-8"))


def compare_dataset(ds_id: str, results: Path) -> tuple[list[str], list[str]]:
    summary = load_summary(ds_id, results)
    baselines = summary.get("baselines", {})
    fk = baselines.get(FILEKG, {})
    wins, losses = [], []
    for patent in PATENTS:
        pb = baselines.get(patent, {})
        for m in METRICS:
            fv, pv = fk.get(m), pb.get(m)
            if not isinstance(fv, (int, float)) or not isinstance(pv, (int, float)):
                continue
            tag = f"{ds_id} | {patent} | {m}"
            if fv >= pv - 1e-9:
                wins.append(f"{tag}: FileKG {fv:.3f} >= {pv:.3f}")
            else:
                losses.append(f"{tag}: FileKG {fv:.3f} < {pv:.3f}")
    return wins, losses


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results_patent_compare")
    ap.add_argument("--registry", choices=("synthetic", "real"), default="synthetic")
    args = ap.parse_args()
    results = ROOT / "data" / "evaluation" / args.results_dir

    if args.registry == "real":
        reg = json.loads((ROOT / "data/benchmarks/registry_real.json").read_text(encoding="utf-8"))
        ds_ids = [d["id"] for d in reg["datasets"]]
        out_name = "REAL_PATENT_METRICS_COMPARISON.md"
    else:
        ds_ids = ["filekg_main", "code_dependency", "personal_mixed"]
        out_name = "PATENT_METRICS_COMPARISON.md"

    all_wins: list[str] = []
    all_losses: list[str] = []
    for ds in ds_ids:
        if (results / ds / "metrics.json").exists():
            w, l = compare_dataset(ds, results)
            all_wins.extend(w)
            all_losses.extend(l)

    out = ROOT / "data" / "evaluation" / out_name
    lines = [
        "# FileKG vs 专利代理基线 — 量化对标",
        "",
        f"> 结果目录：`data/evaluation/{args.results_dir}`",
        "",
        f"## 汇总：胜 {len(all_wins)} 项 / 负 {len(all_losses)} 项",
        "",
    ]
    if all_losses:
        lines.append("### 未领先项（需继续优化）")
        lines.extend(f"- {x}" for x in all_losses)
        lines.append("")
    lines.append("### 领先项（节选）")
    for x in all_wins[:40]:
        lines.append(f"- {x}")
    if len(all_wins) > 40:
        lines.append(f"- …共 {len(all_wins)} 项")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)
    if all_losses:
        print("\n未领先:")
        for x in all_losses:
            print(" ", x)
        return 1
    print("\n全部指标 FileKG >= 专利代理基线")
    return 0


if __name__ == "__main__":
    sys.exit(main())
