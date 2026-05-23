from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.evaluation.baselines import Baseline, build_baselines, build_corpus_from_graph
from src.evaluation.metrics import (
    SERENDIPITY_RELATIONS,
    QueryMetrics,
    aggregate,
    average_precision,
    explainability_coverage,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    recall_subset,
    relevant_set,
    graph_discovery_at_k,
    serendipity_at_k,
)
from src.evaluation.statistics import filekg_vs_best_baseline
from src.indexing.builder import IndexBuilder
from src.indexing.embedder import Embedder
from src.search.engine import SearchEngine
from src.storage.factory import create_eval_stores

logger = logging.getLogger(__name__)
K = 20


def load_ground_truth(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("queries", data)


def run_evaluation(
    dataset_path: Path,
    ground_truth_path: Path,
    *,
    output_dir: Path,
    clear_index: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    Embedder.reset()
    dataset_id = dataset_path.name
    graph, chroma = create_eval_stores(dataset_id)
    builder = IndexBuilder(graph, chroma)

    t0 = time.perf_counter()
    build_info = builder.build(dataset_path, clear=clear_index)
    index_time = time.perf_counter() - t0

    engine = SearchEngine(graph, chroma)
    corpus = build_corpus_from_graph(graph, chroma)
    baselines = build_baselines(graph, chroma, engine, corpus)
    queries = load_ground_truth(ground_truth_path)

    all_results: dict[str, list[QueryMetrics]] = {b.name: [] for b in baselines}
    per_query: dict[str, list[dict[str, Any]]] = {b.name: [] for b in baselines}
    relation_contrib: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for qitem in queries:
        q = qitem["q"]
        direct = set(qitem.get("direct", []))
        indirect = set(qitem.get("indirect", []))
        all_rel, dset, iset = relevant_set(list(direct), list(indirect))

        for baseline in baselines:
            t1 = time.perf_counter()
            results = baseline.search(q, k=K)
            latency = (time.perf_counter() - t1) * 1000
            names = [r.get("name", "") for r in results]

            qm = QueryMetrics(
                query=q,
                ap=average_precision(names, all_rel),
                p_at_k=precision_at_k(names, all_rel, K),
                r_at_k=recall_at_k(names, all_rel, K),
                ndcg_at_k=ndcg_at_k(names, all_rel, K),
                recall_direct=recall_subset(names, dset, K),
                recall_indirect=recall_subset(names, iset, K),
                serendipity=serendipity_at_k(results, dset, iset, K),
                graph_discovery=graph_discovery_at_k(results, dset, iset, K),
                explain_coverage=explainability_coverage(results, dset, K),
                latency_ms=latency,
                retrieved=names,
            )
            all_results[baseline.name].append(qm)
            per_query[baseline.name].append(
                {
                    "query": q,
                    "ap": qm.ap,
                    "r_at_k": qm.r_at_k,
                    "recall_indirect": qm.recall_indirect,
                    "serendipity": qm.serendipity,
                }
            )

            if baseline.name == "FileKG-Full":
                for r in results[:K]:
                    for rel in all_rel:
                        if _found(r.get("name", ""), rel):
                            for p in r.get("explanation_paths") or []:
                                rt = p.get("rel_type", "DIRECT")
                                if rt in SERENDIPITY_RELATIONS or rt in (
                                    "IN_FOLDER",
                                    "SAME_TYPE",
                                    "NEAR_IN_TIME",
                                    "SIMILAR_TO",
                                ):
                                    relation_contrib[q][rt] += 1
                            if r.get("is_seed") and not r.get("explanation_paths"):
                                relation_contrib[q]["SEMANTIC_SEED"] += 1

    leakage = _query_filename_leakage(queries)

    summary = {
        "dataset": str(dataset_path),
        "file_count": build_info.get("file_count"),
        "index_time_sec": round(index_time, 2),
        "query_count": len(queries),
        "eval_profile": os.environ.get("FILEKG_EVAL_PROFILE", "default"),
        "config_file": os.environ.get("FILEKG_CONFIG", "config.yaml"),
        "embedding_model": os.environ.get("FILEKG_EMBEDDING_MODEL") or None,
        "llm_enabled": os.environ.get("FILEKG_LLM_ENABLED"),
        "visual_enabled": os.environ.get("FILEKG_VISUAL_ENABLED"),
        "metrics_version": "corrected_v2",
        "matching": "strict_basename",
        "serendipity_relations": sorted(SERENDIPITY_RELATIONS),
        "query_leakage_ratio": leakage,
        "baselines": {},
        "relation_contribution": dict(relation_contrib),
        "relation_build_stats": build_info.get("relation_stats", {}),
        "per_query": per_query,
        "statistical_tests": {
            "filekg_vs_best_baseline_ap": filekg_vs_best_baseline(per_query),
        },
    }
    for name, mlist in all_results.items():
        summary["baselines"][name] = aggregate(mlist)

    out_json = output_dir / "metrics.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(summary, output_dir / "report.md")
    graph.close()
    return summary


def _found(retrieved: str, target: str) -> bool:
    from src.evaluation.metrics import match_relevant

    return match_relevant(retrieved, target)


def _query_filename_leakage(queries: list[dict]) -> float:
    """查询文本与标注文件名重叠比例（越高说明评测越简单）。"""
    import re
    from pathlib import Path

    n = 0
    for qitem in queries:
        q = qitem["q"].lower()
        for fn in qitem.get("direct", []) + qitem.get("indirect", []):
            stem = Path(fn).stem.lower()
            for tok in re.split(r"[_\-\.]", stem):
                if len(tok) >= 2 and tok in q:
                    n += 1
                    break
            else:
                if stem in q:
                    n += 1
    return n / len(queries) if queries else 0.0


def _write_report(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# 对比实验报告（修正版 v2）",
        "",
        f"- 数据集: `{summary['dataset']}`",
        f"- 文件数: {summary.get('file_count')}",
        f"- 查询数: {summary.get('query_count')}",
        f"- 索引耗时: {summary.get('index_time_sec')}s",
        f"- 匹配规则: 严格文件名",
        f"- 查询-文件名泄漏率: {summary.get('query_leakage_ratio', 0):.1%}",
        "",
        "## 主要指标 (Top-20 平均)",
        "",
        "> 同时关注 **P@20**（精确率）与 **NDCG@20**（排序质量），避免仅看召回。",
        "",
        "| 方法 | MAP@20 | **P@20** | R@20 | **NDCG@20** | R_direct | R_indirect | Serendipity* | GraphDisc. | Explain | 延迟ms |",
        "|------|--------|----------|------|-------------|----------|------------|--------------|------------|---------|--------|",
    ]
    for name, m in summary.get("baselines", {}).items():
        lines.append(
            f"| {name} | {m.get('MAP@20', 0):.3f} | **{m.get('P@20', 0):.3f}** | "
            f"{m.get('R@20', 0):.3f} | **{m.get('NDCG@20', 0):.3f}** | "
            f"{m.get('Recall_direct@20', 0):.3f} | "
            f"{m.get('Recall_indirect@20', 0):.3f} | {m.get('Serendipity@20', 0):.3f} | "
            f"{m.get('GraphDiscovery@20', 0):.3f} | "
            f"{m.get('Explainability@20', 0):.3f} | {m.get('latency_ms_avg', 0):.0f} |"
        )
    lines.extend(
        [
            "",
            "*Serendipity 仅计核心关系: DEPENDS_ON, WORKFLOW_WITH, REFERENCES, 版本链等（不含 IN_FOLDER/SAME_TYPE）。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
