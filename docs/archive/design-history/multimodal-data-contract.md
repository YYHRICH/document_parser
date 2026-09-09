# 文档解析多模态数据契约 v1.0（评审稿）

## 1. 目标与边界

解析层统一输出 `ParsedDocument 2.2`。杨侧通过朱侧基础设施适配器消费该对象并进行多模态增强；质量层输出 `QualityPackage 1.0`，Wiki 只消费质量门通过的正文和资源。本契约禁止为了补齐字段而推测页码、坐标、OCR 或图像语义。

## 2. 最小交付单元

每个解析版本必须包含：

```text
<source_id>/
├── parsed_document.json
├── optimized.md
├── quality_package.json
├── assets/
└── package-record.json
```

`source_id` 表示原始资料的稳定身份；`parse_id` 表示一次解析版本；`document_id` 必须在 ParsedDocument 和 QualityPackage 中一致。

## 3. 图片 Asset

```json
{
  "path": "images/figure-0001.png",
  "kind": "image",
  "file_type": "image/png",
  "sha256": "64位小写SHA-256",
  "width": 1280,
  "height": 720,
  "anchor": {
    "page_number": 3,
    "bbox": [72.0, 120.0, 540.0, 420.0],
    "page_width": 612.0,
    "page_height": 792.0,
    "coordinate_system": "pdf_points_top_left"
  },
  "referenced_by_block_ids": ["block UUID"],
  "metadata": {
    "caption": "图片标题",
    "caption_source": "source",
    "evidence_status": "verified"
  }
}
```

约束：路径必须为 POSIX 安全相对路径；文件必须存在且哈希一致；本地 Markdown 图片引用必须在 assets 中闭合；不允许 data URI。缺少宽高、页码或 bbox 时使用 `null`，同时在 capability 中说明原因。

## 4. 文档块与定位

每个 block 至少包含 `id`、`order_index`、`kind`、`markdown` 和 `anchor`。页码从 1 开始；bbox 顺序固定为 `[left, top, right, bottom]`。杨侧输入使用左上角原点、0–1000 的 `normalized_1000` 坐标。页面宽高存在时表示 `page_unit` 对应的实际尺寸；缺失时保留归一化 bbox、不得换算物理坐标，并将相应 capability 标为 partial。图片、表格必须通过 block ID 与正文阅读顺序关联。

## 5. OCR

OCR 行或词使用 `ocr_spans`，包含 `level/text/bbox/confidence/page_number/rotation_angle`。OCR 原文不得被视觉模型描述覆盖。视觉模型生成的 caption 必须使用 `caption_source=vision_model`、`evidence_status=inferred`。

## 6. 表格

表格使用 `tables[]`，并通过 `block_id` 指向 `kind=table` 的 block。杨侧 `items.content.table.rows` 固定为 `string[][]`，同时提供原始 HTML；rows 用于普通行列内容，HTML 用于保留合并单元格结构。只有 rows/HTML 而没有带位置与 span 的原生 cells 时，应将 table capability 标为 `partial`，保留 HTML 且不得反推 `TableCell.row_span/col_span`。

## 7. Capability 声明

固定能力键建议为 `text/assets/page/bbox/ocr/tables/reading_order`。状态取值：`available/partial/unavailable/failed`。除 available 外必须给出 reason。字段为空与能力不可用含义不同，因此不能只靠空数组表达证据缺失。

## 8. 质量门

以下情况禁止发布：空正文、质量状态 rejected/reparse_required、资源路径逃逸、data URI、文件缺失、哈希不一致、表格指向不存在或非 table block。caption、页码、bbox、OCR 缺失但已诚实声明 capability 时可以 `pass_with_warnings`。

## 9. 与杨欣川产物的确认结果

已确认不需要缩略图；图片按 visual_type 决定 Caption/OCR；每张图片保留 `image_caption` 与 `image_ocr` 两个独立结果槽位；原始图注、OCR、VLM Caption 不互相覆盖；VLM 使用 qwen3-vl-plus，并记录模型、模型版本及提示词版本。对应关系通过稳定 asset/item/chunk ID 保存。

叶曜华仍需确认语义 Gate 阈值；姚丞韬仍需确认 Wiki 实际索引字段和资源大小限制。详细字段映射见《杨欣川多模态产物对齐说明》。

## 10. 兼容规则

新增可选字段属于向后兼容；删除字段、修改字段含义、改变坐标系默认值必须提升主版本。下游必须按 `schema_name + schema_version` 校验，不能依赖解析器私有 JSON。
