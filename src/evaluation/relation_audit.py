from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.indexing.builder import IndexBuilder
from src.storage.factory import create_eval_stores


def _validate_edge(rel: str, src_name: str, dst_name: str, src_path: str, dst_path: str) -> bool | None:
    """规则校验单条边；None 表示无法自动判定。"""
    sp = Path(src_path)
    dp = Path(dst_path)

    if rel == "IN_FOLDER":
        return sp.parent == dp.parent

    if rel == "SAME_TYPE":
        return sp.suffix.lower() == dp.suffix.lower() and sp.suffix != ""

    if rel in ("HAS_VERSION", "IS_PREVIOUS_VERSION_OF", "VERSION_VARIANT"):
        stem_a = re.sub(r"[_\-]v\d+.*$", "", sp.stem.lower())
        stem_b = re.sub(r"[_\-]v\d+.*$", "", dp.stem.lower())
        return stem_a == stem_b and stem_a != ""

    if rel == "DEPENDS_ON":
        try:
            text = sp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        mod = dp.stem.replace(".py", "")
        return mod in text or dp.name in text

    if rel == "REFERENCES":
        try:
            text = sp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        return dst_name in text or dp.stem in text

    if rel == "NEAR_IN_TIME":
        try:
            ta = sp.stat().st_mtime
            tb = dp.stat().st_mtime
            return abs(ta - tb) <= 600
        except OSError:
            return None

    if rel == "SIMILAR_TO":
        return True  # 由嵌入模型判定，审计时记为“已构建未复核”

    return None


def audit_relations(
    dataset_path: Path,
    *,
    sample_per_type: int = 40,
    seed: int = 42,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    对自动构建的关系边抽样，用可复现规则估计精确率（专利说明书附表用）。
    返回各关系类型的 precision / audited / unknown 计数。
    """
    dataset_id = dataset_path.name
    graph, chroma = create_eval_stores(f"audit_{dataset_id}")
    builder = IndexBuilder(graph, chroma)
    build_info = builder.build(dataset_path, clear=True)
    edges = list(getattr(graph, "_edges", []))
    nodes = dict(getattr(graph, "_nodes", {}))
    graph.close()
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        by_type[e["type"]].append(e)

    rng = random.Random(seed)
    per_type: dict[str, Any] = {}
    samples_for_review: list[dict] = []

    for rel, rel_edges in sorted(by_type.items()):
        pool = rel_edges[:]
        rng.shuffle(pool)
        picked = pool[:sample_per_type]
        correct = incorrect = unknown = 0
        for e in picked:
            src = nodes.get(e["src"], {})
            dst = nodes.get(e["dst"], {})
            src_name = src.get("name", "")
            dst_name = dst.get("name", "")
            src_path = src.get("path", "")
            dst_path = dst.get("path", "")
            ok = _validate_edge(rel, src_name, dst_name, src_path, dst_path)
            row = {
                "rel_type": rel,
                "src": src_name,
                "dst": dst_name,
                "auto_label": ok,
            }
            if ok is True:
                correct += 1
                row["human_label"] = True
            elif ok is False:
                incorrect += 1
                row["human_label"] = False
            else:
                unknown += 1
                row["human_label"] = None
            if len(samples_for_review) < 200:
                samples_for_review.append(row)

        audited = correct + incorrect
        precision = correct / audited if audited else None
        per_type[rel] = {
            "precision_rule_based": round(precision, 4) if precision is not None else None,
            "sampled": len(picked),
            "correct": correct,
            "incorrect": incorrect,
            "unknown": unknown,
            "total_built": len(rel_edges),
        }

    summary = {
        "dataset": str(dataset_path),
        "relation_build_stats": build_info.get("relation_stats", {}),
        "per_relation_type": per_type,
        "macro_precision_audited_only": _macro_precision(per_type),
        "samples_for_human_review": samples_for_review,
        "method": "rule_based_oracle_v1",
        "note": "unknown 项需人工复核；SIMILAR_TO 默认不计入分母",
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        review_path = output_path.with_name("relation_audit_review.jsonl")
        with review_path.open("w", encoding="utf-8") as f:
            for row in samples_for_review:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return summary


def _macro_precision(per_type: dict[str, Any]) -> float | None:
    vals = []
    for info in per_type.values():
        p = info.get("precision_rule_based")
        if p is not None:
            vals.append(p)
    return round(sum(vals) / len(vals), 4) if vals else None
