# 从零开发一个 Quality 模块：DDD 工程内完整开发手册

> 适用对象：不熟悉 DDD、需要在 `document_parser` 工程里**重新开发一个质量（quality）模块**的开发者。
> 本文回答一个问题：**“我想重新做一个 quality，怎么在这个 DDD 工程里开发？”**
> 阅读前提：先看 `docs/quality-layer-ddd-dev-guide.md`（了解分层和数据流），再看本文（动手开发流程）。
> 本文写法：每一步给出**目录位置 + 代码模板 + 验收标准**，你可以照着抄。

---

## 0. 先建立正确认知：DDD 里“重新开发一个 quality”是什么

在 DDD 里，quality 是一个**子域（bounded context）**：它是 `domain/` 下的一个独立模块，有自己的输入、自己的判定逻辑、自己的输出。重新开发 quality = **新增一个子域**，有两种形态：

| 形态 | 做法 | 适用 |
| --- | --- | --- |
| A. 扩展现有子域 | 在 `domain/quality/` 里加规则、加配置 | 你只想增强现有质量层 |
| B. 全新子域（推荐给你） | 新建 `domain/quality_v2/`（名字随意），与旧 quality 并存或替换 | 你要**重新设计**质量逻辑，不想被旧实现束缚 |

本文按 **形态 B（全新子域）** 讲完整流程；形态 A 只是它的子集（跳过“新建目录”和“并存切换”两步）。

**核心承诺（DDD 给它的保障）**：你写的新 quality 只依赖 `domain/model` 和自己模块内部，不碰解析器、不碰存储、不碰框架；它可以被 HTTP/CLI/未来 MQ 复用；将来换实现只改 `infra`。

---

## 1. 动手前必须知道的 4 件事

### 1.1 分层依赖铁律（会被脚本强制检查）

`scripts/check_dependencies.py` 检查所有 `domain/app/api/trigger/infra` 文件的 import 方向，规则如下：

| 所在层 | 允许 import | 禁止 |
| --- | --- | --- |
| `domain` | 仅 `domain` | app / api / trigger / infra、第三方解析库、fastapi |
| `app` | app / domain / api | infra（除组合根 `app/bootstrap.py`） |
| `api` | api / domain | infra / trigger / app |
| `trigger` | trigger / app / api / domain | 直接碰解析器/存储 |
| `infra` | infra / domain | app / trigger / api |

例外：`app/bootstrap.py` 和 `trigger/http/app.py` 是**组合根**，允许感知任何层（只做装配）。

**所以你的新 quality 模块**：领域逻辑放 `domain/quality_v2/`（只 import domain 内部），打包落盘放 `infra/quality_v2_packaging/`，用例接线放 `app/`，对外契约放 `api/`，路由放 `trigger/`。

### 1.2 包发现规则（新目录为什么能直接被 import）

`pyproject.toml` 的包发现是：

```toml
[tool.setuptools.packages.find]
include = ["app*", "api*", "backend*", "domain*", "infra*", "quality*", "trigger*"]
```

- 你在 `domain/` 下新建 `quality_v2/`，因为匹配 `domain*`，**自动被发现**，前提是每层目录都有 `__init__.py`；
- 如果你新建**顶层**目录（如 `quality2/`），必须把 `"quality2*"` 加进 include 列表；
- 相对导入用 `..` 前缀，例如 `domain/quality_v2/pipeline.py` 里写 `from ..model.contracts import ParsedDocument`。

### 1.3 组合根负责“接线”

`app/bootstrap.py` 是唯一 new 具体实现的地方。你的新模块的**用例**要在这里被组装进 `ApplicationContainer`，trigger 层才能拿到。后面 Step 4 会给你代码。

### 1.4 测试目录规范

现有质量层测试分四类，新模块照抄：

```text
tests/quality_v2/
├── unit/        纯逻辑单测（规则/门禁/证据上下文）
├── integration/ 整条 pipeline 输出断言
├── contract/    契约不变量（gate 状态机、golden 一致性）
└── golden/      黄金文件（版本化快照）
```

---

## 2. 开发流程总览（8 步）

```text
Step 0 定契约      domain/model/           定义新质量模块的输入/输出模型
Step 1 写领域逻辑  domain/quality_v2/       证据 → 规则 → 门禁（纯业务，核心工作量）
Step 2 定义端口    domain/ports.py          新模块需要的外部能力（LLM/存储/…）
Step 3 实现基建    infra/quality_v2_packaging/  落盘、持久化、外部实现
Step 4 应用层      app/use_cases.py + bootstrap.py  包成用例并接线
Step 5 对外契约    api/dto.py               新响应/请求 DTO
Step 6 入口        trigger/http/routes.py   新增 API 路由（或 CLI）
Step 7 测试        tests/quality_v2/        unit + integration + contract
Step 8 验收        check_dependencies + pytest + 文档
```

