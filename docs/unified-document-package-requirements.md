# 统一文档输入输出层需求：质量优化 Agent 文档包

> 文档用途：提供给中间统一输入输出层开发同事，作为解析器结果归一化到质量层的交接契约。  
> 当前契约基线：`ParsedDocument 2.2`  
> 适用范围：一次只处理一个文档；多文档并行、队列和重试由上游负责。

## 1. 先说结论

质量优化 Agent **不能只接收一个 Markdown 文件**。Markdown 只能作为展示和检索文本，无法支撑阅读顺序、标题树、表格合并单元格、引用绑定、图片归属和来源追溯。

统一层至少要输出：

1. 一份可校验的结构化 `parsed_document.json`；
2. Markdown 中引用的真实图片/附件资源；
3. 每个结构对象的稳定 ID、顺序和来源定位；
4. 解析器能力和证据缺失声明。

质量层会根据这些数据主动判断和修复格式/结构，但不会补造解析器没有提供的事实。

## 2. 统一层的职责边界

### 2.1 统一层负责

- 接收上游选择的单个解析器结果；
- 将 MinerU、Docling、Fallback 等私有结果转换为同一份 `ParsedDocument 2.2`；
- 保留解析器真实产生的文本、结构、页码、bbox、资源和 provenance；
- 对缺失或不可靠的证据设置 `capabilities` 状态和 `reason`；
- 保证稳定 ID、字段类型和相对路径安全；
- 在质量层不需要解析器私有对象的前提下，提供可回溯的原生 artifact 引用。

### 2.2 统一层不负责

- 比较多个解析器结果，质量层只处理最终选定的一份统一文档；
- 预先替质量 Agent 决定所有质量问题；
- 修改原文事实、数字、公式、参考文献或图片内容；
- 生成最终的 `optimized.md`、`canonical_document.json`、`quality_report.json`；
- 负责多文档并行、任务队列、跨文档关系和 Agent 调度。

## 3. 推荐的文档包目录

```text
document_package/
├─ parsed_document.json       # 必须：ParsedDocument 2.2
├─ assets/                    # 有资源引用时必须提供
│  ├─ images/figure-1.png
│  └─ attachments/appendix.xlsx
├─ source/                    # 强烈建议：原始上传文件
│  └─ original.pdf
└─ native/                    # 可选：解析器原生结构/页面证据
   ├─ docling_document.json
   └─ page-001.png
```

### 3.1 资源传输的两种形式

- **内嵌模式**：`DocumentAsset.content` 直接进入 JSON（JSON 序列化为 base64）。适合小图片和小附件。
- **边车模式**：JSON 只记录安全相对路径、类型、大小和摘要，实际 bytes 放在 `assets/`。统一层 Adapter 在交给质量层前，必须把边车文件加载为 `DocumentAsset.content`，从而构造合法的 `ParsedDocument`。

不要把大文档的所有图片无条件 base64 塞进一个巨型 JSON；推荐使用边车模式，但不能让质量层拿到一个无法解析资源的半成品对象。

## 4. `parsed_document.json` 根对象

根对象必须可以通过项目当前模型校验：

```python
from document_parser.core.contracts import ParsedDocument

parsed = ParsedDocument.model_validate_json(
    Path("parsed_document.json").read_text(encoding="utf-8")
)
```

### 4.1 根字段要求

