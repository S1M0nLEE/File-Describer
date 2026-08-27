# Benchmark fixtures

本目录存放**公开 / 扩展 benchmark 的标注与 metadata**，不含完整原始二进制文件。

| 文件 | 来源 |
|------|------|
| `hippocamp_adam_subset.json` | [HippoCamp](https://huggingface.co/datasets/MMMem-org/HippoCamp) Adam-Subset QA（样例） |
| `version_lineage_subset.json` | 扩展合成：版本链专项 |
| `office_workflow_subset.json` | 扩展合成：办公共现专项 |
| `doc_references_subset.json` | 扩展合成：文档引用专项 |

完整合成集生成：

```bash
python scripts/generate_evaluation_benchmark.py --extended-only --clean
# 或完整生成（含 filekg_main 等）:
python scripts/generate_evaluation_benchmark.py --scale small --clean
```

HippoCamp 真实文件下载：

```bash
python scripts/download_hippocamp_subset.py
```

相关测试：`tests/test_extended_benchmarks.py`、`tests/test_real_benchmark.py`。