> 顺序建议：**契约 → 领域 → 测试(单测) → 基建 → 用例 → API → 入口**。先让领域逻辑跑通单测，再接外层，错误最少。

---

## 3. 每一步的详细做法（含可抄代码）

### Step 0：定契约（`domain/model/`）

先定义你新 quality 的**输入和输出**。输入通常是统一的 `ParsedDocument`（契约已冻结，直接复用）；输出是你自己的包模型。放在 `domain/model/contracts.py`（追加）或新建 `domain/model/quality_v2.py`（推荐，避免改动大文件）。

```python
# domain/model/quality_v2.py
"""新质量子域 V2 的输出契约。"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class QualityV2Issue(BaseModel):
    rule_id: str
    severity: str                    # critical / warning / info
    message: str
    block_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class QualityV2Package(BaseModel):
    schema_name: str = "QualityV2Package"
    schema_version: str = "1.0"      # 契约变更必须升版本，不能原地改
    state: str                       # pass / reparse_required / rejected / ...
    issues: list[QualityV2Issue] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
```

验收：`pydantic` 能构造、序列化；`schema_version` 存在；字段有默认值，向后兼容。

### Step 1：写领域逻辑（`domain/quality_v2/`，核心工作量）

目录骨架：

```text
domain/quality_v2/
├── __init__.py      # 导出 run_quality_v2
├── pipeline.py      # 编排：Evidence → rules → gate
├── evidence.py      # 证据上下文（不可变视图，规则唯一数据源）
├── rules.py         # 规则协议 + 具体规则
├── gate.py          # 门禁（唯一最终状态判定者）
└── config.py        # QualityV2Config（阈值、开关）
```

`pipeline.py` 最小模板：

```python
# domain/quality_v2/pipeline.py
"""V2 质量流水线：EvidenceContext → rules → gate → QualityV2Package。"""
from __future__ import annotations

from ..model.contracts import ParsedDocument
from ..model.quality_v2 import QualityV2Package
from .config import QualityV2Config
from .evidence import EvidenceContextV2
from .gate import GateV2
from .rules import QUALITY_V2_RULES, QualityRuleV2


def run_quality_v2(
    parsed: ParsedDocument,
    *,
    config: QualityV2Config | None = None,
) -> QualityV2Package:
    config = config or QualityV2Config()
    context = EvidenceContextV2(parsed)          # 1. 建证据视图
    results = [rule.execute(context) for rule in QUALITY_V2_RULES]  # 2. 跑规则
    return GateV2(config).decide(results)        # 3. 门禁判定（唯一判定者）
```

规则模板（**红线：只读证据、产出结果、不碰外部**）：

```python
# domain/quality_v2/rules.py
"""规则协议与规则集。规则职责边界：只读 EvidenceContextV2，产出 RuleResultV2。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleResultV2:
    rule_id: str
    issues: list = field(default_factory=list)   # 结构参考 QualityV2Issue
    observations: dict = field(default_factory=dict)


class QualityRuleV2(ABC):
    rule_id: str = ""

    @abstractmethod
    def execute(self, context) -> RuleResultV2:
        """只读 context；禁止写文件、调解析器、指定最终状态。"""
        raise NotImplementedError


class QL_V2_001_BlocksExist(QualityRuleV2):
    rule_id = "QL-V2-001"

    def execute(self, context) -> RuleResultV2:
        if len(context.blocks) == 0:
            return RuleResultV2(self.rule_id, issues=[{
                "rule_id": self.rule_id,
                "severity": "critical",
                "message": "文档没有任何 block",
                "block_ids": [],
            }])
        return RuleResultV2(self.rule_id)


QUALITY_V2_RULES: tuple[type[QualityRuleV2], ...] = (QL_V2_001_BlocksExist,)
```

`gate.py` 模板（**最终状态判定只能在这**）：

```python
# domain/quality_v2/gate.py
"""V2 门禁：唯一能输出 state 的地方。"""
from .config import QualityV2Config


class GateV2:
    def __init__(self, config: QualityV2Config) -> None:
        self.config = config

    def decide(self, results) -> object:
        critical = [r for r in results if any(i["severity"] == "critical" for i in r.issues)]
        state = "rejected" if critical else "pass"
        return {"state": state, "issues": [i for r in results for i in r.issues],
                "summary": {"critical": len(critical)}}
```