| 字段 | 必须 | 要求 |
| --- | --- | --- |
| `schema_name` | 是 | 固定为 `ParsedDocument` |
| `schema_version` | 是 | 当前为 `2.2`；不兼容变更必须升级版本 |
| `document_id` | 是 | 文档级稳定 ID；同一输入重复归一化不能随机变化 |
| `filename` | 是 | 原始文件名，不用于推断结构事实 |
| `file_type` | 是 | MIME 类型或统一文件类型 |
| `markdown` | 是 | 完整 Markdown；保持解析器实际输出，不要用质量规则预修复 |
| `blocks` | 是 | 所有可定位的文本/结构块，至少为空数组 |
| `tables` | 是 | 所有结构化表格，至少为空数组 |
| `assets` | 是 | 所有图片/附件资源，至少为空数组 |
| `ocr_spans` | 是 | OCR 有结果时提供；无 OCR 时为空数组并声明能力状态 |
| `confidence` | 是 | text/layout/reading_order/table/overall，范围 0–1 |
| `provenance` | 是 | 实际解析器、版本、参数和耗时 |
| `capabilities` | 是 | 证据可用性；缺失或失败必须有 reason |
| `source_size_bytes` | 否 | 原始文件大小 |
| `source_sha256` | 否 | 原始文件摘要；如提供必须是合法 SHA-256 |
| `routing_decision` | 否 | 上游路由信息；不能替代 `provenance` |
| `warnings` | 否 | 解析器警告，不能只写在日志里 |
| `native_artifacts` | 否 | 原生文件的安全相对路径和摘要 |
| `alternatives` | 否 | 仅用于记录候选结果，不作为质量层默认输入 |

即使没有表格、图片或 OCR，也建议显式输出空数组，而不是根据解析器不同而省略字段。

## 5. blocks：质量 Agent 的主要结构输入

每个 `DocumentBlock` 必须包含：

```json
{
  "id": "稳定 UUID",
  "source_block_id": "parser-native-id",
  "order_index": 12,
  "kind": "paragraph",
  "native_type": "text",
  "text": "原始文本（如果解析器能提供）",
  "heading_level": null,
  "markdown": "这一块对应的 Markdown",
  "anchor": {
    "page_number": 2,
    "bbox": [72.0, 144.0, 510.0, 168.0],
    "page_width": 595.0,
    "page_height": 842.0,
    "coordinate_system": "top-left",
    "bbox_granularity": "block",
    "provenance_status": "available",
    "section_path": ["第二章", "方法"],
    "table_cell": null,
    "original_text": "原始定位文本"
  },
  "metadata": {}
}
```

### 5.1 `id` 和顺序

- `id` 在同一文档中必须唯一；质量修复前后不能变化；
- 同一输入重复运行时，ID 应保持稳定，不能使用每次随机生成的 UUID；
- `source_block_id` 用于回溯解析器原生对象，能提供就必须提供；
- `order_index` 是解析器实际给出的阅读顺序，不要为了“看起来合理”提前重排；
- 质量层允许通过 Patch 调整顺序，但不会修改原始来源 ID。

### 5.2 `kind` 必须使用统一枚举

```text
heading
paragraph
list
table
image
formula
header
footer
page_number
aside
footnote
reference
```

不要把所有对象都归为 `paragraph`。至少要正确区分 `heading`、`table`、`image`、`formula` 和 `reference`，否则对应 Skill 无法安全工作。

### 5.3 标题

标题 block 应提供：

- `kind="heading"`；
- 解析器实际识别到的 `heading_level`，不能凭编号猜完后覆盖原值；
- 原始标题文本和 Markdown；
- `anchor.section_path`（如果解析器有）；
- 编号、标题文字和专有名词不能在统一层被改写。

### 5.4 引用和参考文献

正文引用必须作为原始 block 文本保留。参考文献 block 使用 `kind="reference"`，并在 `metadata` 中保留稳定的：

```json
{
  "reference_label": "3",
  "citation_style": "numeric"
}
```

如果解析器只能确认它是参考文献区域、不能确认编号，保留原文并在 `capabilities.reference_labels` 中声明 `partial` 或 `unavailable`，不要猜编号。

## 6. 页面和定位证据

质量 Agent 需要按页建立索引。对于有分页的 PDF、扫描件、长截图和 Office 转换结果：

- 每个可定位 block 尽量提供 `anchor.page_number`；
- bbox 必须使用真实坐标，不能把像素坐标冒充 PDF 坐标；
- 同一文档的坐标原点、页面宽高和单位必须一致；
- `bbox_granularity` 必须说明是 `page`、`block`、`table`、`cell` 还是其他粒度；
- 没有 bbox 时置空并声明能力缺失，不要填 `[0, 0, 0, 0]` 伪造定位；
- 页眉、页脚、页码如果输出为 block，必须保留原始 kind 和页码，质量 Skill 再判断是否属于重复结构。

