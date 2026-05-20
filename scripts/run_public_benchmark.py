#!/usr/bin/env python3
"""
Full public benchmark: build -> index -> semantic qrels -> evaluate -> report.
Uses separate processes for index/eval to avoid Chroma stale collection handles.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list, desc: str) -> int:
    print(f"\n=== {desc} ===")
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        print(f"FAILED: {desc} (exit {r.returncode})")
    return r.returncode


def main():
    parser = argparse.ArgumentParser(description="Public dataset benchmark pipeline")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--skip-qrels", action="store_true")
    parser.add_argument("--ablation", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    dataset = ROOT / "data" / "datasets" / "filekg_main_public"
    eval_dir = ROOT / "data" / "evaluation"

    if not args.skip_build:
        build_cmd = [py, str(ROOT / "scripts" / "build_filekg_main.py"), "--output", str(dataset)]
        if args.quick:
            build_cmd.append("--quick")
        if run(build_cmd, "Build public dataset") != 0:
            return 1

    if not args.skip_index:
        if run([py, str(ROOT / "scripts" / "run_indexing.py"), str(dataset)], "Index (new process)") != 0:
            return 1

    if not args.skip_qrels:
        if run([py, str(ROOT / "scripts" / "rebuild_qrels.py"), str(dataset)], "Semantic qrels") != 0:
            return 1

    eval_cmd = [py, str(ROOT / "scripts" / "run_evaluation.py"), str(dataset), "--output", str(eval_dir)]
    if args.ablation:
        eval_cmd.append("--ablation")
    if run(eval_cmd, "Evaluate (new process)") != 0:
        return 1

    src = eval_dir / "experiment_data.json"
    dst = eval_dir / "experiment_data_public.json"
    if src.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    run([py, str(ROOT / "scripts" / "generate_paper_report.py")], "Paper report")
    print(json.dumps({
        "dataset": str(dataset),
        "evaluation": str(dst),
        "report": str(eval_dir / "paper_report.md"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
