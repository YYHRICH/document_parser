# 周报（2026-08-24 ~ 2026-08-28）

> 负责人：wood-heart_0 ｜ 方向：工程架构 ｜ 主题：Document Parser DDD 分层架构重构

## 1. 当前任务目标

本周负责完成 `document_parser` 工程的 **DDD 分层架构重构**，核心目标：

- 拆掉"大而全"的 `core/gateway` 门面与 `backend/app.py` 直写业务的 HTTP handler，建立 **trigger / app / domain / infra / api 五层 + 端口适配器** 的清晰边界；
- 让 Web、CLI、未来 MQ 复用同一套业务用例，解析器、存储、转换实现可替换而不改业务代码；
- 完成代码迁移、依赖方向自动化校验、全量回归测试，并输出架构文档。

## 2. 本周进展与产出

### （1）调研类：分层方案选型

- **调研范围**：DDD 四层、整洁架构（Clean Architecture）、六边形架构（Ports & Adapters）对当前工程的适用性。
- **核心对比结论**：`core/` 包名职责模糊、gateway 同时承担应用编排与基础设施选择、trigger 层写业务是当前主要坏味道；业界方案都指向"领域与框架解耦 + 端口反向依赖"，与本工程三入口（Web/CLI/未来 MQ）复用诉求一致。
- **推荐方案**：采用 **端口与适配器 + 用例驱动** 的六层结构（`trigger → app → domain ← infra`，`api → domain`），理由：与现有 3 人分工（路由 / 集成 / 质量）边界天然吻合，迁移成本低，且不引入额外框架依赖。

### （2）开发类：重构完成情况

- **重构规模**：1 个提交（`ca21585`），共 **137 个文件变更，净增 2296 行 / 删除 680 行**，一次性完成目录迁移与代码整改。
- **分层落地**：
  - `core/` 清空拆分：`contracts` → `domain/model/`；`gateway` → `app/orchestration.py::DocumentParsePipeline`（编排上移，适配器直接实现 `ParserPort`）；`converter` → `infra/`；
  - `quality/` 拆分为领域与实现：规则 / 门禁 / 证据 / 修复进 `domain/quality/`，打包写入进 `infra/quality_packaging/`，`run_quality` 收敛为 `app/use_cases.py` 质量用例；
  - `routing/` → `domain/routing/`，新增 `CapabilityRegistry`，**解除对解析器实例的反向依赖**；
  - `parsers/` → `infra/parsers/`，MarkItDown / Docling / MinerU / OCR / AnyDoc 统一实现 `ParserPort`；
  - `backend/` 兼容 shim 移除：`schemas` → `api/dto.py`，`storage` → `infra/storage/api_storage.py`。
- **新增关键组件**：
  - `domain/ports.py`：`ParserPort` / `ConverterPort` / `StoragePort` / `EventPublisherPort` 协议定义；
  - `app/bootstrap.py` 组合根（`ApplicationContainer`）+ `app/use_cases.py`（`Parse / Reparse / RunQuality` 三个用例）；
  - `trigger/` 薄入口：HTTP（FastAPI）、CLI、MQ 占位；
  - `scripts/check_dependencies.py`：**自动校验依赖方向铁律（单向、无环）**；
  - 前端契约收敛：OpenAPI → `frontend/api-types.ts` + `scripts/gen_frontend_types.py`。
- **测试结果**：全量回归 **237 passed, 1 xfailed**（耗时约 4 分钟），重构前后行为无回归。

### （3）实验类：回归验证

- **验证设计**：以全量 pytest 为基准（契约 / 路由 / 归一化 / Adapter / API / quality 单元与集成），对比重构前后同一套用例是否保持通过；
- **结果**：237 个用例全部通过，`routing-adaptor-quality-fix` 相关功能无回归，确认迁移只动了结构、未动行为。

## 3. 问题与下一步计划

### 当前问题

- 阶段 4 余项：**MQ consumer / `EventPublisherPort` 实现尚未开发**，`trigger/mq/` 目前仅为占位；
- 阶段 5 可选：**独立部署拆分**（解析 / 质量 / 存储各自独立进程）未验证；
- `scripts/check_dependencies.py` 已可运行但**尚未接入 CI 门禁**，依赖方向仍靠人工触发校验。

### 下一步计划

- 实现 MQ 消费入口与 `EventPublisherPort` 的具体实现，接通异步解析链路，输出可运行的 MQ 触发 demo；
- 将 `check_dependencies.py` 接入 CI，作为架构依赖方向的强制门禁；
- 视需要做阶段 5 的独立部署可行性验证（解析与质量拆服务后的性能 / 成本对比）。

---

## 附：三个分析角度自查（供评审快速对齐）

- **技术效果**：相比原 gateway 门面，分层后领域与框架 / 解析器 / 存储彻底解耦，换实现不改业务代码；方案与主流 DDD / 整洁架构一致，未引入额外框架成本。
- **工程实现**：重构为纯代码迁移，无新增运行时资源开销；依赖方向自动化校验降低架构腐化成本；后续拆服务以端口为边界，工程改动可控。
- **产品价值**：Web / CLI / 未来 MQ 共用一套用例，新增入口与替换解析器只需改 `infra`，交付和排障效率提升；行为未变，结果可信度由 237 条回归测试保障。
