# 单文档质量修复 Agent 实现规格与开发计划

> 分支：`feature/quality-layer`
> 状态：Draft
> 当前输入：解析器输出经 Adapter 转换后的统一质量文档视图
> 适用输出：`optimized.md` 和 `quality_package.json`
> 目标：检查并修复单个文档的格式/结构问题，输出 Wiki 可直接消费的 Markdown 和结构化 JSON。

> 当前交付约束：质量层不输出产物哈希、manifest 或人工复核状态。无法安全自动判断的结果以 warning、reparse_required 或 rejected 表达。

---

## 1. 本 Spec 的目标

本 Spec 指导质量层从“规则检查流水线”演进为“单文档质量修复 Agent”。上游负责选择解析器、统一输出和多文档并行；本分支只处理一次一个文档包。

核心原则是：坏情况不要求穷举，合格状态必须可验证。LLM 负责主动理解文档、发现未被规则覆盖的格式问题并输出修复后的统一文档；质量工具负责读取上下文、验证 Schema、检查内容不变量、重跑确定性规则、生成审核文件和回滚失败修复。

### 1.1 成功标准

- 任意当前阶段解析器结果都能通过 Adapter 进入同一个 `DocumentPackageView`；上游统一层完成后只替换 Adapter；
- 单文档 Agent 能够在有问题时迭代检查和修复，无需预先枚举所有坏样例；
- 修复候选符合统一文档 Schema，block/table/cell ID、来源定位和事实内容不会被无证据改写；
- 修复后生成 `optimized.md` 和包含 canonical document、quality report 的 `quality_package.json`；
- `quality_package.json` 能逐对象保留 `verified`、`inferred`、`reparse_required` 或 `rejected` 结论；
- 通过确定性验证和规则重跑后才接受修复，LLM 不能自行宣布通过；
- 修复失败、无改善、超预算或内容不变量破坏时，保留原版本并返回 rejected 或 reparse_required；
- LLM 关闭、超时、非法输出或不可用时，确定性检查和双文件生成仍可运行；
- 既有契约、Golden、no-op、拒绝和原子落盘测试持续通过。

### 1.2 非目标

- 不在质量层选择或执行 Docling、MinerU、OCR 或其他解析器；
- 不负责多文档批处理、并行调度、队列、重试编排或跨文档关系；
- 不依赖任何解析器的私有对象；
- 不让 LLM 修改正文事实、数字、单位、日期、公式、代码、URL、原始 ID、页码或 bbox；
- 不允许 LLM 执行任意 Python、Shell、文件系统写入或网络操作；
- 不把 LLM 的自由文本直接当作最终 Markdown、canonical JSON 或审核结论；
- 不要求规则列举所有版式错误；规则主要负责已知不变量、证据约束和修复后验收。

---

## 2. 开工前必须确认的契约决策

以下决策应形成团队记录。未确认前，可以实现内部兼容逻辑，但不应把有争议的期望写死为稳定 golden。

