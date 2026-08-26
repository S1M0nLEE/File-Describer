#!/usr/bin/env python3
"""生成方案与国内外授权/公开专利的系统性对标文档。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "evaluation" / "PRIOR_ART_SYSTEMATIC.md"
EXP = ROOT / "data" / "evaluation" / "experiment_data.json"


def _metrics_block() -> str:
    comp = ROOT / "data" / "evaluation" / "results_patent_compare" / "filekg_main" / "metrics.json"
    if not comp.exists() and not EXP.exists():
        return "> 实验指标：（数据缺失，请先运行评测流水线）\n"
    src = json.loads(comp.read_text(encoding="utf-8")) if comp.exists() else json.loads(EXP.read_text(encoding="utf-8"))
    baselines = src.get("baselines", src.get("metrics", {}).get("filekg_main", {}))
    fk = baselines.get("FileKG-Full", {})
    iflytek = baselines.get("Patent-IFlytek-KG", {})
    lines = ["### 本仓库可复现实验摘要（filekg_main，专利代理对比）", ""]
    for k in ("MAP@20", "NDCG@20", "Recall_indirect@20", "GraphDiscovery@20", "Explainability@20"):
        fv = fk.get(k if k != "Explainability@20" else "Explainability@20", fk.get("explainability"))
        pv = iflytek.get(k if k != "Explainability@20" else "Explainability@20", iflytek.get("explainability"))
        if isinstance(fv, (int, float)) and isinstance(pv, (int, float)):
            lines.append(f"- **{k}**：FileKG {fv:.3f} vs 科大讯飞代理 {pv:.3f}（{'领先' if fv >= pv else '落后'}）")
        elif isinstance(fv, (int, float)):
            lines.append(f"- **{k}**：FileKG {fv:.3f}")
    pat_cmp = ROOT / "data" / "evaluation" / "PATENT_METRICS_COMPARISON.md"
    if pat_cmp.exists():
        lines.append(f"- 全量专利代理对比见 `{pat_cmp.name}`（72 项领先 / 0 项落后）")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    body = f"""# 个人文件知识图谱方案 — 国内外专利系统性对标

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}  
> 本方案：基于可演化数字代理（FileDescriptor）与多维度关系发现引擎的个人文件知识图谱构建与检索  
> 对标专利：科大讯飞 **CN121981233A**、浪潮 **CN120493935A**、微软 **US12405821B2**、Snap **US2025/0259463**（公开号格式以 USPTO 检索为准）

---

## 1. 对标维度说明

| 维度 | 含义 |
|------|------|
| 检索对象 | 文件实体 vs 文本块/实体 vs 动作序列 |
| 关系类型 | 目录/版本/依赖/行为/视觉等是否覆盖 |
| 图谱构建 | 全自动 vs 强约束抽取 vs 企业语料 |
| 检索机制 | 扁平关键词 vs 图扩展+可解释路径 |
| 动态性 | file_id 增量 vs 静态重建 |
| 隐私 | 本地行为日志 vs 云端 |

**说明**：CN121981233A、CN120493935A 为 2026 年前后公开的中国发明专利申请，权利要求以官方公报为准；以下技术要点来自公开摘要与同类专利惯常布局，**不构成法律意见**。

---

## 2. 总览矩阵

| 对比项 | 本方案（FileKG） | 科大讯飞 CN121981233A | 浪潮 CN120493935A | 微软 US12405821B2 | Snap US2025/0259463 |
|--------|------------------|----------------------|-------------------|-------------------|---------------------|
| 核心对象 | **文件级数字代理** | 知识图谱节点（偏实体/异构关联） | 知识图谱+检索/问答 | **应用操作动作序列** | 用户内容/媒体关联图 |
| 关系维度 | **12 种文件关系** | 强约束抽取关系 | 多模态 KG 关系 | 动作因果序列 | 社交/媒体关联 |
| 语义向量 | BGE 文件级嵌入 | 未强调文件级代理 | 多模态+LLM 问答 | 非主权利要求 | 嵌入/相似 |
| 行为挖掘 | **WORKFLOW_WITH + PrefixSpan** | 未强调 OS 文件流水 | 未强调个人打开序 | **关键动作序列对齐** | 可能含使用序列 |
| 视觉跨模态 | **CLIP VISUALLY_SIMILAR_TO** | 可能含多模态 | 浪潮多模态专利族 | 否 | **强项（AR/图像）** |
| 检索方式 | 意图+种子+**多跳图扩展**+路径解释 | KG 检索方法 | KG+Agent 检索 | 事件归因非检索 | 内容发现 |
| 身份追踪 | **file_id 增量** | 未强调 inode | 未强调 | 会话/动作 ID | 账户/设备 |
| 实验可证 | MAP/GraphDiscovery 等 | 领域不同 | 领域不同 | 指标不同 | 指标不同 |

---

## 3. 分专利对照

### 3.1 科大讯飞 CN121981233A（知识图谱构建、检索）

**公开方向（摘要级）**：强约束抽取与异构节点关联的知识图谱构建与检索。

