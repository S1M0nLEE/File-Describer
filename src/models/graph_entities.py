"""Graph entity models: Folder, Project, Tag."""

from dataclasses import dataclass, asdict
from typing import Any, Dict
import hashlib


@dataclass
class Folder:
    id: str
    path: str
    name: str

    @staticmethod
    def generate_id(folder_path: str) -> str:
        normalized = folder_path.replace("\\", "/")
        return hashlib.md5(f"folder:{normalized}".encode("utf-8")).hexdigest()

    def to_neo4j_props(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Project:
    id: str
    name: str
    root_path: str = ""

    @staticmethod
    def generate_id(name: str) -> str:
        return hashlib.md5(f"project:{name}".encode("utf-8")).hexdigest()

    def to_neo4j_props(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Tag:
    id: str
    name: str

    @staticmethod
    def generate_id(name: str) -> str:
        return hashlib.md5(f"tag:{name}".encode("utf-8")).hexdigest()

    def to_neo4j_props(self) -> Dict[str, Any]:
        return asdict(self)