| ID | 待确认事项 | 建议决策 | 未确认时的处理 |
| --- | --- | --- | --- |
| D-01 | sdp-004 两份 column_path 标注冲突 | `annotations/quality/golden.jsonl` 作为人工事实源，`expected/...` 由其生成；采购字段版本更符合文件名，但仍需数据负责人确认 | 将 sdp-004 标记为冲突，CI 一致性测试失败并给出差异，不静默任选 |
| D-02 | sdp-005 期望写为 `mixed`，但 Gate 无此枚举 | `mixed` 仅描述内部 binding 状态；最终 Gate 选 `pass_with_warnings`、`reparse_required` 或 `rejected` | 以自动判定为准，不产生人工复核状态 |
| D-03 | capability 无 `not_applicable` | 后续公共契约增加 `not_applicable` | 当前使用 `unavailable` + evidence=`not applicable`，并由 Gate 的 applicability 判断其是否阻塞 |
| D-04 | 质量结果是否保存产物哈希 | 不保存哈希或 manifest | 仅输出两个质量产物 |
| D-05 | LLM metrics 不在已列出的 QualityPackage 1.0 字段中 | 由契约负责人确认后再增加；否则只做内部日志/测试计数 | 不私自向公共 JSON 增加字段 |
| D-06 | `reparse_recommendation.parser_id` 的允许值 | 由路由分支提供 parser catalog 和静态建议映射 | 无合法 parser_id 时直接 rejected，不产生人工复核队列 |
| D-07 | canonical block content 的规范化规则 | 默认保留输入 `markdown`，只允许白名单修复产生变化 | 未确认的格式优化全部 no-op |
| D-08 | 只有未修复 info issue 时应为 pass 还是 pass_with_warnings | 建议 info 不阻塞 pass，warning 才触发 pass_with_warnings；以产品展示约定为准 | 在 Gate 配置中显式固定，禁止不同规则自行解释 |
| D-10 | LLM 在质量层中的角色 | 单文档正式修复 Agent：LLM 主动检查、输出修复候选并根据验证反馈继续修复；默认可关闭 | 关闭时运行确定性检查/审核路径，不假装完成 LLM 修复 |
| D-17 | 临时输入与上游统一层 | 当前以各解析器 Adapter 映射到 `DocumentPackageView`；上游统一层完成后接入新 Adapter | Agent、工具和验证器只依赖内部视图 |
| D-18 | LLM 修复输出形态 | LLM 返回结构化修复后的文档或局部区域；系统确定性生成 Markdown、canonical JSON 和审核文件 | 非结构化自由文本只作为失败输入，不直接提交 |
| D-19 | 修复接受条件 | 由 Schema、内容不变量、来源约束和规则重跑共同决定；LLM 可以改善状态，但不能自行解除 blocker | 验证失败则反馈给 LLM、回滚或转人工 |
| D-20 | 审核粒度 | `quality_report.json` 同时提供文档级状态和 block/table/asset/reference 级可用性结论 | 无法定位时至少给出页码、block 或 issue 范围 |
| D-21 | 工具传输 | 核心先定义 Python 工具协议；MCP 作为可选外部传输层，不让核心逻辑依赖 MCP 运行时 | 离线测试使用 fake tool/agent |
| D-22 | Agent 框架选择 | 使用 Agno 负责单 Agent 运行、工具循环、结构化输出和 session；revision、验证、回滚和产物仍由质量层负责 | 不使用 Team/多 Agent；没有 Agno 时运行确定性路径 |

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

质量层保留确定性入口，同时增加单文档 Agent 入口：

```python
def run_quality(document, *, config=None) -> QualityPackage:
    """确定性检查、canonical 构建和审核输出；不调用 LLM。"""


def run_quality_repair(document, *, config=None, llm_client=None) -> QualityPackage:
    """单文档质量修复 Agent；内部迭代后输出最终 QualityPackage。"""
```

`document` 当前由各解析器 Adapter 转为内部 `DocumentPackageView`；在上游统一层完成前，可直接由 `ParsedDocument 2.2` 适配。多文档并行由调用方负责。

### 3.2 单文档 Agent 流水线

```text
输入文档包 / Adapter
  → 建立稳定 revision 和文档索引
  → 生成摘要、问题提示和可分页上下文
  → LLM 主动检查文档区域并输出修复候选
  → Schema / 内容不变量 / 来源约束校验
  → 重新构建 canonical 与审核结果
  → 确定性规则和 Gate 重跑
  → 通过：提交当前 revision
  → 未通过：反馈验证结果并继续下一轮
  → 无改善、超预算或不可安全解释：回滚并人工复核
  → 三件套 + manifest 原子落盘
```

规则不负责发现所有异常；Agent 可以通过只读工具主动检查未被规则覆盖的结构问题。规则和验证器负责定义“好的文档”必须满足的可枚举条件。

### 3.3 内部模块建议

