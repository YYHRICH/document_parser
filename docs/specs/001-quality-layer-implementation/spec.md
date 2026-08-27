# 确定性文档质量层实现规格与开发计划

> 分支：`feature/quality-layer`
> 状态：Draft v0.2
> 当前输入：解析器输出经 Adapter 转换后的统一质量文档视图
> 适用输出：`optimized.md`、`canonical_document.json`、`quality_report.json` 和 `package_manifest.json`
> 目标：以真实证据执行确定性检查、有限白名单修复和 Gate 判定，并生成可审计产物。

---

## 1. 本 Spec 的目标

本 Spec 定义一个只处理单份 `ParsedDocument` 的确定性质量层。上游负责选择解析器、统一输出和多文档并行；质量层只负责证据检查、白名单修复、能力判定、Gate、canonical 构建与可审计产物。

### 1.1 成功标准

- 固定 `ParsedDocument` fixture 可独立生成合法 `QualityPackage`；
- 规则输出只基于真实证据，证据不足时明确降级或转人工；
- 白名单修复不改变事实内容，且可重放、幂等；
- 相同输入与配置重复运行时，产物和 manifest 哈希稳定；
- schema、规则、Gate、golden、no-op、拒绝和原子落盘测试持续通过。

### 1.2 非目标

- 不负责解析器选择、重解析执行、多文档批处理、并行调度、队列或重试；
- 不依赖任何解析器私有对象；
- 不自动改写正文事实、数字、单位、日期、公式、代码、URL、原始 ID、页码或 bbox；
- 不接入外部自动修复运行时。

## 2. 开工前必须确认的契约决策

以下决策应形成团队记录。未确认前，可以实现内部兼容逻辑，但不应把有争议的期望写死为稳定 golden。

| ID | 待确认事项 | 建议决策 | 未确认时的处理 |
| --- | --- | --- | --- |
| D-01 | sdp-004 两份 column_path 标注冲突 | `annotations/quality/golden.jsonl` 作为人工事实源，`expected/...` 由其生成；采购字段版本更符合文件名，但仍需数据负责人确认 | 将 sdp-004 标记为冲突，CI 一致性测试失败并给出差异，不静默任选 |
| D-02 | sdp-005 期望写为 `mixed`，但 Gate 无此枚举 | `mixed` 仅描述内部 binding 状态；最终 Gate 明确选 `manual_review_required` 或 `reparse_required` | 默认按 `manual_review_required` 开发；若已有确定的重解析策略再改为 `reparse_required` |
| D-03 | capability 无 `not_applicable` | 后续公共契约增加 `not_applicable` | 当前使用 `unavailable` + evidence=`not applicable`，并由 Gate 的 applicability 判断其是否阻塞 |
| D-04 | `quality_report.artifacts` 是否包含自身哈希 | 不包含自身；自身哈希只放在 manifest | 禁止实现递归自哈希 |
| D-06 | `reparse_recommendation.parser_id` 的允许值 | 由路由分支提供 parser catalog 和静态建议映射 | 无合法 parser_id 时不能构造伪推荐；保持人工复核并报告配置缺口 |
| D-07 | canonical block content 的规范化规则 | 默认保留输入 `markdown`，只允许白名单修复产生变化 | 未确认的格式优化全部 no-op |
| D-08 | 只有未修复 info issue 时应为 pass 还是 pass_with_warnings | 建议 info 不阻塞 pass，warning 才触发 pass_with_warnings；以产品展示约定为准 | 在 Gate 配置中显式固定，禁止不同规则自行解释 |
| D-20 | 审核粒度 | `quality_report.json` 同时提供文档级状态和 block/table/asset/reference 级可用性结论 | 无法定位时至少给出页码、block 或 issue 范围 |

### 2.1 Golden 单一事实源建议

建议建立以下约束：

- `manifest.jsonl`：数据文件身份和状态的唯一事实源；
- `annotations/quality/golden.jsonl`：人工质量标注的唯一事实源；
- `expected/golden/quality_expectations.jsonl`：面向测试的派生产物；
- 每条标注至少包含 `sample_id`、`source_sha256`、`annotation_revision`；
- 提供脚本或测试验证 annotations 与 expected 一致，禁止双份手工维护。

---

## 3. 总体架构

### 3.1 公共入口

```python
def run_quality(document, *, config=None) -> QualityPackage:
    """执行确定性检查、白名单修复、canonical 构建和审核输出。"""
```

