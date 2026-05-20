#!/usr/bin/env python3
"""Evaluation: baselines, metrics, ablation, robustness."""

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_config
from src.evaluation.metrics import (
    average_precision,
    explain_coverage,
    graph_discovery_at_k,
    graph_only_discovery_at_k,
    indirect_recall_at_k,
    ndcg_at_k,
    path_fidelity_sample,
    r_indirect_at_k,
    recall_at_k,
    robustness_ratio,
    serendipity_at_k,
)
from src.models.file_descriptor import FileDescriptor
from src.pipeline.embedder import Embedder
from src.pipeline.graph_builder import GraphBuilder
from src.retrieval.query_parser import QueryParser
from src.retrieval.vector_search import VectorSearcher
from src.retrieval.graph_expander import GraphExpander
from src.retrieval.ranker import Ranker
from src.utils.helpers import normalize_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASELINES = [
    "BM25",
    "VectorOnly",
    "Vector+Metadata",
    "Vector+SIMILAR_TO",
    "FileKG-Full",
]


def load_annotations(dataset_path: Path) -> dict:
    p = dataset_path / "annotations.json"
    if not p.exists():
        raise FileNotFoundError(f"No annotations at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def path_to_id(path: str) -> str:
    return FileDescriptor.generate_id(path.replace("\\", "/"))


def resolve_ids_by_path_or_inode(
    paths: List[str],
    files_cache: Dict[str, FileDescriptor],
) -> Set[str]:
    """Map qrel paths to current FileDescriptor ids (inode-stable after move)."""
    inode_to_id = {f.file_id: f.id for f in files_cache.values() if f.file_id}
    path_to_fid = {f.path: f.id for f in files_cache.values()}

    ids: Set[str] = set()
    for raw in paths:
        norm = normalize_path(raw)
        if norm in path_to_fid:
            fid = path_to_fid[norm]
            ids.add(fid)
            f = files_cache.get(fid)
            if f and f.file_id in inode_to_id:
                ids.add(inode_to_id[f.file_id])
            continue
        if Path(norm).exists():
            ids.add(FileDescriptor.generate_id(norm))
        name = Path(norm).name
        for f in files_cache.values():
            if f.name == name and (norm in f.path or f.path.endswith(name)):
                ids.add(f.id)
                if f.file_id in inode_to_id:
                    ids.add(inode_to_id[f.file_id])
        ids.add(path_to_id(norm))
    return ids


def build_valid_edges(anno: dict, files_cache: Dict[str, FileDescriptor]) -> Set[Tuple[str, str]]:
    edges: Set[Tuple[str, str]] = set()
    base_hint = ""
    for rel in anno.get("relations", []):
        src, tgt = rel.get("source", ""), rel.get("target", "")
        if not src or not tgt:
            continue
        if Path(src).is_absolute():
            sid = path_to_id(src)
            tid = path_to_id(tgt)
        else:
            sid = path_to_id(normalize_path(src))
            tid = path_to_id(normalize_path(tgt))
        edges.add((sid, tid))
    return edges


class EvaluationRunner:
    def __init__(self, dataset_path: Path, disabled_relations: Optional[Set[str]] = None):
        self.dataset_path = dataset_path.resolve()
        self.config = get_config()
        self.disabled_relations = disabled_relations or set()
        self.anno = load_annotations(self.dataset_path)
        self.embedder = Embedder(self.config)
        self.parser = QueryParser(self.config)
        self.searcher = VectorSearcher(self.config)
        self.searcher.refresh()
        self.expander = GraphExpander(self.config, disabled_relations=self.disabled_relations)
        self.ranker = Ranker(self.config)
        self.builder = GraphBuilder(self.config)
        self.builder.load_cache()
        self.files_cache = self.builder._files_cache
        self._valid_edges = build_valid_edges(self.anno, self.files_cache)

        self._bm25 = None
        self._bm25_ids: List[str] = []
        self._init_bm25()

    def close(self):
        self.expander.close()
        self.builder.close()

    def _init_bm25(self):
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return
        docs = []
        self._bm25_ids = []
        for fid, f in self.files_cache.items():
            text = (f.display_summary or f.name or f.path or "").lower().split()
            docs.append(text)
            self._bm25_ids.append(fid)
        if docs:
            self._bm25 = BM25Okapi(docs)

    def _bm25_search(self, query: str, top_k: int) -> List[str]:
        if not self._bm25:
            return self._bm25_ids[:top_k]
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [self._bm25_ids[i] for i in ranked[:top_k]]

    def _bm25_score_map(self, query: str, file_ids: List[str]) -> Dict[str, float]:
        if not self._bm25 or not file_ids:
            return {}
        id_to_idx = {fid: i for i, fid in enumerate(self._bm25_ids)}
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        max_s = max(scores) if len(scores) else 1.0
        out: Dict[str, float] = {}
        for fid in file_ids:
            idx = id_to_idx.get(fid)
            if idx is not None and max_s > 0:
                out[fid] = float(scores[idx]) / max_s
        return out

    def _merge_seeds(self, vector_seeds: List[str], bm25_seeds: List[str]) -> List[str]:
        seen = set()
        merged = []
        for fid in vector_seeds + bm25_seeds:
            if fid not in seen:
                seen.add(fid)
                merged.append(fid)
        return merged

    def retrieve(self, baseline: str, query: str, top_k: int = 20) -> tuple:
        parsed = self.parser.parse(query)
        reasoning_map: Dict[str, List[str]] = {}
        qtext = parsed.semantic_text

        if baseline == "BM25":
            ranked_ids = self._bm25_search(qtext, top_k)
        elif baseline == "VectorOnly":
            ranked_ids = self.searcher.search(qtext, filters={}, top_n=top_k)
        elif baseline == "Vector+Metadata":
            ranked_ids = self.searcher.search(qtext, filters=parsed.to_filters(), top_n=top_k)
        elif baseline in ("Vector+SIMILAR_TO", "FileKG-Full"):
            vec_n = self.config.vector_seed_top_n if baseline == "FileKG-Full" else 100
            hard_filters = parsed.to_filters() if self.config.metadata_filter_hard else {}

            seeds_v = self.searcher.search(qtext, filters=hard_filters, top_n=vec_n)
            if baseline == "FileKG-Full" and self.config.use_hybrid_seeds:
                seeds_b = self._bm25_search(qtext, self.config.bm25_seed_top_n)
                seeds = self._merge_seeds(seeds_v, seeds_b)
            else:
                seeds = seeds_v

            rel_filter = {"SIMILAR_TO"} if baseline == "Vector+SIMILAR_TO" else None
            hops = 1 if baseline == "Vector+SIMILAR_TO" else None
            expanded = self.expander.expand(seeds, max_hops=hops, relation_filter=rel_filter)

            pool_n = max(vec_n, top_k * 8, 200)
            vector_pool = self.searcher.search(qtext, filters=hard_filters, top_n=pool_n)
            candidate_ids = set(vector_pool)
            if baseline == "FileKG-Full":
                q_emb_probe = self.embedder.encode(qtext)
                qv = np.array(q_emb_probe, dtype=np.float32)
                qv = qv / (np.linalg.norm(qv) + 1e-8)
                for e in expanded:
                    if e.file_id in candidate_ids or len(e.reasoning_path) <= 1:
                        continue
                    f = self.files_cache.get(e.file_id)
                    if not f or not f.file_embedding:
                        continue
                    fv = np.array(f.file_embedding, dtype=np.float32)
                    fv = fv / (np.linalg.norm(fv) + 1e-8)
                    if float(np.dot(qv, fv)) >= self.config.min_graph_expand_vector:
                        candidate_ids.add(e.file_id)

            subset = {fid: self.files_cache[fid] for fid in candidate_ids if fid in self.files_cache}
            q_emb = self.embedder.encode(qtext)
            bm25_map = self._bm25_score_map(qtext, list(subset.keys()))
            scored = self.ranker.score_and_rank(
                q_emb, subset, seeds, expanded,
                parsed_keywords=parsed.keywords,
                top_k=top_k,
                bm25_scores=bm25_map,
                vector_seed_ids=seeds_v,
            )
            ranked_ids = [s.file_id for s in scored]
            for s in scored:
                reasoning_map[s.file_id] = s.reasoning_path
            return ranked_ids, reasoning_map
        else:
            ranked_ids = []

        return ranked_ids, reasoning_map

    def evaluate_query(self, baseline: str, query_item: dict, k: int = 20) -> dict:
        relevant_paths = list(query_item.get("relevant", []))
        relevant_ids = resolve_ids_by_path_or_inode(relevant_paths, self.files_cache)
        indirect_paths = list(query_item.get("indirect", []))
        indirect_ids = resolve_ids_by_path_or_inode(indirect_paths, self.files_cache)

        ranked_ids, reasoning_map = self.retrieve(baseline, query_item["query"], top_k=k)
        vector_top = set(self.searcher.search(query_item["query"], filters={}, top_n=k))
        targets = relevant_ids | indirect_ids

        return {
            "map": average_precision(relevant_ids, ranked_ids, k),
            "ndcg": ndcg_at_k(relevant_ids, ranked_ids, k),
            "recall": recall_at_k(relevant_ids, ranked_ids, k),
            "r_indirect": r_indirect_at_k(relevant_ids, ranked_ids, indirect_ids, k),
            "indirect_recall": indirect_recall_at_k(indirect_ids, ranked_ids, k),
            "graph_discovery": graph_discovery_at_k(ranked_ids, reasoning_map, k),
            "graph_only_discovery": graph_only_discovery_at_k(ranked_ids, reasoning_map, vector_top, k),
            "serendipity": serendipity_at_k(ranked_ids, reasoning_map, vector_top, targets, k),
            "explain_coverage": explain_coverage(reasoning_map, ranked_ids, k),
            "path_fidelity": path_fidelity_sample(
                reasoning_map, ranked_ids, self._valid_edges, k, sample_n=30,
            ),
        }

    def run_all(self, baselines: Optional[List[str]] = None, k: int = 20) -> dict:
        baselines = baselines or BASELINES
        results = {"dataset": self.anno.get("dataset"), "baselines": {}, "k": k}
        queries = [
            q for q in self.anno.get("queries", [])
            if q.get("relevant") or q.get("query")
        ]
        for bl in baselines:
            metrics = []
            for q in queries:
                if not q.get("relevant"):
                    continue
                metrics.append(self.evaluate_query(bl, q, k))
            if metrics:
                agg = {key: sum(m[key] for m in metrics) / len(metrics) for key in metrics[0]}
            else:
                agg = {}
            results["baselines"][bl] = {"aggregate": agg, "per_query": metrics}
            logger.info("%s: %s", bl, agg)
        return results


def run_robustness_move(dataset_path: Path) -> dict:
    """Path-hash id changes on move; inode remains stable."""
    anno = load_annotations(dataset_path)
    if not anno.get("queries"):
        return {"moved": 0, "id_stable": True}
    src = anno["queries"][0]["relevant"][0] if anno["queries"][0].get("relevant") else None
    if not src or not Path(src).exists():
        return {"moved": 0, "id_stable": True, "note": "no sample file"}
    p = Path(src)
    old_id = path_to_id(str(p.resolve()).replace("\\", "/"))
    dest = p.parent / ("moved_" + p.name)
    shutil.move(str(p), str(dest))
    new_id = path_to_id(str(dest.resolve()).replace("\\", "/"))
    shutil.move(str(dest), str(p))
    return {
        "old_id": old_id,
        "new_id": new_id,
        "id_stable": old_id == new_id,
        "note": "path-hash id changes on move; file_id (inode) stable — use inode-aware qrels",
    }


def run_robustness_retrieval(dataset_path: Path, k: int = 20) -> dict:
    """Move one relevant file, incremental update, compare recall@k before/after."""
    from src.pipeline.graph_builder import GraphBuilder

    anno = load_annotations(dataset_path)
    queries = [q for q in anno.get("queries", []) if q.get("relevant")]
    if not queries:
        return {"note": "no queries"}

    q0 = queries[0]
    src = q0["relevant"][0]
    p = Path(src)
    if not p.exists():
        return {"note": f"missing {src}"}

    cfg = get_config()
    runner = EvaluationRunner(dataset_path)
    before_v = runner.evaluate_query("VectorOnly", q0, k)
    before_f = runner.evaluate_query("FileKG-Full", q0, k)
    runner.close()

    dest = p.parent / ("robust_" + p.name)
    shutil.move(str(p), str(dest))

    builder = GraphBuilder(cfg)
    try:
        builder.load_cache()
        t0 = time.perf_counter()
        builder.incremental_update(dest)
        incremental_ms = (time.perf_counter() - t0) * 1000
        builder.load_cache()
    finally:
        builder.close()

    q_moved = dict(q0)
    q_moved["relevant"] = [str(dest.resolve()).replace("\\", "/")]

    runner2 = EvaluationRunner(dataset_path)
    after_v = runner2.evaluate_query("VectorOnly", q_moved, k)
    after_f = runner2.evaluate_query("FileKG-Full", q_moved, k)
    runner2.close()

    shutil.move(str(dest), str(p))

    return {
        "file": str(p),
        "incremental_update_ms": round(incremental_ms, 1),
        "vector_only": {
            "recall_before": before_v["recall"],
            "recall_after": after_v["recall"],
            "robustness_recall": robustness_ratio(before_v["recall"], after_v["recall"]),
        },
        "filekg_full": {
            "recall_before": before_f["recall"],
            "recall_after": after_f["recall"],
            "robustness_recall": robustness_ratio(before_f["recall"], after_f["recall"]),
        },
    }


def write_report(results: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "experiment_data.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# FileKG Evaluation Report\n", f"Dataset: {results.get('dataset', 'unknown')}\n\n"]
    lines.append(
        "| Baseline | MAP | NDCG | Recall | R_indir | GraphDisc | GraphOnly | Serendipity | ExplainCov | PathFid |\n"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for bl, data in results.get("baselines", {}).items():
        a = data.get("aggregate", {})
        lines.append(
            f"| {bl} | {a.get('map', 0):.3f} | {a.get('ndcg', 0):.3f} | {a.get('recall', 0):.3f} | "
            f"{a.get('r_indirect', 0):.3f} | {a.get('graph_discovery', 0):.3f} | "
            f"{a.get('graph_only_discovery', 0):.3f} | {a.get('serendipity', 0):.3f} | "
            f"{a.get('explain_coverage', 0):.3f} | {a.get('path_fidelity', 0):.3f} |\n"
        )
    if results.get("robustness"):
        lines.append(f"\n## Robustness\n\n```json\n{json.dumps(results['robustness'], indent=2)}\n```\n")
    if results.get("robustness_retrieval"):
        lines.append(
            f"\n## Robustness Retrieval\n\n```json\n"
            f"{json.dumps(results['robustness_retrieval'], indent=2)}\n```\n"
        )
    if results.get("ablation"):
        lines.append("\n## Ablation\n\n")
        for name, agg in results["ablation"].items():
            lines.append(
                f"- **{name}**: MAP={agg.get('map', 0):.3f}, "
                f"GraphOnly={agg.get('graph_only_discovery', 0):.3f}, "
                f"Recall={agg.get('recall', 0):.3f}\n"
            )

    md_path = out_dir / "report.md"
    md_path.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {json_path} and {md_path}")


def run_ablation(
    dataset_path: Path,
    relations: Optional[List[str]] = None,
    k: int = 20,
) -> dict:
    relations = relations or [
        "SIMILAR_TO", "DEPENDS_ON", "REFERENCES", "WORKFLOW_WITH",
        "NEAR_IN_TIME", "HAS_VERSION", "VISUALLY_SIMILAR_TO", "SAME_TYPE",
    ]
    ablation = {}
    full_runner = EvaluationRunner(dataset_path)
    try:
        full_agg = full_runner.run_all(baselines=["FileKG-Full"], k=k)["baselines"]["FileKG-Full"]["aggregate"]
    finally:
        full_runner.close()

    for rel in relations:
        disabled = {rel}
        runner = EvaluationRunner(dataset_path, disabled_relations=disabled)
        try:
            res = runner.run_all(baselines=["FileKG-Full"], k=k)
            agg = res["baselines"]["FileKG-Full"]["aggregate"]
            delta = {
                key: agg.get(key, 0) - full_agg.get(key, 0)
                for key in agg
            }
            ablation[f"disable_{rel}"] = {**agg, "delta": delta}
        finally:
            runner.close()
    ablation["_full"] = full_agg
    return ablation


def main():
    parser = argparse.ArgumentParser(description="Run FileKG evaluation")
    parser.add_argument("dataset_path", type=Path, nargs="?", default=ROOT / "data" / "datasets" / "filekg_main")
    parser.add_argument("--baselines", nargs="*", default=None)
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--ablation", action="store_true")
    parser.add_argument("--ablation-relations", nargs="*", default=None)
    parser.add_argument("--robustness", action="store_true")
    parser.add_argument("--robustness-retrieval", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--output-name", type=str, default=None, help="JSON filename stem")
    args = parser.parse_args()

    out_dir = args.output or (ROOT / "data" / "evaluation")
    stem = args.output_name or args.dataset_path.name

    runner = EvaluationRunner(args.dataset_path)
    try:
        results = runner.run_all(baselines=args.baselines, k=args.k)
        if args.robustness:
            results["robustness"] = run_robustness_move(args.dataset_path)
        if args.robustness_retrieval:
            results["robustness_retrieval"] = run_robustness_retrieval(args.dataset_path, k=args.k)
        if args.ablation:
            results["ablation"] = run_ablation(
                args.dataset_path,
                relations=args.ablation_relations,
                k=args.k,
            )
    finally:
        runner.close()

    out_json = out_dir / f"{stem}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(results, out_dir)
    if stem != "experiment_data":
        (out_dir / "experiment_data.json").write_text(
            out_json.read_text(encoding="utf-8"), encoding="utf-8"
        )
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()
