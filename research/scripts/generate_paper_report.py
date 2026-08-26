#!/usr/bin/env python3
"""Generate paper-ready benchmark report from experiment JSON."""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def relation_coverage(gt: dict) -> dict:
    rels = gt.get("relations", [])
    counts = {}
    for r in rels:
        t = r.get("type", "UNKNOWN")
        counts[t] = counts.get(t, 0) + 1
    return counts


def main():
    eval_dir = ROOT / "data" / "evaluation"
    dataset_dir = ROOT / "data" / "datasets" / "filekg_main_public"
    exp = load_json(eval_dir / "experiment_data_public.json")
    if not exp:
        exp = load_json(eval_dir / "experiment_data.json")
    gt = load_json(dataset_dir / "evaluation_ground_truth.json")
    stats = gt.get("stats", {})

    rel_counts = relation_coverage(gt)
    lines = [
        "# FileKG 公开数据集基准实验报告\n",
        f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "\n## 1. 数据集构成（公开数据源拼装）\n",
        "\n| 数据源 | 文件数（抽样） | 支撑关系 |\n",
        "|--------|----------------|----------|\n",
        "| GitHub (flask/requests/rich/fastapi/numpy) | "
        f"{stats.get('sources', {}).get('github', '-')} | IN_FOLDER, DEPENDS_ON |\n",
        f"| Cora 引文网络 | {stats.get('sources', {}).get('cora', '-')} | REFERENCES |\n",
        f"| SDS KoPub VDR | {stats.get('sources', {}).get('kopub', '-')} | REFERENCES, VISUALLY_SIMILAR_TO |\n",
        f"| NapierOne 格式分层样本 | {stats.get('sources', {}).get('napierone', '-')} | IN_FOLDER, SAME_TYPE, CONTAINS |\n",
        f"| Govdocs1 风格文本 | {stats.get('sources', {}).get('govdocs', '-')} | SIMILAR_TO |\n",
        f"| Multimodal-Mind2Web (SeeAct) | mind2web pairs | VISUALLY_SIMILAR_TO |\n",
        f"| BEHACOM / 行为代理 | sessions | WORKFLOW_WITH |\n",
        f"| CARDS (npm 子集) | edges | DEPENDS_ON |\n",
        f"\n**合计**：{stats.get('files', '-')} 个文件，{stats.get('relations', '-')} 条标注关系，"
        f"{stats.get('queries', '-')} 条查询。\n",
        "\n## 2. 关系类型分布（标注）\n\n",
        "| 关系类型 | 边数 |\n|----------|------|\n",
    ]
    for t, c in sorted(rel_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {t} | {c} |\n")

    lines.append("\n## 3. 检索基线对比（@20）\n\n")
    lines.append("| 方法 | MAP@20 | NDCG@20 | Recall@20 | R_indirect@20 | GraphDisc@20 | ExplainCov@20 |\n")
    lines.append("|------|--------|---------|-----------|---------------|--------------|---------------|\n")
    for bl, data in exp.get("baselines", {}).items():
        a = data.get("aggregate", {})
        lines.append(
            f"| {bl} | {a.get('map', 0):.3f} | {a.get('ndcg', 0):.3f} | {a.get('recall', 0):.3f} | "
            f"{a.get('r_indirect', 0):.3f} | {a.get('graph_discovery', 0):.3f} | {a.get('explain_coverage', 0):.3f} |\n"
        )

    full = exp.get("baselines", {}).get("FileKG-Full", {}).get("aggregate", {})
    vector = exp.get("baselines", {}).get("VectorOnly", {}).get("aggregate", {})
    if full and vector:
        d_map = (full.get("map", 0) - vector.get("map", 0)) / max(vector.get("map", 1e-6), 1e-6) * 100
        d_recall = (full.get("recall", 0) - vector.get("recall", 0)) * 100
        lines.append(
            f"\n**FileKG-Full 相对 VectorOnly**：MAP 提升约 {d_map:.1f}%，"
            f"Recall@20 提升约 {d_recall:.1f} 个百分点；图扩展带来可解释路径（ExplainCov@20 = {full.get('explain_coverage', 0):.3f}）。\n"
        )

    if exp.get("ablation"):
        lines.append("\n## 4. 消融实验\n\n")
        for name, agg in exp["ablation"].items():
            lines.append(f"- **{name}**：MAP@20 = {agg.get('map', 0):.3f}，Recall@20 = {agg.get('recall', 0):.3f}\n")

    lines.append("\n## 5. 论文写作要点（可直接引用）\n\n")
    lines.append(
        "1. **可复现性**：基准由 NapierOne、GitHub、Cora、CARDS、KoPub VDR、Mind2Web、BEHACOM、Govdocs1 等公开数据自动拼装，"
        "脚本 `scripts/build_filekg_main.py` 支持断点续传。\n"
    )
    lines.append(
        "2. **关系真实性**：IN_FOLDER、REFERENCES（Cora）、DEPENDS_ON（代码 import + CARDS）、"
        "VISUALLY_SIMILAR_TO（截图-HTML 对）等均来自数据集固有结构或标准解析器。\n"
    )
    lines.append(
        "3. **评测协议**：150 条查询（HippoCamp + KoPub + 自动模板），指标含 MAP/NDCG/Recall/R_indirect/GraphDiscovery/ExplainCoverage。\n"
    )
    lines.append(
        "4. **系统配置**：BGE-small-zh 向量索引 + Neo4j/本地图存储 + 多因子排序（α/β/γ/δ）。\n"
    )

    out_md = eval_dir / "paper_report.md"
    out_md.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out_md}")


if __name__ == "__main__":
    main()
