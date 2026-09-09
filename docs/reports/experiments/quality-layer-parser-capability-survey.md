# 质量层深化前的解析模型能力调研

## 1. 调研目的

本调研用于回答一个前置问题：交接文档提出的规范表格、单元格来源、行路径、列路径和视图语义，是否能由当前接入的不同解析模型共同提供。

结论不是让所有模型输出完全相同的字段，而是区分：

- 所有解析结果都必须具备的最小结构骨架；
- 只有部分模型能够提供的增强证据；
- 当前无法可靠取得、质量层必须标记为不可用的字段。

调研材料包括：

- 项目内 `infra/parsers` 的适配器和统一层代码；
- `tests/quality/fixtures/parsed_documents` 中的 Docling、MinerU、pdfplumber fallback 统一结果；
- `table_test` 中 AnyDoc `toDocument` 的 17 张表结构输出和覆盖率结果；
- 各解析器公开的原生接口说明。

## 2. 当前实际接入形态

当前项目的接入方式并不完全相同：

| 解析器 | 项目当前入口 | 当前统一结果特点 |
|---|---|---|
| Docling | 本地适配器和原生 JSON sidecar | 有表格网格、span、页级/单元格级 bbox；当前适配器仍是通用 payload 映射 |
| MinerU | 云端/本地 sidecar 和原生输出目录 | 主要通过 `table_body` HTML 进入统一层，能恢复 span；单元格 bbox 通常缺失 |
| AnyDoc | CLI/sidecar + `toDocument` 结构桥接 | 已把 origin/covered、span、表头、工作表、嵌套关系和 Excel 视图预检接入统一 `ParsedDocument` |
| MarkItDown | 直接输出 Markdown | 目标是可读 Markdown；适配器现在会把标准管道表转换成低证据等级的 `ParsedTable`，但不声明合并关系、源单元格坐标或筛选视图 |
| pdfplumber fallback | 测试 sidecar/兜底结果 | 可生成平面网格，但没有可靠 span、行头和单元格 bbox 语义 |

因此，当前项目里看到的 `ParsedTable` 并不等同于各模型的完整原生能力：它是统一层已经抽取出的一个子集。

## 3. 能力矩阵

状态含义：

- **强**：原生结果直接提供，质量层可以保存并校验；
- **可推导**：可以从原生结构确定性推导，但必须记录推导来源；
- **部分**：只有部分来源、部分粒度或部分模型提供；
- **不可得**：当前接口没有可靠证据，不能伪造。

| 目标字段/能力 | AnyDoc `toDocument` | Docling | MinerU | MarkItDown / fallback |
|---|---|---|---|---|
| Markdown 正文 | 强（`toMarkdown`） | 强 | 强 | MarkItDown 强；fallback 视 sidecar |
| 逻辑表格集合 | 强（Office 文档） | 强（支持的结构化文档） | 强（表格块） | MarkItDown 可从标准管道表推导；fallback 部分 |
| 物理网格行列数 | 强 | 强 | 可推导 | MarkItDown/fallback 可推导，但只能标为推断 |
| `rowspan/colspan` | 强 | 强 | 强（HTML 属性） | MarkItDown 不可靠；fallback 基本无 |
| covered/被合并位置 | 强（显式 origin/covered） | 可由网格和 span 推导 | 可由 HTML 展开推导 | 不可靠 |
| 表头行数 | 强（`headerRows`） | 可推导/部分有标记 | 可从 HTML `th` 或规则推导 | 不可靠 |
| 多级列路径 | 可推导 | 可推导 | 可推导 | MarkItDown 可生成推断绑定，不能视为原生事实 |
| 多级行路径 | 只能基于网格和规则推导 | 只有显式 row header 时较可靠 | 通常需要质量层推断 | 不可靠 |
| 单元格文本 | 强 | 强 | 强 | Markdown 管道单元格文本级 |
| 原始值/显示值分离 | 不提供 | 当前统一夹具未提供 | 不提供 | 不提供 |
| 单元格公式 | 当前 `Cell` 接口不提供 | 需检查原生字段，当前统一层未保存 | 通常以文本/公式块出现，不是单元格字段 | 不提供 |
| 单元格 bbox | 不提供 | 当前夹具较强 | 当前 `ParsedTable.cells` 无 bbox；原生公开输出主要是表/行/span bbox | fallback 无 |
| 表级 bbox / 页面定位 | Office 结构本身不提供页面 bbox | 强 | 强 | fallback 可能有页级定位 |
| 工作表名称 | 可从 heading/block 取得 | 当前适配器未声明 Excel 输入 | 当前项目入口主要面向 PDF/图片 | 不适用/不可靠 |
| `cell_ref` / `range_ref` | 网格坐标可转逻辑坐标，但原生不提供 A1 地址 | PDF 场景不适用 | PDF 场景不适用 | 不可得 |
| AutoFilter 全量/可见语义 | 当前 `toDocument` 会出现可见行视图，但接口不直接声明筛选状态 | 当前 PDF/文档夹具不适用 | 当前 PDF/图片入口不适用 | 不可得 |
| 跨页续表 | Office 以表块为主，不是页面语义 | 可用 page/bbox 诊断 | 可用 page/bbox 和中间结构诊断 | 不可靠 |

