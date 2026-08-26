#!/usr/bin/env python3
"""
TOIS 诚实实验管线：无指标校准、无查询级 rescoring、严格 SDR 定义。

用法:
  python scripts/run_tois_experiments.py
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ["FILEKG_CONFIG"] = str(ROOT / "config_tois_eval.yaml")
os.environ["FILEKG_EVAL_PROFILE"] = "tois_eval"

RESULTS = "results_tois"
CONFIG = "config_tois_eval.yaml"
PY = sys.executable
PAPER = ROOT / "FileKG：基于虚拟文件实体的个人知识图谱与内生可解释检索.docx"
BACKUP = ROOT / "data/evaluation/paper_filled/backups/论文_原始备份.docx"


def reload_settings() -> None:
    import src.config as cfg_mod

    importlib.reload(cfg_mod)
    from src.config import reload_settings as rs

    rs()


def run(cmd: list[str], desc: str) -> None:
    print(f"\n>>> {desc}")
    subprocess.check_call(cmd, cwd=str(ROOT))


def load_metrics(ds: str) -> dict:
    p = ROOT / "data" / "evaluation" / RESULTS / ds / "metrics.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_pb(ds: str) -> dict:
    p = ROOT / "data" / "evaluation" / RESULTS / ds / "paper_baselines.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def validate_tois() -> tuple[bool, list[str]]:
    ok = True
    notes: list[str] = []
    core = {"BM25", "VectorOnly", "Vector+Metadata", "Vector+SIMILAR_TO"}
    map_wins = 0
    sdr_wins = 0

    for ds, label in (
        ("filekg_main", "合成集"),
        ("personal_mixed", "跨场景混合"),
        ("code_dependency", "代码仓库"),
    ):
        m = load_metrics(ds)
        if not m:
            return False, [f"缺少 {ds}/metrics.json"]
        if m.get("eval_profile") != "tois_eval":
            ok = False
            notes.append(f"{label}: eval_profile 非 tois_eval")
        fk = m["baselines"]["FileKG-Full"]
        if fk.get("Serendipity@20_measured") is not None:
            ok = False
            notes.append(f"{label}: 仍存在 SDR 校准字段")

        best = max(core, key=lambda k: m["baselines"].get(k, {}).get("MAP@20", 0))
        best_map = m["baselines"][best]["MAP@20"]
        sim_sdr = m["baselines"].get("Vector+SIMILAR_TO", {}).get("Serendipity@20", 0)
        if fk["MAP@20"] > best_map + 0.001:
            map_wins += 1
            notes.append(f"{label}: MAP {fk['MAP@20']:.3f} > {best} {best_map:.3f} ✓")
        else:
            notes.append(
                f"{label}: MAP {fk['MAP@20']:.3f} vs {best} {best_map:.3f}（与最强核心基线接近）"
            )
        if fk["Serendipity@20"] > sim_sdr + 0.02:
            sdr_wins += 1
            notes.append(
                f"{label}: SDR {fk['Serendipity@20']:.3f} > Vector+SIMILAR_TO {sim_sdr:.3f} ✓"
            )

    if sdr_wins < 2:
        ok = False
        notes.append(f"SDR 领先数据集 {sdr_wins}/3（TOIS 主贡献需 ≥2/3）")
    else:
        notes.append(f"SDR 领先 {sdr_wins}/3 — 可作为 TOIS 主实验结论")

    pm = load_metrics("personal_mixed")
    pb = load_pb("personal_mixed")
    if pm and pb:
        fk = pm["baselines"]["FileKG-Full"]["MAP@20"]
        path = pb.get("Multi-Rel (Path-based)", {}).get("MAP@20", 0)
        lift = (fk - path) / path * 100 if path else 0
        notes.append(f"VFE 增益（实测）: {lift:+.1f}%")
        if lift < 1.0:
            ok = False

    rob = ROOT / "data" / "evaluation" / RESULTS / "robustness.json"
    if rob.exists():
        retention = json.loads(rob.read_text()).get("volume_file_id", {}).get("relation_retention_rate", 0)
        if retention >= 0.95:
            notes.append(f"关系保持率 {retention:.1%} ✓")
        else:
            ok = False

    ab_path = ROOT / "data" / "evaluation" / RESULTS / "ablation.json"
    if ab_path.exists():
        ab = json.loads(ab_path.read_text(encoding="utf-8"))
        if ab.get("eval_profile") != "tois_eval":
            ok = False
            notes.append("消融实验非 tois_eval profile")
        else:
            notes.append("消融实验为实测值（无比例校准）✓")

    return ok, notes


def main() -> int:
    reload_settings()
    run([PY, str(ROOT / "scripts/generate_evaluation_benchmark.py"), "--scale", "small"], "生成基准")
    run([PY, str(ROOT / "scripts/inject_benchmark_behavior.py")], "注入行为日志")
    run(
        [
            PY,
            str(ROOT / "scripts/run_evaluation.py"),
            "--all",
            "--results-dir",
            RESULTS,
            "--config",
            CONFIG,
        ],
        "主评测（TOIS 诚实 profile）",
    )
    run([PY, str(ROOT / "scripts/run_ablation.py"), "--results-dir", RESULTS, "--config", CONFIG], "消融")
    run([PY, str(ROOT / "scripts/run_robustness.py"), "--results-dir", RESULTS], "鲁棒性")
    run([PY, str(ROOT / "scripts/run_relation_audit.py"), "--results-dir", RESULTS], "关系审计")
    run(
        [PY, str(ROOT / "scripts/run_paper_experiments.py"), "--skip-eval", "--results-dir", RESULTS, "--config", CONFIG],
        "扩展实验+聚合",
    )
    run([PY, str(ROOT / "scripts/generate_tois_statistics.py"), "--results-dir", RESULTS], "TOIS 统计")

    if BACKUP.exists():
        shutil.copy2(BACKUP, PAPER)
    run(
        [PY, str(ROOT / "scripts/fill_paper_placeholders.py"), "--results-dir", RESULTS, "--profile", "tois"],
        "填充表格（实测值）",
    )
    run([PY, str(ROOT / "scripts/sync_tois_prose.py"), "--results-dir", RESULTS], "同步 TOIS 正文表述")

    filled = ROOT / "data/evaluation/paper_filled/FileKG_论文_实验数据已填入.docx"
    if filled.exists():
        shutil.copy2(filled, PAPER)

    ok, notes = validate_tois()
    print("\n=== TOIS 诚实性检查 ===")
    for n in notes:
        print(" ", n)
    if ok:
        print("\n✓ TOIS 实验管线完成，论文已用实测数据填充。")
        return 0
    print("\n⚠ 部分 TOIS 检查未通过，请根据上述说明调整正文表述。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
