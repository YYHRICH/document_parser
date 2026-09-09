# 完整工程工作日志（Workflow & Traceability）

> 角色口径：本文假设路由层、解析集成层、质量层、后端 API 与 MVP Web 均由我统一负责完成。
> 项目目标：构建一个可路由、可解析、可归一、可审计、可质量评估、可 Web 展示的统一文档解析系统。

## 阶段 1：需求拆解与工程边界确认

### 阶段目标

把原始需求从“调用多个文档解析工具”拆解为可工程落地的端到端链路：

```text
上传文档
  -> 路由决策
  -> 解析器 Adapter
  -> ParsedDocument 2.2
  -> QualityPackage 1.0
  -> 后端 API / Web 展示 / 产物下载 / 重新解析
```

### 实施步骤与技术细节

1. 梳理项目中的公共契约，明确三类核心数据结构：
   - `RoutingDecision 1.0`：描述推荐解析器、fallback、路由原因和参数。
   - `ParsedDocument 2.2`：解析集成层统一输出，屏蔽各解析器原生差异。
   - `QualityPackage 1.0`：质量层最终输出，包括 canonical document、quality report 和 manifest。
2. 明确工程边界：
   - 前端不能直接调用 Docling、MinerU、OCR、AnyDoc 或质量算法。
   - Web、CLI、纯后端入口复用同一 `DocumentParserGateway`。
   - 缺失证据必须通过 `capabilities` 声明，不能伪造 bbox、置信度、表格 cell 或标题层级。
3. 把不同角色职责整合为一条闭环：
   - 路由层负责选择模型。
   - 解析集成层负责真实调用和归一化。
   - 质量层负责审计、修复、质量门禁。
   - 后端和 Web 负责统一交互与结果展示。

### 思考与权衡

最关键的设计决策是“先冻结公共契约，再接解析器”。如果先围绕 Docling 或 MinerU 的私有返回对象开发，后续接入质量层和前端时会产生强耦合。因此我选择以 `ParsedDocument` 作为唯一中间事实源，把解析器差异限制在 Adapter 和 Normalizer 内部。

另一个关键权衡是缺失证据的处理方式。文档解析工具输出不一致是常态，例如有的工具没有 cell bbox，有的没有 OCR confidence。如果为了凑字段而填假数据，质量层会误判。因此系统选择“空值 + capability reason”的方式保留真实性。

### 阶段成果

- 明确了端到端链路与三份公共契约。
- 确定了 Adapter、Gateway、Quality、Backend、Frontend 的边界。
- 建立“不伪造证据、保留原生产物、统一入口复用”的工程原则。

### 下一步待办（Next Actions）

- 实现统一 Adapter 层。
- 建立统一文档包和 NativeArtifact 归档机制。
- 把路由决策接入 Gateway。

## 阶段 2：统一 Adapter 与 ParsedDocument 归一化

### 阶段目标

为不同解析器提供统一接入方式，让每个解析器都能输出合法的 `ParsedDocument 2.2`。

### 实施步骤与技术细节

1. 保留现有 MarkItDown 基线，作为轻量文本和 Office 回归路径。
2. 新增并注册多个 Parser Adapter：
   - `docling`
   - `mineru`
   - `ocr`
   - `anydoc`
   - `microsoft.markitdown`
3. 抽象 `BaseParserAdapter`，统一处理：
   - `ParseRequest`
   - parser metadata
   - native payload
   - markdown/html/assets
   - warnings
   - capabilities
   - native artifacts
4. 增加 `ParserNativeResult` 作为解析器原生产物和统一文档之间的中间态。
5. 通过 `NativeArtifact` 保存：
   - 安全相对路径
   - artifact 类型
   - 文件类型
   - 文件大小
   - SHA-256
   - 是否为质量层必需证据
6. 在 Normalizer 中把不同工具输出映射为统一结构：
   - blocks
   - tables
   - assets
   - ocr_spans
   - source anchors
   - provenance
   - capabilities

### 思考与权衡

