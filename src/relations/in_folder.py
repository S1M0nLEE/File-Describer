"""IN_FOLDER relation: file -> folder."""

from pathlib import Path
from typing import Any, Dict, List

from src.models.file_descriptor import FileDescriptor
from src.models.graph_entities import Folder
from src.relations.base import RelationExtractor


class InFolderExtractor(RelationExtractor):
    relation_type = "IN_FOLDER"

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        edges = []
        seen_folders = set()
        for f in file_nodes:
            parent = str(Path(f.path).parent).replace("\\", "/")
            folder_id = Folder.generate_id(parent)
            if folder_id not in seen_folders:
                seen_folders.add(folder_id)
            edges.append((f.id, folder_id, "IN_FOLDER", {"folder_path": parent}))
        return edges

    @staticmethod
    def folder_nodes(file_nodes: List[FileDescriptor]) -> List[Folder]:
        folders = {}
        for f in file_nodes:
            parent = str(Path(f.path).parent).replace("\\", "/")
            fid = Folder.generate_id(parent)
            if fid not in folders:
                folders[fid] = Folder(id=fid, path=parent, name=Path(parent).name or parent)
        return list(folders.values())
