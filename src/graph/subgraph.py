"""从图存储导出子图（节点 + 边），供前端力导向可视化。"""
from __future__ import annotations

from collections import Counter, deque
from typing import Any

from src.graph.relation_styles import RELATION_LABELS_ZH
from src.storage.factory import GraphStore


def export_subgraph(
    store: GraphStore,
    *,
    center_id: str | None = None,
    hops: int = 2,
    max_nodes: int = 100,
    relation_types: set[str] | None = None,
    max_edges: int = 300,
) -> dict[str, Any]:
    if hasattr(store, "_nodes") and hasattr(store, "_edges"):
        return _export_memory(
            store,
            center_id=center_id,
            hops=hops,
            max_nodes=max_nodes,
            relation_types=relation_types,
            max_edges=max_edges,
        )
    if center_id:
        return _export_via_neighbors(
            store,
            center_id=center_id,
            hops=hops,
            max_nodes=max_nodes,
            relation_types=relation_types,
        )
    return {"nodes": [], "edges": [], "center_id": None, "truncated": False}


def _node_payload(file_id: str, props: dict[str, Any], *, is_center: bool) -> dict[str, Any]:
    name = props.get("name") or file_id
    label = name if len(name) <= 28 else name[:25] + "…"
    return {
        "id": file_id,
        "file_id": file_id,
        "label": label,
        "name": name,
        "path": props.get("path", ""),
        "extension": props.get("extension", ""),
        "status": props.get("status", "ACTIVE"),
        "summary": (props.get("ai_summary") or props.get("summary") or "")[:120],
        "is_center": is_center,
    }


def _edge_payload(e: dict[str, Any]) -> dict[str, Any]:
    rel = e["type"]
    return {
        "id": f"{e['src']}|{rel}|{e['dst']}",
        "from": e["src"],
        "to": e["dst"],
        "type": rel,
        "label": RELATION_LABELS_ZH.get(rel, rel),
        "weight": float(e.get("weight", 1.0)),
        "directed": rel
        in (
            "DEPENDS_ON",
            "REFERENCES",
            "CONTAINS",
            "HAS_VERSION",
            "IS_PREVIOUS_VERSION_OF",
            "IS_TEMPORARY_OF",
            "IS_BACKUP_OF",
        ),
    }


def _export_memory(
    store: Any,
    *,
    center_id: str | None,
    hops: int,
    max_nodes: int,
    relation_types: set[str] | None,
    max_edges: int,
) -> dict[str, Any]:
    nodes_map: dict[str, dict] = {}
    edges_out: list[dict] = []
    edge_keys: set[str] = set()
    state = {"truncated": False}

    def add_edge(e: dict[str, Any]) -> None:
        if relation_types and e["type"] not in relation_types:
            return
        key = (e["src"], e["type"], e["dst"])
        if key in edge_keys:
            return
        if len(edges_out) >= max_edges:
            state["truncated"] = True
            return
        edge_keys.add(key)
        edges_out.append(_edge_payload(e))

    def include_node(fid: str, is_center: bool = False) -> bool:
        if fid in nodes_map:
            if is_center:
                nodes_map[fid]["is_center"] = True
            return True
        if len(nodes_map) >= max_nodes:
            state["truncated"] = True
            return False
        props = store._nodes.get(fid)
        if not props:
            return False
        nodes_map[fid] = _node_payload(fid, props, is_center=is_center)
        return True

    if center_id:
        if center_id not in store._nodes:
            return {"nodes": [], "edges": [], "center_id": center_id, "truncated": False}
        include_node(center_id, is_center=True)
        queue: deque[tuple[str, int]] = deque([(center_id, 0)])
        visited = {center_id}
        while queue:
            fid, depth = queue.popleft()
            if depth >= hops:
                continue
            for e in store._edges:
                if e["src"] != fid and e["dst"] != fid:
                    continue
                other = e["dst"] if e["src"] == fid else e["src"]
                add_edge(e)
                if other in visited:
                    continue
                if not include_node(other):
                    continue
                visited.add(other)
                queue.append((other, depth + 1))
    else:
        degree: Counter[str] = Counter()
        for e in store._edges:
            if relation_types and e["type"] not in relation_types:
                continue
            degree[e["src"]] += 1
            degree[e["dst"]] += 1
        seeds = [fid for fid, _ in degree.most_common(max_nodes)]
        for fid in seeds:
            include_node(fid)
        seed_set = set(seeds)
        for e in store._edges:
            if e["src"] in seed_set and e["dst"] in seed_set:
                add_edge(e)

    return {
        "nodes": list(nodes_map.values()),
        "edges": edges_out,
        "center_id": center_id,
        "truncated": state["truncated"],
        "node_count": len(nodes_map),
        "edge_count": len(edges_out),
    }


def _export_via_neighbors(
    store: GraphStore,
    *,
    center_id: str,
    hops: int,
    max_nodes: int,
    relation_types: set[str] | None,
) -> dict[str, Any]:
    rel_list = list(relation_types) if relation_types else None
    center = store.get_file(center_id)
    if not center:
        return {"nodes": [], "edges": [], "center_id": center_id, "truncated": False}
    nodes_map = {
        center_id: _node_payload(center_id, center, is_center=True),
    }
    edges_out: list[dict] = []
    seen_edges: set[str] = set()
    frontier = {center_id}
    for _ in range(hops):
        next_f: set[str] = set()
        for fid in frontier:
            for nb in store.get_neighbors(fid, rel_types=rel_list, hops=1):
                other = nb["file_id"]
                rel = nb.get("rel_type", "")
                eid = f"{fid}|{rel}|{other}"
                if eid not in seen_edges:
                    seen_edges.add(eid)
                    edges_out.append(
                        {
                            "id": eid,
                            "from": fid,
                            "to": other,
                            "type": rel,
                            "label": RELATION_LABELS_ZH.get(rel, rel),
                            "weight": float(nb.get("weight", 1.0)),
                            "directed": rel
                            in (
                                "DEPENDS_ON",
                                "REFERENCES",
                                "CONTAINS",
                                "HAS_VERSION",
                                "IS_PREVIOUS_VERSION_OF",
                            ),
                        }
                    )
                if other not in nodes_map and len(nodes_map) < max_nodes:
                    node = store.get_file(other) or {}
                    nodes_map[other] = _node_payload(other, node, is_center=False)
                    next_f.add(other)
        frontier = next_f
    return {
        "nodes": list(nodes_map.values()),
        "edges": edges_out,
        "center_id": center_id,
        "truncated": len(nodes_map) >= max_nodes,
        "node_count": len(nodes_map),
        "edge_count": len(edges_out),
    }
