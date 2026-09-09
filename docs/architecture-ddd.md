# Document Parser 架构设计（DDD 分层 · 面向松耦合 / 可拆分 / 可复用）

> 状态：DDD 分层重构已完成并投入当前主链；HTTP、CLI、解析、统一、质量和交付均使用现有分层。MQ 仅为后续可选入口，不属于当前运行要求。
> 适用范围：`document_parser` 单仓库（Python 3.11 + FastAPI）
> 目标：**松耦合、可拆分、可复用**
>
> 当前边界：`domain` 保存领域模型和规则，`app` 编排用例，`infra` 实现解析器、存储和质量包，`trigger` 提供 HTTP/CLI 入口，`frontend` 只通过 API 使用后端。

---

## 1. 三个目标的具体含义

| 目标 | 在本工程中的含义 | 衡量方式 |
| --- | --- | --- |
| 松耦合 | 领域模型不依赖框架/解析器/存储；换实现不改业务代码 | 依赖方向单向；端口接口稳定 |
| 可拆分 | 解析、质量、存储、入口可以拆成独立进程/服务/目录 | 用例可独立运行；端口可换实现 |
| 可复用 | 同一套领域与用例同时服务 Web / CLI / 未来 MQ / 其他系统 | 所有入口只调 `app` 层用例 |

---

## 2. 分层定义

采用 **端口与适配器（Ports & Adapters）+ 用例驱动** 的分层，共六层。这里的 `api` 是传输契约，不是领域层；`domain` 只定义业务语义和端口，`app` 负责事务边界与用例编排：

```text
  trigger       薄入口：HTTP 路由 / CLI / MQ 消费 / 定时任务
     │ 只做参数转换、鉴权、响应封装，不写业务
     ▼
  app           应用层：用例编排（一个用例 = 一条可独立测试的业务流程）
     │ 依赖 domain 的模型与服务，通过端口接口拿基础设施
     ▼
  domain        核心领域层：领域模型 + 领域服务 + 端口接口定义
     ▲                            │
     │ 实现 domain 声明的端口       │ 接口契约，infra 负责实现
     │                            ▼
  infra         基础设施层：解析器适配器 / 存储 / LLM / 转换 / 打包 实现

  api           对外契约层：HTTP/RPC DTO、请求/响应模型、版本化公共契约
                （被 trigger 与外部消费者复用；不承载领域端口实现）
```

### 2.1 各层职责与依赖铁律

| 层 | 允许放什么 | 依赖谁 | 禁止 |
| --- | --- | --- | --- |
| `domain` | 领域模型（`ParsedDocument`、`ParseRequest`、`QualityPackage`）、领域服务（路由决策、质量规则、门禁、修复）、端口接口（`ParserPort`、`StoragePort`、`ConverterPort`、`EventPublisherPort`） | 标准库；允许使用已冻结的 schema/value-object 库（当前为 pydantic），不得依赖应用配置或运行时 | import `fastapi`、`parsers`、`backend`、`infra`、任何第三方解析库 |
| `app` | 用例：`ParseDocumentUseCase`、`RunQualityUseCase`、`ReparseUseCase`、编排服务（`DocumentParsePipeline`）、事务边界、事件发布调用 | `domain`、`api`、标准库 | 直接 import `infra` 实现类；直接碰文件系统/HTTP/MQ；把 FastAPI 异常作为业务结果 |
| `api` | 传输 DTO、请求/响应模型、对外 RPC/HTTP 契约定义 | `domain`（仅在需要暴露领域值时） | 依赖 `infra`、`trigger`、应用实现；在 DTO 中暴露第三方对象 |
| `trigger` | FastAPI 路由、CLI 入口、MQ 监听器、Job 调度 | `api`、`app`、`domain`（仅输入模型如 `ParseRequest`） | 写业务编排；直接调解析器/存储实现 |
| `infra` | 具体实现：各解析器、`ApiStorage`、`LegacyOfficeConverter`、`Normalizer`、`LlmClient`、打包写入 | `domain`（端口）、第三方库 | 反向依赖 `app`/`trigger` |

依赖方向铁律（单向、无环）：

```text
trigger → app → domain ← infra
    └──────→ api → domain
```

`domain` 是业务核心；在本项目允许的依赖中，它只依赖标准库和冻结的 schema/value-object 工具。`infra` 是唯一允许依赖第三方解析、转换、存储、HTTP/MQ SDK 的地方。`api` 与 `trigger` 都是边界层，不能被 `domain` 或 `infra` 反向依赖。

---

