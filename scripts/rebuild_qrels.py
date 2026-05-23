#!/usr/bin/env python3
"""Rebuild semantic qrels after indexing (uses files_cache embeddings)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_config
from src.evaluation.semantic_qrels import update_dataset_annotations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dataset_path",
        type=Path,
        default=ROOT / "data" / "datasets" / "filekg_main_public",
    )
    args = parser.parse_args()
    stats = update_dataset_annotations(args.dataset_path.resolve(), get_config())
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
