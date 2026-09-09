# 文档解析模块面向 Wiki 的重构规格

## 1. 规格状态

- 状态：历史设计稿，已由当前三文件质量交付契约取代，不再作为实施清单
- 适用仓库：`document_parser`
- 关联计划：`docs/archive/design-history/wiki交付重构计划.md`
- 核心决策：保留 DDD 分层，直接替换旧契约，不实现兼容层

当前实施依据为仓库 `README.md`、`contracts/wiki_ingest/README.md` 和运行时代码。本文中涉及 manifest、多文件目录包、产物哈希或删除当前 `QualityPackage` 的条目只保留为设计过程记录，不得继续照此实施。

本文是本次重构的执行规格。若旧文档中关于 `ParsedDocument`、`QualityPackage`、质量四件套或兼容策略的描述与本文冲突，以本文为准。

本规格以 224 个业务文档实例、192 份唯一内容和四种解析模型结果的对齐实验为证据基线。实验发现 31 组跨业务重复内容、21 份扫描主导 PDF、成功但空结果、中文乱码、空表格结构、data URI、资源引用问题和长文分片根级结构缺失。相关设计不得只依赖解析器运行状态、字符数或四种模型的最小公共字段。

## 2. 背景

当前系统已经具备路由、多个解析器 Adapter、统一模型、确定性质量规则、Gate、存储和 HTTP 接口，但正式交付仍存在以下问题：

1. `ParsedDocument` 同时承担解析中间表示和下游交付数据，身份、正文权威来源和来源定位不够明确；
2. Markdown 与 blocks 可以分别修改，存在内容漂移；
3. 质量流水线先执行全局 Markdown 修复，再诊断问题，修复缺少 issue 驱动和结构化 Patch；
4. `RepairProposal` 已定义但没有接入主流水线；
5. MinerU 表格可能以 HTML 形式进入 table block，质量层没有完成 HTML 到 Markdown 的确定性修复；
6. 质量结果存在单 JSON 和四文件目录两套写法，主应用没有统一使用原子质量包 Writer；
7. Wiki 需要消费质量层正式输出，但当前没有明确的 Wiki 交付契约和准入字段；
8. API 允许客户端覆盖质量结果，破坏质量层作为可信出口的边界。
9. 当前模型缺少一等的来源画像、页和分片对象，无法稳定表达扫描比例、页覆盖和长文分片连续性；
10. source_id、原始内容修订、解析运行和 Wiki 交付修订的身份语义尚未完全拆开；
11. 重解析建议绑定具体解析器会让质量领域依赖基础设施实现；
12. 现有质量规则没有完整覆盖成功但空、扫描无 OCR、乱码、页覆盖、空表、残留 data URI 和来源映射缺失。

## 3. 目标

完成以下闭环：

```text
路由
  → 解析
  → 统一 ParsedDocument
  → 第一次质量诊断
  → 修复提案和验证
  → 安全修复
  → 第二次质量诊断
  → 准入判断
  → WikiIngestPackage
  → 原子写入
  → Wiki 消费
```

成功后：

- 统一层可以稳定表达来源画像、页、分片、正文、章节、表格、资源、OCR 和来源定位；
- 质量层只自动修改可证明安全的格式和结构；
- Wiki 只读取 manifest 即可判断是否允许入库并定位所有内容文件；
- 所有 Wiki 内容都能回溯到源文档证据；
- 解析、质量、交付和 Wiki 语义保持清晰边界。
- 质量层只声明重新解析所需能力，由路由层选择解析器和参数。

## 4. 强制原则

### 4.1 直接替换

- 不保留旧 `QualityPackage`；
- 不实现旧模型转换器；
- 不维护旧 JSON 响应兼容分支；
- 删除不再使用的旧样例、旧测试和旧接口；
- 不创建带版本号的文件、目录、类名或迁移模块。

### 4.2 DDD 边界

- domain 不依赖 trigger 和 infra；
- 解析器私有对象不得泄漏到领域模型；
- 质量领域返回 `DocumentQualityResult`，不写文件；
- app 将质量结果组装为 `WikiIngestPackage`；
- infra 负责物理文件、哈希、路径安全和原子写入；
- Wiki 只依赖 `contracts/wiki_ingest/` 和文件包。

### 4.3 内容安全