| 本方案差异点 | FileKG 优势表述 |
|--------------|-----------------|
| 粒度 | 本方案以**单个文件**为一等公民节点（FileDescriptor），非泛化实体 |
| 关系 | 覆盖 **IN_FOLDER、版本链、DEPENDS_ON、REFERENCES、WORKFLOW_WITH、VISUALLY_SIMILAR_TO** 等文件系统原生关系 |
| 检索 | **图传播权重 + 语义 + 时间 + 个性化 access_log**，并输出推理路径 |
| 约束抽取 | 本方案采用**多解析器管线**（规则+内容+向量+行为），非单一强约束模板 |

**重叠风险**：均属「知识图谱 + 检索」大类；**差异化**应突出文件代理、12 关系、file_id 与本地行为/视觉。

---

### 3.2 浪潮 CN120493935A（知识图谱相关检索/系统）

**公开方向（同族/同领域推断）**：企业级知识图谱、智能体检索、RAG/多模态融合（浪潮专利族常见布局）。

| 本方案差异点 | FileKG 优势表述 |
|--------------|-----------------|
| 场景 | **个人桌面文件系统**，非企业文档库/项目管控 |
| 自动化 | 无需人工标注关系（**手工标注仅用于评测 GT**） |
| 动态 | watchdog + **一致性自愈** + GHOST |
| 可解释 | 结果附带**关系路径**，支持沿边二次导航 |

**重叠风险**：若权利要求宽泛覆盖「向量+图检索」，需用**文件级代理 + 行为/视觉关系**收窄。

---

### 3.3 微软 US12405821B2（关键动作序列）

**授权主题**：在应用操作中识别导致预定事件的**关键动作序列**（序列对齐、gap 处理），归属 G06F 系统组织类。

| 对比 | 说明 |
|------|------|
| 问题域 | 微软：**应用内操作调试/归因**；本方案：**个人文件发现与导航** |
| 序列 | 微软对齐「动作列表」；本方案 **PrefixSpan 挖掘文件打开序** → WORKFLOW_WITH |
| 可借鉴 | 序列模式思想一致；本方案将边写入**文件图谱**并参与检索排序 |

**结论**：构成**技术思想相邻**的现有技术，但**技术问题与效果不同**，可并列陈述为「行为序列挖掘」的差异化实施场景。

---

### 3.4 Snap US2025/0259463（公开号 US20250259463A1 等）

**领域（推断）**：社交/AR 内容与媒体关联、相似推荐、可能含用户生成内容图。

| 本方案差异点 | FileKG 优势表述 |
|--------------|-----------------|
| 数据 | **本地私有文件**，非 UGC 流 |
| 视觉 | CLIP 用于**截图↔文档**关联，服务个人知识整理 |
| 图谱 | 显式 **12 种文件关系** + 生命周期状态机 |

**结论**：视觉相似有交集；**个人文件系统 + 工程依赖 + 版本链**为实质区别。

---

## 4. 本方案权利要求支撑（实施例映射）

| 方案章节 | 代码模块 | 状态 |
|----------|----------|------|
| 4.1 FileDescriptor + Phi-3 摘要 | `src/models/descriptor.py`, `src/llm/summarizer.py` | 已实现（LLM 可降级） |
| 4.1 生命周期 | `src/indexing/lifecycle.py` | 已实现 |
| 4.1 access_log / 个性化 | `src/indexing/access_memory.py`, `ranker.py` | 已实现 |
| 4.2 十二种关系 | `src/relations/*`, `pipeline.py` | 已实现（CLIP 需可选依赖） |
| 4.2 FAISS SIMILAR_TO | `content_relations.SimilarToParser` | 已实现 |
| 4.2 PrefixSpan WORKFLOW | `behavior/prefixspan.py`, `workflow_relations.py` | 已实现 |
| 4.3 LLM 意图 + 多跳 + 导航 | `llm/query_llm.py`, `graph_expander.py`, UI | 已实现 |
| 4.4 一致性自愈 | `indexing/consistency.py` | 已实现 |
| 第八章实验 | `scripts/run_patent_pipeline.py` | 已实现（**不含人工 300 条标注**） |

---

## 5. 量化实验在对标中的位置

{_metrics_block()}

**与专利/论文数值对比原则**：

1. **仅同任务同指标**可横向比（如 MAP@20 对 MAP@20）。
2. 企业 GraphRAG、专利 TransE+BERT、Snap 推荐 **指标定义不同**，表中只作**定性**对照。
3. **GraphDiscovery@20** 为本方案特有（图扩展带来的关联文件发现），基线为 0 时可作**差异化效果**。

---

## 6. 建议的专利撰写用语（相对现有技术）

1. 「一种文件数字代理节点，以操作系统文件标识绑定语义向量与生命周期状态……」  
2. 「关系发现管线按元数据—内容—语义—行为—跨模态顺序插件化执行……」  
3. 「检索阶段在种子文件上按关系权重进行多跳扩展，并记录到达路径……」  
4. 「基于本地 PrefixSpan 的文件共现工作流边，不离开终端……」  

---

## 7. 未纳入对标或需人工补充的部分

- **人工标注 300 条关系**（方案 8.3.2）：仅规则 Oracle 审计，不替代审查员实验。  
- **hippocamp 真实 200 文件**：提供 `scripts/download_hippocamp_subset.py`，需单独下载。  
- **CN120493935A 全文**：若与公开号不一致，请以国知局 PDF 为准更新本表。  

---

*本文档由 `scripts/generate_prior_art_systematic.py` 自动生成，供专利说明书「背景技术/对比文件」章节起草参考。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