## 3. 当前工程 → 目标结构映射

### 3.1 现状问题（迁移前基线）

- `core/gateway.py` 是"大而全"门面：路由 + fallback + 解析 + 格式转换在一条链路里；它已经可注入部分依赖，但仍同时承担应用编排和基础设施选择。
- `backend/app.py` 的 HTTP handler 里直接做了解析、存储、质量编排，属于 trigger 层写业务；`reparse` 还重复了同一套落盘流程。
- `quality/` 已有较清晰的质量子域，但 `quality/api.py` 与 `backend/app.py` 之间缺少稳定的应用端口/用例边界。
- `pyproject.toml` 的包映射只覆盖部分运行包，目标目录迁移前必须先统一包发现/导入策略，否则"目录已移动但安装包不可用"。
- `core/` 包名含义模糊（领域？应用？基础？），职责不清。
- `routing/`、`normalizers/` 是顶层包，和 `core`、`quality` 平级，没有表达它们各自属于哪一层。
- 质量层 `quality/` 实际是独立的子域（bounded context），但没有与"解析域"分层。

### 3.2 映射表

| 当前路径 | 归属 | 目标路径 | 说明 |
| --- | --- | --- | --- |
| `core/contracts.py` ✅ | 领域模型 | `domain/model/contracts.py` | 当前唯一领域协议，不保留并行版本 |
| `core/inspector.py` ✅ | 领域服务 | `domain/service/source_inspector.py` | 源信号提取是纯领域逻辑 |
| `routing/` ✅ | 领域服务 | `domain/routing/` | 路由决策、策略、能力注册表 |
| `normalizers/` ✅ | 领域助手/防腐层 | `domain/normalization/` | 纯逻辑，只依赖 contracts |
| `quality/rules|gates|evidence|repairs` ✅ | 领域服务（质量子域） | `domain/quality/rules` 等 | 质量规则/门禁/修复策略 |
| `quality/pipeline.py`、`models_internal.py`、`ids.py`、`config.py` ✅ | 领域服务（质量子域） | `domain/quality/` | 规则编排与内部模型 |
| `infra/parsers/gateway.py` ✅ | 应用编排 | `app/orchestration.py::DocumentParsePipeline` | 路由+fallback+转换编排上移；解析器适配器直接实现 `ParserPort` |
| `quality/api.py` | 应用层 | `app/use_cases.py::run_quality` | `run_quality` 即质量用例 |
| `backend/schemas.py` ✅ | 对外契约 | `api/dto.py` | 请求/响应 DTO 唯一来源；`backend/` 兼容 shim 已移除 |
| `backend/app.py` 路由部分 ✅ | 触发层 | `trigger/http/routes.py` + `trigger/http/app.py` | FastAPI 装配已在 trigger |
| `backend/main.py` ✅ | ASGI 启动 | `trigger/http/main.py` | 组合根负责依赖注入，HTTP 入口只负责启动 |
| `parsers/*`、`parsers/base.py`、`parsers/registry.py` ✅ | 基础设施 | `infra/parsers/` | 各解析器适配器，实现 `ParserPort` |
| `core/converter.py` ✅ | 基础设施 | `infra/converter.py` | 老 Office 格式转换，实现 `ConverterPort` |
| `backend/storage.py` ✅ | 基础设施 | `infra/storage/api_storage.py` | 文件持久化，实现 `StoragePort` |
| `quality/packaging/writer.py` ✅ | 基础设施 | `infra/quality_packaging/` | 产物落盘 |
| `core/document_package.py` ✅ | 基础设施 | `infra/packaging/` | 包读写（校验逻辑可留 domain） |
| `tools/`、`scripts/` | 开发工具 | `scripts/` | 保留，作为开发/验证脚本 |
| `frontend/` | 独立消费者 | `frontend/`（不动） | 只通过 `api` 契约与后端交互 |
| `tests/` | 测试 | `tests/{unit,domain,app,trigger,infra}/` | 按层组织，用例测试不启动 FastAPI |

---

## 4. 核心机制（如何做到松耦合）

### 4.1 端口与适配器

每个"可能被替换的外部依赖"在 `domain/ports.py` 声明接口，`infra/` 提供实现：