质量层直接接收 `ParsedDocument 2.2`；多文档并行由调用方负责。

### 3.2 确定性流水线

```text
ParsedDocument
  → EvidenceContext
  → whitelist repairs
  → deterministic rules
  → capability matrix
  → Gate
  → canonical document + QualityPackage
```

### 3.3 模块边界

```text
quality/
├── contracts.py                # 共享公共契约的唯一边界
├── evidence/                   # 只读证据索引与可用性
├── rules/                      # 已知不变量与确定性检查
├── repairs/                    # 白名单、幂等修复
├── gates/                      # capability 汇总与最终 Gate
├── builders/                   # canonical 构建
└── packaging/                  # 哈希、原子写入与校验
```

规则只定义可验证的质量条件；任何无法安全确定的情况必须保留证据并降级。

## 4. 内部核心模型

公共 Pydantic 模型只用于边界。规则之间建议使用内部不可变模型，避免规则直接修改 ParsedDocument。

### 4.1 EvidenceRequirement

```python
@dataclass(frozen=True)
class EvidenceRequirement:
    kind: EvidenceKind
    required_state: Literal["available", "partial_allowed"]
    scope: Literal["document", "block", "table", "cell"]
    purpose: str
```

每条规则必须声明 `required_evidence`。规则调度器先读取 `capabilities`，再决定：

- 执行规则；
- 以有限证据执行，并限制最高状态；
- 跳过规则并输出 `unavailable`；
- 产生 manual/reparse blocker。

### 4.2 RuleResult

```python
@dataclass(frozen=True)
class RuleResult:
    issues: tuple[IssueDraft, ...] = ()
    relation_candidates: tuple[RelationCandidate, ...] = ()
    binding_candidates: tuple[BindingCandidate, ...] = ()
    repair_proposals: tuple[RepairProposal, ...] = ()
    capability_observations: tuple[CapabilityObservation, ...] = ()
```

Rule 不得：

- 直接修改文档；
- 写文件；
- 指定最终 Gate；
- 调用解析器或路由器；
- 将外部自由文本直接写入 canonical content。

### 4.3 证据引用

内部证据引用应是结构化定位，而不是自由文本：

```python
@dataclass(frozen=True)
class EvidenceRef:
    object_type: Literal[
        "document", "block", "table", "cell", "ocr_span",
        "asset", "native_artifact", "capability", "provenance"
    ]
    object_id: str
    field_path: str
    value_sha256: str | None = None
```

最终公共 `evidence` 可由这些引用渲染。`value_sha256` 用于检测缓存或重复运行时引用的证据是否已变化。

### 4.4 稳定 ID

统一采用 UUIDv5 或等价的确定性哈希 ID：

```text
binding_id = uuid5(namespace, document_key + table_id + cell_id + row_key + column_path)
relation_id = uuid5(namespace, document_key + relation_type + from_id + to_id + marker_offset)
issue_id    = uuid5(namespace, document_key + rule_id + affected_ids + evidence_key)
```

禁止使用随机 UUID、数组下标或运行时间生成公共 ID。

---

## 5. 规则规格

### 5.1 规则命名约定

```text
QL-CONT-*   内容完整性
QL-PROV-*   来源与可追溯性
QL-TBL-*    表格网格与字段绑定
QL-HDG-*    标题树
QL-REF-*    引用关系
QL-RPR-*    白名单修复
QL-GATE-*   Gate 不变量

```

规则 ID 一旦进入 golden 或 `applied_repairs`，不得随意重命名。

### 5.2 完整性和来源规则

| Rule ID | 检查 | 主要证据 | 失败处理 |
| --- | --- | --- | --- |
| QL-CONT-001 | blocks 是否存在、ID 是否唯一 | blocks | 严重冲突进入 rejected/manual |
| QL-CONT-002 | order_index 是否唯一、连续或可确定排序 | blocks/order_index、anchor | 冲突部分禁止 verified 关系 |
| QL-CONT-003 | block kind 与内容最低一致性 | kind、markdown | warning/manual，不自动改 kind |
| QL-PROV-001 | source_block_id 可回溯 | blocks、provenance | provenance capability 降级 |
| QL-PROV-002 | page/bbox 合法且粒度真实 | anchor、table/cell bbox | 删除或拒绝伪造 locator；产生 issue |
| QL-PROV-003 | assets/native_artifacts 引用和 sha256 结构合法 | assets、native_artifacts | 按 required_for_quality 判断 blocker |
| QL-PROV-004 | capabilities 非 available 状态是否有 reason | capabilities | 契约错误；按严重性 rejected/manual |

