from __future__ import annotations

import json
from pathlib import Path

from src.behavior.prefixspan import mine_frequent_adjacent_pairs, mine_frequent_subsequences
from src.config import settings
from src.models.descriptor import FileDescriptor
from src.relations.base import RelationEdge, RelationParser
from typing import Any as Neo4jStore


class WorkflowParser(RelationParser):
    """从本地行为日志挖掘 WORKFLOW_WITH 关系。"""

    name = "workflow"

    def discover(
        self, descriptors: list[FileDescriptor], store: Neo4jStore
    ) -> list[RelationEdge]:
        if settings.patent_visual_only:
            return []
        log_path = Path("data/workflow_log.jsonl")
        if not log_path.exists():
            return []

        path_to_id = {d.path: d.file_id for d in descriptors}
        sequences: list[list[str]] = []
        current: list[str] = []

        with log_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    fid = path_to_id.get(entry.get("path", ""))
                    if not fid:
                        continue
                    if entry.get("event") == "session_end":
                        if len(current) >= 2:
                            sequences.append(current)
                        current = []
                    else:
                        if not current or current[-1] != fid:
                            current.append(fid)
                except json.JSONDecodeError:
                    continue
        if len(current) >= 2:
            sequences.append(current)

        min_sup = settings.workflow_min_support
        pair_count = mine_frequent_adjacent_pairs(sequences, min_support=min_sup)
        long_patterns = mine_frequent_subsequences(sequences, min_support=min_sup, max_len=4)

        edges: list[RelationEdge] = []
        for (a, b), support in pair_count.items():
            edges.append(
                RelationEdge(
                    a,
                    "WORKFLOW_WITH",
                    b,
                    weight=0.6,
                    props={"support": support, "miner": "prefixspan_adjacent"},
                )
            )
        for pattern, support in long_patterns:
            if len(pattern) < 3:
                continue
            for i in range(len(pattern) - 1):
                edges.append(
                    RelationEdge(
                        pattern[i],
                        "WORKFLOW_WITH",
                        pattern[i + 1],
                        weight=0.55,
                        props={"support": support, "pattern_len": len(pattern)},
                    )
                )
        return edges
