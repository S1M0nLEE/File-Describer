from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.config import settings
from src.models.descriptor import FileStatus
from src.storage.factory import GraphStore

logger = logging.getLogger(__name__)

ARCHIVE_DIR_NAMES = {"archive", "archived", "归档", "backup_archive"}


class LifecycleManager:
    """方案 4.1.2：ACTIVE/DORMANT/ARCHIVED/DEPRECATED 状态迁移。"""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def run(self, *, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now()
        stats = {"dormant": 0, "archived": 0, "deprecated": 0, "active": 0}
        workflow_nodes = self._workflow_key_nodes()
        deprecated_candidates = self._previous_version_targets()

        for fid, node in self._iter_files():
            status = node.get("status", FileStatus.ACTIVE.value)
            path = node.get("path") or ""

            if self._is_archive_path(path):
                if status != FileStatus.ARCHIVED.value:
                    self._set_status(fid, FileStatus.ARCHIVED)
                    stats["archived"] += 1
                continue

            if fid in deprecated_candidates:
                dep_at = deprecated_candidates[fid]
                if now >= dep_at and status not in (
                    FileStatus.DEPRECATED.value,
                    FileStatus.ARCHIVED.value,
                ):
                    self._set_status(fid, FileStatus.DEPRECATED)
                    stats["deprecated"] += 1
                continue

            if status == FileStatus.DORMANT.value:
                continue

            last_hit = self._last_access(node)
            dormant_cutoff = now - timedelta(days=settings.dormant_days)
            if last_hit and last_hit < dormant_cutoff and fid not in workflow_nodes:
                self._set_status(fid, FileStatus.DORMANT)
                stats["dormant"] += 1
            elif status == FileStatus.DORMANT.value and last_hit and last_hit >= dormant_cutoff:
                self._set_status(fid, FileStatus.ACTIVE)
                stats["active"] += 1

        return stats

    def _iter_files(self):
        if hasattr(self.store, "_nodes"):
            return list(self.store._nodes.items())
        return [(f["file_id"], f) for f in self.store.list_all_files()]

    def _set_status(self, fid: str, status: FileStatus) -> None:
        if hasattr(self.store, "_nodes") and fid in self.store._nodes:
            self.store._nodes[fid]["status"] = status.value
        elif hasattr(self.store, "set_file_status"):
            self.store.set_file_status(fid, status.value)

    def _is_archive_path(self, path: str) -> bool:
        parts = {p.lower() for p in Path(path).parts}
        return bool(parts & ARCHIVE_DIR_NAMES)

    def _last_access(self, node: dict) -> datetime | None:
        logs = node.get("access_log") or []
        if logs:
            try:
                last = logs[-1]
                ts = last.get("hit_at") if isinstance(last, dict) else getattr(last, "hit_at", None)
                if ts:
                    return datetime.fromisoformat(str(ts))
            except Exception:
                pass
        la = node.get("last_accessed")
        if la:
            try:
                return datetime.fromisoformat(str(la))
            except Exception:
                pass
        try:
            return datetime.fromisoformat(node.get("modified_time", ""))
        except Exception:
            return None

    def _workflow_key_nodes(self) -> set[str]:
        key: set[str] = set()
        edges = getattr(self.store, "_edges", [])
        for e in edges:
            if e.get("type") == "WORKFLOW_WITH":
                key.add(e["src"])
                key.add(e["dst"])
        return key

    def _previous_version_targets(self) -> dict[str, datetime]:
        """被 IS_PREVIOUS_VERSION_OF 指向的旧版本，观察 M 天后 DEPRECATED。"""
        obs = timedelta(days=settings.deprecated_observation_days)
        now = datetime.now()
        targets: dict[str, datetime] = {}
        edges = getattr(self.store, "_edges", [])
        for e in edges:
            if e.get("type") != "IS_PREVIOUS_VERSION_OF":
                continue
            old_id = e["src"]
            mod = self.store.get_file(old_id) or {}
            try:
                base = datetime.fromisoformat(mod.get("modified_time", ""))
            except Exception:
                base = now
            targets[old_id] = max(targets.get(old_id, base), base) + obs
        return targets
