# 质量层实现规格与开发计划

> 分支：`feature/quality-layer`  
> 状态：Draft v0.1  
> 适用输入：`ParsedDocument 2.2`  
> 适用输出：`QualityPackage 1.0`  
> 目标：在不改变解析事实、不执行路由和解析器的前提下，完成证据驱动的质量检查、安全修复、结构关系绑定、质量准入和四件套落盘。

---

## 1. 本 Spec 的目标

本 Spec 用于指导 `feature/quality-layer` 的编码、测试和联调，解决以下问题：

1. 明确质量层的模块边界、入口、执行顺序和内部数据模型；
2. 将表格绑定、标题树、引用关系、完整性和来源检查拆为可测试规则；
3. 定义白名单修复、能力矩阵和 Gate 的确定性推导方式；
4. 定义 LLM 可选辅助的安全边界、降级行为和测试方法；
5. 给出里程碑、提交拆分、测试矩阵、验收标准和联调清单。

### 1.1 成功标准

- 同一输入、同一配置重复运行，产物内容、稳定 ID 和 SHA-256 一致；
- 每个 `verified` binding/relation/capability 都能回指 ParsedDocument 中的真实证据；
- 缺少证据时安全降级，不生成伪造文字、标题、表头、数字、bbox 或来源关系；
- no-op 是合法输出，且不会产生虚假的 `applied_repairs`；
- 五种 Gate 状态通过统一决策器推导，规则模块不得自行指定最终状态；
- 无 LLM、LLM 超时、LLM 返回非法结构时，纯规则主流程仍可完成且结果不被错误升级；
- 四个 golden 样例和新增的 no-op、reparse、rejected 测试均通过；
- 原有契约回归测试持续通过。

### 1.2 非目标

- 不选择或执行 Docling、MinerU、OCR；
- 不实现 Adapter、后端或 Web；
- 不修改 ParsedDocument 中的解析事实；
- 不使用 LLM 对原文进行自由改写；
- 不根据语义相似度把不唯一关系升级为 `verified`；
- 不在本分支单方面改变公共 Pydantic 契约字段语义。

---

## 2. 开工前必须确认的契约决策

以下决策应形成团队记录。未确认前，可以实现内部兼容逻辑，但不应把有争议的期望写死为稳定 golden。

| ID | 待确认事项 | 建议决策 | 未确认时的处理 |
| --- | --- | --- | --- |
| D-01 | sdp-004 两份 column_path 标注冲突 | `annotations/quality/golden.jsonl` 作为人工事实源，`expected/...` 由其生成；采购字段版本更符合文件名，但仍需数据负责人确认 | 将 sdp-004 标记为冲突，CI 一致性测试失败并给出差异，不静默任选 |
| D-02 | sdp-005 期望写为 `mixed`，但 Gate 无此枚举 | `mixed` 仅描述内部 binding 状态；最终 Gate 明确选 `manual_review_required` 或 `reparse_required` | 默认按 `manual_review_required` 开发；若已有确定的重解析策略再改为 `reparse_required` |
| D-03 | capability 无 `not_applicable` | 后续公共契约增加 `not_applicable` | 当前使用 `unavailable` + evidence=`not applicable`，并由 Gate 的 applicability 判断其是否阻塞 |
| D-04 | `quality_report.artifacts` 是否包含自身哈希 | 不包含自身；自身哈希只放在 manifest | 禁止实现递归自哈希 |
| D-05 | LLM metrics 不在已列出的 QualityPackage 1.0 字段中 | 由契约负责人确认后再增加；否则只做内部日志/测试计数 | 不私自向公共 JSON 增加字段 |
| D-06 | `reparse_recommendation.parser_id` 的允许值 | 由路由分支提供 parser catalog 和静态建议映射 | 无合法 parser_id 时不能构造伪推荐；保持人工复核并报告配置缺口 |
| D-07 | canonical block content 的规范化规则 | 默认保留输入 `markdown`，只允许白名单修复产生变化 | 未确认的格式优化全部 no-op |
| D-08 | 只有未修复 info issue 时应为 pass 还是 pass_with_warnings | 建议 info 不阻塞 pass，warning 才触发 pass_with_warnings；以产品展示约定为准 | 在 Gate 配置中显式固定，禁止不同规则自行解释 |

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

建议对外只暴露一个主要入口：

```python
def run_quality(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    llm_advisor: LLMAdvisor | None = None,
) -> QualityPackage:
    ...
```

落盘操作可由独立函数承担，避免规则测试必须访问文件系统：

```python
def write_quality_package(
    package: QualityPackage,
    output_dir: Path,
) -> PackageManifest:
    ...
```

如果现有契约要求 `run_quality()` 同时落盘，可在入口中组合两个函数，但内部仍保持计算与 I/O 分离。

