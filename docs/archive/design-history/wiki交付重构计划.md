# 文档解析模块面向 Wiki 的重构计划

> 状态说明：本文保留重构过程中的设计推演。当前已经实施并冻结的交付方式，以仓库 `README.md` 和 `contracts/wiki_ingest/README.md` 为准：三个基础文件 `optimized.md`、`structure.json`、`quality_issues.json`，大表按需追加 `table_index.sqlite3`。本文后续章节中涉及 manifest、多文件目录包、产物哈希或并行旧契约的内容均为历史方案，不再执行。

关联执行文档：

- [重构规格](../../../specs/archive/wiki交付重构/spec.md)
- [分阶段 Goal Prompts](../../../specs/archive/wiki交付重构/goal-prompts.md)

## 一、重构目标

本次重构保留现有 DDD 和 Ports and Adapters 分层，只调整统一文档模型、质量处理流程和 Wiki 交付出口。

当前质量层交付约束：落盘 `optimized.md`、`structure.json` 和 `quality_issues.json` 三个文件。结构 JSON 包含 canonical document，问题 JSON 包含质量报告、修复记录和人工复核状态；不保存产物哈希或 manifest。

目标链路：

```text
模型路由
  → 具体解析器
  → 统一层 ParsedDocument
  → 质量诊断
  → 修复提案、校验与应用
  → 重新诊断
  → Wiki 准入判断
  → WikiIngestPackage
  → Wiki 建库、索引、召回和问答
```

本次采用直接替换策略：

- 不保留旧模型、转换器和兼容分支；
- 删除旧 `QualityPackage` 及旧质量包接口；
- 类名、文件名和目录名不带格式版本号；
- `revision_id` 只表示文档内容或处理结果的修订，不表示数据结构版本；
- Wiki 只消费质量层确认后的文件包；
- Wiki 不导入解析项目的 Python 领域类，只依赖跨系统 Schema 和文件包。

本计划的设计基线来自 224 个业务文档实例、192 份唯一内容及四种解析模型结果的全量对齐与抽样复核。实验结论见 [原文与四模型解析结果保真度实验分析](../../reports/experiments/原文与四模型解析结果保真度实验分析.md)。结构设计不得只取四种模型的最小公共字段，也不得把解析器成功状态当作内容可交付证明。

## 二、DDD 边界

```text
trigger/        HTTP、CLI 等输入适配
app/            用例编排和跨领域 DTO 组装
domain/         路由、统一文档、质量规则和领域策略
infra/          解析器、存储和文件包写入
contracts/      文档解析系统与 Wiki 的跨系统 JSON Schema
```

| 模块 | 输入 | 输出 | 职责 |
|---|---|---|---|
| 路由模块 | 文件信号、用户参数 | `RoutingDecision` | 选择解析器、fallback 和参数 |
| 解析适配器 | 原始文件、路由决策 | `ParserNormalizationBundle` | 调用具体模型并提取原生证据 |
| 统一层 | 解析器原生结果 | `ParsedDocument` | 统一 block、章节、表格、资源和来源定位 |
| 质量领域 | `ParsedDocument` | `DocumentQualityResult` | 诊断、修复、复检、能力和准入判断 |
| 应用层 | `DocumentQualityResult` | `WikiIngestPackage` | 编排流程并组装跨系统交付对象 |
| 基础设施层 | `WikiIngestPackage` | 物理文件包 | 原子写入、哈希、路径和完整性校验 |
| Wiki | Wiki 文件包 | 页面、索引和问答结果 | 页面生成、切块、embedding、召回和问答 |

质量领域产生可信内容和准入结论，应用层组装 Wiki DTO，基础设施层负责落盘。质量规则不依赖目录结构和 JSONL 写入细节。

质量领域不直接指定某个解析器。质量层只声明失败原因和重新解析所需能力，路由模块根据来源画像、模型能力矩阵和历史尝试选择解析器与参数。

## 三、统一层模型

### 1. 身份语义

```text
source_id
  业务命名空间内的逻辑来源身份

source_revision_id
  原始文件内容身份，由原始字节哈希确定

parser_run_id
  一次具体解析执行的身份

revision_id
  一次正式 Wiki 交付结果的身份
```