### 5.3 表格网格恢复

#### 5.3.1 网格算法

对每个 cell 占用以下物理槽位：

```python
for row in range(cell.start_row, cell.start_row + cell.row_span):
    for col in range(cell.start_col, cell.start_col + cell.col_span):
        grid[row][col].append(cell.cell_id)
```

必须检测：

- `row_span` 或 `col_span` 小于 1；
- 坐标为负或越过 `num_rows/num_cols`；
- 不同 cell 占用同一槽位；
- 声明尺寸与实际最大坐标不一致；
- 非预期内部空洞；
- header 标记与所在区域明显冲突。

只有槽位唯一、尺寸一致、header 区域可确定时，`table_grid_reliable` 才能是 `verified`。

#### 5.3.2 多级表头与 column_path

对每个叶子数据列，自顶向下收集覆盖该列的 header cell：

```python
["采购信息", "供应商", "含税单价"]
```

规则：

1. 仅按同一 `cell_id` 去除因 row_span 展开导致的重复；
2. 不按文本全局去重，不同层级同名仍应保留；
3. 去除空字符串，但不得补造缺失标题；
4. 同一层级存在多个互斥候选时，binding 不得 verified；
5. `column_path=[]` 时不得 verified；
6. 公共字段保留 `list[str]`，仅展示时才用 `/` 拼接；
7. evidence 记录每个 path segment 对应的 cell、行列和 span。

#### 5.3.3 row_key

优先级：

1. 明确 `row_header=true` 的单元格；
2. 唯一且连续的首列非 header 文本，可作为 `inferred`；
3. 多级 row header 按来源顺序组合，但 evidence 保留每个原始 cell；
4. 缺失、冲突或重复且无法区分时，不追加虚构序号，安全降级。

#### 5.3.4 bbox

- cell bbox 存在：使用 cell locator；
- 只有 table bbox：保留 table locator，`bbox_granularity=table`；
- evidence 记录 start_row、start_col、row_span、col_span；
- 禁止按平均宽高推算 cell bbox。

#### 5.3.5 跨页续表和列漂移

只有满足以下前置条件时才产生续表候选：

- 页面相邻；
- 阅读顺序相邻；
- 表格在前页底部和后页顶部，或存在明确 continuation 证据；
- 至少有一项结构证据：重复表头、列数、列 bbox、原始 parser continuation 标志。

比较特征：

- `num_cols`；
- 规范化 header path 序列；
- 各列 bbox 中心点和宽度的页面归一化比例；
- 列顺序；
- 重复表头的一致性；
- 前后页数据类型轮廓，仅作为辅助，不作为事实证据。

下列情况禁止跨页 verified：

- 列数变化且无法由 colspan 解释；
- header 对应不唯一；
- 列顺序交换；
- 多列位置显著漂移；
- 只有表级 bbox 且表头不足；
- 存在弱续表线索，但确定性结构证据不足。

页内确定 binding 可以保留为 verified，跨页关系单独降级，避免整表全有或全无。

#### 5.3.6 表格规则清单

| Rule ID | 功能 |
| --- | --- |
| QL-TBL-001 | 单元格坐标与 span 合法性 |
| QL-TBL-002 | 物理网格占位冲突和空洞检测 |
| QL-TBL-003 | header 区域恢复 |
| QL-TBL-004 | 多级 column_path 生成 |
| QL-TBL-005 | row_key 生成与唯一性检查 |
| QL-TBL-006 | binding 来源粒度检查 |
| QL-TBL-007 | 跨页续表候选识别 |
| QL-TBL-008 | 列漂移检测与降级 |

### 5.4 标题树

先按 `(order_index, block_id)` 确定性排序，再使用 heading stack：

1. 当前标题级别为 `L`；
2. 弹出 stack 中 level `>= L` 的标题；
3. 最近的较低级标题作为 parent；
4. 当前标题入栈。

状态规则：

