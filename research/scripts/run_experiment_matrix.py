#!/usr/bin/env python3
"""
Run the full 4D experiment matrix: Function × Dataset × Baseline × Metrics.
Each dataset is indexed in a separate process (fresh Chroma + graph).
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "data" / "evaluation" / "experiment_matrix.json"
EVAL_DIR = ROOT / "data" / "evaluation"


def run(cmd: list, desc: str) -> int:
    print(f"\n=== {desc} ===")
    print(" ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        print(f"FAILED: {desc} (exit {r.returncode})")
    return r.returncode


def load_matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def ensure_datasets(py: str, specs: list, skip_create: bool) -> int:
    if skip_create:
        return 0
    for spec in specs:
        ds_path = ROOT / spec["path"]
        if (ds_path / "annotations.json").exists():
            continue
        if spec["id"] in ("filekg_main", "code_dependency", "personal_mixed"):
            if run(
                [py, str(ROOT / "scripts" / "create_datasets.py"), "--dataset", spec["id"]],
                f"Create dataset {spec['id']}",
            ) != 0:
                return 1
    if run([py, str(ROOT / "scripts" / "enhance_graph_queries.py")], "Enhance graph queries") != 0:
        return 1
    return 0


def run_dataset(
    py: str,
    spec: dict,
    k: int,
    skip_index: bool,
    ablation: bool,
    robustness: bool,
) -> dict:
    ds_path = ROOT / spec["path"]
    ds_id = spec["id"]
    out_json = EVAL_DIR / f"{ds_id}.json"

    if not ds_path.exists():
        return {"dataset": ds_id, "error": f"missing {ds_path}"}

    if spec.get("index") and not skip_index:
        if run([py, str(ROOT / "scripts" / "run_indexing.py"), str(ds_path)], f"Index {ds_id}") != 0:
            return {"dataset": ds_id, "error": "indexing failed"}

    if spec.get("rebuild_qrels"):
        if run([py, str(ROOT / "scripts" / "rebuild_qrels.py"), str(ds_path)], f"Qrels {ds_id}") != 0:
            return {"dataset": ds_id, "error": "qrels failed"}

    eval_cmd = [
        py, str(ROOT / "scripts" / "run_evaluation.py"), str(ds_path),
        "--output", str(EVAL_DIR), "--output-name", ds_id, "--k", str(k),
    ]
    if ablation and spec.get("ablation"):
        eval_cmd.append("--ablation")
        rels = spec.get("ablation")
        if isinstance(rels, list):
            eval_cmd.extend(["--ablation-relations", *rels])
    if robustness and spec.get("robustness"):
        eval_cmd.append("--robustness")
        eval_cmd.append("--robustness-retrieval")

    if run(eval_cmd, f"Evaluate {ds_id}") != 0:
        return {"dataset": ds_id, "error": "evaluation failed"}

    if out_json.exists():
        return json.loads(out_json.read_text(encoding="utf-8"))
    return {"dataset": ds_id, "error": "no output json"}


def main():
    parser = argparse.ArgumentParser(description="Run full FileKG experiment matrix")
    parser.add_argument("--datasets", nargs="*", help="Subset of dataset ids")
    parser.add_argument("--skip-create", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--no-ablation", action="store_true")
    parser.add_argument("--no-robustness", action="store_true")
    parser.add_argument("--quick", action="store_true", help="Only filekg_main + code_dependency")
    args = parser.parse_args()

    py = sys.executable
    matrix = load_matrix()
    k = matrix.get("k", 20)
    specs = matrix["datasets"]

    if args.quick:
        specs = [s for s in specs if s["id"] in ("filekg_main", "code_dependency")]
    if args.datasets:
        specs = [s for s in specs if s["id"] in args.datasets]

    if ensure_datasets(py, specs, args.skip_create) != 0:
        return 1

    out_path = EVAL_DIR / "experiment_matrix_results.json"
    prev = {}
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "matrix_version": matrix.get("version"),
        "k": k,
        "datasets": dict(prev.get("datasets", {})),
    }

    for spec in specs:
        res = run_dataset(
            py, spec, k,
            skip_index=args.skip_index,
            ablation=not args.no_ablation,
            robustness=not args.no_robustness,
        )
        results["datasets"][spec["id"]] = res

    out_path = EVAL_DIR / "experiment_matrix_results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")

    report_cmd = [py, str(ROOT / "scripts" / "generate_matrix_report.py")]
    run(report_cmd, "Matrix report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
