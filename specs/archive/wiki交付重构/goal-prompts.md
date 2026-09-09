# Wiki 交付重构分阶段 Goal Prompts

> 归档说明：这些 prompts 记录了早期分阶段设计，不再执行。当前实现已经收口为唯一质量域和三文件 Wiki 交付契约；涉及 manifest、多文件目录包、并行契约或删除当前质量模型的 Goal 均已失效。后续开发以仓库 `README.md`、`contracts/wiki_ingest/README.md` 和现有测试为准。

## 使用方式

以下 prompts 按依赖顺序执行。每次只执行一个 Goal；前一个 Goal 的验收未通过，不进入下一个 Goal。

所有 Goal 共用以下约束：

- 工作目录：`S:\Agent_study\wiki\document_parser`
- 开始前完整阅读：
  - `specs/archive/wiki交付重构/spec.md`
  - `docs/archive/design-history/wiki交付重构计划.md`
  - `docs/reports/experiments/原文与四模型解析结果保真度实验分析.md`
- 保留现有 DDD 和 Ports and Adapters 依赖方向；
- 直接替换旧契约，不做兼容，不写迁移器；
- 不创建带版本号的类、文件和目录；
- 使用 `apply_patch` 修改文件；
- 先检查 Git 状态，保留用户已有改动；
- 只改当前 Goal 范围内的文件，不顺手重构无关模块；
- 每个行为变化必须有测试；
- 完成后运行目标测试、相关集成测试和 `git diff --check`；
- 最终报告修改文件、关键决策、测试结果和尚未解决的问题；
- 如果发现 spec 内部矛盾，停止实施并给出具体冲突位置，不自行发明新边界。

---

## Goal 1：冻结 Wiki 交付契约

### Prompt

```text
你正在 document_parser 仓库实施 Wiki 交付重构的第一个 Goal。

目标：
建立文档解析系统与 Wiki 之间唯一的跨系统交付契约，使 Wiki 可以只读取 manifest 判断是否允许入库，并找到正文、章节、表格、资源、来源映射和质量报告。

必须完成：
1. 创建 contracts/wiki_ingest/。
2. 定义以下 JSON Schema：
   - manifest.schema.json
   - source_profile.schema.json
   - block.schema.json
   - section.schema.json
   - table.schema.json
   - asset.schema.json
   - source_map.schema.json
   - quality_report.schema.json
   - diagnostics.schema.json
3. 创建一份完整固定样例，覆盖：
   - source_id、source_revision_id 和 revision_id
   - 业务命名空间内的逻辑来源身份
   - source_profile 摘要
   - pass_with_warnings 与 ingest_allowed
   - heading、paragraph、table、image blocks
   - section tree
   - 普通表格和合并单元格
   - asset
   - page 和 bbox source locator
   - quality issue 和 applied repair
   - parser、normalization、quality 三类 issue origin
   - capability-driven reparse recommendation
4. manifest 中每个 artifact 必须包含 path、media_type、sha256、size_bytes 和 required。
5. 明确 blocks、section tree、table JSON、assets 和 source map 的权威关系。
6. 增加 Schema 加载、样例验证、路径安全、对象引用完整性测试。

约束：
- 不修改领域模型和业务流水线。
- 不添加 Wiki 页面、slug、chunk、embedding 或召回字段。
- 不添加格式代际标识字段。
- 不使用解析器私有字段作为跨系统必需字段。
- source map 必须能引用 block、section、table、cell 和 asset。
- source_id 不得直接由内容哈希充当；不同业务来源的同内容文件必须可区分。
- 表格 JSON 必须允许保留原始 HTML、cells、span、派生 Markdown 和转换血缘。
- quality report 的重解析建议只声明 required_capabilities，不指定强制 parser。

验收：
- 所有 Schema 是合法 JSON Schema。
- 固定样例通过全部 Schema。
- manifest 中的 artifact 路径与样例文件一致。
- table 和 block、section 和 block、asset 和 block 的引用全部有效。
- manifest 的 source、source revision、delivery revision 和 source_profile 语义明确。
- issue origin、required_capabilities 和 evidence_refs 通过 Schema 校验。
- 测试通过，git diff --check 通过。

交付时说明：
- 字段所有权；
- 哪些字段由解析层产生；
- 哪些字段由质量层产生；
- 哪些内容明确留给 Wiki 生成。
```

