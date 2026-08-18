---
skill_id: reading_order
purpose: 恢复 block 的阅读顺序和段落边界
applies_to: 双栏、页眉页脚、跨页段落、标题正文顺序异常
priority: specialist
---

# Reading Order Skill

## 1. 目标与边界

修复已有 block 的排列顺序、栏位切换和段落边界，使 Markdown 顺序尽量接近原文视觉阅读顺序。只移动或分隔已有 block；不改写事实文本，不删除疑似正文，也不凭语义补齐缺失段落。

## 2. 需要读取的证据

按以下顺序读取：

1. `get_page_context(page_number)`：当前页全部 block、页码和短预览；
2. block 的 `order_index`、`anchor.bbox`、`anchor.page`、`kind` 和 `section_path`；
3. `get_neighbor_page_context()`：判断跨页段落和页眉页脚连续性；
4. 文档 outline：确认标题与正文的归属；
5. 对双栏页，读取同页所有 block，不要只看局部片段。

## 3. 判断流程

### 3.1 单栏页面

- 以视觉纵向位置为主，通常从上到下排列；
- 同一段落被拆成多个 block 时，结合相邻 bbox、标点和行距判断是否应相邻；
- 标题应出现在其正文之前，图注应紧邻对应 asset；
- 页眉/页脚只有在多页重复、位置稳定且与正文语义无关时，才可作为结构性重复处理。

### 3.2 双栏页面

- 先确认栏位边界，再在每一栏内部按纵向排序；
- 默认读取顺序是左栏从上到下，再右栏从上到下，但必须用标题、段落连续性和页面布局验证；
- 不能仅凭 `x` 坐标把跨栏标题、通栏表格或通栏图片拆开；
- 两种栏序都合理时，不自动移动，转人工复核。

### 3.3 页眉页脚

只有同时满足“跨页重复 + bbox 位于页顶/页底 + 不属于正文语义”时，才考虑从正文顺序中排除。不要因短文本、页码或公司名看起来像页眉就直接删除。

## 4. 允许的 Patch

- `move_block`：交换已有 block 的顺序；
- `update_block_markdown`：只补段落边界、换行或明显的 Markdown 边界；
- 必要时使用 page scope，并把当前页和受影响邻页放入 `scope_pages`。

不使用 `remove_block`；重复 block 的删除由 `completeness` Skill 负责。

## 5. 人工复核条件

- 双栏阅读方向无法由 bbox 和标题/段落证据确定；
- 页眉页脚与正文内容相同或可能是章节信息；
- 段落跨页时缺少下一页或上一页证据；
- block bbox 缺失、坐标系不一致或页面旋转信息不明；
- 移动一个 block 会同时改变多个章节的归属。

## 6. 输出检查

确认移动前后每个 block 的文本、ID、页码、bbox 和 provenance 不变；`affected_ids` 必须包括被移动 block 以及顺序边界涉及的对象，并用 page/block 的 bbox 和相邻结构填充 `evidence_refs`。