- 不自动改写正文事实；
- 不自动修改数字、日期、金额、单位、公式和 URL；
- 不自动猜测 OCR 字符、标题、表格值、caption 或缺失段落；
- LLM 只能提出结构化 Patch，不得直接输出最终正文并绕过验证；
- 输出证据状态不得高于输入证据状态。
- 质量领域不得硬编码解析器 ID；
- 解析器声明支持某项能力，不等于当前文档已经观测到该能力；
- 成功状态、字符数和块数不得单独作为 Wiki 准入依据。

## 5. 范围

### 5.1 本次范围

- 重建统一文档领域模型；
- 调整所有解析器 Adapter 的规范化映射；
- 建立 blocks 到 Markdown 的确定性渲染；
- 建立正式章节树和多来源定位；
- 建立来源画像、页对象和分片对象；
- 合并具有明确页范围的长文分片并保留分片血缘；
- 分离资源描述与二进制载荷；
- 将 data URI 解码为旁路资源载荷并改写为稳定资产引用；
- 重构质量诊断、修复、复检和 Gate；
- 实现 MinerU 表格 HTML 到 Markdown 修复；
- 建立 Wiki 交付 Schema、Assembler 和 Writer；
- 修改存储、应用用例、HTTP DTO 和前端类型；
- 删除旧质量包入口和旧契约；
- 更新所有相关测试、样例和文档。

### 5.2 非范围

- Wiki 页面规划；
- WikiLink 和知识图谱；
- 检索切块与 embedding；
- 关键词、向量和图扩展召回；
- LLM 问答 Agent；
- 评测数据集和问答指标；
- 评测系统对生产交付包的反向修改。

## 6. 目标领域模型

### 6.1 来源身份

`DocumentSource` 必须包含：

```text
source_id
source_namespace
filename
media_type
size_bytes
sha256
language
```

要求：

- `source_id` 是业务命名空间内的逻辑来源身份；
- `source_id` 不依赖解析器，也不直接等于内容哈希；
- 同一逻辑来源使用不同解析器时 `source_id` 不变；
- 不同业务来源即使 SHA-256 相同也不能合并为一个 `source_id`；
- `sha256` 必须从原始字节计算；
- `source_revision_id` 由逻辑来源和原始内容身份确定；
- `parser_run_id` 标识一次具体解析、回退或参数尝试；
- `revision_id` 标识一次正式 Wiki 交付结果；
- `revision_id` 对来源修订、被采用的解析结果和质量修复结果敏感；
- 解析运行历史不得通过覆盖同一 revision 目录保存。
- parser_run_id 只在 ParserRun 中保存，不在 ParsedDocument 顶层重复；
- revision_id 不属于 ParsedDocument，由应用层在质量结果确定后计算。

### 6.2 来源画像、页与分片

`SourceProfile` 必须包含：

```text
media_type
page_count
sheet_count
has_text_layer
scan_page_ratio
image_count_hint
table_count_hint
is_long_document
preflight_diagnostics[]
```

不适用的字段为空并标记 not_applicable，未执行预检与预检失败必须区分。

`DocumentPage` 必须包含：

```text
page_id
page_number
width
height
rotation
ocr_status
block_ids[]
parser_page_ref
```

`DocumentPart` 必须包含：

```text
part_id
order_index
start_page
end_page
parser_result_ref
```

要求：

- 页码从一开始并在同一文档中唯一；
- 已知原文页数时 pages 必须能够解释每个原始页；
- 有明确页范围的分片在统一层排序并合并；
- 合并后仍保留 block 到 part 的关系；
- 页范围重叠、遗漏或无法确定顺序时不得猜测合并，必须生成 normalization issue；
- 工作表文档使用 sheet 相关定位，不伪造 PDF 页码。

### 6.3 来源定位

`SourceLocator` 支持一个对象对应多个来源区域：

```text
source_object_id
page_number
bbox
page_width
page_height
coordinate_system
character_start
character_end
original_text_hash
provenance_status
```

要求：

- 页码从一开始；
- bbox 必须带可解释的坐标系和页面尺寸；
- 字符范围只能指向明确保存的源文本；
- 缺少证据时字段为空，禁止生成伪坐标；
- 多页、跨区域对象使用多个 locator。

### 6.4 文档块

`DocumentBlock` 必须包含：

```text
block_id
source_block_id
order_index
kind
text
markdown
heading_level
section_id
source_locators[]
metadata
```

要求：