| 端口（domain 声明） | 实现（infra） | 可替换对象 |
| --- | --- | --- |
| `ParserPort.parse/normalize(request, signals)` | `infra/parsers/*` 各适配器 | 解析器（本地/云端/未来新解析器） |
| `ConverterPort.convert(content, extension) -> ConversionOutcome` | `LegacyOfficeConverter` | LibreOffice/在线转换 |
| `StoragePort.save_package(...)` / `load_document(...)` | `ApiStorage` | 本地磁盘/S3/MinIO |
| `QualityPackagerPort.write(package, dir)` | `write_package_directory` | 打包方式 |
| `LlmAdvisorPort.advise(...)` | `infra/llm/` 客户端 | LLM 供应商 |
| `EventPublisherPort.publish(topic, payload)`（占位） | 未来 MQ 适配器 | 通知机制（可替换为日志/内存/消息队列） |

约定：

- `domain/ports.py` 里只有 `typing.Protocol` / ABC 与纯数据，没有实现。
- `app` 用例构造函数注入端口实现（组合根在 `app/bootstrap.py` 组装）。
- 新增解析器 = 新增一个 `infra/parsers/*` 适配器 + 注册表登记，**不改 domain/app/trigger**。

### 4.2 用例与编排（app 层）

用例返回领域结果或应用结果对象；HTTP 状态码、`HTTPException`、上传文件对象和 FastAPI 依赖只允许出现在 trigger。失败语义在 app/domain 中使用明确异常或结果类型表达，由 trigger 统一映射为协议响应。每个用例必须声明事务边界：解析成功、文档包落盘、质量包落盘是否原子，以及失败时是否允许留下半成品。

编排（路由 → 候选解析器 → fallback → 格式转换 → 元数据补齐）属于应用层职责，落在 `app/orchestration.py::DocumentParsePipeline`；各解析器只实现自己的 `ParserPort` 适配器，不感知 fallback 与转换。

一个用例对应一个业务目标，方法名即业务语言：

```python
class ParseDocumentUseCase:
    def __init__(self, pipeline: DocumentParsePipeline, storage_port: StoragePort, event_publisher): ...

    def execute(self, request: ParseRequest) -> ParseApplicationResult: ...
    def list_parsers(self) -> list[ParserCapability]: ...

class ReparseDocumentUseCase:
    def execute(self, parse_id: str, parser_id: str, options) -> ParseApplicationResult: ...

class RunQualityUseCase:
    def execute(self, document: ParsedDocument) -> QualityPackage: ...
```

- 用例之间不互相调用；跨用例协作通过领域事件（如 `ParseCompleted` → 触发质量/归档）。
- 每个用例都能在无 FastAPI、无真实解析器的情况下用桩对象单测。

### 4.3 组合根与依赖注入

组合根还必须负责生命周期管理（例如解析器客户端、转换器和事件发布器的 `close`），并为测试提供显式的内存端口实现。不得在用例或领域代码中直接 `new` 端口实现；组合根是唯一允许感知"谁是谁"的装配点（`app/bootstrap.py`、`trigger/http/app.py` 豁免依赖方向检查）。

---

## 5. 可拆分性说明

按依赖方向，"拆"是单向且安全的：

- **入口可拆**：HTTP 服务、CLI、MQ consumer、定时任务各自是独立进程，共用 `app` + `domain` + `api`，互不影响。
- **解析器可拆**：`infra/parsers` 每个适配器可独立为子进程/worker（云端解析本来就进程外）；`ParserPort` 保持不变。
- **质量层可拆**：质量子域是独立 bounded context，端口 `QualityPort` 稳定后，可拆成独立服务或库。
- **存储可拆**：`StoragePort` 换 S3/MinIO 实现即可，不影响用例。
- **部署可拆**：`trigger/http`、`trigger/cli`、未来 `trigger/mq` 可以各自打镜像/进程，domain 与 app 作为共享代码库发布。

> 注意：可拆分 ≠ 现在就拆。单仓库单进程下，"可拆分"表现为**代码边界清晰、端口稳定**，拆只是改部署方式，不改代码。

---

## 6. 可复用性说明

- **库式复用**：`domain` + `app` + `api` 构成可发布的核心包，任何新入口（Web、CLI、内部服务、测试桩）都通过 `app` 用例进入，保证行为一致。
- **入口复用**：`trigger/http/routes.py` 的 handler 与 `trigger/cli/main.py` 复用同一 `ParseDocumentUseCase` 与 `DocumentParsePipeline`；未来 MQ consumer 直接复用，不再复制编排。
- **测试复用**：`tests/` 中用例与编排测试不启动 HTTP，一套用例测试服务 Web 和 CLI 两条链路。
- **对外复用**：`api/` 的 DTO 与契约可被其他团队/服务直接引用（例如前端 `api-types.ts`、下游质量消费方）。

---

## 7. 迁移路线（渐进式，不推翻重来）