约束：

- source_id 不依赖解析器，也不直接等于内容哈希；
- 不同业务来源即使内容相同，也不能因为 SHA-256 相同而合并为一个 source_id；
- 同一逻辑来源的原始内容变化后 source_revision_id 变化；
- 每次解析、回退或参数变化生成新的 parser_run_id；
- revision_id 对来源修订、被采用的解析结果和质量修复结果敏感；
- 文件包目录中的 revision_id 只表示正式交付修订，不承担解析运行历史。

### 2. ParsedDocument

```text
ParsedDocument
├── source
│   ├── source_id
│   ├── source_namespace
│   ├── filename
│   ├── media_type
│   ├── size_bytes
│   ├── sha256
│   └── language
├── source_revision_id
├── source_profile
├── parser_run
├── parts[]
├── pages[]
├── blocks[]
├── sections[]
├── tables[]
├── assets[]
├── ocr_spans[]
├── declared_capabilities
├── observed_capabilities
├── diagnostics[]
└── native_artifacts[]
```

约束：

- source_profile 使用 `SourceProfile`，保存页数或工作表数、文本层、扫描比例、图片与表格预检信息和超长文档信号；
- parser_run 内唯一保存 parser_run_id、解析器身份、公开参数、状态和运行诊断；
- parts 使用 `DocumentPart`，保存解析分片身份、页范围、顺序和原始结果引用；
- pages 使用 `DocumentPage`，保存原始页号、尺寸、旋转、OCR 状态和块顺序；
- `blocks` 是正文唯一权威表示；
- `normalized.md` 由统一渲染器从 blocks 生成，不独立修改；
- block、section、table、cell、asset 和 OCR span 都有稳定 ID；
- 内容对象使用 `source_locators[]` 回溯页码、bbox 或字符范围；
- declared_capabilities 只描述解析器声明能力，observed_capabilities 只描述当前文档实际观测证据；
- 未观测、不支持、不适用和执行失败必须区分，字段为空时记录缺失原因；
- 不知道的置信度使用空值并记录原因，禁止默认满分；
- 公共 JSON 不嵌入 Base64 二进制。

revision_id 不进入 ParsedDocument。应用层在质量结果确定后，根据 source_revision_id、被采用的结构内容和修复结果生成正式交付 revision_id。

### 3. 结构对象

`DocumentBlock`：

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

`SectionNode`：

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

现有 `section_path` 只作为章节树构建输入，不再作为唯一章节表示。

表格 JSON 是权威结构，Markdown 和 CSV 是派生文件；`TableCell` 增加稳定 `cell_id` 和 `source_locators[]`。

资源模型只保存 `asset_id`、path、role、media_type、sha256、size、尺寸、caption、来源定位和引用 block。资源 bytes 通过旁路载荷交给 infra 写入，不进入 `ParsedDocument`。

MarkItDown 等解析器产生的 data URI 在解析适配与统一阶段解码为旁路资源载荷，并改写为稳定 asset 引用。质量层负责检测残留 data URI、校验资产哈希和引用闭合，不在领域规则中直接写二进制文件。

MinerU 长文分片在统一层按明确页范围合并为统一的 pages 和 blocks，同时保留 part_id。质量层验证合并后的页范围是否连续、重复或遗漏，不负责猜测无法确定的分片顺序。

## 四、质量领域

### 1. 正式输出

```text
DocumentQualityResult
├── validated_document
├── issues[]
├── repair_plan
├── applied_repairs[]
├── rejected_repairs[]
├── observed_capabilities
├── gate_decision
├── reparse_recommendation
└── metrics
```

领域结果不包含文件 manifest，也不负责物理目录。

每个 issue 必须包含 origin_layer、detected_by、affected_object_ids、evidence_refs、repairability 和 recommended_action。origin_layer 取 parser、normalization、quality 或 unknown；证据不足时不得把统一字段缺失直接归因于解析器。

### 2. 新流水线

