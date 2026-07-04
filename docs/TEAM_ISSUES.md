# FileKG 五人协作 Issue 划分（TOIS 投稿）

> 基准分支：`tois-eval`  
> 统一口径：`FILEKG_EVAL_PROFILE=tois_eval` + `config_tois_eval.yaml`  
> 参考：`说明文档.md`、`data/evaluation/results_tois/TOIS_EXPERIMENT_REPORT.md`

---

## 分工总览

| 成员 | 角色 | 负责 Epic | 核心交付 |
|------|------|-----------|----------|
| **A** | 检索与排序 | Epic-A | Ranker/Engine 诚实提升、Case Study |
| **B** | 评测与实验基础设施 | Epic-B | 实验管线、统计检验、可复现包 |
| **C** | 基准与数据 | Epic-C | 扩大 benchmark、标注协议、行为日志 |
| **D** | 论文与表述 | Epic-D | docx 全文 TOIS 化、图表、Limitations |
| **E** | 关系与系统 | Epic-E | 关系质量、消融可解释、鲁棒性 |

**协作规则**

1. 所有 PR 基于 `tois-eval` 开分支，命名：`feat/<epic>-<简述>`
2. 论文数字只引用 `data/evaluation/results_tois/`，禁止混用 `paper_eval`
3. 每周同步：每人更新对应 JSON/报告 + 在 Issue 贴复现命令与结果截图

**建议 Milestone**

- `M1 基础对齐`（2 周）：Issue #1–#8  
- `M2 实验补强`（3 周）：Issue #9–#14  
- `M3 论文定稿`（2 周）：Issue #15–#18  
- `M4 可选加分`（并行）：Issue #19–#20  

---

## Epic-A · 成员 A：检索与排序

### Issue #1 【A】梳理并文档化 Ranker 权重与 TOIS 边界

**背景**：TOIS 禁止查询级 rescoring，但 `config_tois_eval.yaml` 中 relation_weights 仍影响结果，需在论文中可解释。

**任务**

- [ ] 阅读 `src/search/ranker.py`、`config_tois_eval.yaml`
- [ ] 输出 `docs/RANKER_TOIS.md`：各权重含义、与 SDR/MAP 的关系
- [ ] 确认 `tois_eval` 下 `_query_rescore_enabled()` 为 false

**验收**：文档 PR 合并；团队 review 通过

**依赖**：无  
**估时**：2d

---

### Issue #2 【A】优化诚实配置下的 MAP（不含查询作弊）

**背景**：合成集 MAP 0.691 < SIM 0.711，需在**不**恢复 `_paper_rescore_filekg` 前提下尝试改进。

**任务**

- [ ] 只调 `config_tois_eval.yaml` 的 search/relation_weights（记录 grid）
- [ ] 重跑 `run_evaluation.py --all --config config_tois_eval.yaml`
- [ ] 对比 MAP 与 SDR 是否同时下降；更新 `results_tois/`

**验收**：提交 config 变更 + 前后对比表；SDR 仍 ≥ 2/3 数据集领先 SIM

**依赖**：#1  
**估时**：5d

---

### Issue #3 【A】Case Study：可解释路径可视化（3–5 条查询）

**任务**

- [ ] 从 `code_dependency` / `personal_mixed` 选 FileKG 赢 SDR 的查询
- [ ] 导出 Top-20 结果 + `explanation_paths` 为 JSON/Markdown
- [ ] 供成员 D 写入论文 6.x 案例分析节

**验收**：`data/evaluation/case_studies/` 下 ≥3 个案例文件

**依赖**：无  
**估时**：3d

---

## Epic-B · 成员 B：评测与实验基础设施

### Issue #4 【B】固化 TOIS 一键复现与 CI  smoke test

**任务**

- [ ] 完善 `scripts/run_tois_experiments.py` README 片段
- [ ] 新增 `.github/workflows/tois-smoke.yml`：仅跑 `personal_mixed` 小规模评测
- [ ] `validate_tois()` 失败时 CI 标红

**验收**：PR 触发 workflow 绿；本地与 CI 结果一致

**依赖**：无  
**估时**：3d

---

### Issue #5 【B】统计检验增强：Bootstrap CI + 多重比较说明

**背景**：当前 p 值均不显著，TOIS 需要效应量与置信区间。

**任务**

- [ ] 在 `src/evaluation/statistics.py` 增加 bootstrap CI（MAP、SDR）
- [ ] `generate_tois_statistics.py` 输出 CI 到 JSON
- [ ] `TOIS_EXPERIMENT_REPORT.md` 增加表格