- `block_id` 稳定且可重复生成；
- blocks 是正文权威结构；
- `order_index` 唯一、连续；
- Markdown 是单 block 的规范表示；
- 文档级 Markdown 只能由 blocks 和结构对象渲染生成。

### 6.5 章节

`SectionNode` 必须包含：

```text
section_id
parent_section_id
title
level
order_index
heading_block_id
block_ids[]
source_locators[]
```

要求：

- section tree 无环；
- parent 必须存在或为空；
- heading block 必须真实存在；
- block 只能绑定到合法 section；
- 不根据语义猜测缺失标题。

### 6.6 表格

`ParsedTable` 必须包含稳定 table ID、对应 block、caption、行列数、cells、来源定位和派生 Markdown。

`TableCell` 必须包含：

```text
cell_id
text
start_row
start_col
row_span
col_span
column_header
row_header
source_locators[]
```

要求：

- 表格 JSON 是权威结构；
- Markdown 和 CSV 是派生表示；
- 合并单元格由 span 表达；
- 任何派生表示不得改变 cell 文本；
- table block 必须唯一绑定到一张表。

### 6.7 资源

`DocumentAsset` 只保存描述，不保存 bytes：

```text
asset_id
path
role
media_type
sha256
size_bytes
width
height
caption
source_locators[]
referenced_by_block_ids[]
metadata
```

二进制通过 Adapter 旁路载荷进入 Writer。所有路径必须是安全相对路径。

data URI 必须在解析适配与统一阶段安全解码为旁路资源载荷。统一模型只保存资源描述和 asset 引用。无法解码、媒体类型不合法或哈希不一致时生成 normalization issue，不得把 Base64 正文继续交给 Wiki。

### 6.8 能力观测

`declared_capabilities` 表示解析器声明的能力，`observed_capabilities` 表示当前文档实际观测到的证据。两者禁止合并为一个布尔字段。

每项 `CapabilityObservation` 至少包含：

```text
capability
status
evidence_refs[]
missing_reason
metrics
```

status 支持 observed、unavailable、not_applicable、unsupported、not_executed。解析器声明支持表格、OCR 或页定位，不得自动把对应观测状态设为 observed。

### 6.9 ParsedDocument

`ParsedDocument` 聚合：

```text
source
source_revision_id
source_profile
parser_run
parts[]
pages[]
blocks[]
sections[]
tables[]
assets[]
ocr_spans[]
declared_capabilities
observed_capabilities
diagnostics[]
native_artifacts[]
```

模型不包含 Wiki 页面、slug、chunk、embedding 或召回字段。

## 7. 统一和渲染要求

### 7.1 Adapter 输出

每个解析器必须先生成 `ParserNormalizationBundle`，再由统一入口生成 `ParsedDocument`。ParserPort 不再允许部分解析器绕过统一层直接构造不同语义的公共结果。

`ParserNormalizationBundle` 必须保留：

- 原生 block、page、table、cell、asset 和分片引用；
- 解析器状态、公开参数、告警和原生产物哈希；
- 资源二进制旁路载荷；
- 解析器声明能力及当前结果可观测证据；
- 无法映射字段的明确 diagnostics。

统一入口负责构建 SourceProfile、DocumentPage 和 DocumentPart；对具有明确页范围的分片进行确定性合并；将 data URI 转为旁路资源载荷。无法安全完成的映射不得静默丢弃。

### 7.2 ID

- source ID 不包含解析器身份；
- source revision 只表示逻辑来源的原始内容；
- parser run 包含解析器、公开参数和执行身份；
- delivery revision 对最终交付内容敏感；
- block ID 优先使用原始对象 ID；
- fallback ID 使用来源、顺序、类型和稳定位置；
- table、cell、section、asset、OCR span ID 均可重复生成；
- 修复正文不得导致对象 ID 变化。

### 7.3 Markdown Renderer

建立唯一文档 Markdown Renderer：

- 按 block order 输出；
- 标题使用 heading level；
- table block 使用 `ParsedTable.markdown`；
- image block 使用资源相对路径；
- 对 Markdown 特殊字符执行确定性转义；
- 相同结构输入产生完全相同字节；
- 质量修复不得绕过 Renderer 直接维护第二份文档正文。

Renderer 只接受已完成结构校验的对象。分片链接页、data URI 和解析器私有占位符不得成为正式 normalized Markdown 的隐式权威内容。

