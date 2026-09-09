# 中间统一层实施指南：把不同解析器结果输出为统一文档包

> 本文是写给中间统一输入输出层开发者的实施需求，不是质量层的抽象字段清单。<br>
> 你的输入：Docling、MinerU、Fallback/OCR 等不同解析器的原始结果。<br>
> 你的输出：质量层可以直接消费的一份统一文档包。<br>
> 当前统一协议：`ParsedDocument`。项目只维护这一套结构，不保留并行版本。

## 1. 你要解决的问题

不同解析器返回的结构不同：

- 有的主要返回 Markdown；
- 有的返回 blocks、page、bbox 和表格网格；
- 有的返回 HTML 表格和原生 JSON；
- 有的只有 pdfplumber 文本、词坐标或 OCR 结果；
- 同一个概念在不同解析器里可能叫不同名字，甚至完全缺失。

质量层不应该为每个解析器写一套逻辑。中间统一层必须把这些结果转换成同一种结构，并把“解析器没有提供的证据”明确标出来。

目标链路是：

```text
用户文件
  → 上游选择一个解析器
  → 解析器原始结果
  → 对应 Parser Adapter
  → 统一字段/ID/坐标/资源归一化
  → 统一文档包
  → 确定性质量检查与修复
```

质量层只接收最后的统一文档包，不比较多个解析器，也不读取 Docling/MinerU 的私有对象。

## 2. 最终应该输出哪些文件

每次只针对一个文档输出一个目录：

```text
document_package/
├─ parsed_document.json       # 必须，质量层唯一主输入
├─ assets/                    # 有图片/附件引用时必须
│  ├─ images/figure-1.png
│  └─ attachments/appendix.xlsx
├─ source/                    # 强烈建议，原始上传文件
│  └─ original.pdf
└─ native/                    # 可选，解析器原生结果/页面证据
   ├─ docling_document.json
   ├─ mineru_result.json
   └─ page-001.png
```

### 2.1 必须交付

#### `parsed_document.json`

这是质量层唯一必须读取的主文件，必须可以通过：

```python
from document_parser.domain.model.contracts import ParsedDocument

parsed = ParsedDocument.model_validate_json(
    open("parsed_document.json", encoding="utf-8").read()
)
```

它必须能由当前 `ParsedDocument` 模型直接校验，不能是某个解析器的原始 JSON，也不能只是 Markdown。

#### `assets/` 中被引用的资源

如果 `parsed_document.json` 或其中的 Markdown 引用了图片、公式截图或附件，统一包必须提供真实资源。

不能出现：

```markdown
![流程图](images/figure-1.png)
```

但包里没有 `images/figure-1.png`。

资源可以采用两种传输形式：

- 小资源直接在 JSON 的 `DocumentAsset.content` 中内嵌；
- 推荐大资源放在 `assets/`，由 Adapter 在交给质量层前加载为 `DocumentAsset.content`。

### 2.2 强烈建议交付

- `source/original.*`：便于人工复核、重新解析和定位原始页面；
- `native/`：保存解析器原生 JSON、HTML、页面截图、OCR 结果等证据；
- 原生文件的安全相对路径、类型、大小和 SHA-256，写入 `native_artifacts`。

原始文件和原生结果不是质量层的主输入，但没有它们时，复杂问题的人工复核和后续 reparse 会受限。

### 2.3 不要交付为质量层主输入

不要让质量层直接依赖：

- `docling.Document`、MinerU 私有对象等 Python 对象；
- 每个解析器各自不同的 Markdown/JSON 结构；
- 只有页图、没有结构 JSON 的目录；
- 质量层最终生成的 `optimized.md`、`structure.json`、`quality_issues.json`。

这三个质量产物由质量层在确定性检查和修复完成后生成，不由统一层预先生成。

## 3. Adapter 必须如何实现

每个解析器都实现一个 Adapter，但所有 Adapter 的输出必须相同：

```text
Docling 原始结果  ─┐
MinerU 原始结果   ─┼─> Parser Adapter ─> ParsedDocument
Fallback 原始结果 ─┘
```