**验收**：`tois_statistics.json` 含 `map_ci_95`、`sdr_ci_95`

**依赖**：无  
**估时**：4d

---

### Issue #6 【B】消融实验 redesign（解决 SIMILAR_TO 反直觉）

**背景**：禁用 SIMILAR_TO 后 MAP 反升 +0.7%，与论文叙事冲突。

**任务**

- [ ] 分析原因（`scripts/run_ablation.py` + per-query 日志）
- [ ] 设计更合理消融：如「仅结构边」「仅语义边」「完整 FileKG」
- [ ] 在 `filekg_main` + `personal_mixed` 双数据集重跑

**验收**：新 `ablation.json` + 简短分析 Markdown；成员 D 可引用

**依赖**：#9（C 扩查询后更佳）  
**估时**：5d

---

### Issue #7 【B】Reproducibility Package 打包

**任务**

- [ ] 脚本 `scripts/export_repro_bundle.sh`：配置 + 标注 + results_tois + 说明
- [ ] 排除 `data/chroma/` 等大文件
- [ ] Zenodo/附录清单 `docs/REPRO_CHECKLIST.md`

**验收**：他人按 checklist 可在 1 天内复现主表数字（误差 <0.01）

**依赖**：#4、#5  
**估时**：3d

---

## Epic-C · 成员 C：基准与数据

### Issue #8 【C】扩大 personal_mixed 至 ≥50 查询

**任务**

- [ ] 扩展 `scripts/generate_evaluation_benchmark.py`
- [ ] 覆盖：版本链、工作流、跨目录、代码依赖四类模板
- [ ] 更新 `annotations/personal_mixed.json`

**验收**：query_count ≥50；registry 更新；可索引构建成功

**依赖**：无  
**估时**：5d

---

### Issue #9 【C】标注协议与 Cohen's κ

**任务**

- [ ] 编写 `docs/ANNOTATION_GUIDE.md`（direct/indirect 定义、SDR 相关标准）
- [ ] 2 人独立标注 20 条查询子集
- [ ] `scripts/compute_relation_human_precision.py` 或新脚本算 κ

**验收**：论文表 1 旁注 κ 值为实测；替换占位 0.79 若不同

**依赖**：#8 部分查询  
**估时**：5d

---

### Issue #10 【C】真实脱敏个人文件库 pilot（≥1 人）

**任务**

- [ ] 收集 1 名成员脱敏目录（30–80 文件）
- [ ] 手工标注 15–20 查询
- [ ] 注册为新 dataset `personal_real_pilot` + 接入 `run_evaluation.py`

**验收**：`results_tois/personal_real_pilot/metrics.json` 存在

**依赖**：#8 标注规范  
**估时**：7d（含伦理/脱敏 review）

---

### Issue #11 【C】行为日志与工作流边质量

**任务**

- [ ] 审查 `inject_benchmark_behavior.py` 与 `workflow_relations.py`
- [ ] 统计 WORKFLOW_WITH 边数量、覆盖查询比例
- [ ] 不足则改进 session 注入策略

**验收**：报告写入 `data/evaluation/results_tois/workflow_audit.md`；personal 上 WORKFLOW 消融 SDR 降幅可复现

**依赖**：无（与 E 协作）  
**估时**：4d

---

## Epic-D · 成员 D：论文与表述

### Issue #12 【D】全文数字与 tois_eval 对齐审查

**任务**

- [ ] 通读 docx，搜索：`15.2`、`0.39`、`p<0.01`、`全面显著`、`24名`、`志愿者`
- [ ] 与 `placeholder_mapping.json`、`tois_statistics.json` 交叉核对
- [ ] 运行 `sync_tois_prose.py` 后仍残留的 manually fix

**验收**：审查清单 `docs/PAPER_AUDIT.md` 全部勾选

**依赖**：B 的 #5 统计输出  
**估时**：3d

---

### Issue #13 【D】重写 Abstract / Introduction / Conclusion（TOIS 叙事）

**主轴**：SDR 优势 + 可解释路径 + VFE 适度增益 + 动态鲁棒性；**不写**全面 MAP 领先。

**任务**

- [ ] 三稿英文或中文（与投稿语言一致）
- [ ] 贡献点 3–4 条 bullet 与实测数字一致
- [ ] 成员 A/B review

**验收**：PR 更新 docx 或 `docs/paper/` 下 md 源稿

**依赖**：#12  
**估时**：5d

---

### Issue #14 【D】第 6 章实验节重写 + 新增 Limitations

**任务**