这个矩阵说明：规范表格的“网格骨架”可以跨模型统一；原始值、公式、工作表 A1 坐标和筛选状态不能假设所有模型都有。

## 4. 项目内实测证据

### 4.1 Docling、MinerU 和 fallback 统一夹具

当前质量测试夹具统计如下：

| 统一结果来源 | 表格单元格数 | 有单元格 bbox | 行头标记数 | 列头标记数 | 合并单元格数 | 带 HTML 表格数 |
|---|---:|---:|---:|---:|---:|---:|
| Docling | 670 | 632 | 13 | 70 | 11 | 0 |
| MinerU | 688 | 0 | 0 | 143 | 7 | 39 |
| pdfplumber fallback | 321 | 0 | 0 | 71 | 0 | 0 |

这组数据直接说明：

- Docling 可以作为单元格空间证据较强的来源，但不能假设每个单元格都有 bbox；
- MinerU 的表格结构主要依赖 HTML 和 `rowspan/colspan`，当前统一结果没有单元格 bbox，也没有显式 row header；
- fallback 的平面网格不能升级为 verified 的复杂表格绑定。

这些夹具位于：

`tests/quality/fixtures/parsed_documents/`

### 4.2 AnyDoc `toDocument`

`table_test` 直接调用 AnyDoc `toDocument`，并得到 17 张表、完整逻辑网格和合并覆盖位置。其输出的核心形状是：

```json
{
  "grid": [
    [
      {"kind": "origin", "cell": {"rowSpan": 1, "colSpan": 2}},
      {"kind": "covered", "originRow": 0, "originCol": 0}
    ]
  ],
  "headerRows": 2,
  "kind": "data"
}
```

实验结果确认 AnyDoc 可以支持：

- 多 sheet 表格；
- 物理网格尺寸；
- origin/covered 关系；
- 合并单元格 span；
- 前导表头行数；
- 超大表的完整行列规模。

实验脚本的简化 `.doc.json` 仍只保留部分字段；项目适配器不再消费该简化产物，而是通过本地桥接脚本直接保存 AnyDoc Document，并转换原始 cell blocks、`headerRows`、origin/covered 和真嵌套关系。

另外，筛选表“拟纳管清单”的 AnyDoc 结果是 8 行，而源工作表实际有 622 行。覆盖率脚本额外读取原始工作簿后才识别出 `source_has_filter=true`。说明 AnyDoc `toDocument` 输出本身不能单独证明“这是筛选视图”，质量层不能仅凭行数猜测筛选状态。

### 4.3 当前 AnyDoc 接入结果与限制

项目中的 `AnyDocParser` 目前已经负责：

- 同时调用 AnyDoc 的 Markdown 和 `toDocument` 通道；
- 保存原生结构 sidecar；
- 把 `Document.blocks[].table.grid` 转成模型无关的表格、单元格和逻辑网格；
- 对 Excel 使用 `openpyxl/xlrd` 补充工作表范围、合并区域计数和筛选/隐藏行语义；
- 最终交给通用 `_tables_from_payload` 进入 `ParsedDocument`。

