#!/usr/bin/env python3
"""预下载并验证嵌入模型，确保检索可用。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 减少 Windows 符号链接警告
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def main() -> None:
    from src.config import settings
    from src.indexing.embedder import Embedder

    print("=" * 50)
    print("模型配置检查")
    print(f"  目标模型: {settings.embedding_model}")
    print(f"  后端策略: {settings.embedding_backend}")
    print("=" * 50)

    Embedder.reset()
    emb = Embedder.get()
    vec = emb.embed("这是一段用于验证模型加载的中文测试文本。")
    print(f"\n[OK] 后端: {emb.backend}")
    print(f"[OK] 向量维度: {len(vec)} (配置 {settings.embedding_dim})")
    print(f"[OK] 向量范数: {(sum(x*x for x in vec))**0.5:.4f} (归一化应≈1)")

    v2 = emb.embed("实验数据可视化 notebook")
    sim = Embedder.cosine(vec, v2)
    print(f"[OK] 试算相似度: {sim:.4f}")

    if emb.backend == "hash":
        print("\n[WARN] 当前为哈希占位向量，请安装依赖后重试:")
        print("  .venv\\Scripts\\pip install sentence-transformers")
        print("  或: pip install fastembed")
        sys.exit(1)

    print("\n模型已就绪，可执行索引与检索。")


if __name__ == "__main__":
    main()