### 3.2 执行流水线

```text
ParsedDocument 校验
  → EvidenceContext 构建
  → applicability / capability 前置判定
  → 确定性规则执行
  → 生成 issues / candidates / repair proposals
  → 白名单 repair 校验与应用
  → 受影响规则重跑
  → 可选 LLM 顾问调用（只处理未决候选）
  → LLM 建议结构校验与证据引用校验
  → canonical document 构建
  → capability matrix 汇总
  → Gate 推导
  → QualityPackage Pydantic 校验
  → 稳定序列化、哈希与原子化落盘
```

### 3.3 建议目录

```text
quality/
├── __init__.py
├── api.py
├── config.py
├── context.py
├── models_internal.py
├── ids.py
├── pipeline.py
├── evidence/
│   ├── resolver.py
│   ├── requirements.py
│   └── availability.py
├── rules/
│   ├── base.py
│   ├── completeness.py
│   ├── provenance.py
│   ├── tables.py
│   ├── headings.py
│   └── references.py
├── repairs/
│   ├── base.py
│   ├── registry.py
│   └── markdown_safe.py
├── builders/
│   ├── canonical.py
│   ├── markdown.py
│   └── source_locator.py
├── gates/
│   ├── capabilities.py
│   ├── evaluator.py
│   └── invariants.py
├── llm/
│   ├── protocol.py
│   ├── schemas.py
│   ├── prompts.py
│   ├── validator.py
│   └── cache.py
└── packaging/
    ├── canonical_json.py
    ├── hashing.py
    └── writer.py

tests/quality/
├── unit/
├── integration/
├── contract/
├── golden/
└── fixtures/parsed_documents/
```

---

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
- 将 LLM 文本直接写入 canonical content。

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

最终公共 `evidence` 可由这些引用渲染。`value_sha256` 用于检测 LLM 或缓存引用的证据是否已变化。

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
QL-LLM-*    LLM 建议校验
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
- LLM 认为可能续表，但确定性结构证据不足。

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

## 6. 白名单修复

### 6.1 Repair 约束

每个 repair 必须包含：

- 稳定 `rule_id`；
- before/after；
- 受影响 block IDs；
- 结构化证据；
- 可回放参数；
- 幂等性测试；
- 失败后的回滚行为。

### 6.2 MVP 可接受修复

建议第一版只允许低风险、可证明等价的修复，例如：

- 行尾和换行规范化，但需团队先确定 canonical serialization；
- 去除明确的行尾空白；
- 在表格网格 verified 且所有文本完全来自 cells 时，重新渲染损坏的 Markdown 表格；
- 修复明确的 Markdown 分隔符结构，不改变单元格文字；
- 修复完全相同、来源定位相同且上游明确标记为重复的渲染副本。

### 6.3 MVP 禁止修复

- 猜测 OCR 字符；
- 改写句子；
- 补数字、公式、标题、表头或图片描述；
- 根据相邻列推算缺失值；
- 根据视觉平均值伪造 bbox；
- 仅凭 LLM 建议改变事实内容；
- 为制造唯一性而给 row_key 或 reference label 追加序号。

### 6.4 LLM 建议不等于 repair

LLM 对标题层级、续表或引用目标给出的建议属于 advisory decision，不应无条件写入 `applied_repairs`。只有实际改变 `optimized_markdown` 或 canonical 内容且满足白名单定义的操作，才是 repair。

如果公共契约暂时没有 suggestion audit 字段：

- relation/binding 的 evidence 可记录 `suggestion_id`、模型版本和证据引用；
- 接受的 LLM 关系最高仍为 `inferred`；
- 调用计数保留在内部日志和测试结果中；
- 不私自增加 `quality_report.metrics`。

---

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
- repaired issue 不得继续计入 unresolved blocker；
- Gate 必须由最终重跑后的规则结果推导。

### 8.4 manual、reparse、rejected 的边界

| 状态 | 使用条件 |
| --- | --- |
| manual_review_required | 人能够依据现有证据判断，但算法不能唯一确定；或无合法自动重解析建议 |
| reparse_required | 当前证据不足，重新解析大概率可改善，且存在合法 parser_id/options 映射 |
| rejected | 输入契约损坏、核心来源严重矛盾、产物无法安全解释，或安全策略明确拒绝 |

---

## 9. LLM 可选顾问层

### 9.1 是否应在 MVP 启用

建议分两阶段：

- MVP-A：纯规则主链路和全部 Gate 不变量先完成；
- MVP-B：在不改变公共输出兼容性的前提下，加入可关闭的 LLM advisor。

LLM 不应成为 sdp-004、sdp-006 正例通过的必要条件，也不应成为任何契约测试的默认依赖。

### 9.2 合理介入点

当前三个介入点合理，但仅适合生成候选：