```text
第一次诊断
  → 汇总 issue、能力观测、关系、表格绑定和修复提案
  → 校验修复提案
  → 应用白名单结构化 Patch
  → 从修复后的 blocks 重新生成 Markdown
  → 第二次诊断
  → 标记 repaired 和仍未解决的问题
  → 构建最终观测能力和 validated_document
  → Gate 决策
  → 重解析建议
  → DocumentQualityResult
```

删除先全局修改整篇 Markdown、再执行质量规则的处理方式。

新增 `PatchOperation` 和 `RepairPlan`。每个 Patch 必须满足：

- 目标对象存在且修改前哈希匹配；
- 操作属于自动修复白名单；
- 有真实证据引用；
- 不新增文档事实；
- 幂等、可审计、可回滚。

首批自动修复包括行尾空白、Markdown 表格分隔行，以及 MinerU 表格 HTML 到 Markdown 的确定性表示转换。OCR 字符、数字、公式、表格值、标题内容、缺失段落和引用关系不得自动猜测。

首批硬检测规则包括：

| 规则 | 发现的问题 | 默认处置 |
|---|---|---|
| EMPTY_CONTENT | 状态成功但规范正文为空 | 重新解析 |
| SCAN_WITHOUT_OCR | 扫描主导文档缺少有效 OCR 证据 | 重新解析 |
| PAGE_COVERAGE_MISMATCH | 原文页数与输出覆盖页数不一致 | 重新解析或人工复核 |
| MOJIBAKE_DETECTED | 正文系统性乱码或不可读 | 重新解析 |
| EMPTY_TABLE_STRUCTURE | 表格存在但有效单元格为空 | 重新解析 |
| HTML_TABLE_NORMALIZATION | HTML、cells 和 Markdown 表达不一致 | 安全修复或人工复核 |
| DATA_URI_REMAINS | 统一后仍残留 data URI | 阻止入库并返回统一层处理 |
| ASSET_REFERENCE_INTEGRITY | 资源引用、文件和哈希不闭合 | 安全修复、重新解析或人工复核 |
| SPLIT_PAGE_CONTINUITY | 分片页范围重复、遗漏或断裂 | 阻止入库 |
| PROVENANCE_COVERAGE | 正式对象无法回溯原文证据 | 降级或阻止入库 |

解析器运行状态、字符数和块数只作为证据之一，不能单独决定 Gate。

### 3. MinerU 表格 HTML 转 Markdown

MinerU 可能在 `ParsedTable.html` 中提供完整的 `table` 片段，同时在 table block 的 `markdown` 字段中保留原始 HTML。质量层将其视为“表格表示不规范”，通过白名单修复转换成 Markdown。

触发条件：

- `ParsedTable.html` 存在；
- 并且 `ParsedTable.markdown` 为空、仍包含 `table` 标签，或与结构化 cells 不一致；
- 对应的 table block 唯一存在。

修复流程：

```text
读取 ParsedTable.html
  → 解析 thead、tbody、tr、th、td、rowspan 和 colspan
  → 构建或核对 TableCell 网格
  → 从网格生成 Markdown
  → 更新 ParsedTable.markdown
  → 更新对应 table block.markdown
  → 从 blocks 重新生成 normalized Markdown
  → 重新执行表格质量规则
```

处理规则：

- HTML 实体转换为对应文本；
- `br` 转为单元格内换行表示；
- Markdown 管道符和反斜杠正确转义；
- 删除 `script`、`style` 等非表格内容且不执行脚本；
- 不联网加载 HTML 中的图片、样式或外部资源；
- `th` 作为明确表头，未出现 `th` 时不得假装已验证真实表头；
- 多级表头可以派生 column path，但不得补造标题文字。

Markdown 不支持合并单元格，因此：

- `tables/*.json` 和 `TableCell.row_span/col_span` 保存完整结构并作为权威数据；
- Markdown 只是降级展示；
- 合并单元格的文字放在左上角锚点；
- 被覆盖的位置填空，不复制或猜测内容；
- 质量报告记录 `markdown_representation_loss=true`。

自动应用前必须校验：

- 转换前后的单元格文本哈希一致；
- 非空单元格数量一致；
- 行列覆盖范围合法；
- rowspan 和 colspan 不冲突；
- 生成的 Markdown 每行列数一致；
- table、cells 和对应 block 的身份绑定一致。

