from __future__ import annotations

import logging
from pathlib import Path

from src.indexing.scanner import scan_directory
from src.relations.pipeline import RelationDiscoveryPipeline
from src.storage.chroma_store import ChromaStore
from src.storage.factory import GraphStore, create_stores

logger = logging.getLogger(__name__)


class IndexBuilder:
    def __init__(
        self,
        neo4j: GraphStore | None = None,
        chroma: ChromaStore | None = None,
        *,
        id_mode: str = "volume",
    ):
        if neo4j is None or chroma is None:
            g, c = create_stores()
            neo4j = neo4j or g
            chroma = chroma or c
        self.neo4j = neo4j
        self.chroma = chroma
        self.pipeline = RelationDiscoveryPipeline()
        self._id_mode = id_mode
        self._resume_cache: dict[str, dict[str, str]] = {}

    def build(
        self,
        root: str | Path,
        *,
        clear: bool = False,
        max_files: int | None = None,
        project_map: dict[str, str] | None = None,
        resume: bool = False,
        skip_relations: bool = False,
        lightweight: bool = False,
    ) -> dict:
        root = Path(root)
        if clear:
            logger.info("清空索引...")
            self.neo4j.clear_all()
            self.chroma.clear_all()

        fast = __import__("os").environ.get("FILEKG_INDEX_FAST", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if fast:
            descriptors = self._scan_and_upsert_incremental(
                root,
                max_files=max_files,
                project_map=project_map,
                resume=resume,
            )
        else:
            logger.info("扫描目录: %s", root)
            descriptors = scan_directory(
                root,
                max_files=max_files,
                project_map=project_map,
                id_mode=getattr(self, "_id_mode", "volume"),
            )
            logger.info("发现 %d 个文件", len(descriptors))
            for d in descriptors:
                self.neo4j.upsert_file(d)
                if d.file_embedding:
                    self.chroma.upsert_file(d)
            if hasattr(self.neo4j, "flush"):
                self.neo4j.flush()

        scan_stats = getattr(self, "_last_scan_stats", None) or {}
        if lightweight:
            return {
                "root": str(root),
                "file_count": len(descriptors),
                **scan_stats,
            }

        stats: dict[str, int] = {}
        if not skip_relations and descriptors:
            stats = self.pipeline.run(descriptors, self.neo4j)
            if hasattr(self.neo4j, "flush"):
                self.neo4j.flush()

        from src.indexing.access_memory import AccessMemory
        from src.indexing.consistency import ConsistencyChecker
        from src.indexing.lifecycle import LifecycleManager

        lifecycle_stats = LifecycleManager(self.neo4j).run()
        access_stats = AccessMemory(self.neo4j).adjust_relation_weights_from_logs()
        consistency_stats = ConsistencyChecker(self.neo4j, self.chroma).run()

        return {
            "root": str(root),
            "file_count": len(descriptors),
            "relation_stats": stats,
            "lifecycle": lifecycle_stats,
            "access_weight_updates": access_stats,
            "consistency": consistency_stats,
            **scan_stats,
        }

    def _load_resume_index(self, root: Path) -> dict[str, str]:
        key = str(root.resolve())
        if key in self._resume_cache:
            return self._resume_cache[key]
        if hasattr(self.neo4j, "indexed_mtime_by_path"):
            self._resume_cache[key] = self.neo4j.indexed_mtime_by_path(root)
            return self._resume_cache[key]
        out: dict[str, str] = {}
        if hasattr(self.neo4j, "list_all_files"):
            root = root.resolve()
            for rec in self.neo4j.list_all_files():
                p = rec.get("path")
                if not p:
                    continue
                try:
                    resolved = Path(p).resolve()
                    if resolved.is_relative_to(root):
                        out[str(resolved)] = str(rec.get("modified_time") or "")
                except (OSError, ValueError):
                    continue
        self._resume_cache[key] = out
        return out

    def _scan_and_upsert_incremental(
        self,
        root: Path,
        *,
        max_files: int | None,
        project_map: dict[str, str] | None,
        resume: bool = False,
    ) -> list:
        from datetime import datetime

        from src.indexing.scanner import (
            SKIP_DIRS,
            SKIP_DIR_NAMES,
            SKIP_EXTENSIONS,
            SKIP_FILENAMES,
            build_descriptor,
        )

        root = Path(root).resolve()
        resume_index = self._load_resume_index(root) if resume else {}
        if resume:
            logger.info(
                "断点续传: %s（已有 %d 条，将跳过未变更文件）",
                root,
                len(resume_index),
            )
        else:
            logger.info("快速索引（边扫边写）: %s", root)
        descriptors: list = []
        count = 0
        skipped = 0
        updated = 0
        for path in root.rglob("*"):
            if max_files and count >= max_files:
                break
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name in SKIP_FILENAMES:
                continue
            if path.suffix.lower() in SKIP_EXTENSIONS:
                continue
            try:
                resolved = path.resolve()
                if resume and str(resolved) in resume_index:
                    try:
                        old_ts = datetime.fromisoformat(
                            resume_index[str(resolved)]
                        ).timestamp()
                        new_ts = path.stat().st_mtime
                        if abs(old_ts - new_ts) < 1.0:
                            skipped += 1
                            continue
                    except (OSError, ValueError, TypeError):
                        pass
                    updated += 1
                desc = build_descriptor(
                    path,
                    project_map=project_map,
                    id_mode=self._id_mode,
                )
            except (OSError, PermissionError) as e:
                logger.debug("跳过 %s: %s", path, e)
                continue
            self.neo4j.upsert_file(desc)
            if desc.file_embedding:
                self.chroma.upsert_file(desc)
            descriptors.append(desc)
            count += 1
            if count % 500 == 0:
                logger.info("  已写入 %d 个文件…", count)
                if hasattr(self.neo4j, "flush"):
                    self.neo4j.flush()
        logger.info(
            "本目录写入 %d 个文件（跳过 %d，更新 %d）",
            len(descriptors),
            skipped,
            updated,
        )
        self._last_scan_stats = {
            "indexed_new": len(descriptors),
            "skipped_unchanged": skipped,
            "updated": updated,
        }
        if hasattr(self.neo4j, "flush"):
            self.neo4j.flush()
        return descriptors

    def index_single(self, path: str | Path) -> None:
        from src.indexing.scanner import build_descriptor

        path = Path(path)
        desc = build_descriptor(path, id_mode=self._id_mode)
        self.neo4j.upsert_file(desc)
        self.chroma.upsert_file(desc)
        self.pipeline.run([desc], self.neo4j)
        if hasattr(self.neo4j, "flush"):
            self.neo4j.flush()

    def relocate_file(self, old_path: str | Path, new_path: str | Path) -> str:
        """移动后增量更新：保持 volume file_id，更新图与向量元数据。"""
        from src.indexing.file_id import get_file_id
        from src.indexing.scanner import build_descriptor

        old_path = Path(old_path)
        new_path = Path(new_path)
        if not new_path.exists():
            raise FileNotFoundError(new_path)

        if self._id_mode == "path":
            self.neo4j.delete_file(get_file_id(old_path, mode="path"))
            self.chroma.delete_file(get_file_id(old_path, mode="path"))
            self.index_single(new_path)
            return get_file_id(new_path, mode="path")

        fid = get_file_id(new_path, mode="volume")
        desc = build_descriptor(new_path, id_mode="volume")
        desc.file_id = fid
        self.neo4j.update_path(fid, str(new_path.resolve()), new_path.name)
        self.chroma.upsert_file(desc)
        if hasattr(self.neo4j, "flush"):
            self.neo4j.flush()
        return fid
