# Legacy API（已废弃）

`src/api/main.py` 属于旧版 pipeline/retrieval 栈，**请勿使用**。

## 正确入口

```bash
python scripts/run_server.py
# → src.api.app:app  (indexing + storage + search)
```

## 遗留模块（只读/迁移中）

| 路径 | 状态 |
|------|------|
| `src/pipeline/` | 废弃，由 `src/indexing/` 替代 |
| `src/retrieval/` | 废弃，由 `src/search/` 替代 |
| `src/graph/`（除 subgraph/relation_styles） | 废弃，由 `src/storage/` 替代 |
| `src/api/main.py` | 废弃 API 入口 |

现役图可视化仍使用 `src/graph/subgraph.py` 与 `relation_styles.py`（后续会迁至 `src/api/graph_viz/`）。

研究/论文/专利脚本已移至 [`research/scripts/`](../research/scripts/)。
