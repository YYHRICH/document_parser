# Document Parser

这是文档解析层与质量层的实现仓库，负责把不同解析器的结果统一为同一种文档结构，执行证据驱动的质量检查与安全修复，并向 Wiki 交付可直接消费的质量包。

Wiki 问答层和数据评测层属于下游系统。本仓库不负责问答召回、答案生成或评测打分，但会为它们提供稳定的内容、结构、来源和质量结论。

开发、联调、报告和历史资料的入口见 [项目文档导航](docs/README.md)。

## 整体链路

```text
源文件
  -> 模型路由
  -> 文档解析器
  -> 结构统一（ParsedDocument）
  -> 质量诊断
  -> 确定性安全修复
  -> 修复后复检与质量门
  -> Wiki 质量包交付
  -> Wiki 入库 / 问答 / 数据评测
```

核心边界如下：

- 路由层根据文件特征和解析器能力选择解析器，必要时提出重解析建议。
- 解析器适配层读取 Docling、MinerU、AnyDoc、MarkItDown、OCR 等结果。
- 统一层把解析器私有结构转换成统一的 `ParsedDocument`，保留 blocks、表格、资源、坐标和能力声明。
- 质量层只接收 `ParsedDocument`，负责诊断、白名单修复、复检、结构绑定和准入判断。
- Wiki 固定消费 `optimized.md`、`structure.json` 和 `quality_issues.json`；存在大表时同时消费 `table_index.sqlite3`。
- 评测层读取 Wiki 交付包和运行轨迹，产生评测结果，不反向修改质量包。

## Wiki 的正式交付物

每份文档交付一个目录。普通文档包含三个基础文件；任一表格超过 5 万个结构单元格时增加 SQLite 索引：

```text
quality_package/
├── optimized.md
├── structure.json
├── quality_issues.json
└── table_index.sqlite3        # 仅大表存在
```

### `optimized.md`

质量层修复后的最终 Markdown 正文。Wiki 的全文索引、章节切分和文本召回以该文件为准。

当前会自动执行的正文修复包括：

- 清理 Markdown 行尾多余空格；
- 修复 Markdown 表格分隔线；
- 将可验证的 MinerU HTML 表格转换为 Markdown 表格，并同步表格块和全文内容。

质量层不会凭空改写 OCR 文字、补写缺失内容、猜测跨页续表，也不会根据模型常识修正事实。

### `structure.json`

结构 JSON 不重复保存全文，也不保存产物哈希或 manifest。它包含：

- `document_id`：质量包的文档身份；
- `canonical_document.blocks`：按顺序排列的规范化文档块；
- `canonical_document.tables`：普通表内嵌真实单元格和网格；大表只保留表级结构、来源、视图和外置索引说明；
- `canonical_document.table_bindings`：普通表内嵌“行路径—列路径—值”绑定，大表不在 JSON 中展开；
- `table_index`：大表索引文件、表数、单元格数、绑定数、检索键和全文索引状态；
- `canonical_document.relations`：标题父子关系、引用关系等文档内关系；
- `canonical_document.metadata`：结构来源和能力元数据。

### `quality_issues.json`

问题状态 JSON 不重复正文和结构，只包含：

- `quality_report.issues`：修复后仍存在的问题；
- 每条问题的 `rule_id`：产生该问题的质量规则编号，例如 `QL-HDG-004`；
- `quality_report.resolved_issues`：修复前存在、复检后消失的问题；
- `quality_report.applied_repairs`：实际执行的修复规则及受影响对象；
- `quality_report.rejected_repairs`：因证据不足而拒绝的修复；
- `quality_report.capability_matrix`：正文、标题、表格、来源等能力的证据状态；
- `quality_report.gate_summary` 和 `metrics`：最终质量门结论及统计。

问题状态需要区分 `repaired`（已修复）、`manual_review_required`（需要人工复核）、`uncertain`（证据不足）和 `reparse_required`（需要重新解析）。

基础交付文件和可选 SQLite 索引通过同一个 `document_id` 配对。`structure.json` 的 `canonical_document` 和 `quality_issues.json` 的 `quality_report` 不应互相重复。写出前会检查 JSON 引用闭合；大表索引还会检查数据库身份、必要表和 SQLite 完整性。

