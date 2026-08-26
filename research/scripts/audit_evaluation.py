#!/usr/bin/env python3
"""审计实验结果真实性：标注泄漏、匹配宽松度、指标定义、关系贡献等。"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

K = 20


def match_loose(retrieved: str, target: str) -> bool:
    r = retrieved.lower().replace("\\", "/")
    t = target.lower().replace("\\", "/")
    return r == t or r.endswith("/" + t) or t in r


def match_strict(retrieved: str, target: str) -> bool:
    name = Path(retrieved.replace("\\", "/")).name.lower()
    return name == target.lower() or name == Path(target).name.lower()


def filename_in_query(query: str, filenames: list[str]) -> list[str]:
    q = query.lower()
    hits = []
    for fn in filenames:
        stem = Path(fn).stem.lower()
        for token in re.split(r"[_\-\.]", stem):
            if len(token) >= 2 and token in q:
                hits.append(fn)
                break
        if stem in q or fn.lower() in q:
            hits.append(fn)
    return list(set(hits))


def main() -> None:
    gt_path = ROOT / "data" / "benchmarks" / "filekg_main" / "ground_truth.json"
    metrics_path = ROOT / "data" / "evaluation" / "results" / "filekg_main" / "metrics.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    print("=" * 60)
    print("1. 数据集与标注来源")
    print("=" * 60)
    files = list((ROOT / "data" / "benchmarks" / "filekg_main").rglob("*"))
    file_count = sum(1 for f in files if f.is_file() and f.name != "ground_truth.json")
    noise = sum(1 for f in files if f.is_file() and "noise" in str(f))
    print(f"  总文件: {file_count}, 噪声文件: {noise} ({noise/file_count*100:.0f}%)")
    print(f"  查询数: {len(gt['queries'])}")
    print("  [!] 数据与 ground_truth 均由 generate_evaluation_benchmark.py 同脚本生成")
    print("  [!] 非独立第三方标注 → 存在「自指标注」风险")

    print("\n" + "=" * 60)
    print("2. 查询-文件名泄漏（查询词是否出现在目标文件名中）")
    print("=" * 60)
    leak_direct = 0
    leak_any = 0
    for qitem in gt["queries"]:
        q = qitem["q"]
        all_f = qitem.get("direct", []) + qitem.get("indirect", [])
        leaked = filename_in_query(q, all_f)
        if leaked:
            leak_any += 1
        if any(f in qitem.get("direct", []) for f in leaked):
            leak_direct += 1
    n = len(gt["queries"])
    print(f"  至少泄漏到任一相关文件: {leak_any}/{n} ({leak_any/n*100:.0f}%)")
    print(f"  泄漏到 direct 标注: {leak_direct}/{n} ({leak_direct/n*100:.0f}%)")

    print("\n" + "=" * 60)
    print("3. 匹配规则：宽松 vs 严格")
    print("=" * 60)
    # 找宽松匹配误命中
    all_names = [f.name for f in files if f.is_file() and f.name != "ground_truth.json"]
    false_pos_examples = []
    for target in ["main.py", "data", "utils.py", "test"]:
        for name in all_names:
            if match_loose(name, target) and not match_strict(name, target):
                false_pos_examples.append((target, name))
    print(f"  宽松规则 `target in path` 潜在误匹配: {len(false_pos_examples)} 例")
    for t, n in false_pos_examples[:8]:
        print(f"    '{t}' 误匹配 -> {n}")

    print("\n" + "=" * 60)
    print("4. 关系贡献统计（FileKG 实际用了哪些边）")
    print("=" * 60)
    rc = metrics.get("relation_contribution", {})
    rel_totals: dict[str, int] = defaultdict(int)
    for q, rels in rc.items():
        for rt, c in rels.items():
            rel_totals[rt] += c
    total_edges = sum(rel_totals.values())
    for rt, c in sorted(rel_totals.items(), key=lambda x: -x[1]):
        print(f"  {rt}: {c} ({c/total_edges*100:.1f}%)")
    core = rel_totals.get("DEPENDS_ON", 0) + rel_totals.get("WORKFLOW_WITH", 0) + rel_totals.get("REFERENCES", 0)
    print(f"  [!] DEPENDS_ON+WORKFLOW+REFERENCES 合计: {core} ({core/max(total_edges,1)*100:.1f}%)")
    print("  [!] 主要依赖 IN_FOLDER / SAME_TYPE，与方案强调的「核心创新关系」不一致")

    print("\n" + "=" * 60)
    print("5. 指标内在矛盾检查")
    print("=" * 60)
    fk = metrics["baselines"]["FileKG-Full"]
    print(f"  P@20={fk['P@20']:.3f} 但 R@20={fk['R@20']:.3f}")
    print("  → Top-20 中仅约 2 个相关/20，靠「捞全」拉高召回，排序质量一般")
    print(f"  NDCG@20={fk['NDCG@20']:.3f} 远低于 MAP@20={fk['MAP@20']:.3f}")
    print("  → 相关文件常排在靠后位置")
    print(f"  Serendipity@20={fk['Serendipity@20']:.3f}")
    print("  → 当前实现将 IN_FOLDER/SAME_TYPE 等非 SIMILAR_TO 边均计为「意外发现」")

    print("\n" + "=" * 60)
    print("6. 重跑抽样查询（严格匹配 + 修正 Serendipity）")
    print("=" * 60)
    from src.indexing.builder import IndexBuilder
    from src.indexing.embedder import Embedder
    from src.search.engine import SearchEngine
    from src.storage.factory import create_stores
    from src.evaluation.metrics import average_precision, recall_subset, relevant_set

    Embedder.reset()
    graph, chroma = create_stores()
    ds = ROOT / "data" / "benchmarks" / "filekg_main"
    IndexBuilder(graph, chroma).build(ds, clear=True)
    engine = SearchEngine(graph, chroma)

    sample = gt["queries"][:5]
    for qitem in sample:
        q = qitem["q"]
        r_full = engine.search(q)["results"][:K]
        r_vec = engine.search(q, expand_graph=False)["results"][:K]
        dset, iset = set(qitem["direct"]), set(qitem["indirect"])
        all_rel, _, _ = relevant_set(list(dset), list(iset))

        def names_strict(results):
            return [x["name"] for x in results]

        ap_loose_f = average_precision([x["name"] for x in r_full], all_rel)
        ap_strict_f = average_precision(names_strict(r_full), all_rel)  # still uses loose in AP
        # recompute strict AP
        ap_s = 0.0
        hits = 0
        for i, r in enumerate([x["name"] for x in r_full], 1):
            if any(match_strict(r, rel) for rel in all_rel):
                hits += 1
                ap_s += hits / i
        ap_s = ap_s / len(all_rel) if all_rel else 0

        ri_loose = recall_subset([x["name"] for x in r_full], iset, K)
        ri_strict = sum(
            1 for rel in iset if any(match_strict(x["name"], rel) for x in r_full)
        ) / len(iset) if iset else 0

        print(f"\n  Q: {q}")
        print(f"    FileKG Top3: {[x['name'] for x in r_full[:3]]}")
        print(f"    Vector Top3: {[x['name'] for x in r_vec[:3]]}")
        print(f"    MAP 宽松/严格: {ap_loose_f:.2f} / {ap_s:.2f}")
        print(f"    R_indirect 宽松/严格: {ri_loose:.2f} / {ri_strict:.2f}")
        nonsim_paths = [
            p.get("rel_type")
            for x in r_full
            for p in (x.get("explanation_paths") or [])
            if p.get("rel_type") != "SIMILAR_TO"
        ]
        print(f"    非SIMILAR边类型: {set(nonsim_paths) or '无'}")

    graph.close()

    print("\n" + "=" * 60)
    print("7. 审计结论摘要")
    print("=" * 60)
    print("""
  [真实/可信]
  - 五类基线均已实现并同索引公平对比
  - FileKG 在 MAP/R@20 上相对向量基线有提升（约 +4~7% MAP）
  - 向量基线 Serendipity=0、FileKG>0 的相对差异方向正确

  [夸大/需谨慎]
  - 合成数据自标注，难度低于真实个人文件场景
  - 仅 133 文件，Top-20 占全集 15%，召回易偏高
  - 匹配规则过宽 (`文件名 in 路径`)
  - Serendipity 将 IN_FOLDER/SAME_TYPE 计入，0.94 显著高估
  - 关系贡献几乎无 DEPENDS_ON/WORKFLOW_WITH，与报告叙事不符
  - P@20≈0.10 说明结果列表噪声大，用户体验未必好

  [建议]
  - 使用严格文件名匹配重算指标
  - Serendipity 仅计 DEPENDS_ON/WORKFLOW/REFERENCES/HAS_VERSION 等
  - 引入 HippoCamp 等独立真实数据
  - 报告同时给出 P@20 与 NDCG，避免只强调 MAP/Recall
""")


if __name__ == "__main__":
    main()
