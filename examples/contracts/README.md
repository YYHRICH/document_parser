# 领域契约固定样例

本目录保存路由、统一解析和质量结果的固定 JSON，用于契约测试和模块联调。字段定义以 `domain/model/contracts.py` 为唯一事实源；项目只维护当前结构，不保留并行版本或兼容转换器。

## 样例链路

```text
ParseRequest
  -> RoutingDecision       路由层输出
  -> ParsedDocument        解析适配与统一层输出
  -> QualityPackage        质量层内存/API 输出
       -> 三文件 Wiki 交付目录
```

| 样例 | 用途 |
| --- | --- |
| `routing_decision.json` | 验证自动/手动路由选择、原因、参数和回退顺序 |
| `parsed_document.json` | 验证正文块、表格、资源、来源和能力声明 |
| `quality_package.json` | 验证规范结构、问题、修复、能力和质量门 |

三份样例使用同一个 `document_id`，可由 `tests/test_contract_examples.py` 直接验证。样例中的内容、时间和摘要均为固定测试值，不代表真实业务文件。

## RoutingDecision

核心字段包括：

- `mode`、`requested_parser_id`、`selected_parser_id`；
- `reason`、`signals`、`parser_options`；
- `fallback_parser_ids`、`allow_automatic_fallback`、`unavailable_reasons`。

手动模式必须满足 `requested_parser_id == selected_parser_id`，且不得静默自动回退。

## ParsedDocument

所有解析器必须把私有结果转换为当前统一结构，不能把第三方 Python 对象直接交给质量层。主要内容包括：

- 文件身份、路由决策和实际解析来源；
- `markdown` 与有稳定顺序的 `blocks`；
- 带单元格、网格、合并范围和来源定位的 `tables`；
- `assets`、`ocr_spans`、`native_artifacts`；
- 明确说明可用、部分可用、不可用或失败的 `capabilities`。

解析器没有提供的页码、坐标、OCR 或表格证据必须如实缺失，不能用默认值伪造。

## QualityPackage

`QualityPackage` 是质量层在内存和 API 中使用的统一结果，包括：

- 修复后的 Markdown；
- 规范文档块、表格、字段绑定和文档关系；
- 修复后仍存在的问题和已经解决的问题；
- 实际执行与拒绝执行的修复；
- 能力矩阵、质量门和重新解析建议。

它落盘后不是单个 `quality_package.json`，而是 Wiki 正式消费的三个基础文件：

```text
quality_package/
├── optimized.md
├── structure.json
├── quality_issues.json
└── table_index.sqlite3    # 仅存在大表时生成
```

`structure.json` 保存规范结构和普通表绑定，`quality_issues.json` 保存问题状态、修复记录、复核项和准入结论。JSON 不重复保存完整 Markdown，也不保存产物哈希或 manifest。

## 修改要求

公共字段变化时必须在同一次提交中同步：

1. `domain/model/contracts.py`；
2. 本目录固定 JSON；
3. `tests/test_contract_examples.py` 及相关 API/质量测试；
4. `frontend/api-types.ts`；
5. 根 README、Wiki 交付契约和相关开发说明。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_contract_examples.py -q
.\.venv\Scripts\python.exe scripts\gen_frontend_types.py
```