| 情况 | relation 状态 | issue |
| --- | --- | --- |
| level、order、来源一致 | verified | 无 |
| `H1 → H3` 跳级，但最近 H1 唯一 | inferred | heading_level_jump |
| 缺 heading_level | 不创建 verified；可产生候选 | heading_level_missing |
| 开头直接 H2/H3 且无父节点 | manual_review_required | heading_parent_missing |
| order_index 重复或与 page/bbox 冲突 | manual/reparse | reading_order_conflict |
| 普通粗体文本疑似标题 | 不改变 kind | 可选 info |

禁止创建无来源的虚拟 H1/H2 节点。

规则清单：

- QL-HDG-001：标题字段完整性；
- QL-HDG-002：标题层级跳跃；
- QL-HDG-003：标题来源和阅读顺序一致性；
- QL-HDG-004：parent_child 构建；
- QL-HDG-005：孤立标题和歧义父节点。

### 5.5 引用绑定

#### 5.5.1 数字引用 MVP

第一阶段支持：

- `[1]`
- `[12]`
- `[1, 3, 5]`
- `[2–4]` 和 `[2-4]`
- 连续 marker，如 `[1][2]`

范围仅在引用区确实存在所有编号时展开。正文中的 Markdown link、数组、单位等相似文本必须通过上下文过滤，无法排除误判时输出候选而非 verified。

目标索引只从明确的 reference block 和 `reference_label` 建立：

```text
normalized_label → [reference_block_id, ...]
```

- 候选数为 1 且 reference 类型明确：可 verified；
- 候选数为 0：missing target issue；
- 候选数大于 1：ambiguous target issue；
- 不得任选第一个候选。

evidence 保存 marker 原文、字符偏移、归一化 label 和全部候选 IDs。

#### 5.5.2 作者—年份引用

作为第二阶段能力。只有在作者键、年份和后缀均可确定提取，且唯一对应参考文献时才允许 verified。

以下情况最高为 inferred 或 manual：

- `et al.` 对应多个候选；
- 同姓同年；
- `2024a/2024b` 后缀缺失或冲突；
- 仅依赖主题语义相似；
- reference block 无明确 label 或结构。

规则清单：

- QL-REF-001：reference index 构建；
- QL-REF-002：数字 marker 提取；
- QL-REF-003：数字范围展开校验；
- QL-REF-004：目标唯一性判定；
- QL-REF-005：作者—年份候选提取；
- QL-REF-006：reference_of 构建。

---

## 6. 白名单修复和内容不变量

质量层只允许低风险、可证明等价且可重放的白名单修复。当前修复范围为行尾空白、Markdown 表格分隔行，以及 MinerU 输出的完整 HTML 表格转管道 Markdown；HTML 的 rowspan/colspan 仅保留起始格文本并将覆盖格置空，原始 HTML 保持为可追溯证据。没有修复时必须保持输入内容不变。

禁止猜测 OCR 字符、改写句子、补数字/公式/表头/标题、推算缺失值、伪造 bbox 或为唯一性追加序号。任何需要理解语义或改变事实的修改都转人工处理。

每次修复都必须记录 `before`、`after`、规则 ID、受影响 block、参数和结构化证据；同一输入重复执行不得产生第二次修复记录。

## 7. Capability Matrix

### 7.1 能力推导原则

能力不是直接复制 ParsedDocument 的 capability，而是质量层根据输入可用性和规则结果推导：

```text
上游证据可用性
  + 规则执行结果
  + 未解决 issue
  + 文档是否适用该能力
  → 质量 capability state
```

### 7.2 六项能力建议

| 能力 | verified 最低条件 | 常见 blocker |
| --- | --- | --- |
| content_complete | blocks 存在、内容和顺序无完整性 blocker | OCR failed、关键页缺失、空内容 |
| heading_tree_reliable | 所有适用标题关系可确定 | level 缺失、跳级歧义、order 冲突 |
| table_grid_reliable | 所有适用表格网格无占位冲突 | span 冲突、尺寸不一致、空洞 |
| table_field_binding_reliable | row_key、column_path、value 和来源可确定 | header 歧义、列漂移、row key 冲突 |
| provenance_reliable | 来源 ID、page/bbox 粒度和 parser provenance 一致 | source ID 丢失、伪 bbox、来源冲突 |
| non_table_relation_reliable | 标题/引用等适用关系满足唯一性 | citation 多目标、标题父节点不唯一 |

