#!/usr/bin/env python3
"""
运行方案第八章对比实验：多数据集 × 多基线 × 完整指标。

基线:
  BM25 | VectorOnly | Vector+Metadata | Vector+SIMILAR_TO | FileKG-Full

用法:
  python scripts/generate_evaluation_benchmark.py
  python scripts/run_evaluation.py
  python scripts/run_evaluation.py --dataset filekg_main
  python scripts/run_evaluation.py --all
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_registry(name: str = "default") -> list[dict]:
    if name == "real":
        reg_path = ROOT / "data" / "benchmarks" / "registry_real.json"
        if not reg_path.exists():
            raise SystemExit("请先运行: python scripts/download_real_benchmarks.py --all")
    else:
        reg_path = ROOT / "data" / "benchmarks" / "registry.json"
        if not reg_path.exists():
            raise SystemExit("请先运行: python scripts/generate_evaluation_benchmark.py")
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    return reg["datasets"]


def run_one(ds: dict, results_root: Path) -> dict | None:
    ds_path = ROOT / ds["path"].replace("/", os.sep)
    gt_path = ROOT / ds["ground_truth"].replace("/", os.sep)
    if not ds_path.exists() or not gt_path.exists():
        logger.warning("跳过 %s: 路径不存在", ds["id"])
        return None
    queries = json.loads(gt_path.read_text(encoding="utf-8")).get("queries", [])
    if not queries:
        logger.warning("跳过 %s: 无查询", ds["id"])
        return None

    from src.evaluation.runner import run_evaluation

    out = results_root / ds["id"]
    logger.info("=== 评测数据集: %s (%d 查询) ===", ds["name"], len(queries))
    return run_evaluation(ds_path, gt_path, output_dir=out, clear_index=True)


def print_comparison(results_root: Path, summaries: list[tuple[str, dict]]) -> None:
    print("\n" + "=" * 72)
    print("跨数据集对比摘要 (MAP@20 / Recall_indirect@20 / Serendipity@20)")
    print("=" * 72)
    baselines = [
        "BM25",
        "VectorOnly",
        "Vector+Metadata",
        "Vector+SIMILAR_TO",
        "Patent-IFlytek-KG",
        "Patent-Inspur-RAG",
        "Patent-MS-ActionSeq",
        "Patent-Snap-Visual",
        "FileKG-Full",
    ]
    header = f"{'数据集':<18}" + "".join(f"{b[:12]:>14}" for b in baselines)
    print(header)
    print("-" * len(header))
    for ds_id, summary in summaries:
        row = f"{ds_id:<18}"
        for b in baselines:
            m = summary.get("baselines", {}).get(b, {})
            row += f"{m.get('MAP@20', 0):>14.3f}"
        print(row)
    print("\n间接召回 (Recall_indirect@20):")
    for ds_id, summary in summaries:
        parts = [ds_id]
        for b in baselines:
            m = summary.get("baselines", {}).get(b, {})
            parts.append(f"{b}={m.get('Recall_indirect@20', 0):.2f}")
        print("  " + " | ".join(parts))

    comp_path = results_root / "comparison_summary.json"
    comp_path.write_text(
        json.dumps(dict(summaries), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n汇总已保存: {comp_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="filekg_main", help="registry 中的数据集 id")
    parser.add_argument("--all", action="store_true", help="运行所有可用数据集")
    parser.add_argument(
        "--skip-hippocamp",
        action="store_true",
        help="跳过 hippocamp_* 数据集（默认在 registry=real 时不跳过）",
    )
    parser.add_argument(
        "--results-dir",
        default="results_patent_compare",
        help="评测结果子目录名（位于 data/evaluation/）",
    )
    parser.add_argument(
        "--registry",
        choices=("default", "real", "synthetic"),
        default="default",
        help="real=仅真实公开集; synthetic=原 registry.json",
    )
    parser.add_argument(
        "--config",
        default="",
        help="配置文件名或路径，如 config_patent_full.yaml",
    )
    parser.add_argument(
        "--profile",
        choices=("default", "patent_full", "hippocamp_en"),
        default="",
        help="预设环境（覆盖 --config）",
    )
    args = parser.parse_args()
    if args.registry == "synthetic":
        args.registry = "default"

    if args.profile:
        sys.path.insert(0, str(ROOT / "scripts"))
        from patent_env import env_for_profile

        for k, v in env_for_profile(args.profile).items():
            os.environ[k] = v
    elif args.config:
        cfg = Path(args.config)
        os.environ["FILEKG_CONFIG"] = str(cfg if cfg.is_absolute() else ROOT / cfg)
        if "tois" in cfg.stem:
            os.environ["FILEKG_EVAL_PROFILE"] = "tois_eval"
        elif "hippocamp" in cfg.stem:
            os.environ["FILEKG_EVAL_PROFILE"] = "hippocamp_eval"
        elif "paper" in cfg.stem:
            os.environ.setdefault("FILEKG_EVAL_PROFILE", "paper_eval")
        else:
            os.environ.setdefault("FILEKG_EVAL_PROFILE", cfg.stem)

    import importlib

    import src.config as cfg_mod

    importlib.reload(cfg_mod)
    from src.config import reload_settings

    reload_settings()

    from src.indexing.embedder import Embedder

    Embedder.reset()
    emb = Embedder.get()
    logger.info("嵌入后端: %s", emb.backend)
    if emb.backend == "hash":
        logger.error("请使用 .venv 并安装 sentence-transformers 后重试")
        sys.exit(1)

    bench_dir = ROOT / "data" / "benchmarks"
    if args.registry == "default" and not (bench_dir / "filekg_main").exists():
        logger.info("生成合成基准数据...")
        import subprocess

        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "generate_evaluation_benchmark.py")])

    if args.registry == "real":
        args.results_dir = args.results_dir if args.results_dir != "results_patent_compare" else "results_real"

    registry = load_registry(args.registry)
    results_root = ROOT / "data" / "evaluation" / args.results_dir
    summaries: list[tuple[str, dict]] = []

    targets = registry if args.all else [d for d in registry if d["id"] == args.dataset]
    skip_hippo = args.skip_hippocamp
    for ds in targets:
        if skip_hippo and ds["id"].startswith("hippocamp_"):
            continue
        summary = run_one(ds, results_root)
        if summary:
            summaries.append((ds["id"], summary))

    if summaries:
        print_comparison(results_root, summaries)
        _write_final_report(results_root, summaries)


def _write_final_report(results_root: Path, summaries: list[tuple[str, dict]]) -> None:
    lines = [
        "# 对比实验总报告（修正版 v2）\n",
        "\n修正项: 严格文件名匹配 | 标注外置 | Serendipity 仅核心关系 | 报告含 P@20/NDCG\n",
    ]
    for ds_id, s in summaries:
        lines.append(f"## {ds_id}\n")
        lines.append(
            f"- 文件数: {s.get('file_count')}, 查询: {s.get('query_count')}, "
            f"泄漏率: {s.get('query_leakage_ratio', 0):.1%}\n"
        )
        lines.append(
            "| 方法 | MAP@20 | P@20 | R@20 | NDCG@20 | R_indirect | Serendipity* |\n"
        )
        lines.append("|------|--------|------|------|---------|------------|-------------|\n")
        for name, m in s.get("baselines", {}).items():
            lines.append(
                f"| {name} | {m.get('MAP@20', 0):.3f} | {m.get('P@20', 0):.3f} | "
                f"{m.get('R@20', 0):.3f} | {m.get('NDCG@20', 0):.3f} | "
                f"{m.get('Recall_indirect@20', 0):.3f} | {m.get('Serendipity@20', 0):.3f} |\n"
            )
        lines.append("\n")
    lines.append("*Serendipity 不含 IN_FOLDER/SAME_TYPE/NEAR_IN_TIME。\n")
    (results_root / "FINAL_REPORT_CORRECTED.md").write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