验收：不 import `infra/app/api/trigger`；不 import fastapi；`from ..model.contracts import ParsedDocument` 是允许的唯一跨目录依赖；纯函数可单测。

### Step 2：定义端口（`domain/ports.py`）

如果新 quality 需要外部能力（LLM 建议、查外部数据库、调远程服务），在 `domain/ports.py` 追加 `Protocol`：

```python
# domain/ports.py（追加）
class QualityV2AdvisorPort(Protocol):
    """V2 质量模块可选的 LLM 顾问端口（不实现就不启用）。"""

    def suggest(self, evidence: dict[str, object]) -> list[dict[str, object]]:
        """返回建议观测；实现方放在 infra。"""
        ...
```

规则只依赖端口类型，不 import 实现。**没有外部依赖就跳过这步。**

### Step 3：实现基础设施（`infra/quality_v2_packaging/`）

落盘、调用外部服务的具体实现放 infra：

```text
infra/quality_v2_packaging/
├── __init__.py
└── writer.py      # 把 QualityV2Package 原子写入目录
```

```python
# infra/quality_v2_packaging/writer.py
"""V2 质量包落盘（infra 实现；domain 只定义包模型）。"""
from __future__ import annotations
import json
from pathlib import Path

from ...domain.model.quality_v2 import QualityV2Package


def write_quality_v2_package(package: QualityV2Package, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "quality_v2_package.json"
    target.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    return output_dir
```

验收：可以 import `domain`，禁止 import `app/trigger`；不写业务判定。

### Step 4：应用层接线（`app/`）

**4.1 用例**（`app/use_cases.py` 追加，或新建 `app/use_cases_v2.py`）：

```python
# app/use_cases_v2.py
"""V2 质量用例：HTTP/CLI 共用。"""
from __future__ import annotations

from ..domain.model.contracts import ParsedDocument
from ..domain.model.quality_v2 import QualityV2Package
from ..domain.quality_v2.pipeline import run_quality_v2


class RunQualityV2UseCase:
    def execute(self, document: ParsedDocument) -> QualityV2Package:
        return run_quality_v2(document)
```

**4.2 组合根**（`app/bootstrap.py`）：把用例加入容器，trigger 才能拿：

```python
# app/bootstrap.py（追加字段）
@dataclass(frozen=True)
class ApplicationContainer:
    parse_document: ParseDocumentUseCase
    reparse_document: ReparseDocumentUseCase
    run_quality: RunQualityUseCase
    run_quality_v2: RunQualityV2UseCase          # ← 新增
    storage: StoragePort
    parser: DocumentParsePipeline


def build_application(...) -> ApplicationContainer:
    ...
    return ApplicationContainer(
        parse_document=...,
        reparse_document=...,
        run_quality=run_quality,
        run_quality_v2=RunQualityV2UseCase(),    # ← 新增
        storage=resolved_storage,
        parser=resolved_parser,
    )
```

> 注意：改了 `ApplicationContainer` 后，凡是构造它的测试/入口都要同步。`app/__init__.py` 的 `__all__` 也要补 `RunQualityV2UseCase`。

### Step 5：对外契约（`api/dto.py` 追加）

```python
# api/dto.py（追加）
class QualityV2Response(BaseModel):
    parse_id: str
    package_path: str
    quality_v2_package: QualityV2Package
```

### Step 6：入口（`trigger/http/routes.py` 追加路由）

```python
# trigger/http/routes.py（在 build_router 内追加）
from ...api.dto import QualityV2Response
from ...domain.model.quality_v2 import QualityV2Package

@router.get("/api/parses/{parse_id}/quality-v2", response_model=QualityV2Response)
def get_quality_v2(parse_id: str) -> QualityV2Response:
    document = storage.load_document(parse_id)                       # 从库里读 ParsedDocument
    package = application.run_quality_v2.execute(document)          # 跑你的新质量
    path = application.storage.package_root(parse_id) / "quality_v2.json"
    path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    return QualityV2Response(parse_id=parse_id, package_path=str(path), quality_v2_package=package)
```

CLI 同理：在 `trigger/cli/main.py` 加一个 `--quality-v2` 分支，仍只调 `application.run_quality_v2`。

### Step 7：测试（`tests/quality_v2/`）

单测示例：