> `inferred` 表示质量层依据明确编号、页面、坐标或唯一首列等真实证据完成了确定性恢复。它必须保留在 capability/relation evidence 中，但不应自动等同 `manual_review_required`；只有证据冲突、候选不唯一或无法安全解释时才阻断 Gate。

### 7.3 Applicability

内部必须单独计算 applicability：

```python
CapabilityAssessment(
    name="table_grid_reliable",
    applicable=False,
    state="unavailable",
    blocking=False,
    evidence=["document contains no tables"],
)
```

在公共契约增加 `not_applicable` 前，`unavailable` 不得自动等于 blocker。

---

## 8. Gate 决策规格

### 8.1 优先级

```text
rejected
  > reparse_required
  > manual_review_required
  > pass_with_warnings
  > pass
```

### 8.2 推导算法

```python
def decide_gate(issues, capabilities, recommendation):
    blockers = collect_blockers(issues, capabilities)

    if any(b.disposition == "rejected" for b in blockers):
        return REJECTED

    if any(b.disposition == "reparse_required" for b in blockers):
        require_valid_reparse_recommendation(recommendation)
        return REPARSE_REQUIRED

    if any(b.disposition == "manual_review_required" for b in blockers):
        return MANUAL_REVIEW_REQUIRED

    if any(i.status == "unfixed" for i in issues):
        return PASS_WITH_WARNINGS

    return PASS
```

### 8.3 Gate 不变量

- 未解决 critical issue 必须映射为 manual、reparse 或 rejected，不能以普通 unfixed warning 结束；
- `critical_false_pass = true` 时，state 不得为 `pass` 或 `pass_with_warnings`；
- `reparse_required` 必须有合法 recommendation；
- recommendation 只能使用约定 parser catalog 中的 ID 和参数；
- 仅有 info 且产品希望完全干净时可 pass；若契约要求所有未修复 info 均提示，则 pass_with_warnings，需在 D-08 中确认；
- 不适用 capability 不得成为 blocker；
- `inferred` capability 不得仅因状态较低而成为 blocker；
- repaired issue 不得继续计入 unresolved blocker；
- Gate 必须由最终重跑后的规则结果推导。

### 8.4 manual、reparse、rejected 的边界

| 状态 | 使用条件 |
| --- | --- |
| manual_review_required | 人能够依据现有证据判断，但算法不能唯一确定；或无合法自动重解析建议 |
| reparse_required | 当前证据不足，重新解析大概率可改善，且存在合法 parser_id/options 映射 |
| rejected | 输入契约损坏、核心来源严重矛盾、产物无法安全解释，或安全策略明确拒绝 |

---



## 10. Canonical 构建和落盘

### 10.1 canonical blocks

- 按稳定 `(order_index, block_id)` 输出；
- `content` 默认保持输入 markdown；
- `source_locator` 只投影真实来源；
- bbox 粒度必须与实际来源一致；
- 对来源冲突的 block 保留内容，但 provenance_status 降级并产生 issue，除非输入已经不可安全解释。

### 10.2 确定性序列化

- UTF-8；
- JSON key 排序策略固定；
- 数组使用业务稳定顺序，不依赖 dict/set 遍历；
- 换行符固定为 `\n`；
- 是否以末尾换行结束固定；
- 浮点值使用 Pydantic/JSON 的统一序列化规则，禁止在不同文件中使用不同 round 策略。

### 10.3 哈希顺序

```text
1. 生成 optimized.md
2. 生成 canonical_document.json
3. 计算上述两个哈希并写入 quality_report.artifacts
4. 生成 quality_report.json
5. 计算 quality_report.json 哈希
6. 生成 package_manifest.json，记录三个核心产物哈希
7. 校验 manifest
```

quality_report 不记录自身哈希，manifest 不记录自身哈希。

### 10.4 原子化写入

- 在目标目录同级创建唯一临时目录；
- 写完四件套并执行 Pydantic、SHA-256 和文件存在性校验；
- 成功后原子替换最终目录；
- 失败时不暴露半成品；
- 不删除用户已有目录，除非调用方明确允许替换且已有安全替换策略。

---

## 11. 质量输入需求矩阵

建议交付 `../../quality/quality_input_requirements.md`，至少包含：

