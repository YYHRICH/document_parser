---
skill_id: heading_structure
purpose: 恢复标题层级、标题边界和章节归属
applies_to: 标题层级丢失、层级跳跃、标题与正文粘连
priority: specialist
---

# Heading Structure Skill

## 1. 目标与边界

恢复已有标题 block 的层级和 Markdown 边界，使标题树、编号和正文归属一致。可以修复结构标记，不能改写标题文字、编号、专有名词或章节事实。

## 2. 证据优先级

1. block 的 `kind`、现有 `heading_level` 和 `section_path`；
2. 标题编号模式，例如章/节/小节编号的连续性；
3. 标题与正文的 bbox、字体/样式元数据（若上游提供）；
4. 前后标题的层级关系和文档 outline；
5. 相邻页面中同级标题的重复格式。

单一标题的视觉样式不足以决定层级时，必须结合前后标题树。

## 3. 判断规则

- 只在证据支持时修正 `heading_level`，避免为了消除跳级而强行填充中间层级；
- 标题后粘连正文时，优先通过 `update_block_markdown` 加入结构边界；
- 标题文本中已有编号必须保持原样；
- 不把加粗正文、表格标题、图注、页眉和参考文献条目自动当成标题；
- 标题顺序异常属于 `reading_order` Skill，不在本 Skill 中用层级变化掩盖。

## 4. 允许的 Patch

- `update_heading_level`：只修改 1–6 级标题层级；
- `update_block_markdown`：只补标题与正文之间的 Markdown 换行或边界；
- 必要时声明 page/region scope，并引用标题树证据。

## 5. 人工复核条件

- 编号模式本身不连续或存在多个可能的章节树；
- 标题与正文、图注或表题无法区分；
- 需要修改标题文字才能让层级成立；
- 发现标题 block 可能在解析时缺失；
- 同一标题在不同页面出现互相冲突的层级证据。

## 6. 输出检查

验证标题文本和编号的事实词元不变；检查标题树没有产生不合理的层级跳跃、循环或章节错配；`affected_ids` 只包含实际调整的标题/边界 block。