---

## Goal 2：重建统一领域模型

### Prompt

```text
你正在实施 Wiki 交付重构的统一领域模型 Goal。Goal 1 的 contracts/wiki_ingest 已经通过测试。

目标：
直接重建 ParsedDocument 及其子模型，使其成为解析器无关、可追溯、可确定性渲染的内部统一表示。

必须完成：
1. 重构 domain/model 中与 ParsedDocument 有关的模型。
2. 建立：
   - DocumentSource
   - SourceProfile
   - DocumentPage
   - DocumentPart
   - SourceLocator
   - DocumentBlock
   - SectionNode
   - ParsedTable
   - TableCell
   - DocumentAsset
   - OcrSpan
   - ParserRun
   - CapabilityObservation
   - ParsedDocument
3. 拆分四类身份：
   - source_id 是业务命名空间内的逻辑来源身份，不依赖解析器，也不直接等于内容哈希；
   - source_revision_id 对原始内容敏感；
   - parser_run_id 标识一次具体解析尝试；
   - revision_id 标识一次正式 Wiki 交付结果。
4. 所有结构对象使用稳定 ID。
5. SourceLocator 支持多个 page、bbox 或字符范围。
6. SourceProfile 明确区分 not_applicable、not_executed 和 preflight failed。
7. pages 和 parts 支持页覆盖及长文分片血缘。
8. DocumentAsset 不再保存 bytes，只保存描述和安全路径。
9. declared_capabilities 与 observed_capabilities 分离。
10. ParseConfidence 不允许未知值默认满分。
11. ParsedDocument 不包含 Wiki 页面、索引和检索字段。
12. 删除旧 QualityPackage、旧 PackageManifest 及其领域导出，但暂不实现新质量流水线。
13. 更新 domain/model/__init__.py、项目顶层导出和 domain/ports.py 中相关类型。

约束：
- 不保留旧 ParsedDocument 的兼容构造方式。
- 不写旧数据转换器。
- 不修改具体解析器实现；本 Goal 可使用测试构造新模型。
- 不把跨系统 manifest 放进质量领域。
- 字段名和类名不带版本号。
- 不同业务来源即使 SHA-256 相同也不能自动共用 source_id。
- 解析器声明能力不能自动写成当前文档 observed。
- parser_run_id 只保存在 ParserRun 中；revision_id 不进入 ParsedDocument，由应用层在质量结果确定后计算。

验收：
- 同一逻辑来源换解析器后 source_id 相同。
- 不同业务来源的重复内容保持不同 source_id。
- 原始内容变化后 source_revision_id 变化。
- 每次解析尝试具有独立 parser_run_id。
- block、section、table、cell、asset 和 OCR span ID 稳定且唯一。
- page 与 part ID 稳定，明确页范围时覆盖连续。
- section tree 跨字段校验有效。
- table 必须绑定真实 table block。
- asset 引用必须指向真实 block。
- 绝对路径、父目录跳转和非法哈希被拒绝。
- 新模型单元测试通过。

交付时列出所有删除的旧公共类型以及新的领域边界。
```

---

## Goal 3：统一规范化与迁移解析器 Adapter

### Prompt

