#!/usr/bin/env python3
"""Add graph-focused queries (indirect targets) to code_dependency annotations."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.file_descriptor import FileDescriptor


def main():
    base = ROOT / "data" / "datasets" / "code_dependency"
    anno_path = base / "annotations.json"
    if not anno_path.exists():
        print("Run: python scripts/create_datasets.py --dataset code_dependency")
        return 1

    anno = json.loads(anno_path.read_text(encoding="utf-8"))
    queries = anno.get("queries", [])

    graph_queries = [
        {
            "id": "g_dep_1",
            "query": "entry point imports service layer",
            "relevant": [str((base / "app/main.py").resolve()).replace("\\", "/")],
            "indirect": [
                str((base / "app/service.py").resolve()).replace("\\", "/"),
                str((base / "app/db.py").resolve()).replace("\\", "/"),
                str((base / "app/config.py").resolve()).replace("\\", "/"),
            ],
            "eval_focus": "graph",
        },
        {
            "id": "g_dep_2",
            "query": "frontend module dependency chain",
            "relevant": [str((base / "web/index.js").resolve()).replace("\\", "/")],
            "indirect": [str((base / "web/api.js").resolve()).replace("\\", "/")],
            "eval_focus": "graph",
        },
    ]

    existing = {q["id"] for q in queries}
    for gq in graph_queries:
        if gq["id"] not in existing:
            queries.append(gq)

    anno["queries"] = queries
    anno_path.write_text(json.dumps(anno, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "queries.json").write_text(
        json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Updated {anno_path} with {len(queries)} queries ({len(graph_queries)} graph-focused)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
