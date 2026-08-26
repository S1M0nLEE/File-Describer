from __future__ import annotations

import re
from collections import defaultdict
from typing import Any as Neo4jStore

from src.indexing.embedder import Embedder
from src.models.descriptor import FileDescriptor
from src.relations.base import RelationEdge, RelationParser


def _strip_md_wrapper(name: str) -> str:
    """论文_v1.docx.md -> 论文_v1.docx"""
    n = name
    while n.lower().endswith(".md") and n.count(".") >= 2:
        n = n[: -3]
    return n


VERSION_RE = re.compile(r"^(.+)_v(\d+)(\.[^.]+)$", re.IGNORECASE)
VERSION_SUFFIX_RE = re.compile(
    r"^(.+?)[_\-]?(改|修订|final|终稿|修改|v\d+)(\.[^.]+)?$", re.IGNORECASE
)
STEM_VERSION_RE = re.compile(r"^(.+?)[_\-]v(\d+)$", re.IGNORECASE)


class VersionRelationsParser(RelationParser):
    name = "version"

    def discover(
        self, descriptors: list[FileDescriptor], store: Neo4jStore
    ) -> list[RelationEdge]:
        edges: list[RelationEdge] = []
        groups: dict[str, list[tuple[int, FileDescriptor]]] = defaultdict(list)

        for d in descriptors:
            if "/noise/" in d.path.replace("\\", "/").lower():
                continue
            logical = _strip_md_wrapper(d.name)
            m = VERSION_RE.match(logical)
            if m:
                base, ver, _ = m.group(1), int(m.group(2)), m.group(3)
                groups[base.lower()].append((ver, d))
                continue
            stem = logical.rsplit(".", 1)[0] if "." in logical else logical
            sm = STEM_VERSION_RE.match(stem)
            if sm:
                groups[sm.group(1).lower()].append((int(sm.group(2)), d))
                continue
            m2 = VERSION_SUFFIX_RE.match(logical) or VERSION_SUFFIX_RE.match(stem)
            if m2:
                base = m2.group(1).lower()
                groups[base].append((100 if "终稿" in logical or "final" in logical.lower() else 50, d))

        for base, items in groups.items():
            items.sort(key=lambda x: x[0])
            by_ver: dict[int, list[FileDescriptor]] = defaultdict(list)
            for ver, d in items:
                by_ver[ver].append(d)
            for ver, variants in by_ver.items():
                if len(variants) > 1:
                    for i in range(len(variants)):
                        for j in range(i + 1, len(variants)):
                            edges.append(
                                RelationEdge(
                                    variants[i].file_id,
                                    "VERSION_VARIANT",
                                    variants[j].file_id,
                                    weight=0.5,
                                    symmetric=True,
                                    props={"version": ver, "confidence": 0.85},
                                )
                            )
            for i in range(len(items) - 1):
                old_d = items[i][1]
                new_d = items[i + 1][1]
                edges.append(
                    RelationEdge(old_d.file_id, "IS_PREVIOUS_VERSION_OF", new_d.file_id, weight=0.8)
                )
                edges.append(
                    RelationEdge(new_d.file_id, "HAS_VERSION", old_d.file_id, weight=0.3)
                )

        edges.extend(self._semantic_version_guess(descriptors))
        return edges

    def _semantic_version_guess(
        self, descriptors: list[FileDescriptor]
    ) -> list[RelationEdge]:
        embedder = Embedder.get()
        edges: list[RelationEdge] = []
        by_stem: dict[str, list[FileDescriptor]] = defaultdict(list)

        for d in descriptors:
            stem = d.name.rsplit(".", 1)[0].lower()
            stem = re.sub(r"[_\-]?(改|修订|final|终稿|修改)$", "", stem)
            by_stem[stem[:20]].append(d)

        for _, group in by_stem.items():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i + 1 :]:
                    if not a.file_embedding or not b.file_embedding:
                        continue
                    sim = embedder.cosine(a.file_embedding, b.file_embedding)
                    if sim > 0.92:
                        older, newer = (
                            (a, b) if a.modified_time <= b.modified_time else (b, a)
                        )
                        edges.append(
                            RelationEdge(
                                older.file_id,
                                "IS_PREVIOUS_VERSION_OF",
                                newer.file_id,
                                weight=0.6,
                                props={"confidence": sim, "inferred": True},
                            )
                        )
        return edges
