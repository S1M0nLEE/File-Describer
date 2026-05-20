#!/usr/bin/env python3
"""Download HippoCamp Adam subset (placeholder + instructions)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HIPPOCAMP_INFO = {
    "name": "HippoCamp Adam",
    "source": "https://huggingface.co/datasets/chenghao-tan/HippoCamp",
    "subset": "adam",
    "note": "Manual download may be required due to dataset license.",
}


def download_with_hf(target: Path) -> bool:
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id="chenghao-tan/HippoCamp",
            repo_type="dataset",
            local_dir=str(target),
            allow_patterns=["adam/**"],
        )
        return True
    except Exception as e:
        print(f"HuggingFace download failed: {e}")
        return False


def create_stub(target: Path):
    target.mkdir(parents=True, exist_ok=True)
    readme = target / "README.txt"
    readme.write_text(
        "HippoCamp Adam subset placeholder.\n"
        "Install huggingface_hub and run with --use-hf to download.\n"
        f"Source: {HIPPOCAMP_INFO['source']}\n",
        encoding="utf-8",
    )
    anno = {
        "dataset": "hippocamp_adam",
        "relations": [],
        "queries": [
            {"id": "h1", "query": "meeting notes", "relevant": []},
        ],
        "file_count": 0,
        "stub": True,
    }
    (target / "annotations.json").write_text(json.dumps(anno, indent=2), encoding="utf-8")
    print(f"Created stub at {target}")


def main():
    parser = argparse.ArgumentParser(description="Download HippoCamp dataset")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "datasets" / "hippocamp_adam")
    parser.add_argument("--use-hf", action="store_true", help="Try HuggingFace hub download")
    args = parser.parse_args()

    meta_path = args.output / "dataset_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(HIPPOCAMP_INFO, indent=2), encoding="utf-8")

    if args.use_hf and download_with_hf(args.output):
        print(f"Downloaded to {args.output}")
    else:
        create_stub(args.output)
        print("Use: pip install huggingface_hub && python scripts/download_hippocamp.py --use-hf")


if __name__ == "__main__":
    main()