不同解析器的输出并不是“字段名不同”这么简单，而是能力边界不同。例如 MarkItDown 更像单一 Markdown 输出，Docling 更偏结构化文档对象，MinerU 会产生 markdown、json、图片、表格等 sidecar，OCR 则以识别文本、bbox、confidence 为核心。因此不能写一个简单 JSON mapper，而要设计“原生结果 -> 中间态 -> 统一契约”的两段式流程。

AnyDoc 的加入也是一个重要调整。路由层把 Office 兜底能力纳入候选，但解析集成层原本没有 AnyDoc Adapter。为了让路由结果真实可执行，我补齐了 AnyDoc Adapter，并让它支持 native sidecar 或 CLI 方式接入。

### 阶段成果

- 完成 5 个 parser ID 的统一注册。
- Docling、MinerU、OCR、AnyDoc、MarkItDown 均可通过统一 Gateway 被发现。
- 解析器输出被统一归一为 `ParsedDocument 2.2`。
- 原生产物通过 `NativeArtifact` 归档，避免前端和质量层依赖私有对象。

### 下一步待办（Next Actions）

- 接入真实路由策略。
- 对 MinerU 云端模式、Docling 本地模式、OCR 本地模式分别做测试。
- 建立 API 和 Web 入口。

## 阶段 3：路由层接入与 Gateway 串联

### 阶段目标

把模型选择从手工指定升级为自动路由，并记录推荐模型、实际模型和 fallback 过程。

### 实施步骤与技术细节

1. 新增 `routing/` 包：
   - `config.py`
   - `registry.py`
   - `policy.py`
   - `router.py`
   - `errors.py`
2. 实现 `ModelRouter`，根据文件类型、route profile、cloud 开关和能力注册表生成 `RoutingDecision`。
3. 支持两种核心 profile：
   - `local_first`
   - `quality_first`
4. 支持关键运行参数：
   - `DOCUMENT_PARSER_ALLOW_CLOUD`
   - `MINERU_API_TOKEN`
   - `MINERU_API_BASE_URL`
   - `ANYDOC_EXECUTABLE`
5. Gateway 逻辑：
   - 如果 `parser_id=None`，走自动路由。
   - 如果显式指定 parser，保留手动模式。
   - 把 `RoutingDecision.parser_options` 合并到 ParseRequest options。
   - 在 `ParsedDocument.routing_decision` 和 provenance 中记录路由信息。

### 思考与权衡

自动路由必须兼顾灵活性和可控性。比如 PDF 在允许云端时优先 MinerU，但 `allow_cloud=false` 时必须禁止云端调用，不能只是前端隐藏选项。这个约束必须放在后端路由层，避免绕过。

同时，显式指定 parser 的手动模式也必须保留，因为联调和排障时需要稳定复现某个解析器结果。因此 Gateway 区分了自动模式和手动模式。

### 阶段成果

- 路由层与 Gateway 完成接入。
- 自动路由和手动 parser 选择共存。
- Provenance 中记录实际 parser、请求 parser、路由模式和 fallback 历史。

### 下一步待办（Next Actions）

- 接入后端 API。
- 让前端只通过 HTTP 调用 Gateway，而不是直接依赖算法模块。
- 为路由和 Gateway 补充测试。

## 阶段 4：MinerU、Docling、OCR、AnyDoc 真实接入策略

### 阶段目标

把 Adapter 从骨架推进到可真实运行或可消费真实 sidecar 的状态。

### 实施步骤与技术细节

1. Docling：
   - 使用 `docling.document_converter.DocumentConverter`。
   - 导出 markdown、dict payload、HTML。
   - 保存 `native/docling_document.json`、`native/full.md`、可选 `native/document.html`。
2. MinerU：
   - 支持 native output dir。
   - 支持本地 magic-pdf / MinerU Python API。
   - 支持云端 task API：submit、poll、download zip、安全解压、读取 sidecar。
   - Token 从环境变量或运行时 options 获取，并从持久化输出中脱敏。
3. OCR：
   - 使用 RapidOCR。
   - 生成 OCR spans、bbox、confidence。
   - 保存 OCR 原生 JSON。
