---
skill_id: reference_structure
purpose: 维护正文引用与参考文献的结构关系
applies_to: 数字引用、作者年份引用、参考文献顺序和绑定异常
priority: specialist
---

# Reference Structure Skill

## 1. 目标与边界

识别正文引用 marker 与已有参考文献 block 之间的结构关系，并在证据充分时恢复顺序或边界。不能补造参考文献，不能改写作者、年份、标题、期刊、DOI、URL 或正文引用文本。

当前候选支持 `upsert_relation` 和 `remove_relation`，可以调整已有引用关系；关系端点必须来自输入文档，不能创建缺失的参考文献或 marker。

## 2. 必读证据

- 正文 block 中的数字 marker、作者年份 marker 和上下文；
- 参考文献区域的 block 顺序、编号和 `reference_label`；
- 标题树、章节位置、页码和相邻引用；
- 已有 reference relation、source locator 和 provenance；
- 对歧义引用，读取全文中相同 marker 的其他出现位置。

## 3. 判断规则

- 数字引用优先按明确编号和参考文献 label 绑定；
- 作者—年份引用必须同时比较作者、年份和后缀，不能仅凭主题相似；
- `et al.`、同姓同年、`2024a/2024b` 缺失后缀和编号冲突都属于高风险；
- 参考文献顺序异常可以作为结构问题提出，但不能用模型知识推断缺失条目；
- 原文 marker 与条目无法唯一对应时保留原文，并生成人工复核说明。

## 4. 允许的 Patch

- 在已有证据支持时，用 `move_block` 恢复参考文献 block 的顺序；
- 用 `upsert_relation` 建立唯一的 `reference_of` 关系，或用 `remove_relation` 删除已证明错误的已有关系；
- 用 `update_block_markdown` 修复引用区域的明确换行/边界；
- 关系端点、marker 和参考文献文本必须保持在输入范围内。

## 5. 人工复核条件

- 目标文献不唯一或参考文献条目缺失；
- 需要修改正文 marker、作者、年份或文献内容；
- 参考文献编号与页码/章节证据冲突；
- 只能依赖语义相似度作出绑定；
- 发现疑似 OCR 遗漏或重复条目。

## 6. 输出检查

确保所有 marker 和参考文献文本的事实词元不变；证据引用必须指向实际 marker、label 或 relation 字段；不把 `confidence` 当作唯一性证明。

## 7. 输出 few-shot

当正文 marker block 和参考文献 block 的唯一对应关系已有证据时，规范输出为：

~~~json
{"base_revision":"<current-revision>","lineage":["<current-revision>"],"operations":[{"operation":"upsert_relation","relation":{"action":"upsert","relation_type":"reference_of","from_id":"<marker-block>","to_id":"<reference-block>","marker_key":"ref-1"}}],"affected_ids":[],"affected_relation_keys":[],"evidence_refs":[{"object_type":"block","object_id":"<marker-block>","field_path":"reference_marker"},{"object_type":"block","object_id":"<reference-block>","field_path":"label"}],"change_kind":"structure","reasoning":"依据正文 marker、参考文献 label 和页内唯一性建立已有对象之间的关系，不修改引用文本。","confidence":0.9}
~~~
