# 三方联调固定契约样例

这三个 JSON 文件是 MVP 联调的固定输入/输出基准，不是某个解析器的私有格式：

1. `routing_decision.json`：张云雅的路由层输出，朱的解析编排层输入。
2. `parsed_document.json`：朱统一适配 Docling、MinerU、OCR 后的输出，也是质量层输入。
3. `quality_package.json`：质量层输出，交给朱的 Web/API 层展示和下载。

联调链路固定为：

```text
ParseRequest -> RoutingDecision -> ParsedDocument -> QualityPackage
```

字段定义位于 `core/contracts.py`。样例由 `tests/test_contract_examples.py` 直接加载并校验；任何人修改接口时，都必须同步更新契约模型、固定样例和测试。

运行：

```powershell
python -m pytest tests/test_contract_examples.py -q
```
