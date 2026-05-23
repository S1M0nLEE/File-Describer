from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from src.config import settings
from src.evaluation.metrics import average_precision, relevant_set
from src.evaluation.runner import K, load_ground_truth
from src.indexing.builder import IndexBuilder
from src.search.engine import SearchEngine
from src.storage.factory import create_eval_stores

logger = logging.getLogger(__name__)


def _edge_keys(graph) -> set[tuple[str, str, str]]:
    edges = getattr(graph, "_edges", [])
    return {(e["src"], e["type"], e["dst"]) for e in edges}


def _logical_pairs(edges: set[tuple[str, str, str]], id_to_name: dict[str, str]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for src, rel, dst in edges:
        sn = id_to_name.get(src, src)
        dn = id_to_name.get(dst, dst)
        pair = tuple(sorted((sn, dn)))
        out.add((pair[0], rel, pair[1]))
    return out


def _map_on_queries(engine: SearchEngine, queries: list[dict]) -> float:
    if not queries:
        return 0.0
    scores = []
    for qitem in queries:
        q = qitem["q"]
        payload = engine.search(q)
        results = (payload.get("results") or [])[:K]
        names = [r.get("name", "") for r in results]
        all_rel, _, _ = relevant_set(qitem.get("direct", []), qitem.get("indirect", []))
        scores.append(average_precision(names, all_rel))
    return sum(scores) / len(scores)


def _queries_touching_files(gt: list[dict], names: set[str]) -> list[dict]:
    related = []
    for qitem in gt:
        files = qitem.get("direct", []) + qitem.get("indirect", [])
        if any(Path(f).name in names for f in files):
            related.append(qitem)
    return related or gt[: min(5, len(gt))]


def run_robustness_test(
    dataset_path: Path,
    ground_truth_path: Path,
    *,
    move_subdir: str = "relocated",
    max_move_files: int = 8,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """文件移动鲁棒性：volume file_id 增量更新 vs path 身份全量重建。"""
    dataset_path = dataset_path.resolve()
    gt = load_ground_truth(ground_truth_path)

    work_root = settings.data_dir / "robustness_workspace" / dataset_path.name
    if work_root.exists():
        shutil.rmtree(work_root, ignore_errors=True)
    shutil.copytree(dataset_path, work_root)

    scene = work_root / "project_a_research"
    if not scene.is_dir():
        scene = work_root

    candidates = [p for p in scene.rglob("*") if p.is_file() and "noise" not in p.parts]
    candidates = sorted(candidates, key=lambda p: p.name)[:max_move_files]
    dest_dir = scene / move_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    graph_v, chroma_v = create_eval_stores(f"robust_{dataset_path.name}_volume")
    builder_v = IndexBuilder(graph_v, chroma_v, id_mode="volume")
    t0 = time.perf_counter()
    builder_v.build(work_root, clear=True)
    index_build_sec = time.perf_counter() - t0

    edges_before = _edge_keys(graph_v)
    id_to_name_before = {fid: n.get("name", "") for fid, n in graph_v._nodes.items()}

    engine_v = SearchEngine(graph_v, chroma_v)
    moved_names: set[str] = set()
    moved: list[dict[str, str]] = []

    for src in candidates:
        dst = dest_dir / src.name
        if dst.exists():
            dst.unlink()
        moved_names.add(src.name)
        shutil.move(str(src), str(dst))
        fid = builder_v.relocate_file(src, dst)
        moved.append({"from": str(src), "to": str(dst), "file_id": fid})

    t1 = time.perf_counter()
    incremental_sec = t1 - t0 - index_build_sec

    edges_after = _edge_keys(graph_v)
    node_ids_after = set(graph_v._nodes.keys())
    intact = sum(
        1
        for e in edges_before
        if e in edges_after and e[0] in node_ids_after and e[2] in node_ids_after
    )
    relation_retention = intact / len(edges_before) if edges_before else 1.0

    subset = _queries_touching_files(gt, moved_names)
    map_after = _map_on_queries(engine_v, subset)

    graph_v.close()

    # path 模式：在已移动的 work_root 上全量重建
    graph_p, chroma_p = create_eval_stores(f"robust_{dataset_path.name}_path")
    builder_p = IndexBuilder(graph_p, chroma_p, id_mode="path")
    builder_p.build(work_root, clear=True)
    edges_path = _edge_keys(graph_p)
    logical_before = _logical_pairs(edges_before, id_to_name_before)
    id_to_name_path = {fid: n.get("name", "") for fid, n in graph_p._nodes.items()}
    logical_path = _logical_pairs(edges_path, id_to_name_path)
    path_logical_retention = (
        len(logical_before & logical_path) / len(logical_before) if logical_before else 1.0
    )
    graph_p.close()

    result = {
        "dataset": str(dataset_path),
        "files_moved": len(moved),
        "moved_files": moved,
        "queries_evaluated": len(subset),
        "volume_file_id": {
            "relation_retention_rate": round(relation_retention, 4),
            "edges_before": len(edges_before),
            "edges_after": len(edges_after),
            "index_build_sec": round(index_build_sec, 2),
            "incremental_update_sec": round(incremental_sec, 3),
            "MAP@20_after_move": round(map_after, 4),
        },
        "path_based_id": {
            "logical_relation_retention_rate": round(path_logical_retention, 4),
            "note": "移动后按路径重建索引；逻辑边以文件名为键",
        },
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("鲁棒性测试完成: retention=%.2f%%", relation_retention * 100)
    return result