普通表在 JSON 中的字段绑定示例：

```json
{
  "table_id": "anydoc-table-0000",
  "block_id": "canonical-table-block-id",
  "row_key": "华北区域 / 一线单位",
  "row_path": ["华北区域", "一线单位"],
  "column_path": ["人员", "专职单位"],
  "row_cell_ids": ["anydoc-table-0000:r2c0", "anydoc-table-0000:r2c1"],
  "column_cell_ids": ["anydoc-table-0000:r0c2", "anydoc-table-0000:r1c3"],
  "value_cell_id": "anydoc-table-0000:r2c3",
  "value": "是",
  "source_locator": {
    "source_block_id": "anydoc-table-block-0000",
    "container": "sheet",
    "container_name": "专职单位",
    "range_ref": "A1:K622",
    "table_cell": "r2c3",
    "provenance_status": "inferred"
  },
  "status": "inferred"
}
```

大表采用相同语义，但记录位于 `table_index.sqlite3.field_bindings`。Wiki 可按“表格 → 行键 → 列路径 → 值”查询，也可通过 `table_cells` 按工作表、A1 坐标或行列位置回到源单元格。数据库已建立表内行列、行键和源坐标索引；SQLite 支持 FTS5 时还会生成 `cell_search`。

## 质量层处理流程

质量层的确定性入口是：

```python
from document_parser.app.use_cases import run_quality

quality_package = run_quality(parsed_document)
```

内部处理顺序为：

1. 根据统一文档包建立证据上下文；
2. 执行修复前质量诊断；
3. 只应用已登记的确定性白名单修复；
4. 对修复后的文档重新执行质量规则；
5. 构建规范化文档块、表格字段绑定和文档关系；
6. 生成能力矩阵与质量门结论；
7. 生成并校验三个基础文件；大表以流式批次生成并校验 SQLite 索引。

### 当前检查规则

`QL` 表示质量层规则，后缀用于区分检查领域。问题 JSON 中的 `rule_id` 可以直接追溯到下列检查：

| 规则 | 检查内容 |
|---|---|
| `QL-CONT-001` | 正文块是否存在，块 ID 是否唯一 |
| `QL-CONT-002` | 阅读顺序是否缺失或冲突 |
| `QL-CONT-003` | 块类型与正文、标题或表格结构是否一致 |
| `QL-CONT-004` | 解析成功后规范正文是否仍为空 |
| `QL-FMT-001` | 是否存在系统性乱码、替换字符或非法控制字符 |
| `QL-ASSET-001` | 是否残留不应交付的 Base64 数据链接 |
| `QL-ASSET-002` | Markdown 中的本地资源引用能否在资源清单中找到 |
| `QL-PROV-001` | 文档块能否通过来源块编号回溯 |
| `QL-PROV-002` | 页码、坐标框及坐标粒度是否合法、真实 |
| `QL-PROV-003` | 资源和原生中间产物的引用及校验信息是否合法 |
| `QL-PROV-004` | 缺失或降级的解析能力是否说明原因 |
| `QL-HDG-001` | 标题是否具备可判断的层级信息 |
| `QL-HDG-004` | 标题父子树能否可靠建立，是否存在顺序冲突、层级跳跃或缺少父节点 |
| `QL-REF-001` | 参考文献区是否能建立条目索引 |
| `QL-REF-004` | 正文引用能否唯一绑定到参考文献条目 |
| `QL-TBL-001` | 单元格坐标、行列位置及跨行跨列范围是否合法 |
| `QL-TBL-002` | 逻辑网格是否存在占位冲突、越界、错误覆盖或空洞 |
| `QL-TBL-003` | 表格是否具备有效结构和连续表头区域 |
| `QL-TBL-004` | 多级表头能否恢复为完整列路径 |
| `QL-TBL-005` | 行路径和行键能否由明确的行标题或首列建立 |
| `QL-TBL-006` | 字段绑定能否闭合到真实行、列和值单元格 |
| `QL-TBL-007` | 是否存在跨页续表候选及足够的续表依据 |
| `QL-TBL-008` | 跨页表格的列数、列顺序或列几何是否漂移 |
| `QL-TBL-009` | 全文、表格块、表格 Markdown、HTML 与逻辑网格表示是否一致 |
| `QL-TBL-010` | 全量/可见/隐藏行计数、A1 定位及嵌套表格父子引用是否闭合 |

