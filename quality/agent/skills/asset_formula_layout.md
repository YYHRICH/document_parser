---
skill_id: asset_formula_layout
purpose: 恢复图片、公式、图注与正文的结构位置
applies_to: 图片/公式错位、图注分离、资源与说明归属异常
priority: specialist
---

# Asset and Formula Layout Skill

## 1. 目标与边界

恢复已有图片、公式、图注和说明 block 的顺序与归属。只调整结构关系和 Markdown 边界；不修改二进制资源、公式字符、alt 文本、资源路径或图片内容。

## 2. 必读证据

- asset 的稳定 ID、kind、source locator、页码和 bbox；
- caption block、公式 block 与相邻正文的 order/bbox；
- 图片/公式前后的标题、编号和引用；
- 多页 asset 或图注跨页时的邻页上下文；
- 资源路径、尺寸和 provenance 是否完整。

## 3. 判断规则

- 图注通常应与对应 asset 相邻，但必须结合 caption 编号、引用和 bbox；
- 公式不能因 Markdown 渲染失败而被改写成普通文字；
- 一个 caption 可能跨多行/多 block，不要按单行文本随意拆分；
- 多个相邻图片或公式无法唯一配对时，保留原顺序并人工复核；
- 资源缺失不是格式问题，不能凭描述生成替代图片或公式。

## 4. 允许的 Patch

- `move_block`：移动已有 asset、caption、formula 或说明 block；
- `update_asset_references`：修改已有 asset 的 `referenced_by_block_ids`，恢复图片与已有图注/正文 block 的归属；
- `update_block_markdown`：修复图片/公式与说明之间的边界；
- 只有在确有重复证据时才交给 `completeness` Skill 判断删除。

## 5. 人工复核条件

- caption 编号、asset 编号和正文引用不一致；
- 资源路径、bbox 或 provenance 缺失；
- 公式内容可能是 OCR 错误；
- 一个 caption 对应多个 asset，或一个 asset 对应多个 caption；
- 需要改变二进制内容、alt 文本或公式事实。

## 6. 输出检查

确认 asset/公式 ID、资源路径、公式文本、页码、bbox 和 provenance 均未改变，只发生必要的顺序或边界变化。

## 7. 输出 few-shot

当已有公式 block <formula-id> 只有 [[FORMULA_UNAVAILABLE]]，且输入没有 native_formula 或其他可验证来源时，规范输出为：

~~~json
{"base_revision":"<current-revision>","lineage":["<current-revision>"],"operations":[],"affected_ids":[],"evidence_refs":[],"change_kind":"none","reasoning":"这是解析器能力边界，输入没有可验证公式内容；不猜测公式，保留占位符并交给下游标记。","confidence":0.99}
~~~

只有在已有 asset、caption 和 block 的顺序证据唯一时，才输出 move_block 或 update_asset_references；不得借此改写公式、alt 文本或资源路径。
