from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


class AccessMemory:
    """方案 4.1.3：access_log 记录与关系权重个性化强化。"""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def record_hit(
        self,
        file_id: str,
        query: str,
        *,
        relation_type: str | None = None,
    ) -> None:
        entry = {
            "query_hash": query_hash(query),
            "relation_type": relation_type,
            "hit_at": datetime.utcnow().isoformat(),
        }
        node = self.store.get_file(file_id)
        if not node:
            return
        logs: list[dict] = list(node.get("access_log") or [])
        logs.append(entry)
        logs = logs[-200:]
        updates = {"access_log": logs, "last_accessed": entry["hit_at"]}
        self._patch_node(file_id, updates, flush=False)

    def personalized_boost(self, node: dict) -> float:
        logs = node.get("access_log") or []
        if not logs:
            return 0.0
        recent = logs[-20:]
        return min(0.35, 0.02 * len(recent) + 0.05 * sum(1 for e in recent if e.get("relation_type")))

    def adjust_relation_weights_from_logs(self) -> int:
        """统计 SIMILAR_TO / IN_FOLDER 等路径使用频率，微调边 weight。"""
        rel_hits: dict[tuple[str, str, str], int] = defaultdict(int)
        for fid, node in self._iter_nodes():
            for entry in node.get("access_log") or []:
                rt = entry.get("relation_type")
                if not rt:
                    continue
                rel_hits[(fid, rt, entry.get("query_hash", ""))] += 1

        updated = 0
        edges = getattr(self.store, "_edges", None)
        if edges is None:
            return 0
        for e in edges:
            rt = e.get("type")
            if rt not in ("SIMILAR_TO", "IN_FOLDER", "WORKFLOW_WITH"):
                continue
            usage = rel_hits.get((e["src"], rt, ""), 0) + rel_hits.get((e["dst"], rt, ""), 0)
            if usage >= 3:
                e["weight"] = min(1.0, float(e.get("weight", 0.5)) + 0.05 * min(usage, 5))
                updated += 1
        if updated and hasattr(self.store, "flush"):
            self.store.flush()
        return updated

    def _patch_node(self, file_id: str, updates: dict[str, Any], *, flush: bool = False) -> None:
        if hasattr(self.store, "_nodes") and file_id in self.store._nodes:
            self.store._nodes[file_id].update(updates)
            if flush and hasattr(self.store, "flush"):
                self.store.flush()
        elif hasattr(self.store, "patch_file"):
            self.store.patch_file(file_id, updates)

    def _iter_nodes(self):
        if hasattr(self.store, "_nodes"):
            return self.store._nodes.items()
        return ((f["file_id"], f) for f in self.store.list_all_files())