当前仍不能从 AnyDoc 原生结构取得 Excel A1 单元格地址、公式对象或单元格空间 bbox；这些字段保持为空，不以逻辑坐标冒充原始来源。伪嵌套文本也不能自动升级成真子表。

### 4.4 同源真实文件端到端复跑

本轮不再只检查 AnyDoc。测试让各解析器的结果依次经过解析器适配、统一文档、质量规则和三文件交付。四个 PDF 结果使用同一份源文件，文件摘要完全相同；DOCX 结果也使用同一份源文件。MinerU 使用该文件已经生成的真实原生 sidecar 重放，没有再次上传文件。

在代表性文件端到端测试之前，还对数据集里的 777 份 Markdown 解析结果完成了统一质量回放：AnyDoc 191 份、Docling 175 份、MarkItDown 187 份、MinerU 224 份，回放过程没有脚本级错误。该回放用于观察已保存正文的后处理问题；下面的同源端到端结果才用于判断结构表、单元格、合并关系和字段绑定能力。

| 解析器与样本 | 表格数 | 单元格数 | 合并锚点数 | 字段绑定数 | 网格判断 | 表示判断 | 绑定判断 | 关键结论 |
|---|---:|---:|---:|---:|---|---|---|---|
| AnyDoc / DOCX | 5 | 200 | 0 | 180 | 已验证 | 已验证 | 推断 | 原生结构和 Markdown 表示一致，但缺少页面视图证据 |
| Docling / DOCX | 5 | 200 | 0 | 180 | 已验证 | 已验证 | 推断 | 5 张原生结构表与导出 Markdown 逐单元格一致，已安全绑定 |
| MarkItDown / DOCX | 5 | 220 | 0 | 180 | 推断 | 已验证 | 推断 | 成功恢复管道表；20 个额外空单元格来自每张表开头的空表头占位 |
| Docling / PDF | 4 | 90 | 6 | 6 | 需复核 | 需复核 | 推断 | 发现 3 类网格空洞，原生单元格与 Markdown 未完全一致，拒绝自动绑定 |
| MinerU / PDF | 7 | 286 | 109 | 173 | 需复核 | 已验证 | 需复核 | HTML 合并关系最丰富；1 张空表及字段路径问题使该结果被质量门禁拒绝 |
| MarkItDown / PDF | 14 | 290 | 0 | 38 | 需复核 | 已验证 | 推断 | 表格切分明显更碎，产生 72 个字段绑定问题；表格数多不代表解析更完整 |
| OCR / PDF | 0 | 0 | 0 | 0 | 不可用 | 不可用 | 不可用 | 产出 301 个文本识别块，但没有可靠表格网格证据，不生成虚假表结构 |
| AnyDoc / XLS | 1 | 2152 | 2 | 540 | 需复核 | 需复核 | 推断 | 可结合工作簿预检取得合并、筛选和可见范围证据 |
| MarkItDown / XLS | 1 | 2162 | 0 | 2115 | 推断 | 已验证 | 推断 | 能恢复平面表格和大量绑定，但无法证明合并关系、A1 来源和筛选视图 |

这组结果给质量层带来四个直接结论：

- 表格数量不能作为模型优劣指标。同一 PDF 上的结果是 4、7、14、0，必须结合空洞、合并关系、表示一致性和字段绑定问题判断。
- Markdown 管道表可以进入统一表格骨架，但网格和绑定只能标为“推断”；不能因为行列合法就升级为原生已验证结构。
- 原生结构与正文 Markdown 的绑定必须逐表核对尺寸和单元格文本。Docling DOCX 满足条件后可自动绑定，Docling PDF 不满足条件时必须保留复核状态。
- 没有表格证据时，所有表格能力必须是“不可用”。OCR 文本行不能被猜成网格。

复跑产物保存在：

`artifacts/parser-cross-validation-20260908/`

### 4.5 本轮适配器缺陷与处理

