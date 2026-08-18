# 质量层输入需求矩阵（初稿）

> 状态：初稿（基于 tests/quality/fixtures/parsed_documents/ 真实数据字段核对）
> 用途：与朱（统一接入层）联调时的主要反馈载体，避免质量层直接读取 Adapter 私有结构。
> 规则：证据缺失时通过 `capabilities` 声明；非 available 必须给出 reason。

## 需求矩阵

| 规则/能力 | 必需证据 | 可选证据 | 缺失后的最高状态 | 给 Adapter 的反馈 |
| --- | --- | --- | --- | --- |
| content_complete（QL-CONT-*） | `blocks`（id/kind/text/markdown）、`capabilities` | `ocr_spans`、`assets` | manual/reparse | 空页、OCR 失败必须通过 capability reason 声明 |
| provenance（QL-PROV-*） | `blocks[].source_block_id`、`provenance.parser_id` | `native_artifacts`、`anchor.original_text` | manual/rejected | source_block_id 缺失必须在 capabilities 声明不可用 |
| 阅读顺序 | `blocks[].order_index`、`anchor.page_number` | `anchor.bbox` | inferred/manual | order_index 不得伪造；冲突时保留原始值并声明 |
| 标题树（QL-HDG-*） | `kind=heading`、`heading_level`、`order_index` | `anchor.section_path`、`anchor.bbox` | inferred/manual | 保留解析器原始 heading level 与 source text |
| 表格网格（QL-TBL-*） | `tables[].cells`（坐标/span）、`num_rows/num_cols` | cell bbox、`table_image_path` | manual/reparse | 不要只输出 Markdown 表；合并单元格必须保留 span |
| 表格字段绑定 | cells header 标记、`row_header`/`column_header` | cell bbox | inferred/manual | 保留多级表头结构，不得拍平 |
| 跨页续表 | `page_number`、表级 `bbox`、阅读顺序 | 重复表头、parser continuation 标志 | manual | 跨页表格请用明确证据表达（如 continuation 标志） |
| 引用绑定（QL-REF-*） | reference 类型 block、`metadata.reference_label`、正文 marker | `anchor.section_path` | manual | 不要丢失 reference_label；正文引用保留原文文本 |
| 图片/OCR 质量 | `ocr_spans`（bbox/confidence）、`assets` | — | manual/reparse | OCR 路径必须输出 spans 与置信度，缺失时声明原因 |

## 已发现的上游缺口（基于真实 fixtures 核对）

| 缺口 | 涉及样本 | 现状 | 建议 |
| --- | --- | --- | --- |
| `TableCell` 无稳定 cell_id | 全部表格样本 | 质量层用 `(table_id, start_row, start_col)` 临时身份（D-09） | 朱在统一层加 cell_id（公共契约变更，需三人评审） |
| MinerU 云 API 无 cell bbox | sdp-004/005 等 | 保留表级 bbox，`bbox_granularity=table`（不允许伪造 cell bbox） | 有原生结构时通过 `native_artifacts` 提供 |
| 无表格文档的 table capability | sdp-006/007 等 | 质量层内部 applicability 判定不适用（D-03） | 契约确认是否增加 not_applicable |
| fallback 解析器（pdfplumber）无标题层级 | sdp-00x-fallback | heading_level 缺失 → QL-HDG 规则安全降级 | 仅开发期兜底，联调以 MinerU/docling 数据为准 |
| reference_label 来自 metadata | sdp-006/007 | 依赖 `blocks[].metadata.reference_label` | 若统一层能输出 reference 类型与 label 字段，请保持稳定 |

## 验证

```powershell
python -m pytest tests/quality/contract/test_golden_consistency.py -q
```
