from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from src.models.descriptor import FileDescriptor
from src.relations.base import RelationEdge, RelationParser
from typing import Any as Neo4jStore


class MetadataRelationsParser(RelationParser):
    """IN_FOLDER, SAME_TYPE, NEAR_IN_TIME, BELONGS_TO_PROJECT"""

    name = "metadata"

    def discover(
        self, descriptors: list[FileDescriptor], store: Neo4jStore
    ) -> list[RelationEdge]:
        edges: list[RelationEdge] = []
        by_folder: dict[str, list[FileDescriptor]] = defaultdict(list)
        by_ext: dict[str, list[FileDescriptor]] = defaultdict(list)
        by_project: dict[str, list[FileDescriptor]] = defaultdict(list)

        for d in descriptors:
            if d.is_inside_archive:
                continue
            path_norm = d.path.replace("\\", "/").lower()
            if "/noise/" in path_norm:
                continue
            folder = str(Path(d.path).parent)
            by_folder[folder].append(d)
            by_ext[d.extension].append(d)
            if d.project_id:
                by_project[d.project_id].append(d)

        max_folder_clique = 25
        for folder, files in by_folder.items():
            if len(files) < 2:
                continue
            ordered = sorted(files, key=lambda d: d.name)
            if len(ordered) > max_folder_clique:
                for k in range(len(ordered) - 1):
                    a, b = ordered[k], ordered[k + 1]
                    edges.append(
                        RelationEdge(a.file_id, "IN_FOLDER", b.file_id, weight=0.7, symmetric=True)
                    )
            else:
                for i, a in enumerate(ordered):
                    for b in ordered[i + 1 :]:
                        edges.append(
                            RelationEdge(
                                a.file_id, "IN_FOLDER", b.file_id, weight=0.7, symmetric=True
                            )
                        )

        for ext, files in by_ext.items():
            if not ext or len(files) < 2:
                continue
            for i, a in enumerate(files[:50]):
                for b in files[i + 1 : min(i + 6, len(files))]:
                    edges.append(
                        RelationEdge(
                            a.file_id, "SAME_TYPE", b.file_id, weight=0.4, symmetric=True
                        )
                    )

        for pid, files in by_project.items():
            for i, a in enumerate(files):
                for b in files[i + 1 :]:
                    edges.append(
                        RelationEdge(
                            a.file_id,
                            "BELONGS_TO_PROJECT",
                            b.file_id,
                            weight=0.5,
                            symmetric=True,
                            props={"project_id": pid},
                        )
                    )

        edges.extend(self._near_in_time(descriptors))
        return edges

    def _near_in_time(self, descriptors: list[FileDescriptor]) -> list[RelationEdge]:
        from src.config import settings

        window = timedelta(minutes=settings.near_time_window_minutes)
        max_pairs = settings.near_time_max_pairs
        sorted_files = sorted(descriptors, key=lambda d: d.modified_time)
        edges: list[RelationEdge] = []
        i = 0
        while i < len(sorted_files):
            window_files = [sorted_files[i]]
            j = i + 1
            while j < len(sorted_files):
                if sorted_files[j].modified_time - sorted_files[i].modified_time <= window:
                    window_files.append(sorted_files[j])
                    j += 1
                else:
                    break

            if len(window_files) >= 2:
                if len(window_files) > max_pairs:
                    for k in range(len(window_files) - 1):
                        a, b = window_files[k], window_files[k + 1]
                        edges.append(
                            RelationEdge(
                                a.file_id, "NEAR_IN_TIME", b.file_id, weight=0.5, symmetric=True
                            )
                        )
                else:
                    for x in range(len(window_files)):
                        for y in range(x + 1, len(window_files)):
                            edges.append(
                                RelationEdge(
                                    window_files[x].file_id,
                                    "NEAR_IN_TIME",
                                    window_files[y].file_id,
                                    weight=0.5,
                                    symmetric=True,
                                )
                            )
            i = j if j > i + 1 else i + 1
        return edges
