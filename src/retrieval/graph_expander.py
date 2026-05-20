"""Graph expansion from seed file nodes."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from src.config import Config, get_config
from src.graph.factory import create_graph_store
from src.graph.store import GraphStore
from src.graph.constants import FILE_FILE_RELATIONS


@dataclass
class ExpandedNode:
    file_id: str
    graph_weight: float = 0.0
    reasoning_path: List[str] = field(default_factory=list)
    relation_types: List[str] = field(default_factory=list)


class GraphExpander:
    def __init__(self, config: Optional[Config] = None, disabled_relations: Optional[Set[str]] = None):
        self.config = config or get_config()
        self.disabled_relations = disabled_relations or set()
        self.store: GraphStore = create_graph_store(self.config)

    def close(self):
        self.store.close()

    def _resolve_allowed(self, relation_filter: Optional[Set[str]]) -> Set[str]:
        if relation_filter is not None:
            allowed = set(relation_filter)
        else:
            allowed = set(self.config.relation_weights.keys()) - self.disabled_relations
        allowed &= set(FILE_FILE_RELATIONS)
        if hasattr(self.store, "list_file_file_relation_types"):
            allowed &= self.store.list_file_file_relation_types()
        return allowed

    def expand(
        self,
        seed_ids: List[str],
        max_hops: Optional[int] = None,
        relation_filter: Optional[Set[str]] = None,
    ) -> List[ExpandedNode]:
        if not seed_ids:
            return []

        hops = max_hops if max_hops is not None else self.config.max_graph_hops
        allowed = self._resolve_allowed(relation_filter)

        results: Dict[str, ExpandedNode] = {}
        for sid in seed_ids:
            results[sid] = ExpandedNode(file_id=sid, graph_weight=1.0, reasoning_path=[sid])

        if not allowed:
            return list(results.values())

        rows = self.store.expand_files(seed_ids, allowed, max_hops=hops)
        for seed, nid, rels, hop_count in rows:
            w = self._path_weight(rels, hop_count)
            if nid in results and results[nid].graph_weight >= w:
                continue
            results[nid] = ExpandedNode(
                file_id=nid,
                graph_weight=w,
                reasoning_path=[seed, nid],
                relation_types=list(dict.fromkeys(rels)),
            )
        return list(results.values())

    def _path_weight(self, rels: List[str], hops: int) -> float:
        if not rels:
            return 0.3 / max(hops, 1)
        weights = [self.config.relation_weights.get(r, 0.3) for r in rels]
        return sum(weights) / len(weights) / max(hops, 1)
