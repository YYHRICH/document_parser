# Document Parser

这是文档解析层与质量层的实现仓库，负责把不同解析器的结果统一为同一种文档结构，执行证据驱动的质量检查与安全修复，并向 Wiki 交付可直接消费的双文件质量包。

Wiki 问答层和数据评测层属于下游系统。本仓库不负责问答召回、答案生成或评测打分，但会为它们提供稳定的内容、结构、来源和质量结论。

## 整体链路

```text
源文件
  -> 模型路由
  -> 文档解析器
  -> 结构统一（ParsedDocument）
  -> 质量诊断
  -> 确定性安全修复
  -> 修复后复检与质量门
  -> Wiki 双文件交付
  -> Wiki 入库 / 问答 / 数据评测
```

核心边界如下：

- 路由层根据文件特征和解析器能力选择解析器，必要时提出重解析建议。
- 解析器适配层读取 Docling、MinerU、AnyDoc、MarkItDown、OCR 等结果。
- 统一层把解析器私有结构转换成统一的 `ParsedDocument`，保留 blocks、表格、资源、坐标和能力声明。
- 质量层只接收 `ParsedDocument`，负责诊断、白名单修复、复检、结构绑定和准入判断。
- Wiki 只消费质量层最终生成的 `optimized.md` 和 `quality_package.json`。
- 评测层读取 Wiki 交付包和运行轨迹，产生评测结果，不反向修改质量包。

## Wiki 的正式交付物

每份文档交付一个目录，目录中只有两个下游文件：

```text
quality_package/
├── optimized.md
└── quality_package.json
```

### `optimized.md`

质量层修复后的最终 Markdown 正文。Wiki 的全文索引、章节切分和文本召回以该文件为准。

当前会自动执行的正文修复包括：

- 清理 Markdown 行尾多余空格；
- 修复 Markdown 表格分隔线；
- 将可验证的 MinerU HTML 表格转换为 Markdown 表格，并同步表格块和全文内容。

质量层不会凭空改写 OCR 文字、补写缺失内容、猜测跨页续表，也不会根据模型常识修正事实。

### `quality_package.json`

JSON 不重复保存全文，也不保存产物哈希或 manifest。它包含：

- `document_id`：质量包的文档身份；
- `canonical_document.blocks`：按顺序排列的规范化文档块；
- `canonical_document.table_bindings`：表格、文档块、行键、列路径和值之间的结构化绑定；
- `canonical_document.relations`：标题父子关系、引用关系等文档内关系；
- `quality_report.issues`：修复后仍存在的问题；
- `quality_report.resolved_issues`：修复前存在、复检后消失的问题；
- `quality_report.applied_repairs`：实际执行的修复规则及受影响对象；
- `quality_report.rejected_repairs`：因证据不足而拒绝的修复；
- `quality_report.capability_matrix`：正文、标题、表格、来源等能力的证据状态；
- `quality_report.gate_summary` 和 `metrics`：最终质量门结论及统计。

JSON 中的三个文档身份字段必须一致：顶层 `document_id`、`canonical_document.document_id` 和 `quality_report.document_id`。`optimized.md` 与 JSON 通过同一质量包目录和该文档身份配对。

表格字段绑定示例：

```json
{
  "table_id": "mineru-0022",
  "block_id": "canonical-table-block-id",
  "row_key": "1",
  "column_path": ["排行"],
  "value": "1",
  "source_locator": {
    "source_block_id": "mineru-0022",
    "page_number": 4,
    "bbox": [23.0, 268.0, 488.0, 946.0]
  },
  "status": "inferred"
}
```

这使 Wiki 能按“表格 → 行键 → 列路径 → 值”进行结构化检索，同时保留回到原始解析块的线索。

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
7. 生成并校验 `optimized.md` 与 `quality_package.json`。

### 当前修复规则

| 规则 | 作用 | 安全边界 |
|---|---|---|
| `QL-RPR-001` | 清理行尾空格 | 不改变正文字符和段落语义 |
| `QL-RPR-002` | 规范 Markdown 表格分隔行 | 不猜测列数和单元格内容 |
| `QL-RPR-003` | HTML 表格转 Markdown | 必须能定位原表格块；合并单元格造成的表示损失会写入质量报告 |

无法由现有证据安全确定的问题只会进入质量报告，并通过质量门阻止或降级交付。质量层目前不接入会直接改写事实正文的 LLM 修复。

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
- `tables` 保存真实表格网格、单元格坐标、行列跨度和表头/行头信息；
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
examples/            契约和 Wiki 交付示例
scripts/             单次适配、fixture 和数据审计脚本
tools/               数据集回放与保真度审计工具
docs/                架构、统一层、质量层和实验报告
specs/               工程规格与验收要求
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

CLI 会复用应用层编排，并打印解析任务 ID、统一文档包位置、文档身份和实际解析器。质量包的正式双文件输出由应用层存储接口负责。

### 用已有统一文档运行质量层

```powershell
cd S:\Agent_study\wiki
S:\Agent_study\wiki\document_parser\.venv\Scripts\python.exe -c "from pathlib import Path; from document_parser.infra.packaging.document_package import load_document_package; from document_parser.app.use_cases import run_quality; from document_parser.infra.quality_packaging import write_quality_package; root=Path('document_parser/artifacts/example'); pkg=run_quality(load_document_package(root/'document_package')); write_quality_package(pkg, root/'quality_package')"
```

写入后的 `quality_package` 目录只包含 `optimized.md` 和 `quality_package.json`。

## 真实样本演示

仓库中已保存一份真实 MinerU 文档的质量层演示结果：

```text
artifacts/quality-demo-mineru-童装/quality_package/
├── optimized.md
└── quality_package.json
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
- Wiki 不应把 `quality_package.json` 中的 `inferred` 绑定当成无条件事实，应结合质量状态和能力矩阵使用。
- 解析层内部可以保留 `parsed_document.json`、原始文件、原生 JSON、图片和日志，但这些不属于 Wiki 的下游交付。

## 开发约定

修改统一契约、ID 规则、表格结构、资源引用或质量状态时，必须同步更新：

1. 对应领域模型和适配器；
2. 契约示例与校验测试；
3. 质量层规则和代表性 fixture；
4. README、规格文档和实验基线。

新增解析器只需要实现 Adapter 并输出同一种 `ParsedDocument`，不应为该解析器复制一套质量规则。任何无法保真的字段都要在 `capabilities` 或 `warnings` 中明确记录。