迁移原则：先建立可执行的依赖约束，再做兼容性移动；每一步都必须可回滚，并保留旧导入路径的短期兼容 shim。禁止一次性移动所有目录后再集中修复 import。每个阶段完成后必须运行 `pytest`、API 冒烟测试、契约校验和依赖检查。

| 阶段 | 内容 | 改动成本 | 交付物 |
| --- | --- | --- | --- |
| 0 设计基线 ✅ | 本文档；建立依赖检查脚本；记录现状导入与行为基线 | 低 | `docs/architecture-ddd.md`、`scripts/check_dependencies.py`、基线测试报告 |
| 1 目录重排 ✅ | 先迁移 `contracts`、`routing`、`normalizers`、`quality`；再迁移解析器和存储；保留旧路径 shim | 中 | 目录表达分层，`pyproject.toml` 使用可验证的包发现并覆盖新旧路径 |
| 2 端口化 ✅ | 在 `domain/ports.py` 定义端口；`gateway` 与 `backend` 只依赖端口 | 中 | 依赖方向受检，可替换性落地 |
| 3 用例拆分 ✅ | `DocumentParserGateway` 拆为 `DocumentParsePipeline`（编排）+ `ParseDocumentUseCase`/`ReparseUseCase`/`RunQualityUseCase`；`trigger/http/routes.py` 变薄 | 中 | HTTP 与 CLI 复用同一用例 |
| 4 多入口 ✅（CLI）/ ⏳（MQ） | 新增 `trigger/cli/main.py` 复用 `ParseDocumentUseCase`；`trigger/mq/` 与 `EventPublisherPort` 已占位，MQ consumer 待开发 | 低（前序完成后） | 展示"可拆分"收益 |
| 5 可选独立部署 ⏳ | 质量层/解析器独立进程或服务 | 视需要 | 部署拆分 |

---

## 8. 可执行依赖规则

依赖检查脚本必须把 Python import 解析为顶层包/项目层，并按以下规则报告文件路径、违规 import 和建议修复方向：

- `domain` 只能依赖 `domain`、允许的 schema 工具和标准库。
- `app` 只能依赖 `app`、`domain`、`api` 和标准库。
- `api` 只能依赖 `api`、`domain` 和允许的 schema 工具。
- `trigger` 可以依赖 `trigger`、`app`、`api`，不能依赖 `infra` 的具体实现。
- `infra` 可以依赖 `infra`、`domain` 和第三方库，不能依赖 `app`、`api`、`trigger`。
- 测试、脚本、组合根不参与生产依赖方向检查，但必须通过公开端口/用例访问生产代码。

检查脚本必须支持非零退出码、稳定排序、忽略测试/脚本目录，并覆盖相对导入与绝对导入。仅用字符串 grep 不足以作为依赖检查实现。

## 9. 红线（反模式，禁止）

1. `domain` import `fastapi`、`parsers`、`backend` 或任何第三方解析/HTTP 库。
2. `trigger` 层写业务编排（`backend/app.py` 的 handler 即反例，须下沉到用例）。
3. 层间循环依赖（`domain ← app` 同时 `app → domain` 是允许的，但 `infra → app`、`app → trigger` 禁止）。
4. 为 DDD 造空壳层（如 `case/` 与 `app/` 并存但无实质职责差异——本设计采用 **app 即用例层**，不再单设 case 层）。
5. 领域模型泄漏第三方对象（docling/mineru 内部对象不得越过 `domain/ports` 流出）。
6. 绕过 `app` 用例直接调用 `infra` 实现（例外：`trigger` 只做参数转换时允许通过 `api` 契约，不允许直接碰实现）。

---

## 10. 验收标准

- [x] `scripts/check_dependencies.py` 以 AST/import 图检查通过：依赖方向无违规、无环，并返回非零退出码表示失败。
- [x] 各层目录表达职责（api/app/trigger/domain/infra），无 `core/`、`quality/`、`backend/` 残留业务代码。
- [x] `ParserPort`/`ConverterPort`/`StoragePort` 由 `infra` 实现；编排在 `app` 层；trigger 只做参数转换与响应封装。
- [x] Web（HTTP）与 CLI 复用同一 `ParseDocumentUseCase`；新增 `trigger/mq/` 入口只调用例，不复制编排。
- [x] 前端通过 `frontend/api-types.ts` 消费后端 OpenAPI 契约（重新生成：`python scripts/gen_frontend_types.py`）。
- [ ] 阶段 4 余项：MQ consumer / `EventPublisherPort` 实现。
