# 质量层开发指南：DDD 建模下的“按解析器差异化优化 + 统一归一化”

> 适用对象：需要改动质量层、但还不熟悉 DDD 领域建模的开发者。
> 范围：`document_parser` 仓库（Python 3.11 + FastAPI，端口与适配器架构）。
> 目标：让你在不破坏 DDD 边界的前提下，完成“不同解析工具做不同优化，最后归一化”的整体升级。
> 先读：`docs/architecture-ddd.md`（分层总纲）、`docs/architecture-for-leadership.md`（通俗版）。

---

## 0. 一句话结论（先记住这个）

**“按解析器差异化优化”发生在 `infra/parsers` 的适配器里（每家解析器自己把输出归一化成统一的 `ParsedDocument`）；“统一质量判定”发生在 `domain/quality` 里，且只能靠“能力/证据”驱动，不能靠 `if parser_id == ...` 硬编码。** 如果某一家的确提供不了某种证据，就如实声明 `UNAVAILABLE`/`PARTIAL`，质量层会自动降级、如实报告，而不是假装有。

---

## 1. DDD 分层在代码里长什么样

```text
trigger（HTTP/CLI/MQ 薄入口）
   ↓ 只做参数转换、响应封装，不写业务
app（用例编排：ParseDocumentUseCase / RunQualityUseCase / …）
   ↓ 依赖领域，面向端口编程
domain（业务核心：模型 / 路由 / 归一化 / 质量 / 端口）
   ↑ 实现 domain 声明的端口
infra（具体实现：解析器适配器 / 存储 / 转换 / 打包）
api（对外 DTO 契约，被 trigger 与外部复用）
```

**依赖铁律（单向、无环，`scripts/check_dependencies.py` 会校验）：**

```text
trigger → app → domain ← infra
    └──────→ api → domain
```

对你最重要的一条：**`domain` 不能 import `infra`，不能感知任何具体解析工具**。所以“针对 MinerU/MarkItDown/Docling 做不同优化”如果写进了 `domain/quality` 的规则里，就是架构违规。

---

## 2. 质量层现在长什么样（现状地图）

```text
infra/parsers/ 适配器（每家解析器自己的实现）
   ├─ MarkItDown（生产）  Docling / MinerU / OCR / AnyDoc（骨架）
   └─ normalize()：把各家原始输出 → 统一 ParsedDocument  ←【第一道归一化】

domain/quality/（质量子域，纯业务，不感知解析器）
   ├─ pipeline.py          run_pipeline(parsed_document) → QualityPackage（唯一入口）
   ├─ evidence/            证据上下文与可用性判定
   │   ├─ context.py       EvidenceContext：不可变证据视图，规则唯一数据源
   │   ├─ requirements.py  EvidenceRequirement：规则声明“我需要哪些证据”
   │   └─ availability.py  AvailabilityResolver：按 capabilities 判定能执行/受限/跳过
   ├─ rules/               质量规则（只读证据，产出 RuleResult）
   ├─ gates/               能力矩阵 + Gate 最终判定（唯一能定 pass/reparse/rejected 的地方）
   ├─ repairs/             白名单修复（幂等、可回放、可回滚）
   ├─ builders/            构建 canonical document
   └─ config.py            QualityConfig / GateConfig（阈值与开关）

app/use_cases.py::run_quality()  ← 应用层质量入口（HTTP/CLI 都走它）
```

核心数据流：

```text
原始文件
  → 某解析器适配器（infra/parsers）       ← 这里做“解析器专属优化”
  → ParsedDocument（统一契约）
  → EvidenceContext（domain/quality）     ← 从这里开始“统一质量判定”
  → rules → capability matrix → gate
  → QualityPackage（报告 / 修复 / canonical）
```

**关键机制（你要复用而不是绕开它）：**
- `ParsedDocument.capabilities: dict[str, EvidenceCapability]`：每个适配器如实声明自己提供了哪些证据（`AVAILABLE` / `PARTIAL` / `UNAVAILABLE` / `FAILED`，非 available 必须写 `reason`）。
- 规则用 `required_evidence` 声明需求（如 `page_bbox`、`table_cells`、`ocr_confidence`），调度器自动决定：完整执行 / 以有限证据执行（限制最高状态）/ 跳过并输出 `unavailable`。
- 能力矩阵（`gates/capabilities.py`）从“证据可用性 + 规则结果”推导六项标准能力状态，不直接复制 `ParsedDocument.capabilities`。
- Gate（`gates/evaluator.py`）是**唯一**最终状态判定者。

---

## 3. 你的任务在 DDD 下拆成三层去做

