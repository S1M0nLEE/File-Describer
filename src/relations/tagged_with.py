"""TAGGED_WITH relation from filename tags or sidecar metadata."""

import json
import re
from pathlib import Path
from typing import Dict, List, Set

from src.models.file_descriptor import FileDescriptor
from src.models.graph_entities import Tag
from src.relations.base import RelationExtractor

TAG_IN_NAME = re.compile(r"#([\w\-]+)")
TAGS_FILE = ".filekg_tags.json"


class TaggedWithExtractor(RelationExtractor):
    relation_type = "TAGGED_WITH"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        sidecar: Dict[str, List[str]] = {}
        for f in file_nodes:
            if f.name == TAGS_FILE:
                folder = str(Path(f.path).parent).replace("\\", "/")
                try:
                    data = json.loads(f.content_text or "{}")
                    sidecar[folder] = data.get("tags", {}).get("files", {})
                except json.JSONDecodeError:
                    pass

        edges = []
        for f in file_nodes:
            tags: Set[str] = set()
            tags.update(m.group(1) for m in TAG_IN_NAME.finditer(f.name))
            folder = str(Path(f.path).parent).replace("\\", "/")
            if folder in sidecar:
                rel = str(Path(f.path).relative_to(folder)).replace("\\", "/")
                file_tags = sidecar[folder].get(rel) or sidecar[folder].get(f.name)
                if file_tags:
                    tags.update(file_tags if isinstance(file_tags, list) else [file_tags])

            for tname in tags:
                tid = Tag.generate_id(tname)
                edges.append((f.id, tid, "TAGGED_WITH", {"tag": tname}))
        return edges

    @staticmethod
    def tag_nodes(file_nodes: List[FileDescriptor]) -> List[Tag]:
        extractor = TaggedWithExtractor()
        edges = extractor.discover(file_nodes)
        tags = {}
        for _, tid, _, props in edges:
            tname = props.get("tag", tid)
            tags[tid] = Tag(id=tid, name=tname)
        return list(tags.values())
