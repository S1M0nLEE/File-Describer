from __future__ import annotations

from dataclasses import dataclass, field

from src.config import settings
from src.models.relationships import RELATION_LABELS_ZH
from src.storage.factory import GraphStore


@dataclass
class GraphHit:
    file_id: str
    path: str = ""
    name: str = ""
    graph_weight: float = 0.0
    paths: list[dict] = field(default_factory=list)
    is_seed: bool = False
    seed_similarity: float = 0.0


class GraphExpander:
    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.rel_weights = settings.relation_weights or {}

    def expand_seeds(
        self,
        seeds: list[dict],
        *,
        hops: int = 1,
        allowed_relations: set[str] | None = None,
    ) -> dict[str, GraphHit]:
        hits: dict[str, GraphHit] = {}

        for seed in seeds:
            fid = seed["file_id"]
            sim = seed.get("similarity", 0.0)
            hits[fid] = GraphHit(
                file_id=fid,
                path=seed.get("path", ""),
                name=seed.get("name", ""),
                graph_weight=1.0,
                is_seed=True,
                seed_similarity=sim,
            )

        for seed in seeds:
            fid = seed["file_id"]
            self._expand_bfs(fid, seed, hops, hits, allowed_relations)

        return hits

    def _expand_bfs(
        self,
        seed_fid: str,
        seed: dict,
        hops: int,
        hits: dict[str, GraphHit],
        allowed_relations: set[str] | None,
    ) -> None:
        frontier = [(seed_fid, 1.0, seed.get("name", ""))]
        visited: set[str] = {seed_fid}

        for _depth in range(hops):
            next_frontier: list[tuple[str, float, str]] = []
            for fid, path_weight, from_name in frontier:
                neighbors = self.store.get_neighbors(fid, hops=1)
                for nb in neighbors:
                    rel = nb.get("rel_type", "")
                    if allowed_relations is not None and rel not in allowed_relations:
                        continue
                    w = (
                        path_weight
                        * self.rel_weights.get(rel, 0.5)
                        * float(nb.get("weight") or 1.0)
                    )
                    nid = nb["file_id"]
                    nb_path = (nb.get("path") or "").replace("\\", "/").lower()
                    seed_path = (seed.get("path") or "").replace("\\", "/").lower()
                    if "/noise/" in nb_path and "/noise/" not in seed_path:
                        continue
                    props = nb.get("props") or {}
                    explain = {
                        "from_id": fid,
                        "from_name": from_name,
                        "rel_type": rel,
                        "rel_label": RELATION_LABELS_ZH.get(rel, rel),
                        "to_id": nid,
                        "to_name": nb.get("name", ""),
                        "confidence": props.get("confidence"),
                        "relation_subtype": props.get("relation_subtype")
                        or props.get("relation_label"),
                        "s_visual": props.get("s_visual"),
                        "s_text": props.get("s_text"),
                        "s_doc": props.get("s_doc"),
                    }
                    if nid in hits:
                        if w > hits[nid].graph_weight:
                            hits[nid].graph_weight = w
                        hits[nid].paths.append(explain)
                    else:
                        hits[nid] = GraphHit(
                            file_id=nid,
                            path=nb.get("path", ""),
                            name=nb.get("name", ""),
                            graph_weight=w,
                            paths=[explain],
                        )
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.append((nid, w, nb.get("name", "")))
            frontier = next_frontier
