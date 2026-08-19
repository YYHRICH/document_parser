# Document Parser

> 当前分支：`feature/parser-integration-web`
> 负责人：朱（parse-integration）
> 核心目标：真实接入 Docling、MinerU、OCR，统一输出 `ParsedDocument 2.2`，完成后端、
> Web 和从路由到质量结果的工程串联。

## 本分支工作卡：解析集成、前后端与完整串联

### 开始开发前必须阅读

1. `docs/开发分工.md` 中“朱（parse-integration）：统一接入、解耦与完整串联”和三次联调；
2. `docs/朱-parse-integration-契约基线.md` 中第一阶段契约边界和缺失证据策略；
3. `docs/unified-document-package-requirements.md` 中统一文档包、侧车资源和交付前校验要求；
4. `specs/001-document-parser-collaboration/spec.md` 中现有基线、共享开发文件集、统一接入、
   Web、交付形式和 Gate B/C/D；
5. `examples/contracts/README.md` 中三份接口及文件产物约定；
6. `examples/contracts/routing_decision.json`、`parsed_document.json`、
   `quality_package.json`；
7. `core/contracts.py` 中全部公共 Pydantic 模型；
8. `core/gateway.py`、`core/converter.py` 和 `parsers/markitdown/`，理解必须保留的现有
   调用方式和回归能力。

### 朱（parse-integration）负责的接口位置

你同时是两个接口的消费者和生产者：

```text
RoutingDecision 1.0（张输出）
  -> Adapter / Normalizer / Artifact Archive
  -> ParsedDocument 2.2（你输出）
  -> QualityPackage 1.0（叶输出）
  -> Backend / Web / Download / Reparse（你消费并展示）
```

不得要求前端或叶直接读取 Docling、MinerU、OCR 的私有返回对象。

### 本分支必须完成

- 为 Docling、MinerU、OCR 实现统一 Adapter；保留 MarkItDown 和旧 Office 转换回归；
- Adapter 接收统一请求和 parser options，输出受控的原生结果或明确错误；
- 为三类模型实现 Normalizer，生成合法 `ParsedDocument 2.2`；
- 归档原生 JSON、Markdown、图片、表格、OCR 和日志，通过 `NativeArtifact` 暴露安全
  相对路径、类型、大小和 SHA-256；
- 将张的 `RoutingDecision` 接入 Gateway，记录建议模型、实际模型和 fallback 历史；
- 向叶提供真实 page、bbox、block ID、order、heading level、table cells/span、OCR spans
  和能力缺失原因；
- 实现独立后端 API，支持上传、自动/手动模型、任务状态、结果、下载和重新解析；
- 实现 MVP Web，但前端只通过 HTTP/JSON 调用后端；
- 提供单 Adapter、纯后端、CLI 和完整 Web 四类入口，核心逻辑不得复制；
- 使用共享 12 文件开发集生成逐文件执行记录和端到端结果。

建议代码位置：

```text
core/
parsers/docling/
parsers/mineru/
parsers/ocr/
normalizers/
backend/
frontend/
tests/contracts/
tests/adapters/
tests/api/
tests/e2e/
```

### `ParsedDocument` 给叶的最低证据

| 质量目标 | 必须尽量提供 | 缺失时必须做什么 |
|---|---|---|
| 表格绑定 | HTML/Markdown、cells、row/col span、表头、page/bbox、截图 | 在 `capabilities` 写明粒度和原因 |
| 标题恢复 | source block ID、order、heading level、原文、page/bbox | 不确定字段为空，不伪造层级 |
| 引用绑定 | 正文 block、reference block、编号/标识、顺序和来源 | 保存原文，不猜测目标 |
| 图片/OCR | asset、OCR spans、confidence、bbox、旋转和页面信息 | 未运行 OCR 时明确 unavailable |
| 可追溯性 | 输入哈希、解析器/模型版本、参数、耗时、原生产物哈希 | 任一缺失均写 warning/capability |

`routing_decision.selected_parser_id` 是计划模型，`provenance.parser_id` 是实际成功模型；
发生 fallback 时允许不同，但必须记录每次尝试。

### 和张、叶的联调点

- 从张获得稳定解析器 ID、options 和 fallback 规则；Adapter 注册 ID 必须完全一致；
- 向张反馈真实可用性、支持格式、版本和参数限制，不能让路由选择未接入模型；
- 与叶共同确认每项质量规则需要的字段和原生文件；
- 使用 `parsed_document.json` 让叶提前开发，使用 `quality_package.json` 提前开发 Web；
- 接收到 `reparse_required` 后创建新任务或版本，不静默覆盖旧结果。

### 不属于本分支

- 不独立决定哪个模型“最好”，路由策略由张负责；
- 不替叶输出质量结论或凭空补表头、数字、bbox、引用关系；
- 不把第三方对象、大型二进制或本机绝对临时路径直接放进公共 JSON；
- 不为 Web 复制另一套解析代码；
- 不单独改变公共契约字段语义。

### 提交前验收清单

- [ ] Docling、MinerU、OCR 均可通过同一 Adapter 接口独立调用；
- [ ] 三类结果均通过 `ParsedDocument 2.2` 校验；
- [ ] 表格、标题、引用、OCR 所需证据真实保留或明确声明缺失；
- [ ] MarkItDown 和旧 Office 转换回归没有破坏；
- [ ] 后端不启动前端也能测试，前端不导入算法模块；
- [ ] Web/CLI/后端复用同一 Gateway；
- [ ] 下载包包含路由、统一结果、native、质量四件套和 task 信息；
- [ ] 重新解析产生新任务/版本；
- [ ] 共享文件集的成功、失败、跳过和不可用记录完整。

当前公共契约回归命令：

```powershell
venv\Scripts\python.exe -m pytest tests/test_contract_examples.py -q
```

统一文档包打包示例：

```powershell
venv\Scripts\python.exe scripts\build_document_package.py examples\contracts\parsed_document.json outputs\document_package --native-dir native_input --source complex-paper.pdf
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
- 朱（parse-integration）：三类 Adapter、统一输出、后端、Web 和端到端串联；
- 质量负责人：表格字段绑定、标题树恢复、引用绑定、质量门和四件套。

MarkItDown 是需要保留的现有基线，不等于 Docling、MinerU、OCR 已经接入。

## 协作文档

- [三人开发分工](docs/开发分工.md)
- [朱 parse-integration 契约基线](docs/朱-parse-integration-契约基线.md)
- [统一文档包实施指南](docs/unified-document-package-requirements.md)
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
├─ normalizers/          # 解析器原始输出 -> ParsedDocument 的中间层
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