| 规则/能力 | 必需证据 | 可选证据 | 缺失后的最高状态 | 给 Adapter 的反馈 |
| --- | --- | --- | --- | --- |
| content_complete | blocks、capabilities | OCR spans | manual/reparse | 空页和 OCR 失败需明确 reason |
| heading_tree | kind、order_index、heading_level | page/bbox、section_path | inferred/manual | 保留原始 heading level 和 source text |
| table_grid | num_rows、num_cols、cells 坐标/span | cell bbox、image_path | manual/reparse | 不要只输出 Markdown 表 |
| table binding | header flags、row header、cell text | cell bbox | inferred/manual | 保留合并单元格结构 |
| citation binding | reference block、reference_label、正文 marker | section path | manual | 不要丢 reference_label |
| provenance | source_block_id、parser provenance | native artifact ref | manual/rejected | 缺失必须通过 capability reason 声明 |

该矩阵是和朱联调时的主要反馈载体，避免质量层直接读取 Adapter 私有结构。

---

## 12. 测试计划

### 12.1 测试层级

1. **Unit**：规则、canonical builder、内容不变量和 Gate 汇总；
2. **Contract**：输入/输出 Schema、Gate 不变量和四件套；
3. **Integration**：固定 ParsedDocument fixture 的完整确定性流水线；
4. **Packaging**：稳定序列化、manifest、原子写入和篡改检测；
5. **Golden**：共享样例和已知冲突；
6. **Property/Metamorphic**：内容保真、幂等、稳定 ID 和删除证据不会升级结论。

### 12.2 Golden 和安全断言

- Golden 标注冲突必须显式 xfail，不能静默选用任一份；
- 规则、修复和 Gate 不得因缺失证据提升可信度；
- 任何白名单修复都必须可重放且不得伪造来源；
- 四件套必须由同一输入生成，manifest 哈希可复算。

