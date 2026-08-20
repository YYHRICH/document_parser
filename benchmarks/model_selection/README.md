# 模型选择测评依据

本目录不重复复制或重跑前期图片测试。当前路由采用的依据是张云雅已完成的：

- 200 份多格式文档实测；
- 同源 200 份 PDF 的 Docling/MinerU 对比；
- BMP、JPG/JPEG、PNG、TIFF、WEBP 各 10 张的图片实测。

冻结结论：PDF 固定优先 MinerU；`local_first` 图片使用 Docling + RapidOCR；
`quality_first` 的 BMP/JPG/JPEG/PNG/WEBP 使用 MinerU、Docling 回退；TIFF 在提交
MinerU 前必须无损转 PNG，也可直接回退 Docling。

后续只有解析器版本、API 模型版本或图片路由结论变化时，才需要在这里新增可复现的
逐文件结果和汇总。共享开发集的当前期望见
`datasets/shared-dev-v1/annotations/routing.jsonl`。