- [ ] 6.1 设定：明确 `tois_eval`、SDR 定义、数据集规模
- [ ] 6.2–6.6 各节文字与 `results_tois` 表一致
- [ ] 6.7 用户研究：改 Future Work 或删表
- [ ] 新增 Limitations 小节（合成基准、样本量、无用户实验）

**验收**：成员 B 核对每个表格脚注数字

**依赖**：#3 case study、#5 CI、#6 消融  
**估时**：7d

---

### Issue #15 【D】图表重制

**任务**

- [ ] 表 2/4：从 `results_tois` 自动生成 LaTeX/Word 表（脚本或手工）
- [ ] 图：系统架构、Case Study 路径示意、冷启动/鲁棒性曲线

**验收**：图表源文件 + 嵌入 docx

**依赖**：#3、#5  
**估时**：4d

---

## Epic-E · 成员 E：关系与系统

### Issue #16 【E】关系精确率人工抽检（表 1）

**任务**

- [ ] 对 DEPENDS_ON、WORKFLOW_WITH、SIMILAR_TO 各抽 30 边
- [ ] 人工判对错，更新 `relation_precision.json`
- [ ] 与 `run_relation_audit.py` 输出对比

**验收**：`data/evaluation/results_tois/relation_precision_human.json`

**依赖**：无  
**估时**：4d

---

### Issue #17 【E】动态鲁棒性实验文档化与复验

**任务**

- [ ] 复核 `dynamic_robustness.json`、`robustness.json`
- [ ] 确保 Path 基线 `dynamic_mode` 行为有文档
- [ ] 补充 FileKG vs Path 降幅对比表给成员 D

**验收**：`docs/ROBUSTNESS.md` + 数字与 JSON 一致

**依赖**：无  
**估时**：3d

---

### Issue #18 【E】冷启动曲线与正文对齐

**任务**

- [ ] 检查 `cold_start_curve.json` 是否仍含 paper_eval floor
- [ ] `tois_eval` 下重跑并更新表 5 占位符
- [ ] 删除不符合实测的「0.451 vs 0.421」表述

**验收**：fill 后表 5 与 JSON 一致；#12 审查通过

**依赖**：B 的 #4 管线  
**估时**：3d

---

### Issue #19 【E】`get_neighbors` 与多关系检索回归测试

**任务**

- [ ] 为 `memory_graph.get_neighbors` 写测试：同节点 IN_FOLDER + WORKFLOW_WITH 均保留
- [ ] 防止回归导致 SDR/消融异常

**验收**：`tests/test_memory_graph_neighbors.py` 进 CI

**依赖**：无  
**估时**：2d

---

## 可选 Issue（五人协商认领）

### Issue #20 【C+D】用户研究 pilot（N≥12）

**任务**：within-subject，FileKG vs Vector+Metadata，指标：任务成功率、SUS、路径理解度。

**验收**：可写入论文 6.7 的真实数据；否则保持 Future Work

**估时**：2–3 周

---

### Issue #21 【B】公开 baseline 对齐 GraphRAG / dense rerank

**任务**：增加 1 个现代 Graph-RAG 或 cross-encoder rerank 基线（若 TOIS 审稿要求）

**估时**：5d

---

## 依赖关系简图

```
#8 扩查询 ──► #9 κ ──► #10 真实库
                │
#1 Ranker文档 ──► #2 诚实调参 ──► #3 Case Study ──► #14 实验节 / #15 图表
                │
#4 CI/smoke ──► #5 Bootstrap ──► #7 Repro bundle
                │
#11 工作流 ──► #6 消融 redesign
                │
#16 关系抽检 ──► #12 数字审查 ──► #13 Abstract ──► 投稿
#17 #18 鲁棒/冷启动 ──┘
```

---

## GitHub 标签建议

| 标签 | 用途 |
|------|------|
| `epic-A` … `epic-E` | 成员负责域 |
| `milestone-M1` … `M4` | 阶段 |
| `paper` | 论文/docx |
| `experiment` | 需重跑实验 |
| `blocked` | 等待他人输出 |

---

## 第一周建议排期（Kick-off）

| 成员 | 优先 Issue |
|------|------------|
| A | #1 → #3 |
| B | #4 → #5 |
| C | #8 → #11 |
| D | #12（与 B 同步要 statistics JSON） |
| E | #16 → #19 |

---

## 创建 GitHub Issue 命令模板

```bash
gh issue create --title "【A】#1 梳理 Ranker 与 TOIS 边界" \
  --body-file docs/issues/issue-01.md \
  --label "epic-A,experiment,milestone-M1" \
  --milestone "M1 基础对齐"
```

可将各 Issue 正文复制为 `docs/issues/issue-XX.md` 后批量创建。
