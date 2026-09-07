# allin6 正式导入完成报告

## 结果

- Source：224
- 正式包：224
- 已物化图片资源：8471
- 质量门 rejected/reparse_required：0
- 悬空本地图片引用：0

每个包包含 `parsed_document.json`、`optimized.md`、`quality_package.json`、`assets/` 和 `package-record.json`，总清单见 `dataset-manifest.jsonl`。

## 导入方式

本批次导入已有 AnyDoc、Docling、MarkItDown、MinerU 保存结果，没有重新调用解析模型。每个 Source 使用既有质量审计后的选优候选，重新构造 `ParsedDocument 2.2`、执行当前质量流水线并物化 `QualityPackage 1.0`。

图片只复制 Markdown/HTML 实际引用的本地文件，并校验安全相对路径、文件存在性、SHA-256 和 block 引用。任何悬空引用或质量门拒绝都会使批处理失败。

## 证据边界

保存的 Markdown 没有完整保留原始页码、bbox、结构化 OCR 和原生表格 cells。本次没有推测或伪造这些证据，相应 capability 明确记录为 unavailable。后续若需要这些字段，必须从解析器原生产物补录或对原始文件重新解析。

## 暂不包含

- 未写入生命周期 Manifest；按当前安排等待姚丞韬验证后再处理。
- 未发布到姚丞韬仓库；本目录是待验证的正式数据源包。
- 多模态字段仍为 v1 评审稿，待杨欣川、叶曜华确认。
