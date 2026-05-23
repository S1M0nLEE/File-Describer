#!/usr/bin/env python3
"""生成专利撰写用文档包：权利要求对照表、附图（Mermaid）、实施例说明、真实性声明。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATENT = ROOT / "data" / "evaluation" / "patent"
EMBODIMENT = ROOT / "data" / "evaluation" / "results_patent_embodiment"
SYNTH = ROOT / "data" / "evaluation" / "results_patent_compare"


def _load_metrics(root: Path, ds: str) -> dict | None:
    p = root / ds / "metrics.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _fk(m: dict | None, key: str) -> str:
    if not m:
        return "数据缺失"
    v = m.get("baselines", {}).get("FileKG-Full", {}).get(key)
    return f"{v:.4f}" if isinstance(v, (int, float)) else "数据缺失"


def write_claim_chart() -> None:
    lines = [
        "# 权利要求特征对照表（Claim Chart）",
        "",
        "> 供说明书「发明内容 / 具体实施方式」与审查意见答复使用。",
        "",
        "| 特征编号 | 技术特征（摘要） | 代码模块 | 实施例证据 |",
        "|----------|------------------|----------|------------|",
        "| C1 | 文件数字代理 FileDescriptor（file_id、摘要、向量、生命周期） | `src/models/descriptor.py`, `indexing/lifecycle.py` | 索引日志 `metrics.json` → `relation_build_stats` |",
        "| C2 | 插件化关系发现管线（元数据→内容→语义→行为→视觉） | `src/relations/pipeline.py` | `config_patent_full.yaml` 全开关评测 |",
        "| C3 | SIMILAR_TO（FAISS/向量近邻） | `content_relations.SimilarToParser` | 合成/真实 metrics 中 `similar_to` 边计数 |",
        "| C4 | DEPENDS_ON / REFERENCES | `DependsOnParser`, `ReferencesParser` | HippoCamp 邮件/PDF 引用边 |",
        "| C5 | WORKFLOW_WITH（PrefixSpan） | `behavior/prefixspan.py`, `workflow_relations.py` | `access_log` + `workflow` 配置 |",
        "| C6 | VISUALLY_SIMILAR_TO + NEAR_DUPLICATE（多路融合） | `relations/visual_fusion/` | `VISUAL_FUSION_SPEC.md`、B0–B8 |",
        "| C7 | 多跳图扩展 + 路径可解释 | `graph_expander.py`, `ranker.py` | **GraphDiscovery@20**, **Explainability@20** |",
        "| C8 | 一致性自愈 / GHOST | `indexing/consistency.py` | `run_robustness.py` 输出 |",
        "| C9 | 本地行为日志个性化 | `access_memory.py` | `search.weights.personal` |",
        "",
        "## 与对比文件区别（撰写要点）",
        "",
        "| 对比文件 | 区别特征 |",
        "|----------|----------|",
        "| 科大讯飞/浪潮 KG 专利 | **文件级代理** + OS 关系 + **检索路径输出** |",
        "| 微软 US12405821 | 动作序列写入**文件图谱边**并参与排序，非应用调试 |",
        "| Snap 视觉专利 | 本地私有文件 + **12 关系** 联合检索，非 UGC 推荐流 |",
        "",
    ]
    (PATENT / "PATENT_CLAIM_CHART.md").write_text("\n".join(lines), encoding="utf-8")


def write_figures() -> None:
    text = """# 专利附图说明（Mermaid 源图）

## 图1 系统架构

```mermaid
flowchart TB
  subgraph client [用户侧]
    UI[Web/API]
    Watcher[文件监视器]
  end
  subgraph core [FileKG 核心]
    FD[FileDescriptor]
    Pipe[关系发现管线]
    IDX[索引构建器]
    SRCH[检索引擎]
  end
  subgraph store [存储]
    Graph[(图存储 Neo4j/内存)]
    Chroma[(向量库 Chroma)]
  end
  UI --> SRCH
  Watcher --> IDX
  IDX --> FD
  IDX --> Pipe
  Pipe --> Graph
  IDX --> Chroma
  SRCH --> Graph
  SRCH --> Chroma
```

