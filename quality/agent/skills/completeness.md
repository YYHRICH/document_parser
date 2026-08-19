---
skill_id: completeness
purpose: 识别重复、空洞、孤立和明显缺失的结构
applies_to: 空 block、重复 block、孤立表格、结构缺块和来源缺失
priority: specialist
---

# Completeness Skill

## 1. 目标与边界

识别解析结果中的结构完整性问题，但严格区分“重复结构”和“原文确实缺失”。可以删除有充分证据的完全重复 block；不能补写缺失正文、数字、图片、表格行或引用。

## 2. 必读证据

- 全篇 `document_index` 和 block/table/asset 统计；
- 空 block 的 kind、页码、bbox、来源和相邻对象；
- 候选重复 block 的稳定 ID、文本 fingerprint、页码和位置；
- 结构关系：标题树、表格归属、caption/asset 关系和引用关系；
- 相邻页和原始 provenance，用于区分重复页眉与真实重复正文。

## 3. 判断规则

### 3.1 可删除的重复

只有在以下条件同时成立时，才使用 `remove_block`：

- 两个或多个 block 的事实文本和结构内容完全一致；
- 重复对象位于可解释的重复位置，例如重复页眉、重复解析 block；
- 保留对象具有更完整或更可信的页码/bbox/provenance；
- 删除不会破坏标题、表格、引用或 asset 关系。

### 3.2 空 block 和孤立对象

- 空 block 可能是分页占位、扫描空白或结构容器，不可仅凭为空就删除；
- 孤立表格、asset 或 caption 先检查相邻页和关系证据；
- 来源定位缺失属于审核风险，不要虚构 locator 或 provenance。

### 3.3 缺失内容

如果只能判断“这里应该有内容”，但无法证明内容是什么，保留原结果并标记人工复核。不能用论文常识、模板或模型记忆补齐。

## 4. 允许的 Patch

- `remove_block`：仅删除可证明的完全重复 block；
- `move_block`：恢复被重复结构打乱的已有对象顺序；
- `update_block_markdown`：修复空白边界，但不得填入新事实。

## 5. 人工复核条件

- 重复文本相同但 provenance 指向不同真实位置；
- 空 block 可能代表图片、公式或扫描区域；
- 删除会改变表格、标题或引用关系；
- 缺失对象的内容无法从输入证据重建；
- 只有语义相似，没有可验证的 fingerprint。

## 6. 输出检查

删除前确认重复指纹、保留对象、影响关系和 evidence_refs；删除后检查文档仍有稳定顺序，且没有把原本真实出现两次的正文误判成重复。

## 7. 输出 few-shot

只有当两个 block 的事实文本、来源指纹和结构角色都完全重复，并且其中一个明确是重复解析产物时，规范输出为：

~~~json
{"base_revision":"<current-revision>","lineage":["<current-revision>"],"operations":[{"operation":"remove_block","block_id":"<duplicate-block>"}],"affected_ids":[],"evidence_refs":[{"object_type":"block","object_id":"<duplicate-block>","field_path":"content_fingerprint"},{"object_type":"block","object_id":"<kept-block>","field_path":"content_fingerprint"}],"change_kind":"structure","reasoning":"两个已有 block 的正文和 provenance 指纹完全相同，且 duplicate block 没有独立来源关系；删除重复解析产物，不删除真实重复出现的内容。","confidence":0.97}
~~~
无法证明是重复解析产物时输出 no-op，不凭语义相似删除 block。
