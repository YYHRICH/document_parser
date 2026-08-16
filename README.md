# Document Parser

> 当前分支：`feature/router-model-selection`
> 负责人：张
> 核心目标：完成 Docling、MinerU、OCR 的能力注册、自动/手动路由和 JPG/JPEG/PNG
> 能力测评，稳定输出 `RoutingDecision 1.0`。

## 本分支工作卡：模型选型与路由

### 开始开发前必须阅读

1. `docs/开发分工.md` 中“张：模型选型与路由”和三次联调；
2. `specs/001-document-parser-collaboration/spec.md` 中共享开发文件集、路由需求、
   Gate B/C；
3. `examples/contracts/README.md` 中 `RoutingDecision 1.0` 的字段和手动模式硬约束；
4. `examples/contracts/routing_decision.json` 固定输出样例；
5. `core/contracts.py` 中 `DocumentSignals`、`ParserCapability`、`RoutingDecision`、
   `ReparseRecommendation`。

### 你负责的输入和输出

输入：

- `ParseRequest` 中的文件信息、用户指定模型和 options；
- `DocumentSignals`：扩展名、大小、页数、文本层、扫描比例和语言提示；
- Docling、MinerU、OCR 的 `ParserCapability` 与当前可用状态；
- `datasets/shared-dev-v1/manifest.jsonl` 中同一批 `sample_id`、标签和文件哈希；
- 质量层可选的 `ReparseRecommendation`。

唯一公共输出：

```text
RoutingDecision 1.0
```

必须填写自动/手动模式、建议模型、选择原因、参数、fallback 顺序、是否允许 fallback、
不可用原因和创建时间。手动模式必须满足：

```text
requested_parser_id == selected_parser_id
allow_automatic_fallback == false
```

### 本分支必须完成

- 建立 Docling、MinerU、OCR 能力注册表，记录支持格式、版本、网络/GPU 前置条件和
  不可用原因；
- 实现自动路由，至少区分普通文本 PDF、复杂 PDF、扫描件、JPG/JPEG 和 PNG；
- 实现用户指定模型及参数校验，指定模型不可用时明确失败，不静默换模型；
- 实现显式 fallback 规则，并让朱能够记录每次失败；
- 支持接收 `ReparseRecommendation` 并生成新决策或明确拒绝原因；
- 使用共享 12 文件开发集完成 JPG/JPEG/PNG 能力调研和逐文件结果；
- 为自动、手动、不支持格式、模型不可用、fallback 和重解析建议编写测试。

建议代码位置：

```text
routing/
benchmarks/model_selection/
tests/routing/
tests/fixtures/images/
datasets/shared-dev-v1/annotations/routing.jsonl
```

### 和朱、叶的联调点

- 给朱：稳定的 `RoutingDecision`，解析器 ID 必须与 Adapter 注册 ID 完全一致；
- 向朱确认：每个候选模型是否已真实接入、支持哪些参数，禁止只路由到一个不存在的 ID；
- 给叶：每个共享样例的建议模型、实际可用模型和图片测评证据；
- 接收叶：`reparse_required` 中的建议解析器和参数；
- 使用 `routing_decision.json` 先联调，不等待真实 Adapter 或 Web 完成。

### 不属于本分支

- 不把 Docling、MinerU、OCR 的原生结果转换成 `ParsedDocument`；
- 不开发 Web 或后端任务编排；
- 不决定质量状态，不生成表格绑定、标题树或引用关系；
- 不用“返回非空”代替图片解析质量评价；
- 不修改公共字段含义。确需变更时，必须同步契约代码、固定样例、测试和接口说明，
  并由朱、叶共同确认。

### 提交前验收清单

- [ ] 自动和手动模式都覆盖 Docling、MinerU、OCR；
- [ ] JPG/JPEG/PNG 都有真实测评记录；
- [ ] 每次选择都有非空 reason；
- [ ] 手动模式不会静默 fallback；
- [ ] 所有 fallback 和不可用原因可追踪；
- [ ] 固定 `RoutingDecision` 样例和公共契约测试通过；
- [ ] 路由模块不依赖前端，也不直接产生质量结论；
- [ ] 批量结果中的成功、失败、跳过和不可用数量与输入总数一致。

当前公共契约回归命令：

```powershell
python -m pytest tests/test_contract_examples.py -q
```

---

## 项目公共说明

