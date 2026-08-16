# 三方联调接口与固定样例

本文是张云雅、朱和质量负责人之间的联调协议。字段定义以
`core/contracts.py` 为唯一事实源；这里说明谁生产、谁消费、哪些字段在 MVP 中不能省略。

## 1. 固定链路

```text
ParseRequest
  -> RoutingDecision       张云雅生产，朱消费
  -> ParsedDocument        朱生产，质量层消费
  -> QualityPackage        质量层生产，朱的 Web/API 消费
       -> ReparseRecommendation（可选）返回张云雅
```

对应固定样例：

| 阶段 | 样例 | 生产者 | 消费者 |
|---|---|---|---|
| 路由决策 | `routing_decision.json` | 张云雅 | 朱 |
| 统一解析 | `parsed_document.json` | 朱 | 质量负责人 |
| 质量结果 | `quality_package.json` | 质量负责人 | 朱；需要重解析时同时给张云雅 |

三份样例描述同一个 `document_id`，可以直接作为前后端 Mock 和模块 fixture。样例中的
SHA-256、时间和内容是固定测试值，不代表真实文件摘要。

## 2. 接口一：`RoutingDecision 1.0`

张云雅必须输出：

| 字段 | 含义 | MVP 约束 |
|---|---|---|
| `mode` | `auto` 或 `manual` | 两种模式都必须支持 |
| `requested_parser_id` | 用户指定模型 | 自动模式可为空；手动模式必填 |
| `selected_parser_id` | 本次选中的模型 | 必须是已注册且可执行的 ID |
| `reason` | 选择原因 | 不得为空 |
| `signals` | 文件预检特征 | 至少包含扩展名和字节数 |
| `parser_options` | 传给 Adapter 的参数 | 必须可序列化、可复现 |
| `fallback_parser_ids` | 自动模式备用顺序 | 不得包含当前模型或重复模型 |
| `allow_automatic_fallback` | 是否允许自动换模型 | 手动模式必须为 `false` |
| `unavailable_reasons` | 模型不可用原因 | 不得用“未选择”冒充“不可用” |

MVP 正式解析器 ID 由能力注册表确定，但必须分别对应 Docling、MinerU、OCR。现有
MarkItDown 可继续注册用于回归。

手动模式硬约束：

```text
requested_parser_id == selected_parser_id
allow_automatic_fallback == false
```

若指定模型不可用，应返回明确错误或失败任务，不能静默生成另一个模型的
`RoutingDecision`。

## 3. 接口二：`ParsedDocument 2.2`

朱必须把 Docling、MinerU、OCR 的私有结果转换为这一协议，不能把第三方 Python 对象
直接交给质量层。

基础与执行来源：

- `document_id`、`filename`、`file_type`、`source_size_bytes`、`source_sha256`；
- `routing_decision`：保留路由层原决策；
- `provenance`：实际 `parser_id`、模型、版本、参数、耗时及 fallback 历史；
- `markdown`：完整统一正文；
- `warnings`：非致命问题。

`routing_decision.selected_parser_id` 是计划执行模型，`provenance.parser_id` 是实际成功
模型。发生 fallback 时两者允许不同，但必须在 `fallback_history` 中解释。

质量层必须获得的结构证据：

| 字段 | 质量用途 | 缺失时处理 |
|---|---|---|
| `blocks[].source_block_id` | 统一节点回溯 | 在 `capabilities` 声明不可用 |
| `blocks[].order_index` | 阅读顺序和标题恢复 | 不得伪造顺序 |
| `blocks[].heading_level` | 标题树 | 不确定时为空 |
| `blocks[].anchor` | page、bbox、原文和章节路径 | 只填写模型真实提供的信息 |
| `tables[].cells` | 表格网格、表头和 span | 无 cells 时保留 HTML/Markdown/截图并声明缺失 |
| `ocr_spans[]` | 图片/扫描件 OCR 质量 | 非 OCR 路径可为空 |
| `assets[]` | 图片和附件 | 使用安全相对路径和哈希 |
| `native_artifacts[]` | 原生 JSON/Markdown/图片证据 | 大文件只传安全引用，不嵌入 API |
| `capabilities` | 能力可用性和粒度 | `partial/unavailable/failed` 必须给原因 |

朱负责保存真实证据，不负责替质量层判定某个标题或引用一定正确。

## 4. 接口三：`QualityPackage 1.0`

质量负责人必须输出：

- `optimized_markdown`：安全修复后的 Markdown；没有安全修复时允许与输入一致；
- `canonical_document.blocks`：稳定顺序、内容和来源；
- `canonical_document.table_bindings`：表格字段绑定；
- `canonical_document.relations`：标题、引用等关系；
- `quality_report`：状态、issues、修复、能力矩阵、质量门和重解析建议；
- `package_manifest`：核心产物名和 SHA-256。

表格字段绑定最低字段：

```text
binding_id
table_id
block_id
row_key
column_path
value
source_locator
status
evidence
```

合并表头必须使用完整 `column_path`。来源只有表级 bbox 时不能伪造单元格 bbox；可以保留
表级来源，并在 `evidence` 记录 row/column/span。

标题和引用关系：

- 标题层级使用 `relation_type = "parent_child"`；
- 正文引用到参考文献使用 `relation_type = "reference_of"`；
- `status` 必须是 `verified`、`inferred`、`manual_review_required`、
  `reparse_required`、`rejected` 或 `unavailable` 之一；
- 证据不足时不得为了数量输出 `verified`。

质量状态：

```text
pass
pass_with_warnings
manual_review_required
reparse_required
rejected
```

`reparse_required` 必须同时提供 `reparse_recommendation.parser_id`、原因和建议参数。
`critical_false_pass = true` 时禁止输出 `pass` 或 `pass_with_warnings`。

## 5. 产物约定

最终任务包至少包含：

```text
task-result/
├─ routing_decision.json
├─ parsed_document.json
├─ native/
├─ quality/
│  ├─ optimized.md
│  ├─ canonical_document.json
│  ├─ quality_report.json
│  └─ package_manifest.json
└─ task.json
```

所有文件引用必须是任务目录内的安全相对路径；禁止绝对路径、`..` 跳转和把本机临时
目录暴露给 API。

## 6. 联调顺序

1. 张云雅用 `routing_decision.json` 与朱联调，不等待真实 Web；
2. 朱用同一决策和固定模型输出生成 `parsed_document.json`；
3. 质量负责人只读取 `ParsedDocument`，生成 `quality_package.json`；
4. 朱使用固定 `QualityPackage` 开发 Web/API；
5. 三人再用真实 Docling、MinerU、OCR 和 JPG/PNG 做端到端联调。

## 7. 变更规则

公共接口变更必须一次提交以下四项：

1. `core/contracts.py` 中的 Pydantic 模型；
2. 对应固定 JSON 样例；
3. `tests/test_contract_examples.py`；
4. 本接口说明和开发 Spec。

公共字段含义不得由单人直接改变。路由字段由张云雅确认、归一化可实现性由朱确认、质量
证据充分性由质量负责人确认，三人同意后才能合并。

## 8. 验证

```powershell
python -m pytest tests/test_contract_examples.py -q
```

测试必须验证三份样例各自可加载、`document_id` 一致、来源 block 可回溯、table ID 可
衔接，以及手动路由和重解析状态的硬约束。
