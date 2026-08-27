# 质量层独立调试

质量层只读取 `ParsedDocument 2.2`，输出 `QualityPackage 1.0`。它不调用路由、解析器、后端、前端、Agent 或 LLM；与项目其他部分唯一共享的是 `core/contracts.py` 的公开契约。

在仓库根目录使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m quality --input tests\quality\fixtures\parsed_documents\sdp-004-mineru.json
```

完整输出 QualityPackage：

```powershell
.\.venv\Scripts\python.exe -m quality --input tests\quality\fixtures\parsed_documents\sdp-004-mineru.json --json
```

查看修复提案、策略、执行、复检及表格决策：

```powershell
.\.venv\Scripts\python.exe -m quality --input tests\quality\fixtures\parsed_documents\sdp-001-mineru.json --show-repairs
```

需要落盘时指定一个新目录；已有目录默认拒绝覆盖，只有显式指定 `--replace-existing` 才允许替换。

```powershell
.\.venv\Scripts\python.exe -m quality --input tests\quality\fixtures\parsed_documents\sdp-004-mineru.json --output-dir .\outputs\quality-debug
```

## 修复执行模型

质量层不会回写原始 `ParsedDocument`。它先构建只读表示清单，再创建内部工作文档：

```text
RepresentationInventory
  → RepairProposal（目标、前置 SHA-256、证据）
  → RepairPolicy（auto_safe / review_required / forbidden）
  → RepairExecutor（精确目标执行）
  → RepairVerifier（重跑规则必须 no-op）
  → 工作文档 → 规则 / Gate / canonical / QualityPackage
```

每条 `applied_repair` 都记录目标、前后哈希、策略决定、证据引用和复检结果。内容哈希不匹配、策略不允许或复检失败时，修复不会进入工作文档。

## 表格 HTML 转 Markdown

`TableRepresentationResolver` 只依据 HTML、Markdown、cells 的真实表示选择策略，不按 `parser_id` 分支：

- 结构一致、无 `rowspan/colspan` 的 HTML 可自动转换；
- 已有且一致的无 span Markdown 可直接采用；
- 含 span 的 HTML 保留原始 HTML 与 cells，只生成有损候选并进入人工复核；
- 表示冲突、HTML 不完整或目标中出现多次时不会静默覆盖。

`QL-RPR-003` 已是解析器无关的 `table_html_to_markdown` 修复。实际修改的是明确的 document/block Markdown 工作目标；对应 `ParsedTable.html` 作为来源证据通过目标、哈希和引用记录保留。

`quality.contracts` 是质量层访问公共协议的唯一边界。不要在 `quality/` 复制或修改公开契约；需要协议升级时必须单独评审 `core/contracts.py`。