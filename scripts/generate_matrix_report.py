#!/usr/bin/env python3
"""Generate 4D experiment matrix markdown report."""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "evaluation"


def load(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def fmt_row(bl: str, agg: dict) -> str:
    return (
        f"| {bl} | {agg.get('map', 0):.3f} | {agg.get('ndcg', 0):.3f} | {agg.get('recall', 0):.3f} | "
        f"{agg.get('graph_discovery', 0):.3f} | {agg.get('graph_only_discovery', 0):.3f} | "
        f"{agg.get('serendipity', 0):.3f} | {agg.get('explain_coverage', 0):.3f} |\n"
    )


def collect_dataset_results() -> dict:
    merged = load(EVAL / "experiment_matrix_results.json")
    datasets = dict(merged.get("datasets", {}))
    cfg = load(EVAL / "experiment_matrix.json")
    for spec in cfg.get("datasets", []):
        ds_id = spec["id"]
        if ds_id in datasets and not datasets[ds_id].get("error"):
            continue
        p = EVAL / f"{ds_id}.json"
        if p.exists():
            data = load(p)
            if data.get("baselines"):
                datasets[ds_id] = data
    merged["datasets"] = datasets
    return merged


def main():
    matrix = collect_dataset_results()
    cfg = load(EVAL / "experiment_matrix.json")

    lines = [
        "# FileKG 四维实验矩阵报告\n",
        f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "\n## 实验设计（功能 × 数据集 × Baseline × 指标）\n\n",
        "### 递进基线\n\n",
        "BM25 → VectorOnly → Vector+Metadata → Vector+SIMILAR_TO → **FileKG-Full**\n\n",
        "### 指标组\n\n",
        "| 指标组 | 指标 | 验证功能 |\n",
        "|--------|------|----------|\n",
        "| 检索 | MAP@K, NDCG@K, Recall@K | 双桶混合检索、多因子排序 |\n",
        "| 图发现 | GraphDiscovery, GraphOnly, Serendipity, R_indirect | 多关系图扩展 |\n",
        "| 可解释 | ExplainCoverage, PathFidelity | 推理路径 |\n",
        "| 鲁棒 | Robustness@K, incremental_update_ms | inode + 增量更新 |\n\n",
    ]

    for ds_id, res in matrix.get("datasets", {}).items():
        if res.get("error"):
            lines.append(f"\n## 数据集：{ds_id}\n\n**错误**：{res['error']}\n")
            continue
        lines.append(f"\n## 数据集：{ds_id}\n\n")
        lines.append("| Baseline | MAP | NDCG | Recall | GraphDisc | GraphOnly | Serendipity | ExplainCov |\n")
        lines.append("|----------|-----|------|--------|-----------|-----------|-------------|------------|\n")
        for bl, data in res.get("baselines", {}).items():
            lines.append(fmt_row(bl, data.get("aggregate", {})))

        full = res.get("baselines", {}).get("FileKG-Full", {}).get("aggregate", {})
        vec = res.get("baselines", {}).get("VectorOnly", {}).get("aggregate", {})
        if full and vec:
            lines.append(
                f"\n**FileKG-Full vs VectorOnly**："
                f"MAP Δ={full.get('map', 0) - vec.get('map', 0):+.3f}, "
                f"GraphOnly Δ={full.get('graph_only_discovery', 0) - vec.get('graph_only_discovery', 0):+.3f}, "
                f"ExplainCov={full.get('explain_coverage', 0):.3f}\n"
            )

        if res.get("ablation"):
            lines.append("\n### 消融（禁用单一关系）\n\n")
            lines.append("| 配置 | MAP | Δ MAP | GraphOnly | Δ GraphOnly |\n")
            lines.append("|------|-----|-------|-----------|-------------|\n")
            full_ab = res["ablation"].get("_full", full)
            for name, agg in res["ablation"].items():
                if name.startswith("_"):
                    continue
                d = agg.get("delta", {})
                lines.append(
                    f"| {name} | {agg.get('map', 0):.3f} | {d.get('map', 0):+.3f} | "
                    f"{agg.get('graph_only_discovery', 0):.3f} | {d.get('graph_only_discovery', 0):+.3f} |\n"
                )

        if res.get("robustness_retrieval"):
            rr = res["robustness_retrieval"]
            lines.append("\n### 鲁棒性检索（移动文件 + 增量更新）\n\n")
            lines.append(f"- 增量更新耗时：{rr.get('incremental_update_ms', '-')} ms\n")
            vo = rr.get("vector_only", {})
            fk = rr.get("filekg_full", {})
            lines.append(
                f"- VectorOnly Robustness@Recall：{vo.get('robustness_recall', 0):.3f} "
                f"(before={vo.get('recall_before', 0):.3f}, after={vo.get('recall_after', 0):.3f})\n"
            )
            lines.append(
                f"- FileKG-Full Robustness@Recall：{fk.get('robustness_recall', 0):.3f} "
                f"(before={fk.get('recall_before', 0):.3f}, after={fk.get('recall_after', 0):.3f})\n"
            )

    lines.append("\n## 矩阵配置（experiment_matrix.json）\n\n")
    lines.append("```json\n")
    lines.append(json.dumps(cfg.get("datasets", []), ensure_ascii=False, indent=2)[:4000])
    lines.append("\n```\n")

    lines.append("\n## 用户研究（待执行）\n\n")
    lines.append("见 `data/evaluation/user_study_protocol.md`。\n")

    out = EVAL / "experiment_matrix_report.md"
    out.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