```text
你正在实施统一规范化和解析器 Adapter Goal。新的 ParsedDocument 模型已经完成。

目标：
让 MarkItDown、MinerU、Docling、AnyDoc 和 OCR 都通过 ParserNormalizationBundle 与同一规范化入口生成 ParsedDocument，不允许 Adapter 绕过统一语义。

必须完成：
1. 重构 domain/normalization/bundle.py。
2. 新增并接入：
   - identity.py
   - section_builder.py
   - markdown_renderer.py
   - validator.py
3. Markdown Renderer 以 blocks、tables 和 assets 为输入生成文档 Markdown。
4. 从 heading blocks 构建正式 SectionNode tree。
5. 从原文预检和解析结果构建 SourceProfile、DocumentPage 与 DocumentPart。
6. 对具有明确页范围的 MinerU 分片进行确定性合并，保留 part 到 page、block 的血缘。
7. 将 data URI 安全解码为旁路资源载荷，生成稳定 asset 引用，公共模型和 Markdown 不保留 Base64。
8. 调整 ParserPort，使所有 Adapter 走 normalize 路径。
9. 逐个迁移：
   - MarkItDown
   - MinerU
   - Docling
   - AnyDoc
   - OCR
10. 资源 bytes 通过 ParserOutcome 或旁路 payload 返回，领域模型只保留描述。
11. 分开记录 declared_capabilities 与当前文档 observed_capabilities，不虚构缺失证据。
12. 无法映射的原生字段、资源和分片必须生成 normalization issue。
13. MinerU 表格 HTML 原样保留在 ParsedTable.html，cells 尽力解析；不要在此 Goal 内执行质量修复。

约束：
- 不修改路由选择策略。
- 不在 Adapter 中决定 Wiki 准入。
- 不在 Adapter 中修复正文事实。
- 不维护独立的文档级 Markdown 副本；最终 Markdown 必须由统一 Renderer 生成。
- 解析器私有 payload 只能进入 metadata 或 native artifact，不能成为公共必需字段。
- 页范围不明确、重复或遗漏时不得猜测合并顺序。
- data URI 无法安全解码时不得静默删除或继续写入 normalized Markdown。

验收：
- 每个 Adapter 的 fixture 都能生成合法 ParsedDocument。
- 相同输入重复运行产生相同结构 ID 和 Markdown。
- blocks 顺序唯一、连续。
- section tree 合法。
- 已知原文页数时 pages 能解释每个原始页。
- 长文分片在页范围明确时合并连续，并保留 part_id。
- table、asset、OCR 和 locator 引用完整。
- MarkItDown 图片样例不残留 data URI，资源旁路哈希可复算。
- 原生证据不足时 capability 明确标记原因。
- 解析器声明支持但当前结果无证据时不得标记 observed。
- Adapter 单元测试、解析集成测试和路由回归测试通过。

交付时说明每个 Adapter 能提供和不能提供的证据能力。
```

---

## Goal 4：重构质量修复内核

### Prompt

```text
你正在实施质量修复内核 Goal。所有解析器已输出新的 ParsedDocument。

目标：
把质量流水线改成“诊断 → 修复提案 → Patch 验证 → 应用 → 重新渲染 → 复检”，并确保所有自动修复都可证明安全。

必须完成：
1. 重构 domain/quality/pipeline.py。
2. 扩展 models_internal.py：
   - PatchOperation
   - RepairPlan
   - RejectedRepair
   - RepairValidationResult
3. _execute_rules 必须收集 repair_proposals。
4. 重构 repairs/base.py 和 registry.py：
   - proposal validator
   - patch applier
   - registry
   - replay
   - rollback
5. 把现有行尾空白和表格分隔行修复改造成结构化 Patch。
6. 第一次诊断后才能生成修复。
7. 修复后必须从 blocks 重新渲染文档 Markdown。
8. 第二次诊断后对账 issue：
   - repaired
   - unfixed
   - manual_review_required
   - reparse_required
   - rejected
9. 新增 DocumentQualityResult，删除流水线对旧 QualityPackage 的返回。
10. DocumentQualityResult 包含 validated_document，质量层不再维护其他独立正文对象。
11. 每个 issue 记录 origin_layer、detected_by、affected_object_ids、evidence_refs、repairability 和 recommended_action。
12. 记录 issue_ids、evidence_refs、before hash、after hash、target 和回滚信息。

约束：
- 不允许 RepairRule 接收整篇 Markdown 后无目标地改写。
- 不允许 Patch 修改 ID、源哈希、数字、公式、日期、URL、bbox 或原始文本证据。
- LLM 不在本 Goal 内实现。
- 修复失败必须保留修复前文档。
- 相同输入的修复结果必须确定。
- 原生证据不足时不得把公共字段缺失直接归因于 parser。
- Wiki Assembler 只能消费 DocumentQualityResult，不能直接消费 ParsedDocument。

验收：
- 没有 issue 或 proposal 时不产生 applied repair。
- 前置哈希不匹配时 Patch 被拒绝。
- 非白名单字段修改被拒绝。
- 每个 applied repair 能 replay 和 rollback。
- 同一 Patch 应用两次没有二次变化。
- 修复后的 Markdown 与 blocks 一致。
- repaired issue 在第二次诊断中确实消失。
- parser、normalization、quality 和 unknown 问题来源均有模型与测试。
- 质量单元和集成测试通过。

交付时给出一个完整 issue 到 Patch、应用、复检和状态对账示例。
```