| 你的诉求 | DDD 里的落点 | 为什么 |
| --- | --- | --- |
| 每家解析器输出不一样 → 先各自优化 | `infra/parsers/{parser}/` 适配器的 `normalize()` | 归一化的第一道关就在适配器：把每家“脏输出”洗成统一 `ParsedDocument`，质量层永远看不到原始格式 |
| 某些解析器提供不了某类证据 | 适配器里声明 `EvidenceCapability(UNAVAILABLE, reason=...)` | 质量层自动降级该项能力并如实报告，绝不伪造 bbox/置信度/单元格 |
| 同一份统一文档，不同解析器质量判定不同 | 靠“证据驱动” + `QualityConfig` 可配置阈值；**不**在规则里硬编码 parser_id | 保持 domain 与具体工具解耦，换解析器/升级模型不用改业务代码 |
| 某些格式问题需要“修” | `domain/quality/repairs/` 白名单修复 | 只做可证明等价的低风险变换，绝不补内容/猜 OCR |

---

## 4. 为什么不能直接 `if parser_id == "mineru"`（三条硬理由）

1. **依赖方向反了**：`domain/quality` 是业务核心，`parser_id` 属于具体工具。写了这个分支，质量层就开始“认识”具体解析器，`scripts/check_dependencies.py` 虽拦不住字符串判断，但你的规则会变成：每次接入新解析器都要回来改质量规则。
2. **语义错了**：你要的差异化本质是“**证据不可靠**”，不是“**这个解析器坏**”。MinerU 的表格列数问题 = `table_cells` 证据不可靠；OCR 的 bbox 问题 = `page_bbox` 不可靠。证据驱动后，同样的规则对任何解析器都自动生效，还能表达“这个模型版本可靠、那个版本不可靠”。
3. **测试和可解释性**：硬编码分支的规则无法用一份固定用例集测全；证据驱动则能力矩阵里每一格都能解释“为什么这项能力是这个状态”。

**如果确实要“同一能力、不同阈值”**：把阈值放进 `QualityConfig`（`domain/quality/config.py`），由组合根/调用方注入。规则只读配置，不写 `if parser_id`。

---

## 5. 实施步骤（照这个顺序做）

### Step 0：先读 5 个文件，建立心智模型
1. `domain/quality/pipeline.py`（入口与编排顺序）
2. `domain/quality/evidence/context.py` + `availability.py`（规则怎么拿证据）
3. `domain/quality/rules/` 里任一规则，如 `completeness.py`（规则怎么写）
4. `infra/parsers/base.py` 的 `normalize()` / `capability()`（适配器怎么归一化与声明）
5. `tests/quality/` 的 unit + integration（怎么测）

### Step 1：盘点“脏数据”清单（先调研，别急着写代码）
对每个解析器建一张表：

| 解析器 | 常见问题 | 发生在哪一阶段 | 应该在哪一层修 |
| --- | --- | --- | --- |
| MinerU | 表格分隔行列数不一致 | 适配器输出 | `infra/parsers/mineru` 归一化（修格式） |
| MinerU | 某些页面无 bbox | 证据缺失 | 适配器声明 `UNAVAILABLE + reason` |
| OCR | 置信度字段缺失 | 证据缺失 | 声明 `PARTIAL/UNAVAILABLE`，规则自动降级 |
| MarkItDown | 行尾空白 | 适配器输出 | 适配器归一化 或 白名单修复 `QL-RPR-001` |

判据：**“是工具输出格式/内容问题”→ 适配器修；“是证据缺失”→ 声明能力；“是统一规则判定问题”→ 质量层改规则/配置。**

### Step 2：能归一化的，先进适配器（第一优先级）
在 `infra/parsers/{parser}/` 的适配器里把自家输出洗成统一结构，复用：
- `domain/normalization/bundle.py` 的 `stable_uuid` / `make_stable_document_id`（确定性 ID）；
- `infra/parsers/base.py::BaseParserAdapter.normalize()`（统一入口）。

示例骨架（伪代码）：

```python
# infra/parsers/mineru/mineru.py
class MinerUParser(BaseParserAdapter):
    def normalize(self, request, signals):
        # 1. 调 MinerU 拿到原始结果
        # 2. 在这里修 MinerU 专属问题：表格列对齐、块排序、去重复 ID
        # 3. 产出统一的 ParsedDocument（blocks/tables/assets/capabilities）
        # 4. 对缺失证据如实声明：
        #    capabilities["page_bbox"] = EvidenceCapability(
        #        state=EvidenceAvailability.UNAVAILABLE,
        #        reason="MinerU 该模型版本未输出页面 bbox",
        #    )
```

### Step 3：修不了的，如实声明能力（不要伪造）
非 `available` 的能力必须带 `reason`（契约里已强制校验），例如：

```python
capabilities["ocr_confidence"] = EvidenceCapability(
    state=EvidenceAvailability.PARTIAL,
    reason="OCR 仅对图片页输出置信度",
)
```

质量层会自动：该规则受限执行（最高状态被压到 `manual_review_required` 以下）或跳过并输出 `unavailable`。

### Step 4：需要差异化判定的，改规则声明或配置
- 规则原来要求 `table_cells` 必须 `available` → 改成 `EvidenceRequirement(kind="table_cells", required_state="partial_allowed")`，让“部分可用”也能执行但限制最高状态；
- 阈值类差异（如“bbox 覆盖率低于多少算不可靠”）→ 放 `QualityConfig`，规则里 `context` 读取配置，不要硬编码数字。

