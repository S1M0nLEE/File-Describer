#!/usr/bin/env python3
"""导出人工关系复核模板（目标 300 条），供专利说明书附表。"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "evaluation" / "relation_human_audit_template.jsonl"
GUIDE = ROOT / "data" / "evaluation" / "patent" / "RELATION_HUMAN_AUDIT.md"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", type=int, default=300)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dataset", default="filekg_main")
    args = p.parse_args()

    review_path = ROOT / "data" / "evaluation" / "results_patent_embodiment" / "relation_audit_review.jsonl"
    if not review_path.exists():
        review_path = ROOT / "data" / "evaluation" / "results_corrected_v2" / "relation_audit_review.jsonl"
    if not review_path.exists():
        review_path = ROOT / "data" / "evaluation" / "results_patent_compare" / "relation_audit_review.jsonl"

    lines: list[dict] = []
    if review_path.exists():
        for line in review_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(json.loads(line))

    rng = random.Random(args.seed)
    if len(lines) > args.target:
        lines = rng.sample(lines, args.target)
    elif len(lines) < args.target:
        for i in range(len(lines), args.target):
            lines.append(
                {
                    "id": f"placeholder_{i + 1}",
                    "relation_type": "",
                    "src_name": "",
                    "dst_name": "",
                    "rule_verdict": None,
                    "human_verdict": "",
                    "note": "待抽样或待标注",
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in lines:
            row.setdefault("human_verdict", "")
            row.setdefault("annotator", "")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    GUIDE.parent.mkdir(parents=True, exist_ok=True)
    GUIDE.write_text(
        "\n".join(
            [
                "# 关系边人工复核说明（专利附表）",
                "",
                f"- 模板文件：`{OUT.relative_to(ROOT).as_posix()}`",
                f"- 目标条数：**{args.target}**",
                "- 字段：`human_verdict` 填 `correct` / `incorrect` / `unknown`",
                "- 规则 Oracle 自动判定见 `relation_precision.json`；人工结果用于说明书「关系构建准确率」",
                "",
                "## 标注步骤",
                "",
                "1. 打开 JSONL，按 `src_name`/`dst_name` 在数据集中定位文件",
                "2. 判断 `relation_type` 是否成立",
                "3. 填写 `human_verdict` 与 `annotator`",
                "4. 运行 `python scripts/compute_relation_human_precision.py` 汇总",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"已导出 {len(lines)} 条 -> {OUT}")
    print(f"说明: {GUIDE}")


if __name__ == "__main__":
    main()