没有页面证据的无分页纯文本可以正常进入质量层，但页面模式、跨页表格和视觉顺序修复会降级。

## 7. tables：必须保留物理网格

每个 `ParsedTable` 必须包含：

```json
{
  "table_id": "table-001",
  "block_id": "对应 table block 的 UUID",
  "html": "可选原始 HTML",
  "markdown": "可选原始表格 Markdown",
  "caption": "表 1",
  "image_path": null,
  "page_number": 3,
  "bbox": [72.0, 200.0, 520.0, 600.0],
  "num_rows": 5,
  "num_cols": 4,
  "cells": [],
  "metadata": {}
}
```

每个 cell 至少保留：

```json
{
  "text": "额定电压",
  "start_row": 0,
  "start_col": 1,
  "row_span": 1,
  "col_span": 2,
  "column_header": true,
  "row_header": false,
  "bbox": [180.0, 220.0, 300.0, 250.0]
}
```

### 7.1 表格硬约束

- 不能只输出拍平后的 Markdown 表格；
- `row_span`/`col_span` 必须是真实合并信息；
- 不要复制文本填充合并单元格占用的槽位；
- `num_rows`/`num_cols` 应覆盖所有 cell 的实际占用范围；
- `table.block_id` 必须能在 `blocks` 中找到对应 table block；
- 表格事实文本、数字、金额、单位和符号必须保持原样；
- 没有 cell bbox 时提供表级 bbox，并将 `capabilities.table_cells` 或 `page_bbox` 声明为 `partial`，不要伪造 cell bbox。

### 7.2 稳定 cell 身份

当前 `ParsedDocument 2.2` 的 `TableCell` 没有强制 `cell_id` 字段，质量层临时使用：

```text
(table_id, start_row, start_col)
```

统一层如果可以提供稳定 `cell_id`，建议作为后续兼容字段提交，但需要团队评审公共契约变更。无论是否有 `cell_id`，坐标和 span 都不能丢失。

### 7.3 跨页表格

跨页续表至少要保留：

- 每个表格片段的真实 `page_number` 和 bbox；
- 页内 block/order_index；
- 重复表头或 continuation 标记（如果解析器有）；
- 同一表格的稳定 `table_id`，或可以由 metadata 明确表达 continuation；
- 不同页列数、列顺序和合并信息。

不确定是否续表时保留两个结构并声明不确定，不要强行合并。

## 8. assets：图片、公式截图和附件

`assets` 描述的是实际存在的资源，不是资源说明文字。每个资源必须：

- 使用安全的 POSIX 相对路径，例如 `images/figure-1.png`；
- 能在文档包中找到真实 bytes，或能被 Adapter 可靠加载；
- 保留 `kind`、`file_type`、尺寸、anchor 和 provenance；
- `referenced_by_block_ids` 只填写输入中已有的 block ID；
- 资源缺失时不要生成占位图片，应该在 `capabilities.assets` 或相关 warning 中说明。

图片/公式与图注之间如果存在结构关系，统一层至少要保留：

- 图片/公式 block；
- caption block；
- 资源路径；
- page/bbox；
- 已有 `referenced_by_block_ids` 或 metadata 关系证据。

质量层可以通过 `move_block`、`update_asset_references` 和关系 Patch 调整已有关系，但不会凭空创建图片或公式。

## 9. OCR 证据

扫描件、照片和图片型 PDF 如果提供 OCR，`ocr_spans` 至少保留：

```json
{
  "level": "word",
  "text": "收款金额",
  "bbox": [100.0, 80.0, 180.0, 100.0],
  "confidence": 0.93,
  "page_number": 1,
  "rotation_angle": 0.0
}
```

要求：

