#!/usr/bin/env python3
"""端到端调试：模型 → 索引 → 检索。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

QUERIES = [
    ("处理实验数据的代码", ["data_visualization", "data_processing", "实验数据"]),
    ("项目A的论文最新版本", ["论文", "终稿"]),
    ("账单备份", ["账单", "backup"]),
]


def main() -> int:
    from src.indexing.builder import IndexBuilder
    from src.indexing.embedder import Embedder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_stores

    dataset = ROOT / "data" / "dataset"
    if not dataset.exists():
        print("缺少数据集，先运行: python scripts/generate_dataset.py")
        return 1

    Embedder.reset()
    emb = Embedder.get()
    print(f"[1/4] 嵌入后端: {emb.backend}, dim={emb.dimension}")

    print("[2/4] 重建索引...")
    builder = IndexBuilder()
    builder.build(dataset, clear=True)

    print("[3/4] 检索测试...")
    graph, chroma = create_stores()
    engine = SearchEngine(graph, chroma)
    passed = 0
    for q, keywords in QUERIES:
        r = engine.search(q)
        names = [x["name"].lower() for x in r["results"][:5]]
        hit = any(any(kw in n for kw in keywords) for n in names)
        top = r["results"][0]["name"] if r["results"] else "(无)"
        status = "PASS" if hit else "FAIL"
        if hit:
            passed += 1
        print(f"  [{status}] {q}")
        print(f"         Top1: {top}")
        for i, x in enumerate(r["results"][:3], 1):
            print(f"         {i}. {x['name']} (score={x['score']})")

    graph.close()
    print(f"\n[4/4] 通过 {passed}/{len(QUERIES)} 条查询")
    return 0 if passed >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