### 当前修复规则

| 规则 | 作用 | 安全边界 |
|---|---|---|
| `QL-RPR-001` | 清理行尾空格 | 不改变正文字符和段落语义 |
| `QL-RPR-002` | 规范 Markdown 表格分隔行 | 不猜测列数和单元格内容 |
| `QL-RPR-003` | HTML 表格转 Markdown | 必须能定位原表格块；合并单元格造成的表示损失会写入质量报告 |
| `QL-RPR-004` | 恢复 Excel 单元格内部换行 | 只使用原工作簿 `raw_value` 的明确换行证据；必须能同时更新单元格、表格 Markdown、表格 block 和全文，否则拒绝修复并进入复核 |

复杂合并单元格不会被 Markdown 拍平为事实：JSON 以 origin/covered 和 span 保存真实结构，Markdown 仅生成可读的 anchor-copy 表示。嵌套边界、隐藏行、重复行键、缺失 A1 定位或三份表格表示不一致时，质量层会给出具体问题和人工复核状态。无法由现有证据安全确定的问题只会进入质量报告，并通过质量门阻止或降级交付。质量层目前不接入会直接改写事实正文的 LLM 修复。

### 质量状态

最终文档状态包括：

- `pass`：没有阻断性问题；
- `pass_with_warnings`：可以交付，但存在警告或证据能力限制；
- `reparse_required`：需要路由层重新选择解析器或参数；
- `rejected`：当前结果不允许交给 Wiki。

`verified`、`inferred`、`unavailable` 等能力状态描述证据强度，不等同于整篇文档的最终准入状态。

## 统一层输入约束

质量层唯一的领域输入是 `ParsedDocument`，不能直接接收解析器私有对象或仅有一份 Markdown 的目录。统一层至少要保留：

```text
document_id
filename / file_type
markdown
blocks
tables
assets
ocr_spans
confidence
provenance
capabilities
warnings
native_artifacts
```

其中：

- `blocks` 保存标题、段落、列表、表格、图片、公式、引用等内容块及顺序；
- `tables` 保存真实表格网格、origin/covered 覆盖关系、单元格坐标、行列跨度、表头/行头、嵌套父子关系和视图范围；
- `assets` 保存 Markdown 引用的图片和附件，并能回指引用 block；
- `provenance` 保存实际解析器、参数和来源信息；
- `capabilities` 明确页码、bbox、表格单元格、OCR 等证据是否可用；
- 解析器未提供的证据必须声明缺失，不能使用默认值伪造。

统一层交付前应校验：

- JSON 能被统一契约模型验证；
- block、table、asset ID 唯一且引用不悬空；
- `tables[].block_id` 指向真实的表格 block；
- 资源路径为任务目录内的安全相对路径；
- Markdown 中的图片/附件引用都能找到对应资源；
- 所有非可用能力都带有原因；
- 页码、bbox、OCR 置信度和表格 cell 坐标均来自真实解析证据。

## 目录结构

```text
api/                 HTTP 传输 DTO
app/                 应用层用例、组合根与编排
domain/              领域模型、路由、统一模型、质量规则和端口
infra/               解析器适配器、存储、质量包写入和外部技术实现
trigger/             CLI 与 FastAPI 触发入口
frontend/            MVP Web 界面
tests/               契约、适配器、API、路由和质量层测试
examples/            领域契约和质量结果示例
scripts/             单次适配、fixture 和数据审计脚本
tools/               数据集回放与保真度审计工具
docs/                当前开发文档、报告索引和历史归档
specs/               当前工程规格与历史规格归档
artifacts/           本地实验和演示产物，不作为 Wiki 输入
```

## 环境配置

项目使用专属虚拟环境 `.venv`，要求 Python 3.11 或更高版本。

