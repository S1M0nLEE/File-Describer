#!/usr/bin/env python3
"""将 paper_experiment_data.json 中的实测值同步到论文 docx 正文硬编码数字。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "FileKG：基于虚拟文件实体的个人知识图谱与内生可解释检索.docx"
DATA = ROOT / "data" / "evaluation" / "paper_experiment_data.json"


def _load_data(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _vfe_lift(data: dict) -> float:
    pm = data.get("datasets", {}).get("personal_mixed", {}).get("baselines", {})
    pb = data.get("paper_baselines", {}).get("personal_mixed", {})
    fk = pm.get("FileKG-Full", {}).get("MAP@20", 0)
    path = pb.get("Multi-Rel (Path-based)", {}).get("MAP@20", 0)
    return (fk - path) / path * 100 if path else 0.0


def _personal_sdr(data: dict) -> float:
    return (
        data.get("datasets", {})
        .get("personal_mixed", {})
        .get("baselines", {})
        .get("FileKG-Full", {})
        .get("Serendipity@20", 0.0)
    )


def _cold_early_map(data: dict) -> float:
    stages = data.get("cold_start", {}).get("stages", [])
    for s in stages:
        if s.get("stage") == "0-50":
            return float(s.get("MAP@20", 0.451))
    return 0.451


def _meta_early_map(data: dict) -> float:
    return (
        data.get("datasets", {})
        .get("personal_mixed", {})
        .get("baselines", {})
        .get("Vector+Metadata", {})
        .get("MAP@20", 0.421)
    )


def _ablation_drops(data: dict) -> tuple[float, float]:
    ab = {a["variant"]: a for a in data.get("ablation", {}).get("ablations", [])}
    full = ab.get("完整方案", {})
    no_sim = ab.get("禁用 SIMILAR_TO", {})
    no_wf = ab.get("禁用 WORKFLOW_WITH", {})
    f_map = full.get("MAP@20", 0) or 1e-9
    f_sdr = full.get("Serendipity@20", 0) or 1e-9
    map_drop = (f_map - no_sim.get("MAP@20", f_map)) / f_map * 100
    sdr_drop = (f_sdr - no_wf.get("Serendipity@20", f_sdr)) / f_sdr * 100
    return map_drop, sdr_drop


def build_replacements(data: dict) -> list[tuple[str, str]]:
    lift = _vfe_lift(data)
    sdr = _personal_sdr(data)
    cold_fk = _cold_early_map(data)
    cold_meta = _meta_early_map(data)
    map_drop, sdr_drop = _ablation_drops(data)

    return [
        (r"15\.2\s*%", f"{lift:.1f}%"),
        (r"15\.2%", f"{lift:.1f}%"),
        (r"SDR@20\s*[=为]\s*0\.39", f"SDR@20 为 {_fmt(sdr)}"),
        (r"SDR@20达到0\.39", f"SDR@20达到{_fmt(sdr)}"),
        (r"SDR@20 达到 0\.39", f"SDR@20 达到 {_fmt(sdr)}"),
        (r"意外发现率.*?0\.39", f"意外发现率（SDR@20）达到{_fmt(sdr)}"),
        (r"0\.451.*?0\.421", f"{_fmt(cold_fk)}，显著高于 BM25\\+Meta 的 {_fmt(cold_meta)}"),
        (r"MAP@20.*?0\.451", f"MAP@20 为 {_fmt(cold_fk)}"),
        (r"14\.5\s*%", f"{map_drop:.1f}%"),
        (r"14\.5%", f"{map_drop:.1f}%"),
        (r"38\.5\s*%", f"{sdr_drop:.1f}%"),
        (r"38\.5%", f"{sdr_drop:.1f}%"),
    ]


def _fmt(v: float, digits: int = 3) -> str:
    return f"{v:.{digits}f}"


def sync_docx(docx_path: Path, data: dict, *, out_path: Path | None = None) -> int:
    if not docx_path.exists():
        raise FileNotFoundError(docx_path)
    reps = build_replacements(data)
    target = out_path or docx_path
    tmp = target.with_suffix(".sync.tmp.docx")
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
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    data = _load_data(args.data)
    if not data:
        print(f"缺少数据: {args.data}")
        return 1
    count = sync_docx(args.docx, data, out_path=args.out)
    print(f"正文同步替换 {count} 处 -> {args.out or args.docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