- OCR 文本不能被误标为人工确认事实；
- confidence 只能表示解析器/OCR 置信度，不是质量层放行结论；
- bbox 和 page_number 必须使用真实坐标；
- 没有 OCR 或 OCR 失败时，`ocr_spans=[]`，同时声明 `ocr_confidence` 的状态和原因。

## 10. provenance 和 capabilities

### 10.1 provenance

至少保留：

```json
{
  "parser_id": "docling",
  "requested_parser_id": "docling",
  "routing_mode": "manual",
  "model": "版本或模型名",
  "version": "实际版本",
  "parameters": {},
  "parse_duration_ms": 1234,
  "peak_memory_mb": 512,
  "fallback_history": []
}
```

`parser_id`、`version` 和实际参数不能只写在日志；它们是质量结果回溯和换解析器后的对照依据。

### 10.2 capabilities

当前质量层直接使用或映射的能力名包括：

```text
page_bbox       # block/page/table 的页码和 bbox 证据
block_order     # 如果单独声明顺序能力，可使用该名称
heading_level   # 标题层级能力
table_cells     # 表格 cell/span/header 结构
ocr_confidence  # OCR span 和置信度
assets          # 资源是否完整可访问
native_artifacts# 原生证据是否可访问
reference_labels# 参考文献 label 是否可靠（建议）
cross_page      # 跨页关系证据（建议）
```

每个 capability 使用：

```json
{
  "state": "available | partial | unavailable | failed",
  "granularity": "block/table/cell/page",
  "reason": "非 available 时必须填写",
  "evidence": {}
}
```

特别注意：

- 没有表格时，表格证据属于“不适用”，不是解析失败；
- 有表格但没有 cell 结构，应为 `partial`/`unavailable` 并说明原因；
- 非 `available` 状态必须有 `reason`；
- 不要为了让质量门通过而把不确定证据标成 `available`。

## 11. 稳定 ID 和引用完整性

统一层交付前必须检查：

- `document_id` 在文档包内唯一且稳定；
- 所有 `blocks[].id` 唯一；
- `tables[].table_id` 唯一；
- `tables[].block_id` 存在于 blocks；
- `assets[].referenced_by_block_ids` 都存在于 blocks；
- 所有 `source_block_id` 能回溯到解析器原始对象，或明确为空并由 provenance/capability 解释；
- 关系 metadata 中的 from/to 对象都存在；
- 同一资源路径只对应一个资源对象；
- 不使用数组下标作为跨运行公共 ID；
- 质量层修复后，原始 ID、页码、bbox 和 provenance 仍可追溯。

## 12. 缺失证据的处理原则

统一层的原则是“诚实声明，不要伪造”。

| 情况 | 正确做法 | 错误做法 |
| --- | --- | --- |
| 没有 cell bbox | 保留表级 bbox，能力标 `partial` | 填一个估算的 cell bbox |
| 没有标题层级 | 保留原始 heading/文本，能力降级 | 根据编号直接覆盖 heading_level |
| OCR 失败 | 空 `ocr_spans` + reason | 复制 Markdown 当 OCR 证据 |
| 图片文件缺失 | 保留资源 metadata + warning/manual | 生成空白占位图 |
| 引用目标不唯一 | 保留 marker 和候选证据 | 任意绑定第一个参考文献 |
| 页码不明 | `page_number=null` + reason | 用 block 顺序推算页码后伪造 |
| 表格是否续表不明 | 分开保留并声明不确定 | 强行合并两张表 |

质量 Agent 会根据证据状态限制自动修复范围，最终状态可能是 `inferred`、`manual_review_required` 或 `reparse_required`，这是预期行为。

## 13. 推荐的最小 JSON 示例

下面示例展示字段关系，不代表完整文档内容：

