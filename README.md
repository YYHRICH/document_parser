# Document Parser

本仓库是三人协作的统一文档解析与质量处理工程。

当前集成分支同时包含：

- 张：`RoutingDecision 1.0` 路由层，负责模型选择、fallback 顺序和重解析建议。
- 朱：parse-integration，负责 Adapter、Normalizer、Gateway、后端 API、MVP Web、原生产物归档和端到端串联。
- 叶：quality-layer，负责从 `ParsedDocument 2.2` 生成 `QualityPackage 1.0`，包括 canonical document、quality report、manifest 和规则/门禁判断。

## MVP 链路

```text
Web / API / CLI
  -> ParseRequest
  -> RoutingDecision
  -> Docling / MinerU / OCR / AnyDoc / MarkItDown Adapter
  -> ParsedDocument 2.2
  -> quality.run_quality(...)
  -> QualityPackage 1.0
  -> Web 展示、产物下载、reparse
```

前端不能直接调用解析算法或质量算法；Web、CLI 和纯后端入口都应复用同一套 Gateway 与公共契约。

## 朱的职责边界

朱负责把上游路由、解析器和下游质量层串起来：

- 为 Docling、MinerU、OCR、AnyDoc 和 MarkItDown 提供统一 Adapter 接口。
- 将不同解析器的 Markdown、JSON、HTML、图片、表格、坐标和 OCR spans 归一成 `ParsedDocument 2.2`。
- 保存原生产物，并通过 `NativeArtifact` 暴露安全相对路径、类型、大小和 SHA-256。
- 接入张的 `RoutingDecision`，记录建议模型、实际模型和 fallback 历史。
- 对缺失证据只在 `capabilities` 中声明原因，不伪造 bbox、置信度、表格 cell 或标题层级。
- 提供独立后端 API 和 MVP Web，支持上传、模型选择、路由原因、解析结果、质量状态、产物下载和重新解析。
- 消费叶输出的 `QualityPackage 1.0` 并展示，不替叶做质量结论。

## 叶的质量层入口

质量层的确定性入口是：

```python
from quality import run_quality

quality_package = run_quality(parsed_document)
```

质量层输出：

- `optimized_markdown`
- `canonical_document`
- `quality_report`
- `package_manifest`

后端集成时应以 `ParsedDocument` 为输入，得到 `QualityPackage` 后落盘并返回给 Web。

## 关键目录

```text
api/           对外传输契约（DTO）
app/           应用层用例编排（组合根 + 用例）
trigger/       触发层：http（FastAPI）/ cli 共用同一套用例
domain/        核心领域：模型、路由、归一化、质量、端口
infra/         基础设施：解析器适配器 / 存储 / 转换 / 打包 / LLM
frontend/      MVP Web

tests/         契约、Adapter、API、routing、quality 测试
docs/          分工、配置、质量层和统一文档包说明
specs/         产品与工程规格
```

## 常用命令

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests\api -q
.\.venv\Scripts\python.exe -m pytest tests\quality -q
.\.venv\Scripts\python.exe -m uvicorn --app-dir C:\Users\zes\Desktop document_parser.trigger.http.app:app --host 127.0.0.1 --port 8010
```

## 安全约束

- Token 只能来自环境变量或运行时配置，不能写入仓库、输出包、日志或前端。
- `NativeArtifact.path` 和下载路径必须是任务目录内的安全相对路径。
- `allow_cloud=false` 时不能调用云端 MinerU。
- `reparse_required` 必须携带合法重解析建议；新解析应生成新任务，不能静默覆盖旧结果。
