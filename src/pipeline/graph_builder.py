"""Graph builder: Chroma vectors + Neo4j or local JSON graph."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

import chromadb

from src.config import Config, get_config
from src.graph.factory import create_graph_store
from src.graph.store import GraphStore
from src.models.file_descriptor import FileDescriptor
from src.pipeline.embedder import Embedder
from src.pipeline.scanner import FileScanner
from src.pipeline.summarizer import Summarizer
from src.pipeline.text_extractor import TextExtractor
from src.relations import ALL_EXTRACTORS
from src.relations.in_folder import InFolderExtractor
from src.relations.belongs_to_project import BelongsToProjectExtractor
from src.relations.tagged_with import TaggedWithExtractor
from src.pipeline.chroma_store import CHROMA_COLLECTION
from src.utils.helpers import days_since, normalize_path

logger = logging.getLogger(__name__)


class GraphBuilder:
    def __init__(self, config: Optional[Config] = None, enabled_relations: Optional[Set[str]] = None):
        self.config = config or get_config()
        self.enabled_relations = enabled_relations
        self.store: GraphStore = create_graph_store(self.config)
        logger.info("Graph backend: %s", self.store.backend_name)
        self.scanner = FileScanner(self.config)
        self.text_extractor = TextExtractor(self.config)
        self.summarizer = Summarizer(self.config)
        self.embedder = Embedder(self.config)
        self.chroma = chromadb.PersistentClient(path=self.config.chroma_persist_dir)
        self.collection = self.chroma.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self.relation_extractors = self._init_extractors()
        self._files_cache: Dict[str, FileDescriptor] = {}

    def _init_extractors(self):
        extractors = []
        for cls in ALL_EXTRACTORS:
            rtype = cls.relation_type
            if self.enabled_relations and rtype not in self.enabled_relations:
                continue
            if self.config.skip_visual_similarity and rtype == "VISUALLY_SIMILAR_TO":
                continue
            try:
                extractors.append(cls(self.config))
            except TypeError:
                extractors.append(cls())
        return extractors

    def close(self):
        self.store.close()

    def build_full(self, root_path: Path, clear: bool = True):
        root = Path(root_path).resolve()
        logger.info("Scanning %s", root)
        files = self.scanner.scan(root)

        for f in files:
            self.text_extractor.extract(f)
            self.summarizer.summarize(f)

        texts = [f.display_summary or f.name for f in files]
        embeddings = self.embedder.encode(texts)
        for f, emb in zip(files, embeddings):
            f.file_embedding = emb

        self._files_cache = {f.id: f for f in files}

        if clear:
            self.store.clear()
            self._reset_chroma()

        self.store.ensure_indexes()
        self._create_nodes(files)
        self._create_basic_relations(files)
        self._index_chroma(files)

        edges: List = []
        for extractor in self.relation_extractors:
            rtype = extractor.relation_type
            if self.enabled_relations and rtype not in self.enabled_relations:
                continue
            logger.info("Running extractor %s", rtype)
            edges.extend(extractor.discover(files))
        self.store.write_relationships(edges)
        self._update_statuses(files)
        self._persist_cache(root)
        logger.info("Indexed %d files, %d edges (%s)", len(files), len(edges), self.store.backend_name)
        return files

    def incremental_update(self, file_path: Path):
        path = normalize_path(file_path)
        p = Path(path)
        if not p.exists():
            self._delete_file(path)
            return

        files = self.scanner.scan(p.parent)
        target = next((f for f in files if f.path == path), None)
        if not target:
            return

        self.text_extractor.extract(target)
        self.summarizer.summarize(target)
        target.file_embedding = self.embedder.encode(target.display_summary or target.name)
        self._files_cache[target.id] = target

        self.store.merge_node("FileDescriptor", target.id, target.to_neo4j_props())
        self.collection.upsert(
            ids=[target.id],
            embeddings=[target.file_embedding],
            documents=[target.display_summary or target.name],
            metadatas=[target.to_chroma_metadata()],
        )

        all_files = list(self._files_cache.values())
        edges = []
        for extractor in self.relation_extractors:
            edges.extend(extractor.discover(all_files))
        rel_edges = [e for e in edges if e[0] == target.id or e[1] == target.id]
        self.store.write_relationships(rel_edges)
        self._update_statuses([target])

    def _reset_chroma(self):
        try:
            self.chroma.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass
        self.collection = self.chroma.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def _create_nodes(self, files: List[FileDescriptor]):
        folders = InFolderExtractor.folder_nodes(files)
        projects = BelongsToProjectExtractor.project_nodes(files)
        tags = TaggedWithExtractor.tag_nodes(files)

        for f in files:
            self.store.merge_node("FileDescriptor", f.id, f.to_neo4j_props())
        for folder in folders:
            self.store.merge_node("Folder", folder.id, folder.to_neo4j_props())
        for proj in projects:
            self.store.merge_node("Project", proj.id, proj.to_neo4j_props())
        for tag in tags:
            self.store.merge_node("Tag", tag.id, tag.to_neo4j_props())

    def _create_basic_relations(self, files: List[FileDescriptor]):
        in_folder = InFolderExtractor().discover(files)
        self.store.write_relationships(in_folder)

    def _index_chroma(self, files: List[FileDescriptor]):
        if not files:
            return
        batch = 100
        for i in range(0, len(files), batch):
            chunk = files[i : i + batch]
            self.collection.upsert(
                ids=[f.id for f in chunk],
                embeddings=[f.file_embedding for f in chunk],
                documents=[f.display_summary or f.name for f in chunk],
                metadatas=[f.to_chroma_metadata() for f in chunk],
            )

    def _update_statuses(self, files: List[FileDescriptor]):
        now = time.time()
        for f in files:
            age_days = days_since(f.modified_time, now)
            if age_days > 365:
                status = "archived"
            elif age_days > 90:
                status = "dormant"
            else:
                status = "active"
            f.status = status
            self.store.update_file_status(f.id, status)

    def _delete_file(self, path: str):
        fid = FileDescriptor.generate_id(path)
        self.store.delete_file(fid)
        try:
            self.collection.delete(ids=[fid])
        except Exception:
            pass
        self._files_cache.pop(fid, None)

    def _persist_cache(self, root: Path):
        cache_path = self.config.project_root / "data" / "files_cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            fid: {
                **f.to_neo4j_props(),
                "file_embedding": f.file_embedding,
            }
            for fid, f in self._files_cache.items()
        }
        cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_cache(self) -> Dict[str, FileDescriptor]:
        cache_path = self.config.project_root / "data" / "files_cache.json"
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            self._files_cache = {k: FileDescriptor.from_dict(v) for k, v in raw.items()}
        return self._files_cache