任一校验失败时，不覆盖原始 HTML，不生成伪造 Markdown；该 Patch 进入 `rejected_repairs`，并根据缺失证据进入人工复核或重新解析。

证据约束：

- 输出证据状态不得高于输入状态；
- 仅有 page 或 bbox 不足以自动判定为 verified；
- 无法映射的关系或表格绑定必须生成 issue，不能静默丢弃；
- Wiki 必需能力没有观测结果时不得静默放行；
- `reparse_required` 必须带 failure_reasons、required_capabilities 和 evidence_refs；
- 质量领域不得硬编码解析器 ID，路由模块负责把 required_capabilities 解析为模型和参数；
- 同一解析建议没有带来质量增益时，应用层停止自动尝试并转人工复核。

准入规则：

| 质量状态 | ingest_allowed |
|---|---:|
| pass | true |
| pass_with_warnings | true |
| reparse_required | false |
| rejected | false |

## 五、Wiki 交付包

```text
packages/
└── <source_id>/
    └── <revision_id>/
        ├── optimized.md
        ├── structure.json
        └── quality_issues.json
```

`structure.json` 是 Wiki 的结构化预读入口，包含 document_id、canonical_document、表格结构和字段绑定；`quality_issues.json` 保存质量报告、问题状态、修复记录和人工复核项。三个文件通过 document_id 关联，不重复保存 Markdown，不包含 manifest 或产物哈希。

内容权威关系：

| 文件 | 定位 |
|---|---|
| `structure.json.canonical_document.blocks` | 正文权威结构 |
| `structure.json.canonical_document.table_bindings` | 表格字段权威绑定 |
| `structure.json.canonical_document.relations` | 标题、引用等关系 |
| `optimized.md` | 修复后的可读正文 |
| `quality_issues.json.quality_report` | 问题、修复、复核和质量门状态 |

每个表格 JSON 同时保留原始 HTML、结构化 cells、span、派生 Markdown 和转换血缘。质量报告记录 Gate、issue、修复、未解决问题和重新解析所需能力；diagnostics 记录 parser、normalization、quality 三层诊断。

Wiki 页面、slug、overview、purpose、schema、index、WikiLink、chunk、embedding、索引和知识图谱由 Wiki 自己生成。

## 六、代码修改范围

### 1. 领域模型与端口

```text
domain/model/contracts.py
domain/model/__init__.py
domain/ports.py
```

- 重建 `ParsedDocument` 及子模型；
- 新增章节、多来源定位和资源描述；
- 新增 `DocumentQualityResult`；
- 删除 `QualityPackage` 和领域层文件打包职责；
- 调整 ParserPort 和 StoragePort。

### 2. 统一层与解析适配器

```text
domain/normalization/bundle.py
domain/normalization/identity.py
domain/normalization/source_profile.py
domain/normalization/part_merger.py
domain/normalization/section_builder.py
domain/normalization/markdown_renderer.py
domain/normalization/validator.py
infra/parsers/base.py
infra/parsers/markitdown/
infra/parsers/mineru/
infra/parsers/docling/
infra/parsers/anydoc/
infra/parsers/ocr/
```

具体解析器调用方式尽量不变，主要修改原生结果到统一模型的映射。统一入口负责来源画像、pages 和 parts 建模、可证明的分片合并以及 data URI 到旁路资源载荷的转换。

### 3. 质量领域

```text
domain/quality/pipeline.py
domain/quality/models_internal.py
domain/quality/repairs/
domain/quality/repairs/table_html.py
domain/quality/renderers/table_markdown.py
domain/quality/builders/canonical.py
domain/quality/gates/
domain/quality/rules/
```

现有质量规则尽量保留，主要调整输入字段、修复提案输出和复检行为。

### 4. 应用、基础设施和接口

```text
app/use_cases.py
app/orchestration.py
app/bootstrap.py
app/assemblers/wiki_package.py
infra/packaging/wiki_package.py
infra/packaging/wiki_package_writer.py
infra/storage/api_storage.py
api/dto.py
trigger/http/routes.py
frontend/api-types.ts
frontend/app.js
```