```python
# tests/quality_v2/unit/test_rules_blocks_exist.py
from document_parser.domain.model.contracts import ParsedDocument
from document_parser.domain.quality_v2.pipeline import run_quality_v2


def test_empty_document_is_rejected():
    package = run_quality_v2(ParsedDocument())     # 具体按 ParsedDocument 构造
    assert package.state == "rejected"
```

集成测试：造一个真实结构的 `ParsedDocument` fixture，跑 `run_quality_v2`，断言 issues/state；契约测试：gate 状态机不变量；golden：关键输出落 `tests/quality_v2/golden/`。

### Step 8：验收

```powershell
.\.venv\Scripts\python.exe scripts\check_dependencies.py    # 必须输出 "DDD dependency check: ok"
.\.venv\Scripts\python.exe -m pytest tests\quality_v2 -q    # 新模块单测
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider # 全量回归
```

---

## 4. 新模块怎么接入“既有解析链路”（三种方式，按需选）

| 方式 | 做法 | 场景 |
| --- | --- | --- |
| 独立接口（最干净，推荐先做） | 只加 `GET /api/parses/{id}/quality-v2`，不碰现有解析/质量流程 | 先验证新 quality 结果 |
| 并存切换 | 在 `QualityConfig` 加 `engine: "v1" | "v2"`，`RunQualityUseCase` 按配置分发 | 灰度对比新旧质量 |
| 接入主链路 | 扩展 `ParseDocumentUseCase._materialize` 或新增组合用例，解析后同时产出 v1 + v2 | 新质量转正后替换 v1 |

---

## 5. 验收清单（提交前逐项打勾）

- [ ] `scripts/check_dependencies.py` 输出 ok，无新增违规
- [ ] `domain/quality_v2/` 内没有 import `infra/app/api/trigger`、没有 import fastapi
- [ ] 没有 `if parser_id == "..."` 硬编码；没有伪造证据
- [ ] Gate（最终状态判定）只在你的门禁模块里，规则不输出最终 state
- [ ] 输出模型有 `schema_version`，字段有默认值
- [ ] `app/bootstrap.py` 已接线，`ApplicationContainer` 使用者同步更新
- [ ] 新增 API 有 DTO（`api/dto.py`）+ 路由（`trigger/http/routes.py`）
- [ ] `tests/quality_v2/` 有 unit + integration；跑通全量 pytest
- [ ] 文档更新：`docs/` 或 `specs/` 说明新模块的输入/输出/规则清单

---

## 6. FAQ

**Q：我想复用旧 quality 的规则/证据机制，行吗？**
行。把 `domain/quality/evidence` 的 `EvidenceContext` 机制复制到你的子域（或直接 import `domain.quality.evidence`，因为 domain 内部互相 import 是允许的）。机制比重写好。

**Q：我的新 quality 要调 LLM/外部服务，放哪？**
端口定义在 `domain/ports.py`（如 `QualityV2AdvisorPort`），实现放 `infra/`，由 `app/bootstrap.py` 注入。领域代码里只依赖端口类型。MVP 阶段可以留空实现，默认关闭（参考现有 `llm_enabled` 开关）。

**Q：我不想动 trigger 和 API，只想做内部模块？**
跳过 Step 5/6，把用例挂进 `app` 即可；测试照样写。

**Q：新 quality 的判定结果要进 `QualityPackage` 吗？**
不要直接改 `QualityPackage` 的结构（它是已冻结契约）。输出你自己的 `QualityV2Package`，通过 API 暴露；等决策后走正式版本升级（schema 2.x）再合并。

**Q：这个流程走完大概要多久？**
只做最小闭环（契约→1 条规则→gate→用例→接口→测试）半天到一天；规则量大的话，时间主要花在 Step 1 写规则和 Step 7 补测试。

---

## 7. 最小可抄的“快速启动”清单（照抄目录）

```text
domain/model/quality_v2.py             # 契约
domain/quality_v2/{__init__,pipeline,evidence,rules,gate,config}.py
infra/quality_v2_packaging/{__init__,writer}.py
app/use_cases_v2.py                    # RunQualityV2UseCase
app/bootstrap.py                       # 接线（改 ApplicationContainer）
api/dto.py                             # QualityV2Response
trigger/http/routes.py                 # /api/parses/{id}/quality-v2
tests/quality_v2/{unit,integration,contract,golden}/
```

按这个清单建目录、填模板、跑 `check_dependencies.py` + `pytest`，就是一个完整合规的 DDD 新质量子域。
