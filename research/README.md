# Research & Evaluation Scripts

本目录存放**论文、专利、TOIS 评测**相关脚本，与日常索引/检索主路径分离。

## 日常使用请用

```bash
python scripts/generate_dataset.py
python scripts/index_directory.py data/dataset --clear
python scripts/run_evaluation.py      # 公开指标复现（仍在 scripts/）
python scripts/run_robustness.py
```

## 本目录脚本

移动自 `scripts/`，包括 patent/tois/paper 报告生成、ablation、矩阵实验等。运行前请确认 `FILEKG_CONFIG` 与 `data/evaluation/` 路径。

## 指标复现

公开 README 中的 MAP/SDR/关系保持率指标，请使用仓库根目录的 `config_tois_eval.yaml`（若存在）及 `scripts/run_evaluation.py`，输出在本地 `data/evaluation/`（不入库）。
