# Document Parser

> 当前主线：main
> 质量层工作分支：feature/quality-layer
> 共享开发基线：datasets/shared-dev-v1
> 核心目标：仅基于 ParsedDocument 2.2 的真实证据完成表格字段绑定、标题树、引用关系、
> 质量准入和四件套，稳定输出 QualityPackage 1.0。

## 质量层工作卡（feature/quality-layer）

### 开始开发前必须阅读

1. `docs/开发分工.md` 中“叶：质量优化与准入”和三次联调；
2. `specs/001-document-parser-collaboration/spec.md` 中质量能力下限、共享开发文件集、
   质量需求、Gate B/C/D；
3. `examples/contracts/README.md` 中 `ParsedDocument 2.2`、`QualityPackage 1.0`、关系状态和
   四件套约定；
4. `examples/contracts/parsed_document.json` 和 `quality_package.json`；
5. `core/contracts.py` 中 `ParsedTable`、`TableCell`、`CanonicalDocument`、
   `TableFieldBinding`、`CanonicalRelation`、`QualityReport` 和 `QualityPackage`。

### 你的输入和输出

唯一公共输入：

```text
ParsedDocument 2.2
```

质量代码不得直接依赖 Docling、MinerU、OCR 或 MarkItDown 的私有对象。需要补充证据时，
通过公共契约需求反馈给朱。

公共输出：

```text
QualityPackage 1.0
├─ optimized_markdown
├─ canonical_document
│  ├─ blocks
│  ├─ table_bindings
│  └─ relations
├─ quality_report
└─ package_manifest
```

需要落盘的四件套：

```text
optimized.md
canonical_document.json
quality_report.json
package_manifest.json
```

### 本分支必须完成

- 建立质量输入需求矩阵：每条规则需要哪些 block、page、bbox、table、OCR、asset 或
  native artifact；
- 恢复有证据的表格网格、row/col span 和多级表头；
- 为证据充分的表格生成 `TableFieldBinding`，包含稳定 binding ID、row key、完整
  column path、原始 value、source locator、状态和证据；
- 根据 heading level、order 和来源恢复可确认的标题父子关系，输出
  `relation_type = "parent_child"`；
- 根据明确编号或标识绑定正文引用与参考文献，输出
  `relation_type = "reference_of"`；
- 实现 issue、白名单 repair log、capability matrix、gate summary 和五种质量状态；
- 需要更换模型时输出 `ReparseRecommendation`，但不自行调用模型；
- 输出带 SHA-256 绑定的四件套；
- 从共享 12 文件开发集中选择至少 4 个 Golden 样例，维护人工期望和安全降级反例；
- 为确定正例、歧义反例、no-op、人工复核、重解析和拒绝场景编写测试。

建议代码位置：

```text
quality/
quality/rules/
quality/repairs/
quality/gates/
tests/quality/
tests/fixtures/parsed_documents/
datasets/shared-dev-v1/annotations/quality/
datasets/shared-dev-v1/expected/golden/
```

### MVP 三项核心质量能力

#### 1. 表格字段绑定

至少有一个确定样例生成正确 binding，并有一个结构不唯一样例进入安全降级。来源只有
表级 bbox 时保留表级来源，禁止伪造 cell bbox；合并表头必须保留完整 `column_path`。

#### 2. 标题树恢复

使用稳定 block ID 建立 `parent_child`。只有层级、顺序和来源证据一致时才能标记
`verified`；不确定标题进入 `inferred`、人工复核或重新解析，不能强行升级。

#### 3. 引用绑定

正文编号与参考文献标识明确对应时建立 `reference_of`。目标不唯一、编号缺失或只有语义
猜测时不得标记 `verified`。

### 质量状态和安全门

允许状态：

```text
pass
pass_with_warnings
manual_review_required
reparse_required
rejected
```

- `reparse_required` 必须包含建议解析器、原因和建议参数；
- `critical_false_pass = true` 时禁止 `pass` 或 `pass_with_warnings`；
- 安全 no-op 是合法结果，不能为了显示“有优化”而修改原文；
- 不允许凭空创建数字、公式、表头、标题、bbox、图片描述或来源关系。

### 和张、朱的联调点

- 向朱提交明确的输入需求矩阵和缺失证据 issue，不直接读取解析器私有文件结构；
- 使用固定 `parsed_document.json` 先开发，不等待三类真实 Adapter；
- 给朱稳定的 `QualityPackage`，便于后端/Web 提前展示和下载；
- 将 `ReparseRecommendation` 交给张，由张决定新的可执行路由；
- 和张共同确认图片/OCR Golden 的质量标签与低质量判定；
- 所有结果使用共享 manifest 的 `sample_id` 和输入 SHA-256 对齐。

### 不属于本分支

- 不执行自动/手动模型路由；
- 不直接调用 Docling、MinerU 或 OCR；
- 不开发 Adapter、后端或 Web；
- 不用 LLM 无证据自由改写解析事实；
- 不单独修改公共契约字段语义。

### 提交前验收清单

- [ ] 表格正例能够产生可回溯字段绑定，反例不会错误绑定；
- [ ] 标题正例能够建立父子关系，不确定标题安全降级；
- [ ] 编号引用正例能够建立 `reference_of`，歧义引用不假装确定；
- [ ] 五种质量状态都有测试；
- [ ] 所有 repair 都有规则 ID、影响 block 和可回放证据；
- [ ] 四件套齐全且 manifest 哈希合法；
- [ ] `reparse_required` 一定带建议，严重错误不会误放行；
- [ ] Golden 子集至少 4 个，并同时包含确定正例和降级反例；
- [ ] 质量层仅依赖公共 `ParsedDocument`。

当前公共契约回归命令：

```powershell
python -m pytest tests/test_contract_examples.py -q
```

---

## 项目公共说明

`document_parser` 是三人协作开发的统一文档解析模块。本仓库直接基于现有 Python
代码扩展，不另起一套不兼容实现。

## 共享开发文件集

datasets/shared-dev-v1 是三人共同使用的 12 文件开发基线，已合并到 main。

- manifest.jsonl 是文件身份、SHA-256、split 和解析目标的唯一事实源；
- Smoke：sdp-001、sdp-004、sdp-007、sdp-008；
- Golden：sdp-004、sdp-005、sdp-006、sdp-007；
- PDF/图片源文件位于 datasets/shared-dev-v1/sources/tex/，DOCX 回归样例由确定性 Open XML 构建；
- 新增、删除或替换样例必须同步更新 manifest、标注、Spec，并通过 PR。

## 当前状态

已经具备：

- MarkItDown 解析基线；
- `.doc -> .docx`、`.ppt -> .pptx` 旧 Office 转换；
- `DocumentParserGateway` 统一入口；
- `RoutingDecision 1.0`、`ParsedDocument 2.2`、`QualityPackage 1.0` 公共契约；
- 三份可直接用于联调和 Mock 的固定 JSON 样例；
- 契约、跨阶段衔接和错误约束测试；
- shared-dev-v1 12 文件数据集、manifest、标注和可复现源。

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
- [质量层开发进展](docs/quality-layer-progress.md)（M0~M4 已完成，当前 167 测试通过）
- [质量层实现规格](specs/001-quality-layer-implementation/spec.md)
- [质量层契约决策记录](docs/quality-decisions.md)

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
├─ datasets/shared-dev-v1/ # 共享开发文件集、manifest 和标注
├─ specs/                # 完整产品和工程规格
├─ requirements.txt      # 项目运行与测试依赖
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
