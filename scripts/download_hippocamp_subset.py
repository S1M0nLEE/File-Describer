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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "benchmarks" / "hippocamp_adam"
REPO = "MMMem-org/HippoCamp"


def main() -> None:
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        print("请先安装: pip install huggingface_hub")
        sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    print("下载 HippoCamp Adam Subset 标注 (JSON)...")
    json_path = hf_hub_download(
        repo_id=REPO,
        repo_type="dataset",
        filename="Adam/Subset/Adam_Subset.json",
        local_dir=str(OUT / "hf_cache"),
    )
    qa = json.loads(Path(json_path).read_text(encoding="utf-8"))

    print("下载 Adam Subset 原始文件（约 158 个，可能需要几分钟）...")
    files_dir = OUT / "files"
    try:
        snapshot_download(
            repo_id=REPO,
            repo_type="dataset",
            allow_patterns=["Adam/Subset/Adam_Subset/**"],
            local_dir=str(OUT / "hf_cache"),
        )
        src = OUT / "hf_cache" / "Adam" / "Subset" / "Adam_Subset"
        if src.exists():
            import shutil

            if files_dir.exists():
                shutil.rmtree(files_dir)
            shutil.copytree(src, files_dir)
    except Exception as e:
        print(f"[WARN] 文件下载失败: {e}")
        print("将仅生成基于 QA 的 ground_truth（需手动放置文件到 data/benchmarks/hippocamp_adam/files）")

    queries = []
    items = qa if isinstance(qa, list) else qa.get("data", qa.get("questions", []))
    for item in items:
        question = item.get("question") or item.get("query") or item.get("q", "")
        if not question:
            continue
        evidence = item.get("evidence") or item.get("file") or item.get("files") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        files = []
        for ev in evidence:
            if isinstance(ev, dict):
                files.append(ev.get("file_name") or ev.get("path", ""))
            else:
                files.append(str(ev))
        files = [Path(f).name for f in files if f]
        queries.append(
            {
                "q": question,
                "direct": files[:3],
                "indirect": files[3:6],
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
