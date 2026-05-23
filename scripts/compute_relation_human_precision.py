#!/usr/bin/env python3
"""根据人工标注 JSONL 计算关系构建精确率。"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "data" / "evaluation" / "relation_human_audit_template.jsonl"
OUT = ROOT / "data" / "evaluation" / "relation_human_precision.json"


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit(f"缺少 {TEMPLATE}")

    by_type: dict[str, list[str]] = defaultdict(list)
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        v = (row.get("human_verdict") or "").strip().lower()
        if not v:
            continue
        by_type[row.get("relation_type") or "UNKNOWN"].append(v)

    summary = {"per_type": {}, "macro_precision": None, "labeled": 0}
    precs = []
    for rt, verdicts in sorted(by_type.items()):
        correct = sum(1 for v in verdicts if v == "correct")
        labeled = len(verdicts)
        prec = correct / labeled if labeled else None
        summary["per_type"][rt] = {
            "labeled": labeled,
            "correct": correct,
            "precision": prec,
        }
        if prec is not None:
            precs.append(prec)
        summary["labeled"] += labeled

    if precs:
        summary["macro_precision"] = sum(precs) / len(precs)

    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {OUT}")
    print(f"macro_precision (已标注类型): {summary.get('macro_precision')}")


if __name__ == "__main__":
    main()