推荐每个 Adapter 都按以下六步执行。

### 第一步：保留原始结果

先把解析器原始结果保存到 `native/`，不要一开始只保留 Markdown。

原始结果至少记录：

```text
parser_id
parser_version
parser_parameters
原始结果路径
文件类型
文件大小
```

如果原始结果中包含质量层未来可能需要的 page、bbox、table cell、OCR 或关系证据，就通过 `native_artifacts` 暴露安全路径，而不是把私有对象泄漏给质量层代码。

### 第二步：建立统一根对象

Adapter 负责填充：

```text
schema_name = ParsedDocument
document_id
filename
file_type
markdown
blocks
assets
tables
ocr_spans
confidence
provenance
capabilities
```

即使没有表格、图片或 OCR，也要输出空数组：

```json
{
  "blocks": [],
  "tables": [],
  "assets": [],
  "ocr_spans": []
}
```

不要因为某个解析器没有该能力就改变 JSON 结构。

### 第三步：把解析器对象映射成统一 blocks

每个能定位的解析器对象都转换为 `DocumentBlock`。不要把所有内容拼成一个大 paragraph。

至少区分：

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

每个 block 至少保留：

```text
id
source_block_id
order_index
kind
native_type
text
heading_level
markdown
anchor
metadata
```

### 第四步：把表格映射为物理网格

如果原始解析结果存在表格结构，必须填充 `tables[].cells`，不能只把表格转成 Markdown。

保留：

```text
table_id
block_id
page_number
bbox
num_rows
num_cols
caption
cells[].text
cells[].start_row
cells[].start_col
cells[].row_span
cells[].col_span
cells[].column_header
cells[].row_header
cells[].bbox（有则提供）
```

### 第五步：把图片、公式和 OCR 变成可追溯资源

- 将图片/附件复制或链接到 `assets/`；
- `DocumentAsset.path` 使用安全 POSIX 相对路径；
- Markdown 中的资源路径必须和 `assets[].path` 一致；
- 保留 asset 的 page/bbox、尺寸和引用 block；
- OCR 结果写入 `ocr_spans`，不要只把 OCR 文本塞入 Markdown；
- 公式如果只有图片，保留 formula block + asset，不要擅自转写公式。

### 第六步：声明能力和缺失证据

Adapter 不得用默认值掩盖解析器能力缺失。每个能力必须写入 `capabilities`：

```json
{
  "state": "available | partial | unavailable | failed",
  "granularity": "page/block/table/cell",
  "reason": "非 available 时必填",
  "evidence": {}
}
```

例如 MinerU 没有 cell bbox：

```json
{
  "table_cells": {
    "state": "partial",
    "granularity": "table",
    "reason": "解析器只提供表级 bbox，未提供 cell 级 bbox",
    "evidence": {}
  }
}
```

正确做法是降级，不是估算一个 bbox 再标记 `available`。

## 4. 不同解析器如何归一化

下面是实现方向，不要求质量层知道这些解析器的私有类名。

### 4.1 Docling Adapter

通常可以保留较丰富的结构证据：

- 文本/标题/表格/图片对象 → `blocks`；
- 原生 page/provenance/bbox → `anchor`；
- 表格网格和 span → `tables[].cells`；
- 原生 Docling JSON → `native/`；
- 如果图片 bytes 可导出，写入 `assets/`；
- 不要把 Docling 的对象 repr、调试字符串或 Python method repr 写入 Markdown。

如果 Docling 没有提供某个字段，按真实缺失状态声明 capability。

### 4.2 MinerU Adapter

MinerU 可能同时产生 Markdown、HTML、图片和原生结构 JSON：

- Markdown 作为根 `markdown` 和 block markdown 的候选来源；
- HTML/结构 JSON 中的表格网格优先转换到 `tables[].cells`；
- 页面和 bbox 有则保留；
- 云端结果中的原始 JSON、HTML、图片路径保存到 `native/`/`assets/`；
- 没有 cell bbox 时保留表级证据并标记 `partial`；
- 不要把 Markdown 表格当成完整的合并单元格证据。