```powershell
cd S:\Agent_study\wiki\document_parser
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

MinerU 云端解析需要在项目 `.env` 中配置 `MINERU_API_TOKEN`。密钥只从环境变量或运行时配置读取，不写入 README、质量包、日志或前端。

AnyDoc 的 Office 结构通道还需要 Node.js 和 `@firecrawl/anydoc`。XLS/XLSX 默认优先路由到 AnyDoc；适配器优先调用 `toDocument` 保存结构网格，同时调用 Markdown 通道生成正文，并用 `openpyxl/xlrd` 补充工作表、筛选隐藏行、源范围和合并区域计数。若结构通道不可用，会明确降级到 MarkItDown，而不会把 Markdown 猜成复杂表格。

如果只运行已有原生结果或质量层测试，可以不调用云端 MinerU。

## 常用命令

### 运行全部测试

```powershell
cd S:\Agent_study\wiki\document_parser
.\.venv\Scripts\python.exe -m pytest
```

### 运行质量层测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests\quality -q
```

### 启动 HTTP API 和 MVP Web

从 `S:\Agent_study\wiki` 启动：

```powershell
S:\Agent_study\wiki\document_parser\.venv\Scripts\python.exe -m uvicorn document_parser.trigger.http.main:app --host 127.0.0.1 --port 8010
```

也可以在 `document_parser` 目录运行仓库提供的 `start_frontend.bat`。

### 使用 CLI 解析文档

```powershell
cd S:\Agent_study\wiki\document_parser
.\.venv\Scripts\python.exe -m trigger.cli.main .\examples\sample.pdf --parser mineru --output-dir .\outputs\api
```

CLI 会复用应用层编排，并打印解析任务 ID、统一文档包位置、文档身份和实际解析器。质量包的正式三文件输出由应用层存储接口负责。

### 用已有统一文档运行质量层

```powershell
cd S:\Agent_study\wiki
S:\Agent_study\wiki\document_parser\.venv\Scripts\python.exe -c "from pathlib import Path; from document_parser.infra.packaging.document_package import load_document_package; from document_parser.app.use_cases import run_quality; from document_parser.infra.quality_packaging import write_quality_package; root=Path('document_parser/artifacts/example'); pkg=run_quality(load_document_package(root/'document_package')); write_quality_package(pkg, root/'quality_package')"
```

写入后的 `quality_package` 目录固定包含三个基础文件，大表另外包含 `table_index.sqlite3`。

## 真实样本演示

仓库中已保存一份真实 MinerU 文档的质量层演示结果：

```text
artifacts/quality-demo-mineru-童装/quality_package/
├── optimized.md
├── structure.json
└── quality_issues.json
```

样本为《2024年天猫618童装整体销售复盘-28页》，结果包含：

- 347 个规范化文档块；
- 6 个 HTML 表格转换为 Markdown；
- 320 条表格字段绑定；
- 92 条标题关系；
- 1 处行尾空格修复；
- 质量状态为 `pass_with_warnings`，剩余警告为图片引用缺少对应资源。

数据集全量回放工具：

```powershell
cd S:\Agent_study\wiki\document_parser
.\.venv\Scripts\python.exe tools\replay_quality_on_dataset.py --help
```

全量回放生成的 `summary.json`、`report.md` 和 `document_quality_records.jsonl` 是实验分析产物，不是交给 Wiki 的正式文件。

## 安全与边界

- 不在质量层猜测缺失正文、OCR 内容、表格单元格或来源坐标。
- 不允许质量层规则直接依赖某个解析器的私有 Python 对象。
- 资源和原生产物只能使用任务目录内的安全相对路径。
- 云端 MinerU 只有在显式允许且 token 可用时才调用。
- 质量修复必须可定位、可验证；无法安全替换时记录拒绝原因并保留原内容。
- Wiki 不应把 JSON 或 SQLite 中的 `inferred` 绑定当成无条件事实，应结合 `quality_issues.json` 的问题状态和能力矩阵使用。
- 解析层内部可以保留 `parsed_document.json`、原始文件、原生 JSON、图片和日志，但这些不属于 Wiki 的下游交付。

## 开发约定

修改统一契约、ID 规则、表格结构、资源引用或质量状态时，必须同步更新：

1. 对应领域模型和适配器；
2. 契约示例与校验测试；
3. 质量层规则和代表性 fixture；
4. README、规格文档和实验基线。

新增解析器只需要实现 Adapter 并输出同一种 `ParsedDocument`，不应为该解析器复制一套质量规则。任何无法保真的字段都要在 `capabilities` 或 `warnings` 中明确记录。
