# 朱（parse-integration）契约基线

本文固化 parse-integration 开工前的第一步结论：朱负责消费张的
`RoutingDecision 1.0`，生产叶可直接消费的 `ParsedDocument 2.2`，并在 Web/API
层消费叶的 `QualityPackage 1.0`。

## 1. 唯一事实源

- 字段模型：`core/contracts.py`
- 固定样例：`examples/contracts/routing_decision.json`
- 固定样例：`examples/contracts/parsed_document.json`
- 固定样例：`examples/contracts/quality_package.json`
- 契约说明：`examples/contracts/README.md`
- 契约测试：`tests/test_contract_examples.py`

公共字段含义不得在 Adapter、Normalizer、Backend 或 Frontend 中另起一套解释。
任何字段语义变更必须同步修改模型、固定样例、测试、接口说明和 Spec。

## 2. 朱负责的接口边界

```text
RoutingDecision 1.0（张输出，朱消费）
  -> Adapter / Normalizer / NativeArtifact Archive（朱负责）
  -> ParsedDocument 2.2（朱输出，叶消费）
  -> QualityPackage 1.0（叶输出，朱消费并展示）
```

朱不负责决定哪个模型最好；这由张的路由层负责。朱不负责替叶输出质量结论、
表格字段绑定、标题父子关系或引用关系；这些由叶的质量层负责。

## 3. ParsedDocument 2.2 最小输出边界

每个真实解析结果必须至少满足：

- `filename`、`file_type`、`source_size_bytes`、`source_sha256` 可追溯；
- `routing_decision` 保留张的原始路由决策；
- `provenance.parser_id` 记录实际成功执行的解析器；
- `provenance.requested_parser_id`、`routing_mode`、`parameters`、耗时和
  `fallback_history` 按真实执行记录填写；
- `markdown` 是完整统一正文；
- `blocks` 至少保留可用的文档块、阅读顺序、源 block ID 和 source anchor；
- `tables`、`ocr_spans`、`assets` 按模型真实能力提供；
- `native_artifacts` 保存原生 JSON、Markdown、图片、表格、OCR 或日志的安全相对引用；
- `capabilities` 明确 page、bbox、table cells、OCR、heading 等证据的可用状态；
- `warnings` 记录非致命缺失、降级和兼容问题。

`routing_decision.selected_parser_id` 是计划模型，`provenance.parser_id` 是实际成功模型。
发生 fallback 时允许两者不同，但必须在 `provenance.fallback_history` 中解释每次尝试。

## 4. 缺失证据策略

缺失证据不补假值，按以下方式处理：

| 证据类型 | 可提供时 | 不可提供或不确定时 |
| --- | --- | --- |
| page / bbox | 写入 `SourceAnchor`、`ParsedTable`、`OcrSpan` | 留空，并在 `capabilities` 写明原因 |
| block ID / order | 使用解析器原始 ID 和真实阅读顺序 | 不伪造，必要时写 warning |
| heading level | 只填模型明确给出的层级 | 留空，不强行推断 |
| table cells / span | 填 `ParsedTable.cells`、row/col span、表头标记 | 保留 HTML/Markdown/截图，并声明 cells 不可用 |
| OCR spans | 填文本、bbox、confidence、page、rotation | 非 OCR 路径为空，并声明 OCR unavailable |
| 原生产物 | 以 `NativeArtifact` 安全相对路径引用 | 失败时记录错误和能力缺失原因 |

所有 `NativeArtifact.path` 和 `DocumentAsset.path` 必须是任务目录内安全相对路径，
禁止绝对路径、`..` 跳转和本机临时目录外泄。

## 5. 第一阶段验收口径

第一阶段只算完成于：

1. 三份固定样例均能被 `core/contracts.py` 模型加载；
2. `ParsedDocument 2.2` 与 `QualityPackage 1.0` 的 `document_id` 能对齐；
3. 质量层引用的 `source_block_id` 能回到 `ParsedDocument.blocks`；
4. table ID 能从 `ParsedDocument.tables` 衔接到质量层 table binding；
5. 手动路由硬约束和 `reparse_required` 硬约束能被测试拦住；
6. 当前文档和 README 能说明朱的 parse-integration 职责边界。

## 6. 本地验证记录

标准验证命令：

```powershell
python -m pytest tests/test_contract_examples.py -q
```

无 pytest 环境下的轻量基线校验命令：

```powershell
python scripts/validate_contract_baseline.py
```

当前环境的系统 Python 和 Codex 内置 Python 均未安装 `pytest`，因此已使用 Codex
内置 Python 直接执行同等 Pydantic 断言完成验证：

```text
[ok] routing_decision.json validates as RoutingDecision 1.0
[ok] parsed_document.json validates as ParsedDocument 2.2
[ok] quality_package.json validates as QualityPackage 1.0
[ok] fixed examples form one handoff chain
[ok] manual routing mismatch is rejected
[ok] reparse_required without recommendation is rejected
```

后续安装测试依赖后仍应优先运行标准 pytest 命令。