### 4.3 Fallback/pdfplumber/OCR Adapter

兜底解析器的能力可能较少：

- 文本行/词块按真实坐标转换为 blocks；
- 没有可靠标题层级时保留 `kind=heading` 的原始判断，但 `heading_level` 可以为空；
- 没有表格网格时不要从纯文本猜造 cells；
- 扫描件提供 OCR spans 和 confidence；
- 对缺少 page/bbox/source 的字段声明 capability；
- Fallback 结果允许进入质量层，但质量层必须据证据降级，而不是假装和 Docling/MinerU 一样完整。

### 4.4 新解析器 Adapter

新增解析器不需要修改质量规则。只需：

1. 实现同样的 Adapter 接口；
2. 输出当前唯一的 `ParsedDocument`；
3. 增加至少一个固定 fixture；
4. 通过统一契约校验和质量层回归；
5. 在 `provenance.parser_id/version` 中标明实际来源。

## 5. 统一字段的具体要求

### 5.1 稳定 ID

- `document_id`：文档级稳定 ID；
- `blocks[].id`：文档内唯一，质量修复前后不变；
- `blocks[].source_block_id`：解析器原生对象 ID，有则保留；
- `tables[].table_id`：文档内唯一；
- `tables[].block_id`：必须指向一个 `kind=table` 的 block；
- `assets[].referenced_by_block_ids`：只能引用已有 block ID。

同一输入重复归一化时不要使用随机 UUID。推荐根据原文件身份、解析器 ID、解析器版本和原生对象身份生成确定性 ID；如果解析器原生 ID 已稳定，直接保留即可。

当前 `TableCell` 没有强制 `cell_id`，质量层暂时使用：

```text
(table_id, start_row, start_col)
```

如果统一层可以补充稳定 `cell_id`，请先做公共契约评审，不要只在某一个 Adapter 私自增加并让其他 Adapter 缺失。

### 5.2 页面和 bbox

- `anchor.page_number` 从 1 开始；
- bbox 必须是真实坐标，不能用数组下标、像素值或默认四个 0 伪造；
- `coordinate_system`、页面宽高和单位必须一致；
- `bbox_granularity` 写明是 page/block/table/cell；
- 无分页格式可以没有 page_number，但要通过 capability/warning 说明；
- 有页的文档尽量让所有 block/table/asset 可定位到 page。

### 5.3 标题、引用和关系证据

统一层不需要提前生成质量层最终 `CanonicalRelation`，但必须保留质量层判断关系所需的原始证据：

- 标题 block 的 kind、level、编号、section_path；
- 正文 citation marker 的原始文本；
- `kind=reference` 的参考文献 block；
- `metadata.reference_label`、citation style 和原始顺序；
- 图片 block、caption block、asset path、page/bbox；
- 如果解析器已经提供关系候选，可以放入 metadata/native artifact，但不能丢掉端点证据。

关系目标不唯一时，统一层不应替质量层选择第一个候选。

## 6. 必须遵守的“不造证据”规则

| 解析器实际情况 | 统一层正确输出 | 禁止输出 |
| --- | --- | --- |
| 没有 cell bbox | 表级 bbox + `table_cells=partial` | 估算 cell bbox 并标 available |
| 没有标题层级 | 保留原始 heading/text + level 缺失声明 | 根据编号覆盖解析器原值 |
| OCR 失败 | `ocr_spans=[]` + reason | 把普通 Markdown 当 OCR 证据 |
| 图片文件缺失 | asset metadata + warning/manual | 生成空白或假图片 |
| 引用目标有多个 | marker、参考文献 block 和候选证据 | 自动绑定第一个目标 |
| 页码未知 | `page_number=null` + reason | 按 block 顺序猜页码 |
| 表格是否续页不明 | 分页保留、声明不确定 | 强行合并表格 |
| 解析器字段冲突 | 保留冲突信息并降级 | 静默选一个不说明 |

质量层的自动修复能力依赖证据真实性。缺失证据会导致人工复核或重新解析，这是正常的安全结果，不是统一层失败。