---

## Goal 5：实现 MinerU 表格 HTML 修复

### Prompt

```text
你正在实施 MinerU 表格 HTML 到 Markdown 的质量修复 Goal。结构化 Patch 内核已经完成。

目标：
将 ParsedTable.html 中的 table 片段安全解析成 TableCell 网格，并生成与结构证据一致的 Markdown；更新 table 和对应 block 后重跑表格规则。

必须完成：
1. 新增 domain/quality/repairs/table_html.py。
2. 新增 domain/quality/renderers/table_markdown.py。
3. 支持：
   - table、thead、tbody、tr、th、td
   - rowspan、colspan
   - 多级表头
   - HTML entity
   - br
   - Markdown 管道符和反斜杠转义
4. 忽略 script 和 style，不执行脚本，不访问网络。
5. th 才能标记已验证表头；没有 th 时记录 header 未验证。
6. 合并单元格：
   - JSON cells 保留 span；
   - Markdown 文本放左上角锚点；
   - 被覆盖位置为空；
   - 记录 markdown_representation_loss。
7. 修复前验证 table block 唯一绑定。
8. 修复后同时更新 ParsedTable.markdown 和 table block.markdown，并重新生成文档 Markdown。
9. 自动应用前验证：
   - cell 文本哈希一致
   - 非空 cell 数一致
   - 网格覆盖合法
   - span 无冲突
   - Markdown 行列数一致
10. 失败时保留原始 HTML，将 Patch 写入 rejected repairs，并产生人工复核或重解析结论。

约束：
- 不使用正则表达式解析完整 HTML table。
- 不猜测缺失单元格、表头或数值。
- 不复制合并单元格文本填满覆盖区域。
- table JSON 是权威结构，Markdown 是派生表示。

测试至少覆盖：
- 普通表格
- 只有 td 的表格
- thead 和 tbody
- rowspan
- colspan
- rowspan 与 colspan 组合
- 多级表头
- entity、br、管道符
- 非法 span
- 不闭合 HTML
- script/style
- table 与 block 不匹配
- 转换幂等
- 转换失败不覆盖输入

交付时展示普通表格和合并单元格的输入 HTML、cells 和输出 Markdown。
```

---

## Goal 6：实现强制质量规则、证据能力和 Gate

### Prompt

```text
你正在实施强制质量规则、证据能力和 Wiki 准入 Goal。质量修复和表格转换已经完成。

目标：
确保 validated_document、来源映射、实际能力观测、Gate 和重解析建议基于修复后证据，并实现实验发现的主要失败模式，避免证据升级、静默丢失和错误放行。

必须完成：
1. validated_document 使用修复后的 ParsedDocument，不建立另一份独立正文。
2. 实现并注册：
   - EMPTY_CONTENT
   - SCAN_WITHOUT_OCR
   - PAGE_COVERAGE_MISMATCH
   - MOJIBAKE_DETECTED
   - EMPTY_TABLE_STRUCTURE
   - HTML_TABLE_NORMALIZATION
   - DATA_URI_REMAINS
   - ASSET_REFERENCE_INTEGRITY
   - SPLIT_PAGE_CONTINUITY
   - PROVENANCE_COVERAGE
3. 每条规则明确自动修复、重新解析、人工复核或允许降级的条件。
4. provenance_status 不得仅因存在 source_block_id、page 或 bbox 自动变为 verified。
5. relation 或 table binding 无法映射时：
   - 不输出悬挂对象；
   - 生成可定位 issue；
   - 降低对应 capability。
6. observed_capabilities 对 observed、unavailable、not_applicable、unsupported 和 not_executed 做明确区分。
7. Wiki 必需能力未观测时必须阻止入库。
8. Gate 输出 quality_state 和 ingest_allowed。
9. reparse_required 输出 failure_reasons、required_capabilities、evidence_refs 和历史尝试摘要，不输出强制 parser ID。
10. 建立 source map，覆盖 block、section、table、cell 和 asset。
11. Gate 仍是唯一最终状态决策者，单条规则不得直接指定最终文档状态。

约束：
- 输出证据状态不得高于输入状态。
- unavailable 与 not applicable 的处理必须显式。
- parser success、字符数和块数不得单独决定 Gate。
- 质量规则不得导入具体解析器实现或硬编码模型名称。
- required_capabilities 无法由当前路由配置满足时转人工复核并记录配置缺口。
- 本 Goal 不执行自动重解析，只产生建议。

验收：
- 无证据不能 verified。
- 映射失败必有 issue。
- source map 无悬挂目标。
- 成功但空、扫描无 OCR、页覆盖不足、乱码和空表格样例均被阻止入库。
- data URI 残留、资产引用失败和分片断裂样例均产生正确 origin 和处置。
- pass 和 pass_with_warnings 才能 ingest。
- manual、reparse、rejected 均不能 ingest。
- reparse 状态始终带 required_capabilities 和证据。
- Gate 不变量、validated document、relation、binding 和 provenance 测试通过。
```