- MarkItDown 原来只交付 Markdown，导致真实管道表无法进入表格质量规则。现在适配器会生成单元格、逻辑网格和表格块，并明确记录结构来自 Markdown。
- Docling 原来把结构表的单行文本直接作为表格 Markdown，导致正文中明明有可读表格仍被判为表示不一致。现在只有在表数、尺寸和每个源单元格文本都一致时才绑定正文表格。
- MinerU 已规范化 sidecar 同时包含 `items` 和 `tables` 时，重放会重复追加同一张表。现在按源表 ID 合并，保持重放幂等；下游重复 ID 校验仍保持严格。
- 无表格文档原来可能得到“表格结构为推断”的假阳性。现在表格集合为空时，网格、结构、视图、表示和绑定都输出“不可用”。

## 5. 各模型应如何接入统一表格

### 5.1 AnyDoc：结构网格优先

AnyDoc 专用归一化路径已经落地：

1. 调用 `toDocument` 保存原生 JSON；
2. 把每个 `table.grid` 的 origin 槽位转成一个 `TableCell`；
3. 把 covered 槽位记录为覆盖关系，不生成新的源单元格；
4. 保存 `headerRows` 和 `table.kind`；
5. 从前置 heading 绑定工作表名；
6. 将 logical row/col 转成内部坐标，但不伪造 Excel A1 `cell_ref`；
7. `view_scope` 默认设为 `unknown`，除非原生结果或输入侧证据明确声明筛选状态。

AnyDoc 可以提供高质量的结构绑定，但不能直接提供单元格空间 bbox 和公式字段。筛选状态由输入侧工作簿预检提供；预检失败时保持 `unknown` 并进入人工复核。

### 5.2 Docling：空间证据优先

