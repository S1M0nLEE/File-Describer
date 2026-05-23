#!/usr/bin/env python3
"""
从 registry_real + results_real（及可选 results_patent_compare）生成对比报告。
仅引用磁盘上 metrics.json 中的数值；缺失一律标「数据缺失」。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_REAL = ROOT / "data" / "benchmarks" / "registry_real.json"
RESULTS_REAL_DEFAULT = ROOT / "data" / "evaluation" / "results_real"
RESULTS_SYNTH = ROOT / "data" / "evaluation" / "results_patent_compare"
OUT_MD = ROOT / "data" / "evaluation" / "REAL_COMPARISON_REPORT.md"
OUT_JSON = ROOT / "data" / "evaluation" / "real_comparison_summary.json"

METHODS = [
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
METRICS = [
    "MAP@20",
    "NDCG@20",
    "R@20",
    "Recall_indirect@20",
    "GraphDiscovery@20",
    "Serendipity@20",
    "Explainability@20",
]
PATENTS = [
    "Patent-IFlytek-KG",
    "Patent-Inspur-RAG",
    "Patent-MS-ActionSeq",
    "Patent-Snap-Visual",
]
FILEKG = "FileKG-Full"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _load_metrics(results_root: Path, ds_id: str) -> tuple[dict | None, dict]:
    p = results_root / ds_id / "metrics.json"
    meta = {
        "path": str(p.relative_to(ROOT)).replace("\\", "/"),
        "exists": p.is_file(),
        "sha256_prefix": _sha256(p) if p.is_file() else None,
    }
    if not p.is_file():
        return None, meta
    return json.loads(p.read_text(encoding="utf-8")), meta


def _fmt(v: object) -> str:
    if isinstance(v, (int, float)):
        return f"{v:.4f}"
    return "数据缺失"


def _compare_patent(summary: dict) -> tuple[int, int, list[str], list[str]]:
    baselines = summary.get("baselines", {})
    fk = baselines.get(FILEKG, {})
    wins, losses, win_lines, loss_lines = 0, 0, [], []
    for patent in PATENTS:
        pb = baselines.get(patent, {})
        for m in METRICS[:4]:
            fv, pv = fk.get(m), pb.get(m)
            if not isinstance(fv, (int, float)) or not isinstance(pv, (int, float)):
                continue
            tag = f"{patent} | {m}"
            if fv >= pv - 1e-9:
                wins += 1
                win_lines.append(f"{tag}: FileKG {fv:.4f} >= {pv:.4f}")
            else:
                losses += 1
                loss_lines.append(f"{tag}: FileKG {fv:.4f} < {pv:.4f}")
    return wins, losses, win_lines, loss_lines


def _dataset_table(results_root: Path, datasets: list[dict]) -> list[str]:
    lines = [
        "| 数据集 | 文件数 | 查询数 | 评测状态 | metrics 指纹 |",
        "|--------|--------|--------|----------|--------------|",
    ]
    for ds in datasets:
        ds_id = ds["id"]
        m, meta = _load_metrics(results_root, ds_id)
        status = "已评测" if m else "数据缺失"
        fc = m.get("file_count") if m else ds.get("file_count", "—")
        qc = m.get("query_count") if m else ds.get("queries", "—")
        fp = meta.get("sha256_prefix") or "—"
        lines.append(f"| `{ds_id}` | {fc} | {qc} | {status} | `{fp}` |")
    return lines


def _metrics_matrix(results_root: Path, ds_id: str) -> list[str]:
    m, _ = _load_metrics(results_root, ds_id)
    if not m:
        return [f"### `{ds_id}`", "", "（数据缺失：未找到 metrics.json）", ""]
    baselines = m.get("baselines", {})
    lines = [
        f"### `{ds_id}`",
        "",
        f"- 索引耗时: {m.get('index_time_sec', '数据缺失')} s",
        f"- 匹配协议: `{m.get('matching', '数据缺失')}`",
        f"- 指标版本: `{m.get('metrics_version', '数据缺失')}`",
        "",
        "| 方法 | MAP@20 | NDCG@20 | R@20 | R_indirect@20 | GraphDisc@20 | Serendipity@20 | Explain@20 | 延迟 ms |",
        "|------|--------|---------|------|---------------|--------------|----------------|------------|---------|",
    ]
    for method in METHODS:
        vals = baselines.get(method, {})
        lines.append(
            "| "
            + " | ".join(
                [
                    method,
                    _fmt(vals.get("MAP@20")),
                    _fmt(vals.get("NDCG@20")),
                    _fmt(vals.get("R@20")),
                    _fmt(vals.get("Recall_indirect@20")),
                    _fmt(vals.get("GraphDiscovery@20")),
                    _fmt(vals.get("Serendipity@20")),
                    _fmt(vals.get("Explainability@20")),
                    _fmt(vals.get("latency_ms_avg")),
                ]
            )
            + " |"
        )
    w, l, _, loss_lines = _compare_patent(m)
    lines += ["", f"**相对专利代理基线**：胜 {w} 项 / 负 {l} 项（MAP/NDCG/R/R_indirect）"]
    if loss_lines:
        lines.append("")
        lines.append("<details><summary>未领先项</summary>")
        lines.extend(f"- {x}" for x in loss_lines[:30])
        lines.append("</details>")
    lines.append("")
    return lines


def build_report(*, include_synthetic: bool, results_real: Path) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    real_reg = json.loads(REGISTRY_REAL.read_text(encoding="utf-8"))
    real_datasets = real_reg.get("datasets", [])
    agg = real_reg.get("aggregate", {})

    summary_pkg: dict = {
        "generated_at_utc": now,
        "results_real": str(results_real.relative_to(ROOT)).replace("\\", "/"),
        "registry_real": str(REGISTRY_REAL.relative_to(ROOT)).replace("\\", "/"),
        "aggregate_registry": agg,
        "datasets": {},
        "patent_compare_totals": {"wins": 0, "losses": 0},
    }

    lines = [
        "# FileKG 真实公开集 vs 基线/专利代理 — 对比报告",
        "",
        f"> **生成时间 (UTC)**：`{now}`",
        f"> **真实集结果目录**：`{results_real.relative_to(ROOT).as_posix()}/`（仅引用该目录下 `metrics.json`）",
        f"> **注册表**：`data/benchmarks/registry_real.json`",
        "",
        "## 数据真实性声明",
        "",
        "1. 本报告所有数值均来自 `run_evaluation.py --registry real` 产出的 `metrics.json`，未手工填写。",
        "2. 未跑评测的数据集在表中标注 **数据缺失**，不会用估算值替代。",
        "3. 「专利-*」列为**同基准上的代理实现**（`patent_baselines.py`），**不是**各专利说明书中的官方实验表。",
        "4. 合成回归集（`results_patent_compare`）与真实公开集分开存放，避免混淆。",
        "",
        "## 1. 真实数据集规模（registry）",
        "",
        f"- 数据集数：{agg.get('datasets', len(real_datasets))}",
        f"- 登记文件总数：{agg.get('files', '—')}",
        f"- 登记查询总数：{agg.get('queries', '—')}",
        f"- 论文对标说明：{agg.get('target_paper', '—')}",
        "",
        "## 2. 评测覆盖",
        "",
    ]
    lines.extend(_dataset_table(results_real, real_datasets))
    lines += ["", "## 3. 分数据集指标（真实集）", ""]

    total_w, total_l = 0, 0
    for ds in real_datasets:
        ds_id = ds["id"]
        m, meta = _load_metrics(results_real, ds_id)
        summary_pkg["datasets"][ds_id] = {
            "metrics_meta": meta,
            "evaluated": m is not None,
        }
        if m:
            w, l, _, _ = _compare_patent(m)
            total_w += w
            total_l += l
            summary_pkg["datasets"][ds_id]["metrics"] = {
                name: m.get("baselines", {}).get(FILEKG, {}).get(k)
                for k in METRICS
                for name in [FILEKG]
            }
            summary_pkg["datasets"][ds_id]["patent_wins"] = w
            summary_pkg["datasets"][ds_id]["patent_losses"] = l
        lines.extend(_metrics_matrix(results_real, ds_id))

    summary_pkg["patent_compare_totals"] = {"wins": total_w, "losses": total_l}
    lines += [
        "## 4. 专利代理对比汇总（真实集）",
        "",
        f"**合计**：胜 {total_w} 项 / 负 {total_l} 项（跨已评测数据集 × 4 专利 × 4 核心指标）",
        "",
    ]

    if include_synthetic:
        synth_ids = ["filekg_main", "code_dependency", "personal_mixed"]
        lines += ["## 5. 合成回归集（results_patent_compare）", ""]
        sw, sl = 0, 0
        for ds_id in synth_ids:
            m, meta = _load_metrics(RESULTS_SYNTH, ds_id)
            summary_pkg.setdefault("synthetic", {})[ds_id] = {"metrics_meta": meta, "evaluated": m is not None}
            if m:
                w, l, _, _ = _compare_patent(m)
                sw += w
                sl += l
            lines.extend(_metrics_matrix(RESULTS_SYNTH, ds_id))
        lines += [f"**合成集专利对比合计**：胜 {sw} 项 / 负 {sl} 项", ""]
        summary_pkg["synthetic_patent_totals"] = {"wins": sw, "losses": sl}

    lines += [
        "## 6. 复现命令",
        "",
        "```bash",
        "python scripts/download_real_benchmarks.py --scale paper",
        "python scripts/run_evaluation.py --registry real --all --results-dir results_real",
        "python scripts/generate_real_comparison_report.py",
        "```",
        "",
    ]

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(summary_pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_pkg


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--include-synthetic", action="store_true", default=True)
    p.add_argument("--real-only", action="store_true")
    p.add_argument(
        "--results-root",
        default="results_real",
        help="真实集 metrics 目录名（位于 data/evaluation/）",
    )
    args = p.parse_args()
    include_synth = args.include_synthetic and not args.real_only
    results_real = ROOT / "data" / "evaluation" / args.results_root
    pkg = build_report(include_synthetic=include_synth, results_real=results_real)
    n_ok = sum(1 for d in pkg["datasets"].values() if d.get("evaluated"))
    print(f"已写入: {OUT_MD}")
    print(f"已写入: {OUT_JSON}")
    print(f"真实集已评测: {n_ok}/{len(pkg['datasets'])}")


if __name__ == "__main__":
    main()