---

## Goal 7：实现 Wiki Package Assembler 与原子 Writer

### Prompt

```text
你正在实施 Wiki 交付包 Goal。跨系统 Schema和 DocumentQualityResult 已经稳定。

目标：
由 app 将 DocumentQualityResult 组装为 WikiIngestPackage，由 infra 原子写入 packages/<source_id>/<revision_id>/。

必须完成：
1. 新增 app/assemblers/wiki_package.py。
2. 新增 WikiIngestPackage 应用 DTO，不把它放进质量规则模块。
3. 新增或重构 infra/packaging/wiki_package.py 和 writer。
4. 写出：
   - manifest.json
   - content/normalized.md
   - content/blocks.jsonl
   - content/section-tree.json
   - tables/*.json
   - 可生成时的 tables/*.md 和 tables/*.csv
   - assets/assets.jsonl 和二进制资源
   - provenance/source-map.jsonl
   - quality/quality-report.json
   - diagnostics.json
5. manifest 保存 source_id、source_revision_id、revision_id 和 source_profile 摘要。
6. table JSON 保留原始 HTML、cells、span、派生 Markdown 和转换血缘。
7. quality report 保存 issue origin、Gate、修复、未解决问题和 required_capabilities。
8. diagnostics 区分 parser、normalization 和 quality 诊断。
9. 每个 artifact 计算 SHA-256、size 和 media type。
10. manifest 最后生成。
11. 临时目录完整校验后原子 rename。
12. 正式 revision 目录不可原地覆盖。
13. Writer 支持读取并验证已完成包。
14. 输出必须通过 contracts/wiki_ingest 的 Schema。

约束：
- Assembler 负责映射，Writer 不决定质量状态。
- Writer 不修改内容。
- Assembler 只能接受 DocumentQualityResult，不能接受裸 ParsedDocument。
- CSV 无法表达合并单元格时不得替代 table JSON。
- 非准入包允许保存，但 manifest 必须明确 ingest_allowed=false。
- 所有路径执行安全相对路径和目录逃逸校验。

验收：
- 固定输入产生稳定 artifact 字节和哈希。
- manifest 列出的文件全部存在。
- source、source revision、delivery revision 和 source_profile 可正确读取。
- 表格原始表达、结构表达和派生表达之间的血缘完整。
- 篡改、缺失和路径逃逸被拒绝。
- 写入中断不留下正式 revision。
- 已存在 revision 默认拒绝覆盖。
- package round-trip 和 Schema 测试通过。
```

---

## Goal 8：接入应用、存储、HTTP 和前端

### Prompt