1. 跨页表格 continuation 候选排序；
2. 缺 level 或跳级标题的候选父节点/级别；
3. 引用目标多候选时的候选排序和解释。

可选的第四类场景：对 issue 生成面向人工复核的简短说明。该说明不能影响 Gate，也不能写入事实字段。

不建议介入：

- OCR 文字纠错；
- 缺失数字和公式补全；
- bbox 推断；
- 表格缺失值填充；
- 无引用标签时仅凭主题语义建立 verified 关系。

### 9.3 状态上限

即使 evidence_refs 真实存在，校验器通常只能证明“LLM 引用了这些证据”，不能证明其语义结论必然正确。因此：

- 纯 LLM 结论状态上限固定为 `inferred`；
- `verified` 必须由确定性规则独立得出；
- LLM 不能把 manual/reparse blocker 移除；
- LLM 可以帮助缩小人工候选、补充解释，但不能成为 false-pass 的解除条件。

### 9.4 建议 Schema

```json
{
  "schema_version": "1.0",
  "suggestions": [
    {
      "suggestion_id": "stable-id",
      "target_type": "table_continuation",
      "target_ids": ["table-a", "table-b"],
      "proposed_action": {
        "action": "treat_as_continuation",
        "candidate_mapping": [[0, 0], [1, 1]]
      },
      "evidence_refs": [
        {
          "object_type": "table",
          "object_id": "table-a",
          "field_path": "cells",
          "value_sha256": "..."
        }
      ],
      "confidence": 0.78,
      "reasoning": "short explanation"
    }
  ]
}
```

使用判别联合类型，为每种 `target_type` 定义独立的 `proposed_action` Pydantic 模型，禁止自由字典直接进入执行层。

### 9.5 Prompt 约束

Prompt 只提供最小证据投影：

- 目标对象 ID；
- 必要原文；
- header/cell 坐标和 span；
- page/bbox；
- 已有确定性规则结论；
- 允许的 action 枚举；
- 明确要求未知时返回空 suggestions。

不得向模型提供“请修复文档”之类开放指令。必须要求只返回 schema 对象，不使用 Markdown code fence。

### 9.6 validate_suggestion

按顺序校验：

1. JSON/schema 合法；
2. target_type 和 action 在白名单；
3. target_ids 存在且类型正确；
4. evidence_refs 字段路径存在；
5. value_sha256 与当前证据一致；
6. 建议未引入输入中不存在的文字、数字、bbox 或 ID；
7. 建议没有试图提升到 verified；
8. 与确定性规则冲突时拒绝；
9. 接受后仍保留原有 blocker，除非确定性规则重跑独立解决。

### 9.7 成本、延迟和缓存

- 只对规则产生的 manual/inferred 候选调用；
- 按文档批量提交同类候选，设置每批上限；
- 限制证据投影长度，不发送完整 native artifacts；
- 单次超时和整文档总预算均可配置；
- cache key 包含 parser provenance、证据投影哈希、prompt version、schema version、model ID；
- 失败采用负缓存短 TTL，防止同一运行反复请求；
- cache 命中结果仍必须重新执行 evidence hash 校验。

### 9.8 降级行为

以下情况统一降级纯规则模式：

- client 未配置；
- API key 不存在；
- 超时或网络错误；
- schema 解析失败；
- evidence 校验失败；
- 超出调用预算。

降级不得改变原本规则产生的 state。是否向公共 quality_report 增加 warning，需按 D-05 决定；默认只记内部可观测日志，避免“可选顾问不可用”导致文档质量被错误降级。

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

建议交付 `docs/quality_input_requirements.md`，至少包含：

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

1. **Unit**：每条规则的最小正例、边界和反例；
2. **Contract**：ParsedDocument/QualityPackage validator 和 Gate 不变量；
3. **Integration**：完整 `run_quality()`，不落盘；
4. **Packaging**：四件套、哈希、稳定序列化和原子写入；
5. **Golden**：四个共享样例；
6. **Property/Metamorphic**：稳定性、幂等性、证据不伪造；
7. **LLM Offline**：fake advisor、非法返回、超时和无 client。

### 12.2 Golden 4 验收矩阵

| 样例 | 必须验证 | 禁止出现 | 预期 Gate |
| --- | --- | --- | --- |
| sdp-004 | 四个确定 column_path；合并表头按 cell identity 去重；row_key/value/source 正确 | 拍平或丢失父表头、伪造 cell bbox | pass，待 D-01 解决 |
| sdp-005 | 页内确定 binding 保留；漂移列列出 evidence；能力阻塞准确 | 为追求完整而错误跨页绑定 | 默认 manual_review_required；有合法重解析映射时可 reparse |
| sdp-006 | 标题树 verified；数字引用唯一对应；关系 ID 稳定 | 无 marker 证据的引用、跳过唯一性检查 | pass |
| sdp-007 | 输出全部候选；歧义关系不 verified；blocking reason 明确 | 静默选择第一个候选 | manual_review_required |

