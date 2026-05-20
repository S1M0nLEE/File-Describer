#!/usr/bin/env python3
"""Run offline indexing pipeline."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_config
from src.pipeline.graph_builder import GraphBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Build FileKG index")
    parser.add_argument("dataset_path", type=Path, help="Root directory to index")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear existing graph/chroma")
    parser.add_argument(
        "--relations",
        nargs="*",
        help="Only enable these relation types (default: all)",
    )
    args = parser.parse_args()

    cfg = get_config()
    enabled = set(args.relations) if args.relations else None
    builder = GraphBuilder(cfg, enabled_relations=enabled)
    try:
        builder.build_full(args.dataset_path.resolve(), clear=not args.no_clear)
        print(f"Indexing complete: {args.dataset_path}")
    finally:
        builder.close()


if __name__ == "__main__":
    main()