应用层统一编排解析、质量处理、必要的重解析、Wiki 包组装和存储。自动重解析设置最大次数并保留决策记录。删除客户端任意覆盖系统质量结果的接口。

### 5. 跨系统 Schema

```text
contracts/wiki_ingest/manifest.schema.json
contracts/wiki_ingest/source_profile.schema.json
contracts/wiki_ingest/block.schema.json
contracts/wiki_ingest/section.schema.json
contracts/wiki_ingest/table.schema.json
contracts/wiki_ingest/asset.schema.json
contracts/wiki_ingest/source_map.schema.json
contracts/wiki_ingest/quality_report.schema.json
contracts/wiki_ingest/diagnostics.schema.json
```

## 七、实施顺序

1. 根据 Wiki 输入 DTO 固定 manifest、blocks、section、table、asset 和 source map 字段。
2. 直接修改 `ParsedDocument`，实现稳定身份、章节树、多来源定位和资源旁路。
3. 修改所有解析器适配器，建立 blocks 到 Markdown 的统一渲染器。
4. 重构质量流水线，接通修复提案、Patch 校验、修复后复检、首批硬检测规则和能力驱动的重解析建议。
5. 实现应用层 Wiki 包 assembler 和 infra 原子 writer。
6. 修改 Storage、UseCase、HTTP 和前端，使主流程只暴露新的正式出口。
7. 删除旧模型、旧样例、旧质量包写入和旧接口。
8. 更新测试和文档，运行完整测试。

## 八、验收条件

- 同一来源换解析器后 `source_id` 不变；
- 不同业务来源的同内容文件不会被 SHA-256 错误合并；
- 原文内容变化后 `source_revision_id` 变化；
- 每次解析尝试具有独立 `parser_run_id`；
- 正式交付内容变化后 `revision_id` 变化；
- 所有结构对象 ID 唯一且可重复生成；
- pages 覆盖原文页数，parts 页范围连续且可回溯；
- section tree 无环且父子关系合法；
- Markdown 可从统一结构确定性生成；
- MinerU 表格 HTML 可以转换成合法 Markdown；
- 表格转换前后的单元格文本和结构证据保持一致；
- rowspan、colspan 在表格 JSON 中完整保留，Markdown 降级损失被明确记录；
- 表格转换校验失败时不会覆盖原始 HTML；
- 自动修复由 issue 和 proposal 触发；
- Patch 前置哈希不匹配时拒绝应用；
- 修复后重新执行质量规则并正确标记 repaired；
- 无证据不能输出 verified；
- 映射失败生成问题而不是静默丢弃；
- 解析成功但正文为空时禁止入库；
- 扫描主导文档没有 OCR 证据时禁止入库；
- 乱码、空表格、页覆盖异常和残留 data URI 能被对应规则发现；
- 重解析建议只声明所需能力，由路由模块选择解析器；
- 非准入状态的 `ingest_allowed` 为 false；
- manifest 文件清单、大小和 SHA-256 可复算；
- source map 覆盖所有 block、table、cell 和 asset；
- 临时写入失败不留下正式 revision；
- Wiki 能把检索结果追溯到 source、page、bbox 或字符范围。

## 九、不属于本次重构的内容

- Wiki 页面规划、WikiLink 和知识图谱；
- embedding、检索切块和召回策略；
- LLM 问答 Agent；
- 问答数据集、召回指标和答案指标。

评测层可以读取 Wiki 文件包、质量报告和 Wiki 运行轨迹，但只产生评测结果，不修改生产交付包。

## 十、与 Wiki 负责人确认的字段

1. Wiki 是否读取完整 blocks；
2. 表格 JSON 的最小字段；
3. 图片 caption、role 和来源定位字段；
4. source map 的对象粒度；
5. Wiki 允许入库的质量状态；
6. 是否需要解析系统提供建议切块；
7. 通过共享目录、对象存储还是消息事件交付。
8. source_id 使用的业务命名空间和逻辑来源键；
9. source_profile、page 和 bbox 在 manifest 与 source map 中的最小字段；
10. section-tree.json 与 sections.json 最终采用的唯一文件名。

未确认的 Wiki 特有语义不加入 `ParsedDocument`，避免统一层绑定 Wiki 当前实现。