`document_parser` 是三人协作开发的统一文档解析模块。本仓库直接基于现有 Python
代码扩展，不另起一套不兼容实现。

## 当前状态

已经具备：

- MarkItDown 解析基线；
- `.doc -> .docx`、`.ppt -> .pptx` 旧 Office 转换；
- `DocumentParserGateway` 统一入口；
- `RoutingDecision 1.0`、`ParsedDocument 2.2`、`QualityPackage 1.0` 公共契约；
- 三份可直接用于联调和 Mock 的固定 JSON 样例；
- 契约、跨阶段衔接和错误约束测试。

MVP 尚需三人分别完成：

- 张云雅：Docling、MinerU、OCR 自动/手动路由和 JPG/JPEG/PNG 测评；
- 朱：三类 Adapter、统一输出、后端、Web 和端到端串联；
- 质量负责人：表格字段绑定、标题树恢复、引用绑定、质量门和四件套。

MarkItDown 是需要保留的现有基线，不等于 Docling、MinerU、OCR 已经接入。

## 协作文档

- [三人开发分工](docs/开发分工.md)
- [完整开发 Spec](specs/001-document-parser-collaboration/spec.md)
- [三方联调接口](examples/contracts/README.md)
- [契约模型代码](core/contracts.py)
- [固定样例测试](tests/test_contract_examples.py)

## MVP 链路

```text
Web/CLI
  -> ParseRequest
  -> RoutingDecision
  -> Docling / MinerU / OCR Adapter
  -> ParsedDocument
  -> 表格、标题、引用质量处理
  -> QualityPackage
  -> Web 展示、下载或重新解析
```

Web 是主要演示入口，但路由、单个 Adapter、质量层和纯后端必须能够独立运行和测试。

## 当前目录

```text
document_parser/
├─ __init__.py
├─ core/
│  ├─ contracts.py       # 公共 Pydantic 契约，唯一事实源
│  ├─ converter.py       # 旧 Office 格式转换
│  ├─ gateway.py         # 当前统一编排入口
│  └─ inspector.py       # 文件基础特征检查
├─ parsers/
│  └─ markitdown/        # 当前可运行解析基线
├─ docs/
│  └─ 开发分工.md
├─ examples/contracts/   # 三方固定接口样例
├─ specs/                # 完整产品和工程规格
└─ tests/                # 当前契约测试
```

后续按 Spec 增加：

```text
routing/
normalizers/
quality/
backend/
frontend/
benchmarks/
tests/routing/
tests/quality/
tests/api/
tests/e2e/
```

## 公共接口

业务模块只从顶层包导入稳定类型：

```python
from document_parser import (
    DocumentParserGateway,
    ParsedDocument,
    QualityPackage,
    RoutingDecision,
)
```

三人联调链固定为：

```text
ParseRequest -> RoutingDecision -> ParsedDocument -> QualityPackage
```

禁止下游模块直接依赖 Docling、MinerU、OCR 或 MarkItDown 的私有返回对象。

## 当前 Gateway 调用

```python
import mimetypes
from pathlib import Path

from document_parser import DocumentParserGateway

source = Path("document.pdf")
gateway = DocumentParserGateway.from_environment()
try:
    result = gateway.parse_file(
        source,
        file_type=mimetypes.guess_type(source.name)[0]
        or "application/octet-stream",
    )
finally:
    gateway.close()

print(result.markdown)
print(result.provenance.parser_id)
```

现阶段该入口使用 MarkItDown；路由和三类 MVP Adapter 接入后仍应保持这一公开调用方式
兼容。

## 契约验证

```powershell
python -m pytest tests/test_contract_examples.py -q
```

测试会直接加载：

- `examples/contracts/routing_decision.json`；
- `examples/contracts/parsed_document.json`；
- `examples/contracts/quality_package.json`。

修改公共字段时，必须同时更新 Pydantic 模型、固定样例、测试、接口说明和 Spec。

## 维护约束

- 当前仓库是唯一代码基线；
- 个人本地参考材料不进入 Git 仓库；
- 路由层决定调用哪个模型，不产生质量结论；
- Adapter 和统一层保存真实证据，不伪造缺失 bbox、表头或 OCR 置信度；
- 质量层只做有证据的修复和关系绑定；
- 前端只能通过后端 API 使用解析能力；
- 公共协议不兼容变更必须提升 Schema 版本并经三人共同评审。