### 12.3 必增合成场景

| 场景 | 断言 |
| --- | --- |
| no-op | optimized markdown 与输入保持约定一致；repairs 为空 |
| cell bbox 缺失 | locator 使用 table bbox；不存在计算出的 cell bbox |
| table capability unavailable | 表格规则安全跳过并给出 reason |
| span 冲突 | grid 不 verified；不生成错误 binding |
| H1→H3 | inferred + level jump issue |
| heading_level 缺失 | 不生成 verified parent_child |
| citation 0 候选 | missing issue，不生成 verified relation |
| citation 2 候选 | manual review，保存全部候选 |
| OCR failed + 内容不完整 | 合法 recommendation 存在时 reparse |
| 输入 ID 冲突 | rejected 或 manual，取决于是否仍可安全区分 |
| manifest 缺文件 | Pydantic/packaging 校验失败 |

### 12.4 性质测试

- 输入 blocks/tables 数组被随机打乱，输出业务排序和 ID 不变；
- 同一输入运行两次，JSON bytes 和 hashes 一致；
- 所有 verified evidence refs 均能在 ParsedDocument 中解析；
- 输出 bbox 必须来自输入中的某个合法 bbox；
- repair 回放结果一致，第二次运行不重复产生相同 repair；
- 增加无关 info block 不应改变既有 table binding ID；
- 删除必要证据后，状态只能保持或降级，不得升级；
- LLM 开启后不得把纯规则 manual/reparse 结果升级为 pass。

### 12.5 LLM 离线测试

实现 `FakeLLMAdvisor`，覆盖：

- 返回一个 schema 合法、证据真实的建议 → 接受但最高 inferred；
- 引用不存在的 ID → 拒绝；
- value hash 不一致 → 拒绝；
- 返回新增文字/bbox → 拒绝；
- 返回非法 JSON/schema → 降级；
- 抛出 timeout → 降级；
- client=None → 不调用且纯规则结果相同；
- 相同证据第二次调用 → 命中缓存；
- evidence 变化 → 缓存失效；
- LLM 建议与确定性规则冲突 → 规则优先。

### 12.6 回归命令

建议最终形成：

```bash
python -m pytest tests/test_contract_examples.py -q
python -m pytest tests/quality/unit -q
python -m pytest tests/quality/contract -q
python -m pytest tests/quality/integration -q
python -m pytest tests/quality/golden -q
```

在 fixtures 未落地前，golden 测试应明确 skip reason，不能用空 fixture 假装通过。

---

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

### M6：LLM 顾问层（可选增强）

交付：

- LLMAdvisor protocol；
- 判别联合 Schema；
- evidence projection、validator、cache；
- Fake advisor 和降级测试；
- 成本/延迟配置；
- 公共 metrics 是否加入的契约决定。

完成定义：关闭或破坏 LLM 后，纯规则输出不会变差；LLM 无法制造 verified 或解除 blocker。

### M7：联调和交付

交付：

- 接入朱提供的真实 ParsedDocument fixtures；
- 和张确认 reparse catalog/options；
- 跑 shared-dev-v1 golden；
- 更新 README/接口说明；
- 输出已知限制和后续迭代列表。

完成定义：全量质量测试和既有契约回归通过，四件套可供 Web 使用。

---

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
13. `feat(quality): add optional llm advisor`
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
| LLM 幻觉 | 无证据事实进入产物 | typed evidence refs、hash 校验、最高 inferred、规则优先 |
| LLM 不稳定 | 测试波动、延迟增加 | 默认关闭、fake client、缓存、预算、纯规则降级 |
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

### LLM

- [ ] LLM 默认可关闭；
- [ ] 无 key/超时/非法返回可降级；
- [ ] LLM 建议最高 inferred；
- [ ] LLM 不能解除确定性 blocker；
- [ ] evidence ref 和 hash 均校验；
- [ ] fake advisor 覆盖接受、拒绝、缓存和失败路径；
- [ ] 公共 metrics 字段已获得契约确认，或未写入公共输出。

---

## 18. 推荐的实际开工顺序

第一轮先完成 M0 + M1，建立证据模型、能力矩阵和 Gate 不变量；第二轮完成标题树和数字引用，用较简单的关系能力验证架构；第三轮集中实现表格网格、column_path 和跨页降级；随后补 canonical/packaging；最后再接入 LLM 顾问层。

此顺序的关键是先稳定“什么时候不得通过”，再逐步增加“什么时候可以 verified”。这样即使上游 fixtures 尚未完成，质量层也能以合成数据安全推进，并在真实 ParsedDocument 到位后快速联调。
