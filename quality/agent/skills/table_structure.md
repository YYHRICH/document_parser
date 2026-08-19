---
skill_id: table_structure
purpose: 恢复表格网格、表头、合并单元格和列顺序
applies_to: 表头错位、合并单元格错误、列漂移、表格 Markdown 结构异常
priority: specialist
---

# Table Structure Skill

## 1. 目标与边界

根据解析器提供的 cells、span、bbox 和页面关系，恢复表格的结构表达。可以调整网格、行列位置、表头/行头角色和 Markdown 展示；不能新增、删除或改写单元格事实文本。

## 2. 必读证据

- 完整 `table_id`、所有 cell ID、cell 文本和原始顺序；
- `start_row`、`start_col`、`row_span`、`col_span`、header 标记；
- 表格 bbox、页面编号、caption 和相邻 block；
- `get_cross_page_table_context()` 返回的所有续表页；
- 同一表格是否存在重复表头、续表标记或页间列宽变化。

只读取局部 cell 不足以决定列顺序时，必须读取完整表格。

## 3. 重建流程

### 3.1 先确定网格

1. 根据已有行列坐标建立最大网格；
2. 检查 span 是否覆盖冲突位置；
3. 用 bbox 的横向位置和同列上下文判断列映射；
4. 识别表头、行头和数据区，但不因语义猜测而改变文本。

### 3.2 合并单元格

- 只有存在明确 span 或视觉覆盖证据时才保留合并；
- 不要把空白 cell 自动合并成上方或左侧 cell；
- 不能通过复制文本填充被合并区域；
- 合并变化只应影响 grid/span/header role，事实词元必须保持。

### 3.3 跨页续表

读取全部相关页后，先对齐列数、重复表头和列 bbox，再判断续行。无法确认上一页末行与下一页首行属于同一记录时，保留原结构并人工复核。

## 4. 允许的 Patch

- `update_table_cell_layout`：提交已有 cell 的 cell_index、坐标、span 和 header 角色，不携带正文；
- `replace_table_cells`：兼容完整网格提交，仅在确定性重建确有必要时使用；
- `update_block_markdown`：只修复表格 Markdown 分隔线或表格前后的换行；
- 跨页任务使用包含所有相关页的 `scope_pages`。

增量 Patch 的正文由宿主从输入表格复制；如果提供 expected_text_sha256，宿主会校验
候选基于的正文仍是当前 revision。兼容路径中的 `TableCellPatch.text` 仍必须保留事实词元。

## 5. 人工复核条件

- 列数、合并范围或跨页列映射存在多个合理答案；
- cell 文本本身疑似 OCR 错误；
- 表格缺页、截断或 bbox 坐标不可用；
- 需要新增行、列、数字或单位；
- 表格 caption 与实际网格的归属不确定。

## 6. 输出检查

检查每个 cell 的事实词元多重集、span 合法性、行列索引、header 角色和表格页码；确认 Markdown 渲染有表头分隔线，且表格前后有明确换行。


## 7. 输出 few-shot

表格布局问题只输出统一候选 JSON，不输出表格 Markdown。若已有 table <table-id> 的 cell 2 需要从缺口位置恢复到第 1 行第 1 列，且正文指纹为 <sha256>，规范输出为：

~~~json
{"base_revision":"<current-revision>","scope":"page","scope_pages":[4],"lineage":["<current-revision>"],"operations":[{"operation":"update_table_cell_layout","table_id":"<table-id>","cell_layout_patches":[{"cell_index":2,"start_row":1,"start_col":1,"row_span":1,"col_span":1,"expected_text_sha256":"<sha256>"}]}],"affected_ids":[],"evidence_refs":[{"object_type":"table","object_id":"<table-id>","field_path":"cells[2].grid"}],"change_kind":"structure","reasoning":"只修复 cell 网格坐标，不携带或改写单元格正文。","confidence":0.9}
~~~

如果列映射、span 或跨页归属有多个同样合理的解释，规范输出是 operations: []、change_kind: "none"，并在 reasoning 中说明冲突证据。
