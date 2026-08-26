#!/usr/bin/env python3
"""[已废弃] 请改用 scripts/index_directory.py。"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

warnings.warn(
    "scripts/run_indexing.py 已废弃，请使用 scripts/index_directory.py",
    DeprecationWarning,
    stacklevel=1,
)

from src.indexing.builder import IndexBuilder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="[废弃] 索引目录到知识图谱")
    parser.add_argument("path", help="要索引的根目录")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--max-files", type=int, default=None)
    args = parser.parse_args()

    builder = IndexBuilder()
    result = builder.build(args.path, clear=args.clear, max_files=args.max_files)
    print("完成:", result)


if __name__ == "__main__":
    main()
