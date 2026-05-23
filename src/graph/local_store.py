"""JSON-backed local graph store (no Neo4j required)."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

from src.graph.store import EdgeRow, ExpandRow, GraphStore
from src.graph.constants import FILE_FILE_RELATIONS

logger = logging.getLogger(__name__)

LABEL_BY_REL = {
    "IN_FOLDER": "Folder",
    "BELONGS_TO_PROJECT": "Project",
    "TAGGED_WITH": "Tag",
}


class LocalGraphStore(GraphStore):
    backend_name = "local"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.nodes: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self.edges: List[Dict[str, Any]] = []
        self._load()

    def close(self) -> None:
        self._save()

    def verify_connectivity(self) -> None:
        return

    def ensure_indexes(self) -> None:
        return

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self._save()

    def merge_node(self, label: str, node_id: str, props: Dict[str, Any]) -> None:
        existing = self.nodes[label].get(node_id, {})
        existing.update(props)
        self.nodes[label][node_id] = existing

    def write_relationships(self, edges: List[EdgeRow]) -> None:
        for src, tgt, rtype, props in edges:
            tgt_label = LABEL_BY_REL.get(rtype, "FileDescriptor")
            self.edges.append({
                "src": src,
                "tgt": tgt,
                "type": rtype,
                "props": props or {},
                "tgt_label": tgt_label,
            })
        self._save()

    def update_file_status(self, file_id: str, status: str) -> None:
        if file_id in self.nodes.get("FileDescriptor", {}):
            self.nodes["FileDescriptor"][file_id]["status"] = status
            self._save()

    def delete_file(self, file_id: str) -> None:
        self.nodes.get("FileDescriptor", {}).pop(file_id, None)
        self.edges = [e for e in self.edges if e["src"] != file_id and e["tgt"] != file_id]
        self._save()

    def list_file_file_relation_types(self) -> Set[str]:
        found = set()
        for e in self.edges:
            if e.get("tgt_label", "FileDescriptor") == "FileDescriptor":
                found.add(e["type"])
        return found & set(FILE_FILE_RELATIONS)

    def expand_files(
        self,
        seed_ids: List[str],
        allowed_relations: Set[str],
        max_hops: int = 1,
        limit: int = 500,
    ) -> List[ExpandRow]:
        allowed = set(allowed_relations) & set(FILE_FILE_RELATIONS)
        adj: Dict[str, List[tuple]] = defaultdict(list)
        for e in self.edges:
            if e["type"] not in allowed:
                continue
            if e.get("tgt_label", "FileDescriptor") != "FileDescriptor":
                continue
            adj[e["src"]].append((e["tgt"], e["type"]))
            adj[e["tgt"]].append((e["src"], e["type"]))

        results: List[ExpandRow] = []
        seen: Set[tuple] = set()
        for seed in seed_ids:
            frontier = [(seed, [], 0)]
            visited = {seed}
            while frontier:
                current, rel_path, depth = frontier.pop(0)
                if depth >= max_hops:
                    continue
                for nbr, rtype in adj.get(current, []):
                    if nbr in visited:
                        continue
                    visited.add(nbr)
                    new_rels = rel_path + [rtype]
                    key = (seed, nbr)
                    if key not in seen:
                        seen.add(key)
                        results.append((seed, nbr, new_rels, depth + 1))
                    if len(results) >= limit:
                        return results
                    if depth + 1 < max_hops:
                        frontier.append((nbr, new_rels, depth + 1))
        return results

    def _save(self) -> None:
        payload = {
            "nodes": {label: dict(nodes) for label, nodes in self.nodes.items()},
            "edges": self.edges,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw_nodes = payload.get("nodes", {})
            self.nodes = defaultdict(dict)
            for label, nodes in raw_nodes.items():
                self.nodes[label] = dict(nodes)
            self.edges = payload.get("edges", [])
        except json.JSONDecodeError:
            logger.warning("Corrupt local graph file, starting fresh: %s", self.path)
