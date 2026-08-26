#!/usr/bin/env python3
"""
专利「全功能实施例」补强流水线：可复现配置 + 关系审计 + 真实/合成评测 + 文档刷新。

用法:
  python scripts/run_patent_embodiment.py --quick     # 约 1h：合成集 + hippocamp_adam
  python scripts/run_patent_embodiment.py --full      # 含三档案 HippoCamp（耗时长）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd: list[str], label: str, *, env: dict | None = None) -> None:
    print(f"\n{'=' * 60}\n>>> {label}\n{'=' * 60}")
    subprocess.check_call(cmd, cwd=str(ROOT), env=env)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true", help="合成 filekg_main + hippocamp_adam（英文配置）")
    p.add_argument("--full", action="store_true", help="quick + 三档案 HippoCamp")
    p.add_argument("--skip-eval", action="store_true")
    args = p.parse_args()
    if not args.quick and not args.full:
        args.quick = True

    scripts = ROOT / "scripts"
    patent_dir = ROOT / "data" / "evaluation" / "patent"
    patent_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(scripts))
    from patent_env import env_for_profile

    if not args.skip_eval:
        run(
            [
                PY,
                str(scripts / "run_evaluation.py"),
                "--dataset",
                "filekg_main",
                "--config",
                "config_patent_full.yaml",
                "--results-dir",
                "results_patent_embodiment",
            ],
            "合成集 · 全功能配置 (patent_full)",
            env=env_for_profile("patent_full"),
        )

        hippocamp_ids = ["hippocamp_adam"]
        if args.full:
            hippocamp_ids = ["hippocamp_adam", "hippocamp_bei", "hippocamp_victoria"]

        for ds_id in hippocamp_ids:
            run(
                [
                    PY,
                    str(scripts / "run_evaluation.py"),
                    "--registry",
                    "real",
                    "--dataset",
                    ds_id,
                    "--profile",
                    "hippocamp_en",
                    "--results-dir",
                    "results_patent_embodiment",
                ],
                f"真实集 · {ds_id} (hippocamp_en)",
                env=env_for_profile("hippocamp_en"),
            )

    run(
        [
            PY,
            str(scripts / "run_relation_audit.py"),
            "--dataset",
            "filekg_main",
            "--sample",
            "50",
            "--results-dir",
            "results_patent_embodiment",
        ],
        "关系构建精度审计（规则 Oracle）",
    )
    run(
        [PY, str(scripts / "export_relation_audit_template.py"), "--target", "300"],
        "导出 300 条人工复核模板",
    )
    emb_dir = ROOT / "data" / "evaluation" / "results_patent_embodiment"
    if any(emb_dir.glob("*/metrics.json")):
        run(
            [
                PY,
                str(scripts / "generate_real_comparison_report.py"),
                "--results-root",
                "results_patent_embodiment",
                "--real-only",
            ],
            "刷新实施例对比报告",
        )
    run([PY, str(scripts / "generate_patent_package.py")], "生成专利文档包（claim chart / 附图）")

    print("\n完成。专利补强产物:")
    print(f"  实施例评测: data/evaluation/results_patent_embodiment/")
    print(f"  文档包: data/evaluation/patent/")
    print(f"  人工关系模板: data/evaluation/relation_human_audit_template.jsonl")


if __name__ == "__main__":
    main()
