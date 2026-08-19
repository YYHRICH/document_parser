# 表格增量 Patch 复测（P1）

## 变更

新增 `update_table_cell_layout` 操作。Agent 只提交已有单元格的 `cell_index`、坐标、行列跨度和表头属性；宿主从当前 revision 复制单元格正文，并可用 `expected_text_sha256` 拒绝过期候选。原有 `replace_table_cells` 保留为完整网格重建的兼容路径。

## 验证

- 定向 Agent 测试：60 passed。
- 全量测试：267 passed，1 xfailed。
- 真实 DeepSeek/Agno 评测：6/6 accepted，0 agent error。
- 6 个样本的规范化文档 SHA-256 与 P0 基线逐一相同。
- 表格事实召回保持不变：MinerU `5/6`，Docling `5/6`。
- 表格 MinerU 仍记录 `table-001` 为变更对象；Docling 仍主要修改 block 级结构。

## 结论

本轮没有在现有 6 个样本上测出额外的事实召回或 Markdown 改善，因此不能宣称质量指标提升；但表格修复从“模型重写正文”收敛为“模型只提议布局、宿主保留正文”，并增加了过期正文指纹保护。下一步应增加一个专门破坏单元格坐标/span、但正文完整的 fixture，并在 execution 记录中持久化最终 operation 类型，才能单独量化该优化。

基线备份：`quality-before-table-p1/`；本轮产物：`quality/`。