```text
quality/
├── adapters/                    # 不同输入到统一视图
├── agent/                       # 单文档状态机、上下文、LLM loop
├── tools/                       # 读取、候选提交、验证、事务和回滚
├── rules/                       # 已知不变量与确定性检查
├── repairs/                     # 可回放的确定性修复能力
├── builders/                    # Markdown/canonical/review 构建
├── gates/                       # capability 和最终 Gate
└── packaging/                   # 序列化、manifest、原子落盘
```

核心工具先定义为 Python 协议；需要让外部 LLM 通过 MCP 调用时，再提供 MCP wrapper。工具不得暴露任意代码执行或任意文件写入。

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

## 6. 文档修复和内容不变量

### 6.1 修复候选

LLM 不直接写最终文件，而是返回符合 Schema 的 `RepairedDocumentCandidate`，可以覆盖整篇文档或一个有明确边界的区域。候选必须携带：

- `base_revision`；
- 受影响 block/table/asset/reference ID；
- 修复后的结构内容；
- 简短修复原因；
- 证据引用；
- 可选的受影响范围和下一步建议。

系统根据候选计算 before/after 差异和新的 revision，不信任 LLM 自报的哈希或审核结论。

### 6.2 允许改变的内容

- Markdown 标记、空行和表格分隔结构；
- block 类型、层级、父子关系和阅读顺序；
- table/cell 的网格、span、header role、column path 和续表关系；
- 图片、图注、脚注和引用的结构关系；
- canonical 中由上述结构确定性派生的元数据。

### 6.3 内容不变量

修复前后必须保持：

- block/cell 的可见文本、数字、单位、日期、公式、代码和 URL；
- 原始稳定 ID、source locator、页码、bbox 粒度和 provenance；
- 输入中没有的文字、数字、bbox、图片描述和来源关系不得出现；
- 不能通过删除或改写文本来掩盖质量问题。

若结构修复需要改变事实内容，候选必须拒绝并转人工复核。

### 6.4 迭代、回滚和接受

每轮修复都在独立 revision 中执行：

```text
snapshot(revision N)
  → LLM candidate
  → schema/content/provenance validation
  → canonical + review rebuild
  → rules/Gate rerun
  → commit revision N+1 or rollback
```

接受条件由验证器和重跑结果决定，不由 LLM 自行决定。某个 blocker 只有在修复后确定性检查确认消失时才能解除；LLM 可以导致 `verified` 结果，但不能直接声明 `verified`。

### 6.5 不应硬编码的部分

不为每种文档、解析器或样例编写“遇到 X 就改成 Y”的规则。规则和工具只固定统一文档模型的安全边界；具体发现、修复范围、修复顺序和修复内容由 LLM 根据当前文档决定。

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

## 9. 单文档质量修复 Agent

### 9.1 角色

M6 不再是只给候选的 LLM 顾问层。LLM 是单文档的正式格式/结构修复执行者：

- 主动阅读统一文档包，而不是只处理规则已列出的候选；
- 识别规则无法穷举的版式和结构异常；
- 输出修复后的统一文档或局部区域；
- 根据验证工具返回的问题继续修复；
- 在无法安全判断时主动停止并请求人工复核。

LLM 不修改事实内容，也不直接调用解析器、Shell 或文件系统。

### 9.2 读取上下文

文档很大时采用分层读取：

1. 文档级摘要和目录；
2. 章节、页或 block 范围；
3. 表格完整网格及相邻页；
4. 当前问题前后的局部上下文；
5. 修复后全局验证结果。

工具必须支持 cursor/limit 或稳定 region ID，不能要求一次把整个文档放进上下文。

### 9.3 工具协议

第一版工具分为：

```text
get_document_outline
get_document_summary
get_region_context
get_table_context
submit_repaired_candidate
validate_candidate
rerun_quality_checks
commit_revision
rollback_revision
```

`submit_repaired_candidate` 接收结构化文档或区域，不接收任意脚本。MCP 只作为工具协议的可选传输，不改变核心验证逻辑。

