"""Semantic qrels from file embeddings (post-index)."""

import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from src.config import Config, get_config
from src.models.file_descriptor import FileDescriptor
from src.pipeline.embedder import Embedder


def load_files_cache(project_root: Path) -> Dict[str, FileDescriptor]:
    cache_path = project_root / "data" / "files_cache.json"
    if not cache_path.exists():
        return {}
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    return {k: FileDescriptor.from_dict(v) for k, v in raw.items()}


def build_semantic_qrels(
    queries: List[dict],
    files: Dict[str, FileDescriptor],
    config: Config | None = None,
    top_direct: int = 8,
    top_indirect: int = 5,
) -> Tuple[List[dict], dict]:
    """Label relevant files by cosine(query, file_embedding)."""
    config = config or get_config()
    embedder = Embedder(config)
    qrels: dict = {}

    valid = {fid: f for fid, f in files.items() if f.file_embedding}
    if not valid:
        return queries, qrels

    matrix = np.array([f.file_embedding for f in valid.values()], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    matrix = matrix / norms
    ids = list(valid.keys())

    updated_queries = []
    for q in queries:
        qtext = q.get("query", "")
        if not qtext.strip():
            continue
        q_emb = np.array(embedder.encode(qtext), dtype=np.float32)
        q_emb = q_emb / (np.linalg.norm(q_emb) + 1e-8)
        sims = matrix @ q_emb
        order = np.argsort(-sims)

        direct, indirect = [], []
        for idx in order:
            sim = float(sims[idx])
            fid = ids[int(idx)]
            path = valid[fid].path
            if sim < config.min_qrel_similarity:
                break
            if len(direct) < top_direct:
                direct.append(path)
            elif len(indirect) < top_indirect:
                indirect.append(path)
            else:
                break

        if not direct:
            continue

        qid = q["id"]
        qrels[qid] = {"direct": direct, "indirect": indirect}
        q2 = dict(q)
        q2["relevant"] = direct
        q2["indirect"] = indirect
        updated_queries.append(q2)

    return updated_queries, qrels


def update_dataset_annotations(dataset_dir: Path, config: Config | None = None) -> dict:
    config = config or get_config()
    anno_path = dataset_dir / "annotations.json"
    queries_path = dataset_dir / "queries.json"
    if not anno_path.exists():
        raise FileNotFoundError(anno_path)

    anno = json.loads(anno_path.read_text(encoding="utf-8"))
    queries = anno.get("queries") or json.loads(queries_path.read_text(encoding="utf-8"))
    files = load_files_cache(config.project_root)
    if not files:
        raise RuntimeError("files_cache.json missing; run indexing first")

    queries, qrels = build_semantic_qrels(queries, files, config)
    anno["queries"] = queries
    anno_path.write_text(json.dumps(anno, ensure_ascii=False, indent=2), encoding="utf-8")
    queries_path.write_text(json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8")
    (dataset_dir / "qrels.json").write_text(json.dumps(qrels, ensure_ascii=False, indent=2), encoding="utf-8")

    gt_path = dataset_dir / "evaluation_ground_truth.json"
    if gt_path.exists():
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        gt["queries"] = queries
        gt["qrels"] = qrels
        gt_path.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"queries": len(queries), "qrels": len(qrels)}
