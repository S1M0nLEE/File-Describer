# Benchmark fixtures

本目录存放**公开 benchmark 的标注/metadata**，不含完整原始文件。

| 文件 | 来源 |
|------|------|
| `hippocamp_adam_subset.json` | [HippoCamp](https://huggingface.co/datasets/MMMem-org/HippoCamp) Adam-Subset QA（5 条样例） |

完整文件下载：

```bash
python scripts/download_hippocamp_subset.py
# 或
python scripts/download_real_benchmarks.py --hippocamp --subset
```

运行真实 benchmark 集成测试：

```bash
export FILEKG_RUN_REAL_BENCHMARK=1
pytest tests/test_real_benchmark.py -m "real_benchmark and slow" -q
```