### 9.4 修复候选 Schema

```json
{
  "schema_version": "1.0",
  "base_revision": 3,
  "scope": {
    "type": "region",
    "ids": ["table-03", "block-117"]
  },
  "repaired_document": { "...": "统一文档结构" },
  "reasoning": "简短原因，不作为事实证据",
  "evidence_refs": [
    {"object_type": "table", "object_id": "table-03", "field_path": "cells"}
  ]
}
```

LLM 可以返回整篇文档或局部修复区域；系统负责合并、计算差异并生成三份最终产物。LLM 返回的 `reasoning` 不能替代 evidence，也不能直接决定审核状态。

### 9.5 验证顺序

按以下顺序验证每个候选：

1. JSON/Schema 合法；
2. base revision 仍然是当前版本；
3. 所有 ID、scope 和字段路径存在；
4. 结构满足统一文档契约；
5. 内容、数字、公式、URL 和来源不变量保持；
6. table grid、heading tree、relation target 等局部不变量满足；
7. 重新构建 `canonical_document.json` 和 `quality_report.json`；
8. 重跑确定性规则和 Gate；
9. 无改善、冲突或超过预算时回滚并转人工。

### 9.6 审核结果

审核文件对文档和对象分别给出：

```text
auto_usable
manual_review_required
rejected
```

`auto_usable` 只能由验证器和规则重跑支持；LLM 的 confidence/reasoning 只能作为解释，不得单独放行。

### 9.7 预算、缓存和降级

- 单文档最大轮数、总耗时、输入/输出 token 和局部重试次数可配置；
- 相同 `document_id + revision + context_hash + prompt_version + schema_version + model_id` 可缓存；
- 缓存命中仍要重新执行内容和来源哈希校验；
- client 未配置、超时、非法 Schema、内容变化、工具失败或无改善时，保留原 revision；
- LLM 不可用不能把文档错误降级，也不能伪造修复成功；最终审核文件应明确剩余问题。

### 9.8 结束条件

Agent 在以下情况结束：

- 所有适用验证通过且不存在 blocker；
- 剩余问题均已明确标为人工复核；
- 文档被拒绝，无法安全解释；
- 达到预算或连续若干轮没有改善。

多文档并行、任务重试和队列管理不属于 Agent，由上游负责。

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

1. **Adapter**：不同解析器临时输出都能映射到同一 `DocumentPackageView`；
2. **Unit**：规则、canonical builder、内容不变量和审核汇总；
3. **Contract**：输入/输出 Schema、Gate 不变量和三件套；
4. **Integration**：单文档 Agent 的 inspect → repair → validate 循环；
5. **Packaging**：稳定序列化、manifest、原子写入和篡改检测；
6. **Golden**：共享样例和已知冲突；
7. **LLM Offline**：Fake agent、合法修复、非法内容、超时、无改善、回滚和预算耗尽；
8. **Property/Metamorphic**：内容保真、幂等、稳定 ID 和不会因删除证据而升级。

### 12.2 Agent 必测场景

| 场景 | 断言 |
| --- | --- |
| LLM 发现规则未知的格式问题 | 候选可被 Schema 接受，修复后生成一致三件套 |
| 修复改变正文数字 | 候选拒绝，原 revision 保留 |
| 表格 span/续表修复 | 网格、canonical 和审核结果一致 |
| 验证失败 | 反馈给 Agent，未超过预算时继续修复 |
| 连续无改善 | 停止并标记人工复核，不死循环 |
| LLM 超时/非法输出 | 回滚，确定性审核路径仍可运行 |
| 部分区域可用、部分区域歧义 | review report 分对象标记可用和人工复核 |
| 同一候选重复提交 | revision/repair 幂等，不重复污染输出 |
| 大文档 | 使用摘要、cursor 和局部上下文，不发送整篇全文 |

### 12.3 Golden 和安全断言