### 7.4 路由输入与质量反馈

首次路由至少读取 media_type、文本层、扫描比例、页数、图片和表格信号以及旧 Office 格式。默认能力偏好来自实验矩阵：

- 扫描和 OCR 文档优先选择具备 OCR、页定位能力的解析器；
- 复杂表格和图像丰富文档优先选择能输出 cells、资产和 bbox 的解析器；
- 普通文本 PDF 和 DOCX 可选择轻量文本或版面解析器；
- 旧 DOC、PPT、XLS 只能选择已验证支持相应格式的解析器或先执行可追踪格式转换；
- 超长文档必须选择支持稳定分片血缘的解析器或采用外部分片编排。

模型名称、优先级和参数属于路由策略配置，不写入质量规则。质量反馈只提供 required_capabilities、failure_reasons、evidence_refs 和历史增益，路由层据此生成新的 RoutingDecision。

## 8. 质量流水线

### 8.1 执行顺序

```text
输入完整性验证
  → 第一次规则诊断
  → 汇总 RuleResult
  → 形成 RepairPlan
  → Patch 白名单和证据验证
  → 应用 Patch
  → 重新渲染 Markdown
  → 第二次规则诊断
  → issue 状态对账
  → 实际能力观测
  → validated document 和来源映射
  → Gate
  → 重解析建议
  → DocumentQualityResult
```

`DocumentQualityResult` 必须包含：

```text
validated_document
issues[]
repair_plan
applied_repairs[]
rejected_repairs[]
observed_capabilities
gate_decision
reparse_recommendation
metrics
```

质量领域不构造 manifest，不写文件。Wiki Package Assembler 只能消费 DocumentQualityResult，不能绕过质量层直接消费 ParsedDocument。

### 8.2 RuleResult

主流水线必须收集：

- issues；
- repair proposals；
- capability observations；
- relation candidates；
- table binding candidates。

禁止丢弃 `repair_proposals`。

每个 issue 至少包含：

```text
issue_id
code
origin_layer
detected_by
severity
affected_object_ids[]
evidence_refs[]
repairability
recommended_action
status
```

origin_layer 支持 parser、normalization、quality、unknown。若原生解析证据没有被保存，公共字段缺失不得直接归因于 parser。

### 8.3 PatchOperation

Patch 至少包含：

```text
operation
target_type
target_id
field_path
expected_value_hash
replacement
reason
issue_ids[]
evidence_refs[]
```

应用条件：

- 目标和字段存在；
- 前置哈希匹配；
- 操作被注册；
- issue 与证据存在；
- 修改不触碰禁止字段；
- 应用后 Schema 和跨字段约束通过；
- 应用两次无二次变化。

### 8.4 问题状态

- 修复前存在、修复后消失：`repaired`；
- 修复后仍存在：`unfixed`；
- 提案被验证器拒绝：记录到 `rejected_repairs`；
- 无法自动处理：`manual_review_required` 或 `reparse_required`；
- 输入或结果不可用：`rejected`。

### 8.5 首批强制质量规则

| 规则 | 核心判断 | 默认结果 |
|---|---|---|
| EMPTY_CONTENT | 运行成功但规范正文为空 | reparse_required |
| SCAN_WITHOUT_OCR | 扫描主导且没有有效 OCR 页证据 | reparse_required |
| PAGE_COVERAGE_MISMATCH | 原文页或工作表覆盖无法对账 | reparse_required 或 manual_review_required |
| MOJIBAKE_DETECTED | 乱码、不可打印字符或语言分布异常 | reparse_required |
| EMPTY_TABLE_STRUCTURE | 表格对象存在但有效单元格为空 | reparse_required |
| HTML_TABLE_NORMALIZATION | HTML、cells、Markdown 不一致 | repair、manual 或 reparse |
| DATA_URI_REMAINS | 统一结果仍含 data URI | rejected 或 manual_review_required |
| ASSET_REFERENCE_INTEGRITY | 引用、资源、哈希和反向索引不闭合 | repair、manual 或 reparse |
| SPLIT_PAGE_CONTINUITY | 分片页范围重复、遗漏或断裂 | manual_review_required 或 reparse_required |
| PROVENANCE_COVERAGE | 正式输出对象缺少必要来源证据 | pass_with_warnings、manual 或 reparse |

要求：

