#!/usr/bin/env python3
"""关系消融实验（方案 8.5）：逐个禁用关系类型观察 MAP / Serendipity 变化。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

RELATIONS_TO_DISABLE = [
    "DEPENDS_ON",
    "IN_FOLDER",
    "WORKFLOW_WITH",
    "HAS_VERSION",
    "IS_PREVIOUS_VERSION_OF",
    "NEAR_IN_TIME",
]


def main() -> None:
    from src.indexing.builder import IndexBuilder
    from src.indexing.embedder import Embedder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_eval_stores
    from src.evaluation.runner import load_ground_truth, K
    from src.evaluation.metrics import aggregate, average_precision, recall_subset, relevant_set, serendipity_at_k
    from src.search.graph_expander import GraphExpander
    from src.search.intent_parser import IntentParser
    from src.search.ranker import MultiFactorRanker

    ds = ROOT / "data" / "benchmarks" / "filekg_main"
    gt = load_ground_truth(ROOT / "data" / "benchmarks" / "annotations" / "filekg_main.json")

    Embedder.reset()
    graph, chroma = create_eval_stores("filekg_main_ablation")
    IndexBuilder(graph, chroma).build(ds, clear=True)
    engine = SearchEngine(graph, chroma)
    intent = IntentParser()
    expander = GraphExpander(graph)
    ranker = MultiFactorRanker(graph, chroma)
    embedder = Embedder.get()

    def run_variant(disabled: set[str] | None) -> dict:
        metrics = []
        for qitem in gt:
            q = qitem["q"]
            parsed = intent.parse(q)
            emb = embedder.embed(parsed.keywords or q)
            hits = chroma.search_chunks(emb, n_results=30, where=parsed.chroma_where())
            seeds: dict[str, dict] = {}
            for h in hits:
                fid = h.get("file_id")
                if fid and (fid not in seeds or h["similarity"] > seeds[fid]["similarity"]):
                    seeds[fid] = {"file_id": fid, "name": h.get("name", ""), "similarity": h["similarity"]}
            seed_list = list(seeds.values())
            allowed = None
            if disabled:
                from src.models.relationships import RelationType

                allowed = {r.value for r in RelationType} - disabled
            gh = expander.expand_seeds(seed_list, allowed_relations=allowed) if seed_list else {}
            ranked = ranker.rank(q, parsed, gh, emb)
            names = [r["name"] for r in ranked]
            all_rel, dset, iset = relevant_set(qitem.get("direct", []), qitem.get("indirect", []))
            metrics.append(
                type("M", (), {
                    "ap": average_precision(names, all_rel),
                    "recall_indirect": recall_subset(names, iset, K),
                    "serendipity": serendipity_at_k(ranked, dset, iset, K),
                })()
            )
        return {
            "MAP@20": sum(m.ap for m in metrics) / len(metrics),
            "Recall_indirect@20": sum(m.recall_indirect for m in metrics) / len(metrics),
            "Serendipity@20": sum(m.serendipity for m in metrics) / len(metrics),
        }

    full = run_variant(None)
    rows = [{"variant": "完整方案", "disabled": [], **full}]
    for rel in RELATIONS_TO_DISABLE:
        m = run_variant({rel})
        rows.append({"variant": f"禁用 {rel}", "disabled": [rel], **m})

    out = ROOT / "data" / "evaluation" / "results_corrected_v2" / "ablation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"baseline": full, "ablations": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\n已保存: {out}")
    graph.close()


if __name__ == "__main__":
    main()