```text
你正在实施主应用接入 Goal。Wiki Package Assembler 和 Writer 已通过测试。

目标：
让正式解析用例执行“解析 → 质量 → 必要时重解析 → 打包 → 存储”，并通过 HTTP 暴露最终状态和文件包。

必须完成：
1. 修改 app/use_cases.py、orchestration.py 和 bootstrap.py。
2. 应用结果返回 parse_id、source_id、source_revision_id、revision_id、quality_state、ingest_allowed、package_root 和 manifest_path。
3. 接入 StoragePort 和 ApiStorage 的新 Wiki 包读写。
4. 删除旧 quality_package.json 写入和读取。
5. 删除允许客户端 POST 覆盖质量结果的接口。
6. 提供：
   - parse
   - manifest 查询
   - quality report 查询
   - artifact 列表和单文件下载
   - 完整包下载
   - 显式 reparse
7. 自动重解析：
   - 只响应包含 failure_reasons、required_capabilities 和 evidence_refs 的合法建议
   - 由路由层结合 SourceProfile、模型能力矩阵和历史尝试选择 parser 与参数
   - 设置最大次数
   - 记录每次所需能力、原因、实际 parser、参数和状态
   - 相同建议或无质量增益时停止
8. 更新 api/dto.py、frontend/api-types.ts 和 frontend/app.js。

约束：
- trigger 不直接构造 infra 实现。
- API 不返回可以被误认为 Wiki 正式输入的裸 ParsedDocument。
- 质量领域不指定 parser，应用层也不得跳过路由策略自行硬编码模型。
- 密钥和私有 parser options 不进入 manifest 或响应。
- 保留路径安全和临时归档清理。

验收：
- parse 请求最终产生 Wiki 包。
- 响应状态与 manifest 一致。
- 非准入结果可查询但明确不能 ingest。
- 旧质量覆盖接口不存在。
- 下载包可以重新验证。
- 自动重解析不会循环。
- 扫描无 OCR、复杂表格失败和旧 Office 不支持等建议能由路由策略选出具备所需能力的候选。
- 当前没有满足 required_capabilities 的解析器时转人工复核，不伪造可执行建议。
- API、Storage、UseCase 和前端类型测试通过。
```

---

## Goal 9：删除旧契约并完成全量验收

### Prompt

```text
你正在实施 Wiki 交付重构的收口 Goal。前面所有 Goal 已分别通过测试。

目标：
删除旧契约、冲突实现和过时文档，完成全仓库测试与交付审计。

必须完成：
1. 使用 rg 查找并删除所有仍被使用的：
   - QualityPackage
   - package_manifest.json
   - quality_package.json
   - optimized.md 旧四件套假设
   - 旧 Schema 身份和交付标识字段
2. 删除旧 examples/contracts 中不再符合新契约的样例。
3. 删除或重写旧 scripts 和 frontend 映射。
4. 更新：
   - README
   - 架构文档
   - 开发分工
   - 统一文档包要求
   - 质量层进度和决策
5. 检查所有新文件名、目录名和类名不带格式版本号。
6. 建立来自保真度实验的固定回归样例，至少覆盖：
   - 扫描件成功但空
   - PDF 中文乱码
   - 扫描表格只有空结构
   - MinerU 长文分片边界
   - XLSX 单元格对账
   - DOCX data URI 资源化
7. 验证这些样例的问题来源、required_capabilities、Gate 和 Wiki 包产物符合 spec。
8. 运行：
   - 目标单元测试
   - 质量集成测试
   - API 测试
   - 完整 pytest
   - JSON Schema 样例验证
   - git diff --check
9. 审计 Git diff，确认没有无关文件、缓存、临时输出和密钥。

约束：
- 不通过跳过、xfail 或降低断言来制造通过结果。
- 不保留无人使用的兼容代码。
- 不删除仍然有效的路由、解析器或安全测试。
- 不修改 Wiki 仓库。
- 固定回归测试不得依赖外部绝对数据路径，也不得重新调用四种解析模型。
- 如需复核全量实验，只运行只读审计脚本，不覆盖原始文档和已有解析结果。

完成定义：
- specs/archive/wiki交付重构/spec.md 的完成定义逐项满足。
- 完整测试通过。
- 新固定样例可以从解析到 Wiki 包完成端到端验证。
- 六类实验失败模式均有回归测试，且问题归因不混淆 parser、normalization 和 quality。
- 旧 QualityPackage 不再出现在生产调用链。
- 文档描述与实际代码一致。

最终报告必须包含：
- 变更摘要；
- 删除的旧接口；
- 新调用链；
- 全部测试命令和结果；
- 未完成项；若存在未完成项，不得声称重构完成。
```