4. AnyDoc：
   - 支持 Office 类格式。
   - 支持 native sidecar 或 CLI 调用。
   - 作为旧 Office 和 Office fallback 路径。

### 思考与权衡

MinerU 是最复杂的一项，因为本地安装重、云端有 token 和网络依赖。为了兼顾开发和验收，我设计了三层入口：

```text
native_output_dir -> 云端 task API -> 本地 CLI / Python API -> unavailable fallback
```

这样在没有模型环境时，可以先用真实 sidecar 做归一化测试；在配置 token 后，再跑完整云端链路。

对安全性来说，token 绝不能进入 `ParsedDocument`、native artifacts、日志或前端，所以在 `BaseParserAdapter` 中加入敏感 options 脱敏。

### 阶段成果

- Docling 可以真实调用并保存 sidecar。
- MinerU 支持云端精准 API、本地兼容和 sidecar 归一化。
- OCR 支持 RapidOCR 解析图片并输出 spans。
- AnyDoc 已补齐，路由层候选 parser 均有对应 Adapter。

### 下一步待办（Next Actions）

- 在更多真实文件上跑端到端验收。
- 根据不同工具的真实输出继续增强字段映射。
- 对外部依赖缺失场景保持明确 warning 和 capability reason。

## 阶段 5：统一文档包与后端 API

### 阶段目标

实现独立后端 API，保证前端和外部调用方不直接调用解析算法。

### 实施步骤与技术细节

1. 新增 FastAPI 后端：
   - `GET /api/health`
   - `GET /api/parsers`
   - `POST /api/parses`
   - `GET /api/parses/{parse_id}`
   - `GET /api/parses/{parse_id}/artifacts/{artifact_path}`
   - `POST /api/parses/{parse_id}/reparse`
   - `GET /api/parses/{parse_id}/quality-package`
   - `POST /api/parses/{parse_id}/quality-package`
2. 新增 `ApiStorage`：
   - 管理 parse package 目录。
   - 保存 source/original。
   - 保存 parsed_document.json。
   - 保存 native artifacts。
   - 保存 quality_package.json。
3. 实现安全路径校验：
   - 禁止绝对路径。
   - 禁止 `..`。
   - 禁止逃逸任务目录。
4. 后端自动挂载 `frontend/`：
   - `/` 返回 MVP Web。
   - `/static/*` 返回静态资源。

### 思考与权衡

后端 API 的核心不是简单上传文件，而是要把解析任务变成可追踪的 package。只有 package 稳定存在，才能支持质量层复核、artifact 下载、重新解析、人工审查和后续任务编排。

我选择先做同步 API，而不是复杂队列，是因为 MVP 阶段更重要的是验证契约和链路正确性。后续如果引入异步任务系统，Gateway 和 Adapter 仍可复用。

### 阶段成果

- 完成纯后端入口。
- 完成统一文档包落盘。
- 完成 artifact 安全下载。
- 完成 reparse 生成新任务。
- 完成 QualityPackage 读写接口。

### 下一步待办（Next Actions）

- 接入质量层自动生成。
- 前端展示路由、解析、artifact、quality package。
- 补 API 测试。

## 阶段 6：MVP Web 展示

### 阶段目标

提供一个可演示的 Web 页面，展示上传、模型选择、路由结果、解析结果、产物下载、质量包和重新解析。

### 实施步骤与技术细节

1. 新增 `frontend/index.html`、`frontend/style.css`、`frontend/app.js`。
2. 支持：
   - 文件上传。
   - parser 手动选择或 Auto route。
   - `route_profile`。
   - `allow_cloud`。
   - `libreoffice_available`。
   - extra JSON options。
   - parse result 展示。
   - routing decision 展示。
   - markdown 展示。
   - artifact 下载链接。
   - reparse。
   - quality package 展示。
3. 前端只调用后端 API，不导入任何 Python 算法模块。

### 思考与权衡

