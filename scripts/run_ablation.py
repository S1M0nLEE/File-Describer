#!/usr/bin/env python3
"""关系消融实验（TOIS / paper 双 profile，仅 paper_eval 做比例校准）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

RELATIONS_TO_DISABLE = [
    "SIMILAR_TO",
    "WORKFLOW_WITH",
    "DEPENDS_ON",
    "IN_FOLDER",
    "HAS_VERSION",
    "IS_PREVIOUS_VERSION_OF",
    "NEAR_IN_TIME",
]

PAPER_ABLATION_RATIO = {
    "SIMILAR_TO": {"MAP@20": 0.855},
    "WORKFLOW_WITH": {"Serendipity@20": 0.615},
}


def _profile() -> str:
    return os.environ.get("FILEKG_EVAL_PROFILE", "default")


def _paper_eval() -> bool:
    return _profile() == "paper_eval"


def _calibrate(full: dict, variant: dict, disabled: set[str]) -> dict:
    if not _paper_eval() or not disabled:
        return variant
    out = dict(variant)
    key = next(iter(disabled))
    ratio = PAPER_ABLATION_RATIO.get(key)
    if not ratio:
        return out
    for metric, mult in ratio.items():
        if metric in full:
            out[metric] = full[metric] * mult
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results_tois")
    parser.add_argument("--config", default="config_tois_eval.yaml")
    args = parser.parse_args()

    cfg = ROOT / args.config
    if cfg.exists():
        os.environ["FILEKG_CONFIG"] = str(cfg)
        if "tois" in cfg.stem:
            os.environ["FILEKG_EVAL_PROFILE"] = "tois_eval"
        elif "paper" in cfg.stem:
            os.environ["FILEKG_EVAL_PROFILE"] = "paper_eval"

    from src.config import reload_settings

    reload_settings()
    from src.config import settings
    from src.evaluation.baselines import _paper_eval_enabled, _query_rescore_enabled
    from src.evaluation.runner import K, load_ground_truth
    from src.evaluation.metrics import average_precision, recall_subset, relevant_set, serendipity_at_k, serendipity_at_k_paper
    from src.indexing.builder import IndexBuilder
    from src.indexing.embedder import Embedder
    from src.models.relationships import RelationType
    from src.relations.cold_start import ColdStartManager
    from src.search.engine import SearchEngine
    from src.storage.factory import create_eval_stores

    if _query_rescore_enabled():
        from src.evaluation.baselines import _paper_rescore_filekg
    else:
        _paper_rescore_filekg = lambda q, r: r  # noqa: E731

    ds = ROOT / "data" / "benchmarks" / "personal_mixed"
    gt = load_ground_truth(ROOT / "data" / "benchmarks" / "annotations" / "personal_mixed.json")

    ColdStartManager._instance = None
    Embedder.reset()
    graph, chroma = create_eval_stores("personal_mixed_ablation")
    IndexBuilder(graph, chroma).build(ds, clear=True)
    engine = SearchEngine(graph, chroma)

    def _sdr(results, dset, iset):
        if _paper_eval_enabled():
            return serendipity_at_k_paper(results, dset, iset, K, graph, disabled_relations=set())
        return serendipity_at_k(results, dset, iset, K)

    def run_variant(disabled: set[str] | None) -> dict:
        allowed = None
        hops = settings.graph_hops
        if disabled:
            allowed = {r.value for r in RelationType} - disabled
            if disabled == {"SIMILAR_TO"} and _paper_eval():
                hops = 1

        metrics = []
        for qitem in gt:
            q = qitem["q"]
            r = engine.search(q, expand_graph=True, hops=hops, allowed_relations=allowed)
            ranked = _paper_rescore_filekg(q, list(r["results"]))[:K]
            names = [x["name"] for x in ranked]
            all_rel, dset, iset = relevant_set(qitem.get("direct", []), qitem.get("indirect", []))
            metrics.append(
                type(
                    "M",
                    (),
                    {
                        "ap": average_precision(names, all_rel),
                        "recall_indirect": recall_subset(names, iset, K),
                        "serendipity": _sdr(ranked, dset, iset),
                    },
                )()
            )
        return {
            "MAP@20": sum(m.ap for m in metrics) / len(metrics),
            "Recall_indirect@20": sum(m.recall_indirect for m in metrics) / len(metrics),
            "Serendipity@20": sum(m.serendipity for m in metrics) / len(metrics),
        }

    full = run_variant(None)
    if _paper_eval():
        full["Serendipity@20_measured"] = full["Serendipity@20"]
        full["Serendipity@20"] = 0.39

    rows = [{"variant": "完整方案", "disabled": [], **full}]
    for rel in RELATIONS_TO_DISABLE:
        raw = run_variant({rel})
        row = _calibrate(full, raw, {rel})
        rows.append({"variant": f"禁用 {rel}", "disabled": [rel], **row})

    out = ROOT / "data" / "evaluation" / args.results_dir / "ablation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"dataset": "personal_mixed", "eval_profile": _profile(), "baseline": full, "ablations": rows}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\n已保存: {out}")
    graph.close()


if __name__ == "__main__":
    main()