```json
{
  "schema_name": "ParsedDocument",
  "schema_version": "2.2",
  "document_id": "11111111-1111-4111-8111-111111111111",
  "filename": "example.pdf",
  "file_type": "application/pdf",
  "markdown": "# 标题\n\n正文。",
  "blocks": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "source_block_id": "parser-text-001",
      "order_index": 0,
      "kind": "heading",
      "native_type": "heading",
      "text": "标题",
      "heading_level": 1,
      "markdown": "# 标题",
      "anchor": {
        "page_number": 1,
        "bbox": [72, 72, 180, 96],
        "page_width": 595,
        "page_height": 842,
        "coordinate_system": "top-left",
        "bbox_granularity": "block",
        "provenance_status": "available",
        "section_path": [],
        "table_cell": null,
        "original_text": "标题"
      },
      "metadata": {}
    }
  ],
  "assets": [],
  "tables": [],
  "ocr_spans": [],
  "confidence": {
    "text": 0.98,
    "layout": 0.91,
    "reading_order": 0.90,
    "table": 1.0,
    "overall": 0.93
  },
  "provenance": {
    "parser_id": "docling",
    "requested_parser_id": "docling",
    "routing_mode": "manual",
    "model": null,
    "version": "<actual-version>",
    "parameters": {},
    "format_conversion_duration_ms": 0,
    "markitdown_duration_ms": 0,
    "parse_duration_ms": 1234,
    "peak_memory_mb": null,
    "fallback_history": []
  },
  "warnings": [],
  "native_artifacts": [],
  "capabilities": {
    "page_bbox": {
      "state": "available",
      "granularity": "block",
      "reason": null,
      "evidence": {}
    },
    "table_cells": {
      "state": "unavailable",
      "granularity": null,
      "reason": "文档不包含表格",
      "evidence": {}
    },
    "ocr_confidence": {
      "state": "unavailable",
      "granularity": null,
      "reason": "文档有文本层，未执行 OCR",
      "evidence": {}
    }
  }
}
```

## 14. 统一层交付前验收清单

### 14.1 结构校验

- [ ] `ParsedDocument.model_validate_json()` 可以通过；
- [ ] 根字段和空数组完整；
- [ ] 所有 block/table/asset ID 唯一；
- [ ] table block、table ID、asset 引用关系不悬空；
- [ ] 所有相对路径安全，不包含绝对路径或 `..`；
- [ ] `schema_version` 与实际字段一致。

### 14.2 内容和来源校验

- [ ] `markdown` 与 blocks 的原始内容可以互相定位；
- [ ] 数字、公式、URL、引用文本没有在归一化时被改写；
- [ ] page/bbox 坐标系和粒度真实；
- [ ] `source_block_id`、parser/version/parameters 可回溯；
- [ ] 非 available capability 都有 reason；
- [ ] 解析器没有提供的证据没有被填充为默认“可信”。

### 14.3 场景回归

统一层至少应使用以下类型 fixture 做契约回归：

- 普通多段落正文；
- 双栏或复杂阅读顺序；
- 标题层级和编号；
- 合并单元格、多级表头；
- 跨页续表；
- 数字引用和参考文献；
- 扫描/OCR 文档；
- 图片、图注和公式；
- 长文档分页。

## 15. 交付给质量层的接口

统一层交付的唯一主对象是：

```python
ParsedDocument
```

质量层入口：

```python
from quality import run_quality_repair

package = run_quality_repair(
    parsed_document,
    agent_factory=agent_factory,
)
```

质量层会生成：

```text
optimized.md
canonical_document.json
quality_report.json
package_manifest.json
```

这四个质量产物不是统一层输入要求，不需要统一层预先生成。统一层只需保证结构化文档、真实资源和来源能力证据完整可靠。

## 16. 变更流程

以下变化必须先和质量层确认：

- 修改 `ParsedDocument` 公共字段或枚举；
- 修改 `schema_version`；
- 修改 block/table/asset ID 生成规则；
- 删除 `anchor`、`provenance`、`capabilities` 或 table cells；
- 将真实缺失证据改成默认值；
- 改变相对资源路径或 asset 引用语义。

建议统一层先提交一个固定 JSON fixture 和契约测试，再接入真实解析器。质量层会使用该 fixture 验证页面索引、表格 Patch、关系 Patch、审核状态和质量产物一致性。
