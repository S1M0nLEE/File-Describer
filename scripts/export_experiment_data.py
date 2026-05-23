#!/usr/bin/env python3

"""聚合专利举证用实验结果为 experiment_data.json。"""

from __future__ import annotations



import json

import sys

from collections import defaultdict

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))



OUT = ROOT / "data" / "evaluation" / "experiment_data.json"

REGISTRY_DEFAULT = ROOT / "data" / "benchmarks" / "registry.json"
REGISTRY_REAL = ROOT / "data" / "benchmarks" / "registry_real.json"
RESULTS_REAL = ROOT / "data" / "evaluation" / "results_real"
RESULTS_SYNTH = ROOT / "data" / "evaluation" / "results_patent_compare"





def _load_json(path: Path) -> dict | list | None:

    if not path.exists():

        return None

    return json.loads(path.read_text(encoding="utf-8"))





def _load_metrics(ds_id: str, results_root: Path) -> dict | None:

    p = results_root / ds_id / "metrics.json"

    data = _load_json(p)

    return data if isinstance(data, dict) else None





def _baseline_metrics(m: dict) -> dict:

    b = m.get("baselines", {})

    out = {}

    for name, vals in b.items():

        out[name] = {

            "MAP@20": vals.get("MAP@20"),

            "P@20": vals.get("P@20"),

            "Recall@20": vals.get("R@20"),

            "NDCG@20": vals.get("NDCG@20"),

            "R_indirect@20": vals.get("Recall_indirect@20"),

            "Recall_direct@20": vals.get("Recall_direct@20"),

            "Serendipity@20": vals.get("Serendipity@20"),

            "GraphDiscovery@20": vals.get("GraphDiscovery@20"),

            "explainability": vals.get("Explainability@20"),

            "avg_latency_ms": vals.get("latency_ms_avg"),

        }

    return out





def _relation_path_totals(m: dict) -> dict[str, int]:

    totals: dict[str, int] = defaultdict(int)

    for _q, rels in m.get("relation_contribution", {}).items():

        for rt, c in rels.items():

            totals[rt] += c

    return dict(totals)





def _count_noise(ds_path: Path) -> int:

    noise = ds_path / "noise"

    if noise.is_dir():

        return sum(1 for _ in noise.rglob("*") if _.is_file())

    return 0





def _dataset_meta(ds: dict, results_root: Path) -> dict:

    ds_id = ds["id"]

    m = _load_metrics(ds_id, results_root)

    ds_path = ROOT / ds["path"]

    annot = ROOT / ds["ground_truth"]

    query_count = 0

    if annot.exists():

        query_count = len(json.loads(annot.read_text(encoding="utf-8")).get("queries", []))



    meta: dict = {

        "file_count": m.get("file_count") if m else None,

        "query_count": m.get("query_count") if m else query_count,

        "index_time_sec": m.get("index_time_sec") if m else None,

        "query_leakage_ratio": m.get("query_leakage_ratio") if m else None,

        "noise_file_count": _count_noise(ds_path),

        "metrics_version": m.get("metrics_version") if m else None,

        "scenes": _scene_names(ds_path),

    }

    if m:

        build = dict(m.get("relation_build_stats", {}))

        meta["relation_build_counts"] = build

        meta["relation_types_built"] = sorted(build.keys())

        meta["relation_path_usage"] = _relation_path_totals(m)

    return meta





def _scene_names(ds_path: Path) -> list[str]:

    if not ds_path.is_dir():

        return []

    return sorted(

        d.name

        for d in ds_path.iterdir()

        if d.is_dir() and d.name not in ("noise", "annotations")

    )





def _ablation(results_root: Path) -> dict:

    data = _load_json(results_root / "ablation.json")

    if not isinstance(data, dict):

        return {}

    out = {}

    full = data.get("baseline", {})

    out["FileKG-Full"] = {

        "MAP@20": full.get("MAP@20"),

        "Serendipity@20": full.get("Serendipity@20"),

        "Recall_indirect@20": full.get("Recall_indirect@20"),

    }

    for row in data.get("ablations", []):

        if not row.get("disabled"):

            continue

        key = "-" + row["disabled"][0]

        out[key] = {

            "MAP@20": row.get("MAP@20"),

            "Serendipity@20": row.get("Serendipity@20"),

            "Recall_indirect@20": row.get("Recall_indirect@20"),

        }

    return out





def _relation_precision(results_root: Path) -> dict:

    data = _load_json(results_root / "relation_precision.json")

    if not isinstance(data, dict):

        return {}

    per = data.get("per_relation_type", {})

    return {

        rt: info.get("precision_rule_based")

        for rt, info in per.items()

        if info.get("precision_rule_based") is not None

    }





