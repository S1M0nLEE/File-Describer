# 评测指标说明（真实、可复现）

本文档说明 README 中引用的数字**从何而来**、**如何复现**，以及**不应如何解读**。

## 原则

1. **不编造**：公开文档中的数值必须来自 `docs/evaluation_snapshot.json`，该文件由 `scripts/export_public_metrics.py` 从本地 `metrics.json` / `robustness.json` 导出。
2. **合成基准**：所有 MAP / Serendipity 指标均在**脚本生成的合成数据集**上测得，不代表真实用户桌面或第三方 Benchmark 排名。
3. **配置口径**：公开指标使用 `config_tois_eval.yaml` + `FILEKG_EVAL_PROFILE=tois_eval`，**不使用** `paper_eval` profile 下的查询 rescoring 或 Serendipity 硬编码覆盖。

## 快照文件

[`evaluation_snapshot.json`](evaluation_snapshot.json) 为可提交仓库的摘要；完整 report 在 `data/evaluation/`（gitignore）。

| 指标 | 快照字段 | 含义 |
|------|----------|------|
| MAP@20 | `metrics[].filekg_full.MAP@20` | 主合成集排序质量 |
| Serendipity@20 | `metrics[].filekg_full.Serendipity@20` | 通过核心关系边发现的「意外相关」比例 |
| 关系保持率 | `robustness.volume_file_id.relation_retention_rate` | 移动 8 个文件后 volume `file_id` 边保留率 |

## 复现步骤

```bash
# 1. 依赖与模型
pip install -r requirements.txt
python scripts/setup_models.py

# 2. 生成合成 benchmark（small ≈ 238 文件 / 40 查询，与快照规模一致）
python scripts/generate_evaluation_benchmark.py --scale small

# 3. 索引 + 评测（耗时数分钟，需真实嵌入模型）
export FILEKG_CONFIG=config_tois_eval.yaml
export FILEKG_EVAL_PROFILE=tois_eval

python scripts/run_evaluation.py --dataset filekg_main --output results_tois
python scripts/run_evaluation.py --dataset code_dependency --output results_tois
python scripts/run_robustness.py --dataset filekg_main --results-dir results_tois

# 4. 导出可提交快照
python scripts/export_public_metrics.py --results-dir data/evaluation/results_tois
pytest tests/test_metrics_snapshot.py -q
```

## 与 README 演示集的区别

| 场景 | 数据 | 用途 |
|------|------|------|
| Quick Demo | `scripts/generate_dataset.py` → `data/dataset/` | UI 体验、关系路径展示 |
| 合成指标 | `generate_evaluation_benchmark.py` → `data/benchmarks/` | MAP / Serendipity / 鲁棒性 |
| 扩展专项 | `version_lineage` / `office_workflow` / `doc_references` | 关系聚焦消融与 CI 冒烟 |
| 真实 benchmark | `download_hippocamp_subset.py` → HippoCamp | 公开个人文件 QA（见下） |

扩展专项规模与 fixture 见 [`extended_benchmark_snapshot.json`](extended_benchmark_snapshot.json)；**公开 MAP 仍只认** `evaluation_snapshot.json` / `real_benchmark_snapshot.json` 导出结果。

Demo 集含 `ground_truth.json` 标注，可通过 `tests/test_demo_ground_truth.py` 在 CI 中验证（hash 嵌入下仅作 smoke）。

## 真实公开 benchmark（HippoCamp）

- **来源**：[MMMem-org/HippoCamp](https://huggingface.co/datasets/MMMem-org/HippoCamp)
- **Subset 下载**：`python scripts/download_hippocamp_subset.py`（158 文件 / 18 QA）
- **已评快照**：[`real_benchmark_snapshot.json`](real_benchmark_snapshot.json)（adam MAP@20 **0.618**，328 文件 / 123 查询；配置见 `config_hippocamp_eval.yaml`）
- **测试**：`tests/fixtures/benchmarks/hippocamp_adam_subset.json`（真实 QA 标注）+ CI `real-benchmark` job

## 已知局限（简历/面试请如实说明）

- **Vector+SIMILAR_TO** 在 `filekg_main` 上 MAP 可略高于 FileKG-Full（见 snapshot 同目录完整 report）；FileKG 优势主要体现在 **Serendipity@20** 与 **GraphDiscovery@20**。
- 合成查询与文件名存在较高字面重叠（report 中 leakage 约 87.5%），指标偏乐观。
- `personal_mixed` 子集 MAP 低于主集，不应只报最优子集。

## 维护

更新指标后务必：

```bash
python scripts/export_public_metrics.py
pytest tests/test_metrics_snapshot.py tests/test_demo_ground_truth.py -q
```

并同步修改 README 中的数值与 [`RESUME.md`](RESUME.md)。
