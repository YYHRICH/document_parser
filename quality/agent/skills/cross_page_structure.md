---
skill_id: cross_page_structure
purpose: 处理段落、表格、脚注和图注的跨页连续性
applies_to: 续表、跨页段落、脚注跨页、页间结构断裂
priority: specialist
---

# Cross-page Structure Skill

## 1. 目标与边界

通过多页证据恢复跨页结构关系。跨页任务不允许只看当前页，也不允许把“相邻”直接当成“连续”。所有 Patch 必须保留原始页码、bbox、ID 和 provenance。

## 2. 必读证据

1. 全篇 `document_index`，确认页码范围；
2. 目标页和前后邻页的 page context；
3. 对表格调用完整 cross-page table context；
4. 读取标题、续表标记、重复表头、脚注编号、图注编号和 block 顺序；
5. 对跨页段落检查句末标点、列表编号、段落样式和 section path。

## 3. 判断流程

### 3.1 续表

同时满足以下证据时才可合并/重排：

- 下一页存在明确续表标记或重复表头；
- 两页列数、列顺序和 bbox 对齐；
- 首行/末行的 cell 结构可以连续解释；
- 没有新的 caption、标题或分节边界。

### 3.2 跨页段落和脚注

- 句子未结束、段落样式连续且下一页紧接同一 section 时，可考虑移动已有 block；
- 脚注必须依据编号和页面位置关联，不可按语义猜测；
- 新页面出现标题、分页符或独立 caption 时，默认视为新结构。

## 4. 允许的 Patch

- `move_block`：恢复跨页 block 顺序；
- `replace_table_cells`：恢复已证实的续表网格；
- `update_block_markdown`：修复跨页段落或表格的边界换行；
- `scope_pages` 必须覆盖证据页和受影响页，不能只声明一页。

## 5. 人工复核条件

- 缺少任一相邻页或页码证据；
- 续表列漂移、合并单元格和行归属不唯一；
- 跨页 block 可能是新段落、新脚注或新 caption；
- 需要补造被解析器漏掉的内容；
- 任何页码、bbox 或 provenance 冲突。

## 6. 输出检查

检查跨页对象的所有 page/bbox/source 信息保持；确认 Patch 不会把不同章节、不同表格或不同脚注错误合并。

## 7. 输出 few-shot

当上一页末尾 block 和下一页开头 block 的顺序、章节和 bbox 证据唯一时，规范输出为：

~~~json
{"base_revision":"<current-revision>","scope":"page","scope_pages":[5,6],"lineage":["<current-revision>"],"operations":[{"operation":"move_block","block_id":"<next-page-block>","before_block_id":"<following-block>"}],"affected_ids":[],"evidence_refs":[{"object_type":"block","object_id":"<next-page-block>","field_path":"source_anchor.page_number"},{"object_type":"block","object_id":"<following-block>","field_path":"order_index"}],"change_kind":"structure","reasoning":"使用两页的 source anchor、bbox 和段落连续性恢复已有 block 顺序，不拼接或补写缺失正文。","confidence":0.88}
~~~
跨页证据不足时必须 no-op，并在 reasoning 中列出缺失页或冲突对象。