### 12.3 回归命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests\quality -q
```

## 13. 开发里程碑

### M0：契约冻结和测试骨架

交付：

- 完成 D-01 至 D-08 的团队确认记录；
- 建立 `quality/` 与 `tests/quality/` 骨架；
- 建立内部 EvidenceRef、RuleResult、稳定 ID 模型；
- 添加 Gate 不变量测试和 golden 冲突检测；
- 输出质量输入需求矩阵初稿。

完成定义：核心模型可 import，原有 7 个契约回归测试仍通过。

### M1：EvidenceContext、完整性、来源与 Gate

交付：

- capability-aware EvidenceContext；
- QL-CONT-*、QL-PROV-*；
- capability matrix 汇总器；
- Gate evaluator 和 invariants；
- pass、warning、manual、reparse、rejected 五种合成测试。

完成定义：不依赖三大关系能力，也能对基础 ParsedDocument 生成合法 QualityPackage。

### M2：标题树和数字引用

交付：

- stack-based heading tree；
- level 缺失/跳级/顺序冲突降级；
- 数字 citation marker MVP；
- reference target 唯一性；
- sdp-006、sdp-007 对应 fixtures 或临时合成 fixture。

完成定义：正例 verified，歧义反例绝不误绑。

### M3：表格网格和字段绑定

交付：

- span-aware physical grid；
- header region 和完整 column_path；
- row_key、value、source locator；
- 跨页候选和列漂移降级；
- sdp-004、sdp-005 测试。

完成定义：合并表头正例通过；反例保留确定部分并阻止错误跨页绑定。

### M4：白名单修复和 canonical builder

交付：

- repair registry；
- repair replay/idempotence；
- canonical blocks/bindings/relations builder；
- optimized markdown no-op 和安全修复；
- 修复后规则重跑。

完成定义：所有 applied repair 可回放、有证据、重复运行不再次应用。

### M5：Packaging

交付：

- 确定性 JSON/Markdown 序列化；
- 三个核心文件哈希和 manifest；
- 原子化写入；
- 四件套完整性和篡改检测测试。

完成定义：相同输入重复打包，产物 bytes 和 hashes 一致。

### 联调和交付

交付：

- 接入上游提供的真实 `ParsedDocument` fixtures；
- 与路由层确认合法 parser catalog 和 reparse recommendation 映射；
- 消解 golden 标注冲突并完成验收；
- 保持确定性规则、Gate、canonical 与 packaging 回归稳定。

完成定义：固定输入可独立生成一致的 QualityPackage，且所有质量层回归通过。

## 14. 建议提交拆分

每个提交保持单一目的，建议顺序：

1. `test(quality): add contract decisions and gate invariants`
2. `feat(quality): add evidence context and deterministic ids`
3. `feat(quality): add completeness and provenance rules`
4. `feat(quality): add capability matrix and gate evaluator`
5. `feat(quality): restore heading tree safely`
6. `feat(quality): bind numeric citations with uniqueness checks`
7. `feat(quality): reconstruct table physical grids`
8. `feat(quality): build hierarchical table field bindings`
9. `feat(quality): detect cross-page column drift`
10. `feat(quality): add replayable repair registry`
11. `feat(quality): build canonical document and markdown`
12. `feat(quality): package artifacts with stable hashes`
14. `test(quality): enable shared golden fixtures`
15. `docs(quality): publish input requirements and integration guide`

不要在一个提交中同时完成公共契约修改、复杂算法和 golden 更新，否则很难审查期望变化是实现修复还是标注迁移。

---

## 15. 三人联调责任清单

### 15.1 向朱确认

- `examples/contracts/parsed_document.json` 是否覆盖最新 2.2 字段；
- table cells 是否始终带稳定 cell ID；若没有，如何稳定定位；
- header/row_header 标记的生成规则；
- cell bbox 缺失时 capability 如何声明；
- reference_label 是否保留；
- order_index 冲突和跨页表格如何表达；
- required native artifact 缺失时的 reason；
- fixtures 何时从 pending 转为可用。

### 15.2 向张确认

- 可用于 recommendation 的 parser ID 列表；
- 每种质量失败对应哪些允许 options；
- 哪些失败重解析确实可能改善；
- recommendation 是建议还是强制路由输入；
- 如何防止同一文档无限 reparse 循环；
- 是否有 attempt count / previous parser provenance 可供质量层判断。

### 15.3 本分支承诺

- 不调用 parser；
- 不执行 route；
- 不读取 Adapter 私有模型；
- 不创建无证据事实；
- 对上游证据缺口通过需求矩阵反馈；
- 输出稳定、可审计、可回放的 QualityPackage。

---

## 16. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 上游 fixtures 延迟 | golden 无法端到端运行 | 使用最小合成 fixtures 开发，真实 fixtures 到位后只替换数据层 |
| 两份 golden 漂移 | CI 结果不可信 | 单一事实源 + 生成 expected + sha256/revision |
| Gate 规则散落 | 同一 issue 得到不同最终状态 | 所有规则只产 observations，唯一 Gate evaluator 决策 |
| 表格算法过度猜测 | 错误字段绑定 | cell identity 去重、唯一性检查、局部降级 |
| `unavailable` 被误当 blocker | 无表格文档误拒绝 | 内部 applicability 独立计算 |
| reparse 推荐越界 | 质量层变相路由 | 只使用路由团队提供的静态 catalog，不执行推荐 |
| 哈希递归或不稳定 | manifest 永远不一致 | report 不哈希自身、固定序列化、hash golden |

---

## 17. 最终验收清单

### 契约

- [ ] ParsedDocument 2.2 输入验证通过；
- [ ] QualityPackage 1.0 输出验证通过；
- [ ] reparse 状态始终带合法 recommendation；
- [ ] critical_false_pass 与 pass 状态不可能同时出现；
- [ ] manifest 三个核心哈希齐全且可复算。

### 证据安全

- [ ] 所有 verified 结果均有可解析 evidence；
- [ ] 不存在输入中没有的文字、数字、bbox 或来源 ID；
- [ ] table bbox 未被伪装成 cell bbox；
- [ ] 歧义引用未任选目标；
- [ ] 标题跳级未被强制升级；
- [ ] no-op 不产生虚假修复。

### 表格

- [ ] row/col span 正确占位；
- [ ] 合并表头保留完整 column_path；
- [ ] row_key 来源清晰；
- [ ] 跨页列漂移触发安全降级；
- [ ] 页内确定 binding 不因局部歧义全部丢失。

### 工程质量

- [ ] 每条 rule 声明 evidence requirements；
- [ ] rules、repairs、gates 无职责混用；
- [ ] 稳定 ID、稳定排序和稳定哈希测试通过；
- [ ] repair 可回放、幂等；
- [ ] 写文件失败不遗留半成品；
- [ ] 原有契约回归测试通过。



## 18. 推荐的实际开工顺序

先稳定 M1–M5 的确定性规则、白名单修复、canonical、Gate 和 packaging；再接入上游正式统一文档包并完成 golden 验收。质量层仅提供确定性检查与白名单修复。