## 7. 推荐的主 JSON 形状

下面只是最小结构示例；实际字段必须由当前 `ParsedDocument` 校验：

```json
{
  "schema_name": "ParsedDocument",
  "document_id": "11111111-1111-4111-8111-111111111111",
  "filename": "example.pdf",
  "file_type": "application/pdf",
  "markdown": "# 标题\n\n正文。",
  "blocks": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "source_block_id": "docling-text-001",
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

## 8. 统一层交付前必须自动校验

### 8.1 JSON 和引用完整性

- [ ] `ParsedDocument.model_validate_json()` 通过；
- [ ] `schema_name` 正确；
- [ ] blocks/tables/assets/ocr_spans 字段存在，缺失能力使用空数组；
- [ ] 所有 block ID 唯一；
- [ ] 所有 table ID 唯一；
- [ ] `tables[].block_id` 能找到 table block；
- [ ] `assets[].referenced_by_block_ids` 都能找到 block；
- [ ] 所有资源路径是安全相对路径；
- [ ] sidecar 资源都实际存在且 file_type 一致。

### 8.2 证据和内容完整性

- [ ] Markdown、blocks 和 tables 之间可以互相定位；
- [ ] 数字、公式、URL、引用文本没有在归一化时被改写；
- [ ] page/bbox 坐标系和粒度真实；
- [ ] parser/version/parameters 可回溯；
- [ ] 非 available capability 都有 reason；
- [ ] 原始解析器没有提供的证据没有被默认值伪造。

### 8.3 代表性契约 fixture

统一层至少要为以下文档各保留一份固定输出：

- 普通多段落正文；
- 双栏或复杂阅读顺序；
- 标题编号和层级；
- 多级表头、合并单元格；
- 跨页续表；
- 数字引用和参考文献；
- 扫描/OCR 文档；
- 图片、图注和公式；
- 百页级或长文档分页。

同一 fixture 应记录 parser_id/version，便于不同 Adapter 回归。

## 9. 交给质量层后会发生什么

质量层调用：

```python
from document_parser.app.use_cases import run_quality

package = run_quality(parsed_document)
```

质量层会：

1. 从 `ParsedDocument` 建立证据上下文；
2. 执行完整性、来源、标题、引用和表格规则；
3. 应用有明确证据的确定性白名单修复；
4. 在修复后文档上重新检查并构建能力矩阵；
5. 构建规范文档图和质量门结论；
6. 生成 `optimized.md`、`structure.json` 和 `quality_issues.json`。

统一层不需要预先生成这三个质量产物。

## 10. 契约变更流程

以下变更必须先和质量层确认：

- 修改 `ParsedDocument` 公共字段、枚举或字段含义；
- 修改 document/block/table/asset ID 规则；
- 删除 blocks、tables、assets、anchor、provenance 或 capabilities；
- 改变资源路径或 asset 引用语义；
- 把真实缺失证据改成默认 available；
- 把多个解析器结果合并成一个没有来源区分的对象。

本项目直接修改唯一契约，不增加并行模型或兼容转换器。推荐提交顺序：

1. 先提交统一层 Adapter 的固定 JSON fixture；
2. 通过 `ParsedDocument` 契约测试；
3. 再跑质量层测试和代表性文档；
4. 说明哪些字段来自原始解析器，哪些字段是统一层规范化产生的；
5. 任何无法保真的字段都在 capability/warning 中登记。

## 11. 给实施同事的最终判断标准

如果只记住五句话：

1. **不同解析器可以有不同 Adapter，但交给质量层的只能是当前唯一的 `ParsedDocument`。**
2. **不能只输出 Markdown；blocks、tables、assets、anchors 和 provenance 都是质量修复证据。**
3. **解析器没有提供的证据必须声明缺失，不能用默认值或模型常识补齐。**
4. **所有资源路径、对象 ID 和关系端点必须可回溯、可校验、不能悬空。**
5. **统一层交付结构化文档包，质量层再负责确定性检查、白名单修复和最终质量产物。**
