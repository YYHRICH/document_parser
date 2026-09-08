# 数据集交付、多模态与文档生命周期契约

> 状态：v1 候选稿；用于朱恩铄、杨欣川、叶曜华、姚丞韬联合评审。

## 1. 职责边界

- 朱恩铄负责原始文件登记、解析路由、多模型执行、统一为 `ParsedDocument 2.2`、版本与生命周期记录。
- 叶曜华负责读取 `ParsedDocument`，执行质量诊断、安全修复和 Gate，输出 `QualityPackage 1.0`。
- 杨欣川与朱恩铄共同确认图片、OCR、表格、bbox 等多模态证据能被统一契约无损表达。
- 姚丞韬只消费通过 Gate 的 `optimized.md`、`quality_package.json` 与 `assets/`，不依赖解析器私有目录。

## 2. 正式目录

```text
raw/
├── sources/                         # 用户维护的原始资料；允许新增、修改、移动、删除
└── .llmwiki/
    └── .document_parser/
        ├── manifest.json            # 每个 Source 的当前状态
        ├── events.jsonl             # 只追加的生命周期事件
        ├── scans/<scan_id>.json     # 一次扫描汇总（下一阶段）
        └── packages/
            └── <source_id>/
                ├── current.json     # 当前有效 parse_id（下一阶段）
                └── versions/<parse_id>/
                    ├── source/original.ext
                    ├── parsed_document.json
                    ├── optimized.md
                    ├── quality_package.json
                    ├── assets/
                    └── native/
```

`raw/sources/` 中的 Markdown 与 PDF、Office、图片使用同一生命周期规则。解析生成的 Markdown 不写回 `raw/sources/`，避免监听器把输出再次当成新输入。

## 3. Source 与版本

- `source_id` 是稳定业务身份；内容修改、重命名和移动都不能改变它。
- `parse_id` 标识一次解析版本；内容修改或显式重解析必须创建新 `parse_id`。
- 相同路径、SHA-256 不变时记为 `unchanged`，不得重复解析。
- 相同 SHA-256 从旧路径消失并在新路径出现时记为 `moved`。
- 删除只将 Source 标记为 `deleted`，不得直接销毁历史解析包。
- 失败记录为 `parse_failed`，同一 Source 下次扫描记为 `retry`。

事件类型固定为：

```text
added | modified | moved | deleted | unchanged | retry
```

## 4. 多模态输出

多模态内容统一进入 `ParsedDocument.blocks`、`assets`、`tables`、`ocr_spans` 与 `native_artifacts`，不得只在解析器私有 JSON 中存在。

图片资产最小字段：

```json
{
  "kind": "image",
  "path": "assets/image-0001.png",
  "file_type": "image/png",
  "sha256": "64位摘要",
  "referenced_by_block_ids": ["对应图片块 UUID"],
  "metadata": {
    "caption": "原文图注或模型描述",
    "caption_source": "source | ocr | vision_model | unavailable",
    "evidence_status": "verified | inferred | unavailable"
  }
}
```

强制规则：

1. `path` 必须是解析包内安全相对路径，禁止绝对路径和 `..`。
2. 每个图片引用必须指向实际文件，并至少关联一个 block。
3. 页码和 bbox 只能来自真实解析证据；缺失时明确为 unavailable。
4. 视觉模型生成的 caption 标为 `inferred`，不能冒充原文。
5. OCR 文本与视觉描述分字段保存，不互相覆盖。
6. 表格同时保留 cells/span 等结构证据和可显示表示；有损 HTML 转 Markdown 必须记录修复或进入复核。
7. 下游正式包不得包含 data URI；图片必须外链化到 `assets/`。

## 5. 数据集选优

同一 Source 的候选结果按以下顺序选择：

1. 排除质量回放错误与 `rejected`；
2. 排除空 Markdown；
3. 优先具有可验证图片、表格和来源证据的结果；
4. 再比较内容完整性、标题结构、资源完整性；
5. 记录所有候选及拒绝原因，不能只保留最终结果。

当前 `allin6` 轻量交付使用 `quality_then_multimodal_then_model_priority_v1`。它用于建立下游样本，不替代基于完整 `ParsedDocument` 的最终 Gate。

## 6. 下游交付

姚丞韬的轻量数据集：

```text
delivery/
├── dataset-manifest.jsonl
├── summary.json
├── case-analysis.md
├── fallback-cases.json
└── documents/<source_id>/
    ├── selected.md
    └── delivery-record.json
```

正式联调后，每个文档升级为：

```text
documents/<source_id>/
├── optimized.md
├── quality_package.json
└── assets/
```

交给姚侧监听目录时，正文使用用户可见的原文件名：例如
`海尔集团绩效管理手册.pdf` 发布为 `raw/sources/海尔集团绩效管理手册.md`。
内部 `source_id` 不再作为正文文件名，但继续写入文件标记和
`raw/.llmwiki/.document_parser/delivery-manifest.json`，用于修改、重命名、
删除和追溯。同名文档自动追加 Source ID 短后缀，禁止静默覆盖。

生命周期扫描已同时注入两个出站端口：新增、修改会自动生成杨侧可加载的
`mmwiki-0.1` 兼容包并记录 `multimodal_package_path/state`；当前文本质量通过后自动
发布姚侧 Wiki。重命名通过两个端口同步文件名且保持 Source ID，删除则在两侧
标记撤回。`ready_for_enrichment` 只表示杨侧已可取包，不等同于 OCR/Caption 已
完成；杨侧增强结果回传并再次进入最终质量门属于下一阶段接口，不能用该状态
冒充多模态闭环完成。

## 7. 验收条件

- 224 个 Source 全部出现在 manifest，且 `source_id` 唯一。
- 不能把空 Markdown 标为成功交付。
- 每条记录保存全部模型候选、选择理由和质量状态。
- 选中结果不得为 `rejected`。
- 所有路径在另一台机器上仍可解析，禁止 `C:\...` 绝对路径。
- 图片引用、block、asset 文件之间没有悬空关系。
- 修改、移动、删除、失败重试均有自动测试和事件记录。
- 下游确认能读取 manifest、正文和图片；质量层确认能读取完整 `ParsedDocument`。