def _robustness(results_root: Path) -> dict:

    data = _load_json(results_root / "robustness.json")

    if not isinstance(data, dict):

        return {}

    vol = data.get("volume_file_id", {})

    return {

        "relation_retention_rate": vol.get("relation_retention_rate"),

        "incremental_update_sec": vol.get("incremental_update_sec"),

        "MAP@20_after_move": vol.get("MAP@20_after_move"),

        "path_id_logical_retention_rate": data.get("path_based_id", {}).get(

            "logical_relation_retention_rate"

        ),

        "files_moved": data.get("files_moved"),

    }





def _statistical_tests(results_root: Path) -> dict:

    m = _load_metrics("filekg_main", results_root)

    if not m:

        return {}

    tests = m.get("statistical_tests", {})

    fk = tests.get("filekg_vs_best_baseline_ap", {})

    return {

        "FileKG_vs_best_baseline_pvalue": fk.get("p_value"),

        "best_baseline": fk.get("best_baseline"),

        "mean_ap_diff": fk.get("mean_diff"),

        "significant_0_05": fk.get("significant_0_05"),

        "metric": "MAP@20 per-query AP",

        "n_queries": fk.get("queries"),

    }





def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--registry",
        choices=("synthetic", "real", "both"),
        default="both",
        help="导出哪些 registry 的 metrics",
    )
    args = ap.parse_args()

    datasets: dict = {}
    metrics: dict = {}
    notes: dict = {}

    if args.registry in ("synthetic", "both") and REGISTRY_DEFAULT.exists():
        reg = json.loads(REGISTRY_DEFAULT.read_text(encoding="utf-8"))
        for ds in reg["datasets"]:
            ds_id = ds["id"]
            datasets[ds_id] = _dataset_meta(ds, RESULTS_SYNTH)
            m = _load_metrics(ds_id, RESULTS_SYNTH)
            if m:
                metrics[ds_id] = _baseline_metrics(m)
            else:
                notes[ds_id] = "未执行 run_evaluation（合成集）"

    if args.registry in ("real", "both") and REGISTRY_REAL.exists():
        reg_real = json.loads(REGISTRY_REAL.read_text(encoding="utf-8"))
        for ds in reg_real["datasets"]:
            ds_id = ds["id"]
            datasets[ds_id] = _dataset_meta(ds, RESULTS_REAL)
            m = _load_metrics(ds_id, RESULTS_REAL)
            if m:
                metrics[ds_id] = _baseline_metrics(m)
            else:
                notes[ds_id] = "未执行 run_evaluation --registry real"

    results_primary = RESULTS_REAL if args.registry == "real" else RESULTS_SYNTH
    if args.registry == "both":
        results_primary = RESULTS_SYNTH

    main_m = _load_metrics("filekg_main", RESULTS_SYNTH) or {}

    eff = {}

    if main_m:

        b = main_m.get("baselines", {})

        for name in ("FileKG-Full", "VectorOnly", "BM25"):

            if name in b:

                eff[f"{name}_latency_ms"] = b[name].get("latency_ms_avg")

        eff["indexing_time_s_filekg_main"] = main_m.get("index_time_sec")



    audit = _load_json(RESULTS_SYNTH / "relation_precision.json")

    notes.setdefault("relation_precision", "规则 Oracle 自动审计；详见 relation_precision.json")
    notes.update({

        "statistical_tests": "filekg_main 上 FileKG vs 最佳基线配对 t 检验（AP）",

        "robustness": "filekg_main 子集移动；volume file_id 增量 vs path 重建",

        "llm_query_parser": "规则引擎 dateparser/正则；未集成 Ollama/Phi-3",

        "visual_relation": "VISUALLY_SIMILAR_TO 未实现",
        "real_results_dir": str(RESULTS_REAL),
    })

    if isinstance(audit, dict) and audit.get("samples_for_human_review"):

        notes["human_review_file"] = str(

            RESULTS_SYNTH / "relation_audit_review.jsonl"

        )



    pkg = {

        "generated_from": str(results_primary),

        "generated_from_synthetic": str(RESULTS_SYNTH),

        "generated_from_real": str(RESULTS_REAL),

        "metrics_version": "corrected_v2",

        "baselines": [

            "BM25",

            "VectorOnly",

            "Vector+Metadata",

            "Vector+SIMILAR_TO",

            "FileKG-Full",

        ],

        "datasets": datasets,

        "metrics": metrics,

        "ablation": _ablation(RESULTS_SYNTH),

        "relation_precision": _relation_precision(RESULTS_SYNTH),

        "relation_precision_detail": audit if isinstance(audit, dict) else {},

        "efficiency": eff,

        "robustness": _robustness(RESULTS_SYNTH),

        "statistical_tests": _statistical_tests(RESULTS_SYNTH),

        "software": {

            "python": "3.12 (project .venv)",

            "chromadb": ">=0.4.22",

            "neo4j": ">=5.17 (optional; fallback MemoryGraphStore)",

            "embedding_model": "BAAI/bge-small-zh-v1.5",

            "sentence_transformers": ">=2.3.0",

        },

        "notes": notes,

    }

    OUT.parent.mkdir(parents=True, exist_ok=True)

    OUT.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已导出: {OUT}")





if __name__ == "__main__":

    main()

