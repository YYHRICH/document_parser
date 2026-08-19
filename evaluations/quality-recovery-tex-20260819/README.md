# TeX → PDF → 双解析器 → 真实质量 Agent 评测

本目录保存 2026-08-19 的端到端可追溯评测。所有输入均由 `sources/*.tex` 生成，
每份文档包含可见的 `TRACE-*` 标记和固定关键事实。`evaluation_spec.json` 是事实保留率
的声明式真值；`manifest.json` 在 PDF 编译后记录 TeX、PDF 和 Poppler 文本的 SHA-256。

评测矩阵：

| 文档 | 主要压力点 |
| --- | --- |
| `trace-structure` | 多级标题、列表、日期、URL、代码、公式和引用 |
| `trace-tables` | 合并表头、跨页 longtable、单位、负数和百分数 |
| `trace-layout` | 双栏阅读顺序、图注、脚注、公式、引用和重复页眉 |

每份 PDF 分别由 MinerU Cloud v4 和本地 Docling 2.120.2 解析，然后将
`ParsedDocument` 交给项目配置的真实 DeepSeek/Agno Agent。输出结构：

```text
sources/        可追溯 TeX 源文件
pdfs/           XeLaTeX 编译结果
pdf_text/       pdftotext -layout 基线文本
renders/        PDF 页面 PNG，供视觉核验
parses/         MinerU/Docling ParsedDocument 与解析器原始产物
quality/        每个解析结果对应的四件套、execution.json 和 markdown.diff
manifest.json   输入文件哈希与声明真值
summary.json    机器可读评测汇总
summary.md      人工可读结论
```

密钥仅从仓库根 `.env`/环境变量读取，不写入本目录。