- 规则使用 SourceProfile、pages、parts 和实际能力证据，不使用扩展名作唯一判断；
- 字符数、块数和 parser success 只能作为辅助信号；
- 页或 bbox 存在不自动证明正文、OCR 或阅读顺序正确；
- 规则必须区分自动修复、重新解析、人工复核和允许降级；
- 自动修复不得创造缺失原文事实。

### 8.6 MinerU 表格 HTML 修复

触发条件：

- table 存在 HTML；
- Markdown 为空、仍为 HTML，或与 cells 不一致；
- table block 唯一存在。

处理流程：

```text
HTML table
  → 安全解析 tr、th、td、rowspan、colspan
  → 构建并校验 TableCell 网格
  → 渲染 Markdown
  → 更新 ParsedTable.markdown
  → 更新 table block
  → 重建文档 Markdown
  → 重跑表格规则
```

安全要求：

- 不执行 script，不加载网络资源；
- 解码 HTML entity；
- 正确处理 br、管道符和反斜杠；
- th 才是已证实表头；
- 没有 th 时允许生成展示所需的降级 Markdown，但必须标记表头未验证；
- rowspan 和 colspan 完整保留在 cells；
- 合并单元格文本只放左上角锚点；
- 被 span 覆盖的位置为空；
- 记录 `markdown_representation_loss`。

自动应用条件：

- 转换前后 cell 文本哈希一致；
- 非空 cell 数一致；
- 网格覆盖合法且 span 无冲突；
- Markdown 行列数一致；
- table、cells 和 block 绑定一致。

失败时：

- 不覆盖原始 HTML；
- Patch 写入 rejected repairs；
- 证据不足进入人工复核；
- 原生结果不足进入重新解析。

### 8.7 validated document 和证据

- validated document 使用修复后的 block、table 和 asset 内容；
- provenance 状态不能因存在 page 或 bbox 被自动提升；
- 无法映射的 relation 或 binding 不输出悬挂对象，同时生成 issue；
- source map 必须覆盖所有正式输出对象；
- 质量报告保留证据引用和对象 ID。

### 8.8 Gate

| 状态 | ingest_allowed |
|---|---:|
| pass | true |
| pass_with_warnings | true |
| manual_review_required | false |
| reparse_required | false |
| rejected | false |

`reparse_required` 必须提供 failure_reasons、required_capabilities、evidence_refs 和已尝试能力摘要。质量领域不得提供强制 parser ID。路由层根据来源画像、模型能力矩阵和历史尝试选择解析器与参数；应用层限制重解析次数，并在相同建议或无质量增益时转人工复核。

## 9. Wiki 交付契约

### 9.1 目录

```text
packages/<source_id>/<revision_id>/
├── manifest.json
├── content/
│   ├── normalized.md
│   ├── blocks.jsonl
│   └── section-tree.json
├── tables/
│   ├── table-*.json
│   ├── table-*.md
│   └── table-*.csv
├── assets/
│   ├── images/
│   ├── attachments/
│   └── assets.jsonl
├── provenance/
│   └── source-map.jsonl
├── quality/
│   └── quality-report.json
└── diagnostics.json
```

### 9.2 Manifest

必须包含：

```text
contract
source_id
source_revision_id
revision_id
created_at
source
source_profile
producer
quality_state
ingest_allowed
artifacts[]
```

artifact 必须包含 path、media_type、sha256、size_bytes 和 required。

要求：

- manifest 最后生成；
- manifest 列出的文件必须存在；
- 正式目录只能在完整校验后出现；
- revision 完成后不可原地修改；
- 非准入结果可以保存，但 Wiki 必须拒绝入库。
- source_profile 只保存 Wiki 判断和评测需要的摘要，不泄漏解析器私有配置。

### 9.3 权威数据

- `blocks.jsonl`：正文结构；
- `section-tree.json`：章节结构；
- `tables/*.json`：表格结构；
- `assets.jsonl`：资源描述；
- `source-map.jsonl`：来源映射；
- `normalized.md`、表格 Markdown 和 CSV：派生表示。

每个表格 JSON 必须保留可用的原始 HTML、结构化 cells、row span、column span、派生 Markdown 和转换血缘。`quality-report.json` 记录 Gate、issue、修复、未解决问题和 required_capabilities；`diagnostics.json` 保留 parser、normalization、quality 三层诊断及 origin_layer。

## 10. 应用和接口

### 10.1 应用结果

解析用例最终返回：

