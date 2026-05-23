#!/usr/bin/env python3
"""
专利举证用完整实验流水线（从零跑通）。

步骤:
  1. 生成基准数据
  2. 多数据集 × 多基线评测
  3. 关系消融
  4. 关系质量审计
  5. 文件移动鲁棒性
  6. 导出 experiment_data.json
  7. 生成 EXPERIMENT_REPORT.md
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd: list[str], label: str) -> None:
    print(f"\n{'=' * 60}\n>>> {label}\n{'=' * 60}")
    subprocess.check_call(cmd, cwd=str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-benchmark", action="store_true", help="跳过基准生成")
    parser.add_argument("--skip-eval", action="store_true", help="跳过主评测（耗时）")
    parser.add_argument("--quick", action="store_true", help="仅 filekg_main + 少量移动文件")
    args = parser.parse_args()

    scripts = ROOT / "scripts"
    if not args.skip_benchmark:
        run([PY, str(scripts / "generate_evaluation_benchmark.py")], "生成基准数据")

    if not args.skip_eval:
        run([PY, str(scripts / "run_evaluation.py"), "--all"], "多数据集对比评测")

    run([PY, str(scripts / "run_ablation.py")], "关系消融")
    run(
        [PY, str(scripts / "run_relation_audit.py"), "--dataset", "filekg_main"],
        "关系质量审计",
    )

    robust_cmd = [PY, str(scripts / "run_robustness.py"), "--dataset", "filekg_main"]
    if args.quick:
        robust_cmd += ["--max-move", "5"]
    run(robust_cmd, "鲁棒性（file_id vs path）")

    run([PY, str(scripts / "export_experiment_data.py")], "导出 experiment_data.json")
    run([PY, str(scripts / "generate_experiment_report.py")], "生成实验报告")
    run([PY, str(scripts / "generate_prior_art_comparison.py")], "生成现有技术对比")

    print(f"\n完成。")
    print(f"  实验报告: {ROOT / 'data' / 'evaluation' / 'EXPERIMENT_REPORT.md'}")
    print(f"  技术对比: {ROOT / 'data' / 'evaluation' / 'PRIOR_ART_COMPARISON.md'}")


if __name__ == "__main__":
    main()
