# Document Parser

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