## 图2 关系发现管线顺序

```mermaid
flowchart LR
  M[元数据关系] --> C[内容引用/依赖]
  C --> S[SIMILAR_TO]
  S --> B[PrefixSpan 行为]
  B --> V[VISUALLY_SIMILAR_TO]
```

## 图3 检索流程

```mermaid
sequenceDiagram
  participant Q as 查询
  participant P as 意图解析
  participant Seed as 种子检索
  participant G as 图扩展
  participant R as 多因子排序
  Q->>P: 时间/类型/关键词
  P->>Seed: 向量+BM25
  Seed->>G: 多跳关系传播
  G->>R: 路径+权重
  R-->>Q: Top-K + 解释路径
```

## 图4 文件生命周期

```mermaid
stateDiagram-v2
  [*] --> ACTIVE
  ACTIVE --> DORMANT: 长期未访问
  DORMANT --> ACTIVE: 再次访问
  ACTIVE --> DEPRECATED: 观测期
  DEPRECATED --> GHOST: 删除/移动
  GHOST --> [*]: 自愈清理
```
"""
    (PATENT / "PATENT_FIGURES.md").write_text(text, encoding="utf-8")


def write_embodiment_metrics() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    synth = _load_metrics(SYNTH, "filekg_main")
    adam = _load_metrics(EMBODIMENT, "hippocamp_adam") or _load_metrics(
        ROOT / "data/evaluation/results_real", "hippocamp_adam"
    )

    lines = [
        "# 专利全功能实施例 — 指标摘要",
        "",
        f"> 生成时间 UTC: {now}",
        f"> 全功能配置: `config_patent_full.yaml` / HippoCamp: `config_patent_hippocamp.yaml`",
        "",
        "## 数据真实性",
        "",
        "- 下列数值**仅**来自对应目录下 `metrics.json`，由 `run_evaluation.py` 自动计算。",
        "- 「专利-*」为**同基准代理实现**（`patent_baselines.py`），非各公司官方实验表。",
        "",
        "## 合成回归集 filekg_main（中文场景 · patent_full）",
        "",
        "| 指标 | FileKG-Full |",
        "|------|-------------|",
        f"| MAP@20 | {_fk(synth, 'MAP@20')} |",
        f"| NDCG@20 | {_fk(synth, 'NDCG@20')} |",
        f"| GraphDiscovery@20 | {_fk(synth, 'GraphDiscovery@20')} |",
        f"| Explainability@20 | {_fk(synth, 'Explainability@20')} |",
        "",
        "## 真实集 hippocamp_adam（英文 · bge-en · 视觉开启）",
        "",
        "| 指标 | FileKG-Full | BM25 |",
        "|------|-------------|------|",
    ]
    if adam:
        bm25 = adam.get("baselines", {}).get("BM25", {})
        bm25_map = bm25.get("MAP@20")
        bm25_s = f"{bm25_map:.4f}" if isinstance(bm25_map, (int, float)) else "数据缺失"
        lines += [
            f"| MAP@20 | {_fk(adam, 'MAP@20')} | {bm25_s} |",
            f"| GraphDiscovery@20 | {_fk(adam, 'GraphDiscovery@20')} | — |",
            f"| Explainability@20 | {_fk(adam, 'Explainability@20')} | — |",
            f"| eval_profile | `{adam.get('eval_profile', '—')}` |",
        ]
    else:
        lines.append("| （未跑 embodiment 评测） | 数据缺失 | 数据缺失 |")

    lines += [
        "",
        "## 复现",
        "",
        "```bash",
        "python scripts/run_patent_embodiment.py --quick",
        "```",
        "",
    ]
    (PATENT / "PATENT_EMBODIMENT_METRICS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    PATENT.mkdir(parents=True, exist_ok=True)
    write_claim_chart()
    write_figures()
    write_embodiment_metrics()
    print(f"专利文档包已写入: {PATENT}")


if __name__ == "__main__":
    main()
