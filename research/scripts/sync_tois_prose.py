#!/usr/bin/env python3
"""将 TOIS 实测统计同步到论文 docx 正文（改写过强声称）。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "FileKG：基于虚拟文件实体的个人知识图谱与内生可解释检索.docx"


def _load_stats(results_dir: str) -> dict:
    p = ROOT / "data" / "evaluation" / results_dir / "tois_statistics.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _fmt(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}"


def build_replacements(stats: dict) -> list[tuple[str, str]]:
    vfe = stats.get("vfe", {})
    lift = vfe.get("lift_pct", 0)
    sdr = stats.get("datasets", {}).get("personal_mixed", {}).get("filekg_sdr", 0)
    code = stats.get("datasets", {}).get("code_dependency", {})
    syn = stats.get("datasets", {}).get("filekg_main", {})
    ab_sim = stats.get("ablation_deltas", {}).get("similar_to", {})
    ab_wf = stats.get("ablation_deltas", {}).get("workflow_with", {})

    code_p = code.get("statistical_test", {}).get("p_value")
    p_text = _fmt(code_p, 3) if code_p is not None else "0.22"

    reps: list[tuple[str, str]] = [
        (r"15\.2\s*%", f"{lift:.1f}%"),
        (r"15\.2%", f"{lift:.1f}%"),
        (r"提升\s*15\.2\s*%", f"提升 {lift:.1f}%"),
        (r"SDR@20\s*[=为]\s*0\.39", f"SDR@20 为 {_fmt(sdr, 3)}"),
        (r"SDR@20达到0\.39", f"SDR@20达到{_fmt(sdr, 3)}"),
        (r"SDR@20 达到 0\.39", f"SDR@20 达到 {_fmt(sdr, 3)}"),
        (r"意外发现率.*?0\.39", f"意外发现率（SDR@20）为 {_fmt(sdr, 3)}"),
        (r"14\.5\s*%", f"{ab_sim.get('map_drop_pct', 0):.1f}%"),
        (r"14\.5%", f"{ab_sim.get('map_drop_pct', 0):.1f}%"),
        (r"38\.5\s*%", f"{ab_wf.get('sdr_drop_pct', 0):.1f}%"),
        (r"38\.5%", f"{ab_wf.get('sdr_drop_pct', 0):.1f}%"),
        (r"p\s*[<＜]\s*0\.01", f"p={p_text}"),
        (r"p\s*[<＜]\s*0\.05", f"p={p_text}"),
        (r"全面显著优于所有基线", "在 SDR 与可解释路径发现上优于纯向量基线；MAP 与 Vector+SIMILAR_TO 接近"),
        (
            r"显著优于所有对比基线",
            "在意外发现率（SDR）上 consistently 更高；MAP 增益有限且统计不显著",
        ),
        (r"24\s*名", "N/A（用户研究待开展）"),
        (r"24名", "N/A（用户研究待开展）"),
        (r"SUS\s*[=为]\s*82\.5", "SUS（待用户研究）"),
        (r"三位志愿者", "三个查询子集（跨场景混合基准）"),
    ]
    return reps


def sync_docx(docx_path: Path, stats: dict, *, out_path: Path | None = None) -> int:
    reps = build_replacements(stats)
    target = out_path or docx_path
    tmp = target.with_suffix(".tois.tmp.docx")
    n = 0
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = raw.decode("utf-8")
                for pat, repl in reps:
                    text, c = re.subn(pat, repl, text)
                    n += c
                raw = text.encode("utf-8")
            zout.writestr(item, raw)
    shutil.move(tmp, target)
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", type=Path, default=PAPER)
    parser.add_argument("--results-dir", default="results_tois")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    stats = _load_stats(args.results_dir)
    if not stats:
        print(f"缺少 {args.results_dir}/tois_statistics.json，请先运行 generate_tois_statistics.py")
        return 1
    count = sync_docx(args.docx, stats, out_path=args.out)
    print(f"TOIS 正文同步 {count} 处 -> {args.out or args.docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
