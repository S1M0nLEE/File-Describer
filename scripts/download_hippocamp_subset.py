#!/usr/bin/env python3
"""
下载 HippoCamp Adam-Subset 并转换为 FileKG 评测格式。

来源: https://huggingface.co/datasets/MMMem-org/HippoCamp
- 158 个真实个人文件，18 条 QA（subset）
- 用于补充「真实个人文件系统」对比（与合成数据对照）

需要: pip install huggingface_hub
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "benchmarks" / "hippocamp_adam"
REPO = "MMMem-org/HippoCamp"
JSON_REL = "Adam/Subset/Adam_Subset.json"
FILES_PREFIX = "Adam/Subset/Adam_Subset"


def _load_hf_env() -> None:
    """加载 .env 中的 HF_ENDPOINT（国内镜像），须在 import huggingface_hub 之前。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key.startswith("HF_") and key not in os.environ:
            os.environ[key] = val


def _collect_subset_paths(items: list) -> set[str]:
    rel_paths: set[str] = set()
    for item in items:
        top = item.get("file_path")
        if isinstance(top, list):
            rel_paths.update(str(x).replace("\\", "/") for x in top)
        elif isinstance(top, str) and top.strip():
            rel_paths.add(top.replace("\\", "/"))
        for ev in item.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            fp = ev.get("file_path") or ev.get("path") or ""
            if fp:
                rel_paths.add(str(fp).replace("\\", "/"))
    return rel_paths


def _download_files(rel_paths: set[str], cache: Path, files_dir: Path) -> int:
    from huggingface_hub import hf_hub_download

    files_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    for rel in sorted(rel_paths):
        hf_rel = f"{FILES_PREFIX}/{rel}"
        try:
            hf_hub_download(
                repo_id=REPO,
                repo_type="dataset",
                filename=hf_rel,
                local_dir=str(cache),
            )
            src = cache / FILES_PREFIX / rel
            dst = files_dir / Path(rel).name
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
            ok += 1
        except Exception as e:
            print(f"[WARN] 跳过 {rel}: {e}")
    return ok


def main() -> None:
    _load_hf_env()
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("请先安装: pip install huggingface_hub")
        sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "hf_cache"
    print("下载 HippoCamp Adam Subset 标注 (JSON)...")
    json_path = hf_hub_download(
        repo_id=REPO,
        repo_type="dataset",
        filename=JSON_REL,
        local_dir=str(cache),
    )
    qa = json.loads(Path(json_path).read_text(encoding="utf-8"))

    items = qa if isinstance(qa, list) else qa.get("data", qa.get("questions", []))
    subset_items = items[:18]
    rel_paths = _collect_subset_paths(subset_items)
    print(f"下载 Adam Subset 原始文件（{len(rel_paths)} 个，逐文件经 HF 镜像）...")
    files_dir = OUT / "files"
    n_ok = _download_files(rel_paths, cache, files_dir)
    if n_ok == 0:
        print("将仅生成基于 QA 的 ground_truth（需手动放置文件到 data/benchmarks/hippocamp_adam/files）")

    from src.evaluation.hippocamp_qrels import extract_hippocamp_files, split_direct_indirect

    queries = []
    for item in subset_items:
        question = item.get("question") or item.get("query") or item.get("q", "")
        if not question:
            continue
        direct, indirect = split_direct_indirect(item, max_direct=3)
        queries.append(
            {
                "q": question,
                "direct": direct,
                "indirect": indirect,
                "source_id": item.get("id", ""),
            }
        )

    gt = {
        "dataset": "hippocamp_adam",
        "description": "HippoCamp Adam-Subset 适配（真实个人文件 QA）",
        "source": REPO,
        "queries": queries[:18],
    }
    annot = ROOT / "data" / "benchmarks" / "annotations" / "hippocamp_adam.json"
    annot.parent.mkdir(parents=True, exist_ok=True)
    annot.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {len(gt['queries'])} 条查询 -> {OUT / 'ground_truth.json'}")
    if files_dir.exists():
        n = sum(1 for _ in files_dir.rglob("*") if _.is_file())
        print(f"原始文件: {n} 个 -> {files_dir}")


if __name__ == "__main__":
    main()