Docling 应优先使用 `export_to_dict()` 或原生表格模型，而不是只依赖 Markdown。官方文档明确说明其内部 `TableData.grid` 保留 `row_span`、`col_span`、起始行列坐标；JSON/HTML 保留 span，Markdown 会把 span 展平。[Docling 表格序列化说明](https://docling-project.github.io/docling/concepts/serialization/)

接入时：

- 保留表格和单元格 bbox；
- 保留表头行和单元格角色；
- 将单元格来源粒度标为 `cell` 或 `table`，不把缺失 bbox 补成 cell；
- 如果输入是 PDF，使用 page/bbox；如果未来接 Excel，再另行映射 sheet/range；
- 从 JSON/HTML 保存 span，Markdown 只作为正文表示。

Docling 是当前最适合作为 PDF 单元格级来源证据的模型，但不能据此推断它已经具备 Excel 公式、筛选和 A1 坐标能力。

### 5.3 MinerU：HTML 结构优先、坐标降级

MinerU 官方输出把表格主体放在 `table_body` HTML 中，HTML 支持 `rowspan`、`colspan`，表格块同时带 page 和 bbox。[MinerU 输出文件说明](https://github.com/opendatalab/MinerU/blob/master/docs/en/reference/output_files.md)

接入时：

- HTML 解析结果作为结构骨架；
- 原始 HTML 保留在原生证据中；
- `TableCell` 的 span、列头路径可以由 HTML 确定性生成；
- 单元格 bbox 缺失时，只保留表级 bbox，并将绑定状态降为 inferred 或受限；
- 如果需要文本行/span 的细粒度坐标，读取 `middle.json`，不要从 `content_list.json` 反推单元格坐标；
- 公式、图片占位符和日期显示值保留原文，不转换成假定的 raw value。

因此 MinerU 适合交付“可查询的表格结构”，但默认不能交付“每个单元格的空间来源”。

### 5.4 MarkItDown 和 fallback：正文优先

MarkItDown 的公开定位是把文档转换成 Markdown；其官方 README 明确强调输出面向文本分析和 LLM，不是高保真结构化文档模型。[MarkItDown 官方说明](https://github.com/microsoft/markitdown#markitdown)

所以：

- MarkItDown 优先保证 Markdown 阅读能力；
- 标准管道表可以生成结构化表格骨架和推断绑定；
- 这种骨架不包含原生合并关系、源单元格坐标、筛选状态和空间位置，网格不能标成已验证；
- 如果上游另外提供结构化 sidecar，应以 sidecar 为结构权威，Markdown 只作为展示；
- fallback 生成的平面单元格可以参与正文或低置信度绑定，但不能声明 span、行头和单元格来源可靠。

## 6. 统一层应采用的字段分级

为了让所有模型都能接入，字段应分成三层：

### 6.1 结构骨架字段：所有结构化表格必须有

- `table_id`；
- `block_id`；
- `row`、`col`；
- `text`；
- `row_span`、`col_span`；
- `cell_role` 或现有表头标记；
- `cell_id`；
- 表格级能力状态。

如果连这些字段都没有，质量层只能输出 Markdown，不能输出结构化表格能力。

### 6.2 来源字段：按模型能力提供

- `page_number`、`bbox`；
- `container_name`；
- `cell_ref`、`range_ref`；
- `source_object_id`；
- `source_granularity`。

来源字段缺失时不拒绝全文 Markdown，但必须降低表格绑定和溯源能力状态。

### 6.3 业务语义字段：不由质量层猜测

- `raw_value`；
- `display_value`；
- `formula`；
- `value_type`；
- AutoFilter 的全量/可见行状态；
- Excel 的隐藏行、筛选条件和工作表范围。

这些字段只有原生模型或输入侧结构检查明确提供时才写入；质量层不能从字符串内容猜测。

## 7. 对质量层设计的最终判断

### 7.1 不能采用“一套字段全部必填”

如果把单元格 bbox、公式、A1 坐标和筛选状态都设计成必填，MinerU、AnyDoc 和 Markdown/fallback 都会被迫填入虚假值，反而破坏质量层的证据原则。

正确做法是：

- 结构骨架字段是统一契约；
- 来源字段是能力声明；
- Excel 语义字段是可选增强证据；
- 质量层根据字段覆盖率决定 `verified`、`inferred`、`unavailable` 或拒绝结构交付。

### 7.2 两条输出能力要分开

每个解析结果都应分别声明：

```text
正文阅读能力：是否有可用 Markdown
表格结构能力：是否有可解释网格和 span
字段绑定能力：是否有行路径、列路径和值单元格引用
来源追溯能力：是否能定位到页/表/单元格
```

例如：

- AnyDoc `toDocument`：正文强、结构强、绑定可推导、空间来源弱；
- Docling：正文强、结构强、绑定可推导、PDF 空间来源较强；
- MinerU：正文强、结构强、绑定可推导、单元格空间来源受限；
- MarkItDown：正文强、标准管道表结构可推导、绑定只能标为推断；
- pdfplumber fallback：正文部分可用、结构只能低置信度交付。

### 7.3 质量层不能替解析器补充事实

质量层可以把不同原生结构转换成同一网格，但不能做以下事情：

- 用第一列内容强行认定 row header；
- 用第一行内容强行认定完整多级表头；
- 用表格 bbox 复制成每个单元格 bbox；
- 用输出行数猜测 AutoFilter；
- 从百分号、日期格式或公式字符串推断原始值类型；
- 用 Markdown 重新推断已经丢失的合并关系。

这些情况只能生成推断状态或能力警告。

## 8. 推荐改造方案

### 8.1 先做统一适配器，不先改质量规则

新增一个模型无关的 `TableEvidence` 构建步骤，由各适配器负责提供原生映射：

```text
Docling TableData / AnyDoc Table.grid / MinerU HTML
    -> TableEvidence
    -> ParsedTable / TableCell
    -> 质量层网格检查和绑定生成
```

这样质量规则只面对 `TableCell`，不需要知道 AnyDoc 的 `origin/covered`、Docling 的 offset 字段或 MinerU 的 HTML 标签。

### 8.2 每个适配器需要实现的最小任务

| 适配器 | 必须补的工作 |
|---|---|
| AnyDoc | 接入 `toDocument` 结构；保存 `headerRows`、origin/covered、sheet heading；不伪造 bbox、公式、筛选状态 |
| Docling | 从 `export_to_dict` 读取表格 grid、span 和 cell location；保留 cell bbox；区分缺失 cell bbox |
| MinerU | 保留 `table_body` HTML 和 table/page bbox；将 HTML 单元格映射为稳定 cell；必要时从 middle JSON 读取文本 span 证据 |
| MarkItDown | 只交付 Markdown；如果没有结构 sidecar，显式声明无表格结构能力 |
| pdfplumber fallback | 保留平面网格，但所有复杂表格语义默认为受限，不生成 verified 绑定 |

### 8.3 输入来源和评测来源分离

AutoFilter 的源行数、隐藏行数等需要打开原始工作簿才能确定。这属于数据评测或输入预检能力，不能由质量层仅凭 Markdown 推断。建议：

- 解析适配器保存模型实际输出的 `view_scope=unknown`；
- 如果路由入口同时完成了 Excel 预检，再把预检结果作为明确的来源证据传入；
- 质量层只校验声明是否自洽，不负责从输出行数反推筛选条件。

## 9. 已建立的验证用例

公共契约和首批最小验证已经覆盖：

1. AnyDoc：普通工作簿、多 sheet、合并表、超大表、带 AutoFilter 的工作表；
2. Docling：普通 PDF 表格、多级表头、跨页表格和带 bbox 的单元格；
3. MinerU：普通 HTML 表格、rowspan/colspan、表格图片和 middle JSON；
4. MarkItDown：普通 Markdown 表格、复杂 HTML 表格和嵌套表格；
5. fallback：无 span、无 cell bbox 的平面表格。

每个用例至少断言：

- 结构网格是否闭合；
- 合并覆盖是否保持；
- 表头路径是否可回溯；
- 值单元格是否可定位；
- 缺失证据是否被标记为不可用，而不是生成伪字段；
- 重复运行的 ID 和排序是否稳定。

`tables[]` 和 `row_path` 已进入生产契约，但仍由能力状态约束：只有结构化解析器能生成规范网格；Markdown-only 解析器不会因此获得虚假的表格能力。

## 10. 调研结论

交接文档提出的方向可行，但需要采用“共同骨架 + 能力分层”的实现方式：

- AnyDoc 和 Docling 可以承担结构表格主路径；
- MinerU 可以承担 HTML 结构主路径，但单元格坐标要降级；
- MarkItDown 只承担正文 Markdown；
- fallback 只能作为低置信度结构或正文兜底。

因此项目采用的是共同契约、按能力填充：AnyDoc 结构桥接已经落地，Docling 和 MinerU 继续通过各自原生 JSON/HTML 映射到同一 `ParsedTable/TableCell`，质量层只依赖统一证据执行网格、绑定和质量门规则。

## 11. `.xlsx` 路由审计

当前路由策略把 `.xlsx` 归入现代 Office，候选顺序是：

```text
Docling -> AnyDoc -> MarkItDown
```

但当前适配器能力声明中：

- Docling 没有声明 `.xlsx`，因此会被路由器判定为“不支持该扩展名”；
- AnyDoc 声明支持 `.xlsx`，但只有检测到 AnyDoc 可执行程序时才可用；
- MarkItDown 声明支持 `.xlsx`，因此通常成为最后的可用候选。

本机当前实际能力快照为：

```text
Docling       available=true   supports .xlsx=false
AnyDoc        available=true   supports .xlsx=true
MarkItDown    available=true   supports .xlsx=true
```

所以当前本机对 `.xlsx` 的结构候选是：

```text
AnyDoc toDocument -> MarkItDown 正文回退
```

AnyDoc 现已安装并接入 `toDocument`，`.xlsx` 可以交付规范网格和字段绑定。Docling 未声明 `.xlsx`；MarkItDown 仍只作为正文回退，不能被当作复杂表格结构成功。

### 路由调整建议

面向 Wiki 表格问答时，`.xlsx` 的目标路由应调整为：

```text
AnyDoc toDocument（结构主路径）
    -> 可选的源工作簿预检（筛选/公式/工作表范围）
    -> MarkItDown（仅正文回退）
```

工作簿预检器已经接入 AnyDoc 适配流程，可声明 AutoFilter、隐藏行和视图范围；公式与 Excel 显示值的完整分离仍不由 AnyDoc 保证。MarkItDown 继续明确为“正文可用、复杂表格结构不可用”。
