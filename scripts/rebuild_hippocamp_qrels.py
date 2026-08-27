#!/usr/bin/env python3
"""从本地 hf_cache 重建 HippoCamp 标注（direct/indirect 拆分 + 可选补下载缺失文件）。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPO = "MMMem-org/HippoCamp"
BASE_URL = "https://hf-mirror.com/datasets/MMMem-org/HippoCamp/resolve/main/Adam/Fullset/Adam"


def _find_adam_json(profile: str = "adam") -> Path:
    prof = profile.capitalize()
    candidates = [
        ROOT / f"data/benchmarks/hippocamp_{profile}/hf_cache_full/{prof}/Fullset/{prof}.json",
        ROOT / f"data/benchmarks/hippocamp_{profile}/hf_cache/{prof}/Fullset/{prof}.json",
        ROOT / f"data/benchmarks/hippocamp_{profile}/hf_cache/{prof}/Subset/{prof}_Subset.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise SystemExit(f"未找到 {prof} 标注 JSON，请先下载 HippoCamp {profile} Fullset/Subset")


def _collect_rel_paths(items: list) -> set[str]:
    from src.evaluation.hippocamp_qrels import extract_hippocamp_files

    rel: set[str] = set()
    for item in items:
        top = item.get("file_path")
        if isinstance(top, list):
            rel.update(str(x).replace("\\", "/") for x in top)
        elif isinstance(top, str) and top.strip():
            rel.add(top.replace("\\", "/"))
        for ev in item.get("evidence") or []:
            if isinstance(ev, dict):
                fp = ev.get("file_path") or ev.get("path") or ""
                if fp:
                    rel.add(str(fp).replace("\\", "/"))
        for name in extract_hippocamp_files(item):
            rel.add(name)
    return rel


def _download_missing(rel_paths: set[str], files_dir: Path, raw_dir: Path) -> int:
    ok = 0
    for rel in sorted(rel_paths):
        flat = files_dir / Path(rel).name
        if flat.exists() and flat.stat().st_size > 0:
            continue
        encoded = "/".join(quote(part, safe="") for part in rel.split("/"))
        url = f"{BASE_URL}/{encoded}"
        dest = raw_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["curl", "-fsSL", "--retry", "2", "-o", str(dest), url],
            capture_output=True,
        )
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            shutil.copy2(dest, flat)
            ok += 1
            print(f"  补下载: {Path(rel).name}")
    return ok


def rebuild(profile: str = "adam", *, download_missing: bool = False) -> None:
    from src.evaluation.hippocamp_qrels import split_direct_indirect

    json_path = _find_adam_json(profile)
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("data", raw.get("questions", []))

    out_id = f"hippocamp_{profile}"
    bench = ROOT / "data" / "benchmarks" / out_id
    files_dir = bench / "files"
    annot_path = ROOT / "data" / "benchmarks" / "annotations" / f"{out_id}.json"

    if download_missing and files_dir.exists():
        rel_paths = _collect_rel_paths(items)
        n = _download_missing(rel_paths, files_dir, bench / "hf_raw")
        print(f"补下载完成: {n} 个新文件")

    queries = []
    for item in items:
        q = item.get("question") or item.get("query") or item.get("q", "")
        if not q:
            continue
        direct, indirect = split_direct_indirect(item)
        queries.append(
            {
                "q": q,
                "direct": direct,
                "indirect": indirect,
                "source_id": str(item.get("id", "")),
            }
        )

    gt = {
        "dataset": out_id,
        "description": f"HippoCamp 真实个人文件 ({profile}, Fullset)",
        "source": REPO,
        "queries": queries,
        "queries_with_file_gt": sum(1 for x in queries if x["direct"]),
        "queries_with_indirect_gt": sum(1 for x in queries if x["indirect"]),
    }
    annot_path.parent.mkdir(parents=True, exist_ok=True)
    annot_path.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")

    n_files = sum(1 for p in files_dir.rglob("*") if p.is_file()) if files_dir.exists() else 0
    n_ind = sum(len(q["indirect"]) for q in queries)
    print(f"已写入 {annot_path}")
    print(f"  查询: {len(queries)}, indirect 标注: {n_ind} ({gt['queries_with_indirect_gt']} 条查询)")
    print(f"  文件目录: {n_files} 个 -> {files_dir}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="adam", choices=["adam", "bei", "victoria"])
    p.add_argument("--download-missing", action="store_true")
    args = p.parse_args()
    rebuild(args.profile, download_missing=args.download_missing)


if __name__ == "__main__":
    main()