保留 sdp-004、sdp-005、sdp-006、sdp-007 的现有能力断言，并额外断言：

- 修复前后事实文本和数字集合保持；
- 所有 `auto_usable` 对象都有可解析证据和通过的验证项；
- `manual_review_required` 对象保留完整候选和原因；
- 无法安全解释的输入不会被 LLM 输出伪造为 pass；
- 三件套由同一 revision 生成，manifest 哈希可复算。

### 12.4 回归命令

```bash
python -m pytest tests/test_contract_examples.py -q
python -m pytest tests/quality/unit -q
python -m pytest tests/quality/contract -q
python -m pytest tests/quality/integration -q
python -m pytest tests/quality/golden -q
```

### 12.5 Fake Agent 覆盖

Fake Agent 至少覆盖：

- 主动发现并修复一个规则未列出的排版问题；
- 返回 Schema 合法但内容被篡改的候选，必须拒绝；
- 返回未知 ID、非法 span、悬空 relation，必须拒绝；
- 修复后验证仍失败，继续一轮；
- 连续无改善，停止并人工复核；
- timeout、非法 JSON、无 client、工具异常全部回滚；
- 相同 revision/context 命中缓存，证据变化后缓存失效。

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

### M6：单文档质量修复 Agent

交付：

- `DocumentPackageAdapter` 和统一质量文档视图；
- 单文档 Agent 状态机、revision、预算和结束条件；
- 摘要、分页、区域和表格上下文读取工具；
- 结构化 `RepairedDocumentCandidate` Schema；
- LLM 主动检查、修复、验证反馈和回滚循环；
- 内容/数字/来源不变量验证；
- 三件业务文件生成和逐对象审核结果；
- Fake Agent、超时、非法输出、无改善和大文档测试；
- 可选 MCP wrapper，不让核心逻辑依赖 MCP 运行时。

完成定义：在单文档范围内，LLM 能发现并修复规则未穷举的格式问题；修复不会改变事实内容；验证失败会继续修复或安全转人工；关闭或破坏 LLM 不会产生错误放行，三件套和 manifest 始终一致。

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
13. `feat(quality): add single-document repair agent`
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
| LLM 幻觉或丢内容 | 修复候选改变事实或删除结构 | typed candidate、内容/来源不变量、revision、回滚、规则重跑 |
| LLM 不稳定或死循环 | 延迟、成本、重复修复 | 单文档预算、无改善停止、缓存、fake agent、人工复核 |
| Agent 只看到局部而漏修 | 文档仍有未知格式问题 | 文档摘要、分区扫描、全局复检、审核文件保留剩余风险 |
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

### 单文档 Agent

- [ ] Adapter 能把当前解析器输出映射到统一质量视图；
- [ ] LLM 默认可关闭，关闭后确定性审核仍可运行；
- [ ] Agent 能主动检查规则未列举的格式问题；
- [ ] 修复候选通过 Schema、内容、来源和 revision 校验；
- [ ] 修复失败、无改善、超时和非法返回会回滚或转人工；
- [ ] Agent 具有最大轮数、时间/token 预算和明确结束条件；
- [ ] `auto_usable` 只能由验证器和规则重跑支持；
- [ ] 三件业务文件和 manifest 来自同一 revision；
- [ ] Fake Agent 覆盖发现、修复、拒绝、缓存、回滚和失败路径；
- [ ] 多文档并行不进入质量 Agent，由上游负责。

---

## 18. 推荐的实际开工顺序

先保持 M1-M5 的确定性规则、canonical、Gate 和 packaging 稳定；然后实现临时 Adapter 和单文档 Agent 的读/修/验循环；再接入真实 LLM、长文档上下文、缓存和预算；最后接入上游正式统一文档包。

关键顺序是：先定义“什么是合格文档”和“什么绝对不能改”，再让 LLM 在这些边界内主动发现和修复未知问题。这样规则不需要穷举所有坏情况，Agent 也不能用自由改写绕过验收。
