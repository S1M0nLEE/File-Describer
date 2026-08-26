# Roadmap

公开版 FileKG 的后续方向（欢迎 Issue / PR）。

## 已完成

- [x] 文件索引与 VFE（volume 级 `file_id`）
- [x] 12+ 关系发现插件化 Pipeline
- [x] 向量 + 图扩展 + 多因子混合检索
- [x] FastAPI Web UI（检索 / 索引 / 图可视化）
- [x] 可选 RAG（DeepSeek API）与多模态扩展
- [x] 评测脚本与合成基准生成

## 近期（v0.2）

- [ ] 扩大公开 benchmark（≥50 查询，附标注协议说明）
- [ ] 核心路径集成测试覆盖率提升
- [ ] Docker 一键演示镜像
- [ ] 英文文档与示例 GIF 完善

## 中期

- [ ] 关系发现质量审计 UI
- [ ] 跨平台 `file_id` 文档与更多鲁棒性用例
- [ ] 可选在线 Demo（静态页 + 预索引样本库）

## 不参与本仓库范围

- 论文原稿与内部实验校准配置（请使用 `config_tois_eval.yaml` 复现公开指标）
- 含真实个人数据的 benchmark 包

## 贡献

1. Fork → 分支 `feat/...` → PR
2. 确保 `pytest tests/` 与 CI 通过
3. 新功能请附最小测试或 README 说明

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。