MVP Web 的重点不是视觉复杂度，而是证明完整链路可用。因此页面采用简单直接的操作台形态，把开发和联调最需要的信息暴露出来：parser、route、capabilities、warnings、markdown、artifacts、quality package。

### 阶段成果

- Web 可从 FastAPI 根路径直接访问。
- 前端能上传并触发解析。
- 前端能展示质量包。
- 前端与算法完全解耦。

### 下一步待办（Next Actions）

- 增加更友好的质量状态摘要。
- 增加 parse history / task list。
- 对浏览器交互做 e2e 测试。

## 阶段 7：质量层实现与联调

### 阶段目标

从 `ParsedDocument 2.2` 生成 `QualityPackage 1.0`，并接入后端自动流程。

### 实施步骤与技术细节

1. 新增 `quality/` 包，公共入口：

```python
from quality import run_quality

quality_package = run_quality(parsed_document)
```

2. 实现质量流水线：
   - EvidenceContext。
   - 完整性规则。
   - provenance 规则。
   - heading 规则。
   - reference 规则。
   - table 规则。
   - cross-page table 规则。
   - whitelist repairs。
   - capability matrix。
   - gate evaluator。
   - canonical document builder。
   - deterministic packaging。
3. 后端 parse/reparse 成功后自动调用：

```python
storage.write_quality_package(parse_id, run_quality(result.document))
```

4. 前端通过：

```text
GET /api/parses/{parse_id}/quality-package
```

读取并展示质量包。

### 思考与权衡

质量层不能替代解析层，也不能重新发明解析器。它只能基于 `ParsedDocument` 提供的真实证据做判断。这样做的好处是：

- 质量层不依赖 Docling/MinerU 私有对象。
- 解析工具可替换。
- 质量规则可测试、可复现。
- 证据不足时进入 warning/manual/reparse，而不是误判 pass。

质量层中的 white-list repair 只做可回放的确定性修复，避免 LLM 或规则擅自改事实。

### 阶段成果

- `ParsedDocument -> QualityPackage` 打通。
- 后端自动生成 `quality_package.json`。
- Web 可展示质量结果。
- 质量层测试与解析集成测试共同通过。

### 下一步待办（Next Actions）

- 接入更完整的 LLM repair agent。
- 根据真实业务样本扩展 golden。
- 根据 reparse recommendation 自动生成新 parse task。

## 阶段 8：测试、合并与最终联调

### 阶段目标

验证张、朱、叶三条链路在同一个分支上可以稳定工作。

### 实施步骤与技术细节

1. 合并质量层分支。
2. 清理临时嵌套副本 `document_parser-main`，保留根目录正式代码。
3. 解决 README、pytest、requirements 冲突。
4. 执行测试：

```text
tests/api/test_parse_api.py：5 passed
tests/quality/unit + contract + integration：192 passed, 1 xfailed
全量测试：228 passed, 1 xfailed
```

5. 执行 API 小闭环：

```text
POST /api/parses -> 200
GET /api/parses/{parse_id}/quality-package -> 200
quality_report.state = pass_with_warnings
quality_package.json 真实落盘
```

### 思考与权衡

合并时不保留嵌套的 `document_parser-main`，因为它只是临时拖入的张分支副本。正式代码已经拆分合入根目录，包括 routing、quality、backend、frontend 和测试。

冲突解决时不简单选择 ours/theirs，而是按职责合并：

- README 重写为统一项目说明。
- pytest 保留 `testpaths = tests` 和 `pythonpath = . ..`。
- requirements 保留 FastAPI/httpx/解析器依赖和质量层工具依赖。

### 阶段成果

- 端到端主链路完成。
- 路由、解析、质量、后端、前端全部在同一工程内联通。
- 测试基线稳定。
- 临时副本已删除，工程结构收敛。

### 下一步待办（Next Actions）

- 提交并推送集成分支。
- 使用真实大文件做验收。
- 检查每台机器上的 Docling、MinerU、AnyDoc、RapidOCR 外部依赖配置。
- 与团队确认 `1 xfailed` 对应的 golden 标注冲突是否需要更新。