### Step 5：新增规则的标准模板
```python
# domain/quality/rules/your_rule.py
from ..evidence.requirements import EvidenceRequirement, EvidenceKind
from ..models_internal import RuleResult
from .base import QualityRule


class QL_XXX_001_YourRule(QualityRule):
    rule_id = "QL-XXX-001"          # 稳定 ID，进入 golden 后不可改名
    required_evidence = (
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed",
                            scope="table", purpose="校验表格列结构"),
    )

    def execute(self, context) -> RuleResult:
        # 只读 context（EvidenceContext），产出 RuleResult
        # 禁止：写文件 / 调解析器 / 指定最终 Gate / 修改文档
        ...
```

然后：
1. 在 `pipeline.py` 的规则清单里注册；
2. `tests/quality/unit/` 加单测（给定构造好的 ParsedDocument → 断言 RuleResult）；
3. `tests/quality/integration/` 加集成（整条 `run_pipeline` 输出断言）；
4. 有 golden 文件的，同步更新并跑一致性测试。

### Step 6：跑测试
```powershell
.\.venv\Scripts\python.exe -m pytest tests\quality -q          # 质量层
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider   # 全量回归
.\.venv\Scripts\python.exe scripts\check_dependencies.py       # 校验依赖方向
```

### Step 7：更新文档
- 改了契约 → `docs/` 与 `specs/` 同步（尤其 `docs/architecture-ddd.md` 的映射表、质量输入需求矩阵）；
- 新增/变更规则 → 记录规则 ID、依赖证据、判定语义。

---

## 6. 质量层开发的“红线”（spec 强约束）

| 禁止 | 原因 |
| --- | --- |
| 规则直接改文档 / 写文件 | 规则只产观测（RuleResult），状态判定归 Gate |
| 规则调用解析器 / 路由器 / LLM | 破坏单向依赖，domain 不能感知 infra |
| 规则里硬编码 `parser_id` 分支 | 让领域感知具体工具，违背 DDD |
| 伪造证据（假 bbox / 假置信度 / 假单元格） | 能力矩阵会把这些当“可信”，导致假 pass |
| 修复时猜 OCR / 补数字 / 改写句子 | 白名单修复只做可证明等价的变换 |
| `rule_id` 改名 | 破坏 golden 一致性与修复可回放 |
| 绕过 `run_pipeline` 直接构造 QualityPackage | 绕过证据→规则→门禁的语义链 |

---

## 7. 常见反模式自查清单

- [ ] 我在 `domain/quality` 里写了 `import infra`？→ 违规，逻辑应放适配器或用端口。
- [ ] 我写了 `if document.provenance.parser_id == "mineru"`？→ 改用证据/配置。
- [ ] 我把某个解析器的阈值写死在规则里？→ 放 `QualityConfig`。
- [ ] 我为了让规则“跑得通”而把缺失证据标成 available？→ 必须如实声明。
- [ ] 我新增了规则但没加测试、没注册进 pipeline？→ 补上。
- [ ] 我改了 `ParsedDocument` 契约但没同步 Adapter、API、示例和测试？→ 项目只维护当前唯一契约，必须一次改全。

---

## 8. 术语表（DDD → 本项目）

| 术语 | 本项目对应物 |
| --- | --- |
| 领域层 domain | `domain/`（模型、路由、归一化、质量、端口） |
| 应用层 app | `app/use_cases.py`、`app/orchestration.py`、`app/bootstrap.py` |
| 基础设施层 infra | `infra/`（解析器适配器、存储、转换、打包） |
| 端口 Port | `domain/ports.py`（`ParserPort` / `ConverterPort` / `StoragePort` / `EventPublisherPort`） |
| 适配器 Adapter | `infra/parsers/*`、`infra/storage/api_storage.py`、`infra/converter.py` |
| 防腐层（归一化） | `domain/normalization/` + 各适配器 `normalize()` |
| 子域 / 限界上下文 | `domain/quality`（质量子域） |
| 组合根 | `app/bootstrap.py`（唯一 new 具体实现的地方） |
| 依赖注入 | 组合根把 infra 实现注入端口，app 面向端口编程 |

---

## 9. 最小上手路径（如果只有半天）

1. 跑一遍全量测试，看质量层测试覆盖了哪些行为（30 分钟）；
2. 用 `tests/quality/fixtures` 里的一个 ParsedDocument 手动跑 `run_pipeline`，观察报告字段（30 分钟）；
3. 从你最熟的解析器（如 MinerU）挑一个真实问题，按 Step 2→3 落地一个最小改动（2 小时）；
4. 跑 `pytest tests\quality` + `check_dependencies.py`，把改动和结论同步给我 review。

---

> 记住：**归一化是适配器的责任，判定是质量层的责任，解耦靠的是“证据声明”而不是“解析器名字”。** 这样无论以后接入多少种解析工具，质量层规则都不需要跟着改。