```text
parse_id
source_id
source_revision_id
revision_id
quality_state
ingest_allowed
package_root
manifest_path
```

原始 `ParsedDocument` 只用于内部调试，不是 Wiki 输入。

### 10.2 重解析

- 应用层读取质量建议；
- 路由层把 required_capabilities、SourceProfile、模型能力矩阵和历史尝试解析为 parser 与参数；
- 每次重解析记录所需能力、实际 parser、参数、原因和前一次状态；
- 设置最大尝试次数；
- 同一建议不得无限重复；
- 无增益时停止并转人工复核。

### 10.3 HTTP

- parse 响应提供最终状态和 package 位置；
- 提供 manifest、质量报告、artifact 和完整包下载；
- 删除客户端任意覆盖质量结果的接口；
- 所有 artifact 路径继续执行路径逃逸校验。

## 11. 代码范围

重点修改：

```text
domain/model/
domain/normalization/
domain/quality/
domain/ports.py
infra/parsers/
infra/packaging/
infra/storage/
app/
api/dto.py
trigger/http/routes.py
frontend/
contracts/wiki_ingest/
examples/contracts/
tests/
docs/
```

现有路由策略、解析器调用、EvidenceContext、质量规则主体、Gate 优先级和原子写入思路可以复用，但所有输入输出必须满足本文的新边界。

## 12. 测试要求

### 12.1 单元测试

- ID 稳定性和唯一性；
- source、source revision、parser run 与 delivery revision 身份；
- SourceProfile、DocumentPage 和 DocumentPart；
- section tree；
- Markdown Renderer；
- HTML 表格解析与渲染；
- rowspan、colspan、多级表头、entity、br 和转义；
- Patch 前置条件、白名单、幂等和回滚；
- issue 修复状态对账；
- capability 与 Gate；
- 成功但空、扫描无 OCR、页覆盖、乱码、空表、data URI、资产引用、分片连续性和 provenance 规则；
- manifest 和路径安全。

### 12.2 集成测试

- 每个真实 Adapter 都输出合法统一模型；
- MarkItDown data URI 被转换为旁路资源载荷，统一模型和 Markdown 不残留 Base64；
- MinerU 长文分片形成连续 pages、blocks 和 part 血缘；
- MinerU HTML 表格经过质量层后产生 cells 和 Markdown；
- blocks、文档 Markdown、table Markdown 一致；
- 非准入状态不允许 Wiki 入库；
- source map 覆盖正式对象；
- required_capabilities 能由路由层解析，质量领域不依赖具体 parser；
- package 可写、可读、可复算哈希；
- API 返回最终交付状态和下载结果。

### 12.3 回归测试

- MarkItDown、Docling、MinerU、AnyDoc、OCR 解析入口可用；
- 自动和手动路由仍可用；
- fallback 历史完整；
- 旧 Office 转换不受影响；
- 文件和临时目录按预期清理；
- 完整测试集通过。

## 13. 完成定义

同时满足以下条件才算完成：

1. 代码中不再存在被使用的旧 `QualityPackage`；
2. 主应用只生成新的 Wiki 交付包；
3. Wiki Schema、固定样例和 Pydantic DTO 一致；
4. 所有解析器通过统一入口；
5. SourceProfile、pages、parts、声明能力和实际能力证据进入统一模型；
6. 质量修复完成诊断、Patch、复检闭环；
7. 十类强制质量规则具备测试和明确处置；
8. MinerU HTML 表格转换测试覆盖普通表格和合并单元格；
9. Gate 与 `ingest_allowed` 不变量通过；
10. 重解析由质量能力需求驱动并由路由层选模；
11. manifest 和所有 artifact 哈希可验证；
12. API 不允许覆盖系统质量结果；
13. 完整测试通过；
14. 旧契约、旧样例和冲突文档已删除或改写；
15. Git diff 中没有无关改动。

## 14. 实施顺序

1. 冻结 Wiki 交付字段和 Schema；
2. 重建身份、SourceProfile、pages、parts 和统一领域模型；
3. 建立统一 Renderer，迁移 Adapter，并接通分片合并与资源旁路；
4. 重构质量修复内核；
5. 实现强制质量规则、validated document、证据和 Gate；
6. 实现 Wiki Assembler 与原子 Writer；
7. 接入 Storage、UseCase、HTTP 和前端；
8. 删除旧契约并完成全量测试与文档收口。
