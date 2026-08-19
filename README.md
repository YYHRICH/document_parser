# Document Parser

> 当前主线：`main`
> 质量修复工作分支：`feature/quality-layer`
> 当前方向：单文档质量修复 Agent

本仓库负责把上游解析结果转换成可审计、可复核、可供 LLMwiki 使用的文档产物。

质量层不是只列问题的规则检查器，而是一个受约束的单文档质量修复 Agent：LLM 主动理解文档并修复格式/结构，确定性工具负责验证内容、来源和结构不变量，最终输出可直接使用区域和人工复核区域。

单文档质量修复 Agent 以 **Agno** 作为正式 Agent 主运行时；既有确定性质量能力的规则、Gate、revision、canonical 和 packaging 都作为 Agent 工具与安全服务使用。

## 质量修复 Agent 的边界

上游负责：

- 选择 Docling、MinerU、OCR 或其他解析器；
- 将解析器结果统一成文档包；
- 多文档并行、队列、重试和任务编排。

本分支负责：

- 接收一个文档包；
- 主动检查未知的格式和结构问题；
- 通过 LLM 迭代生成修复后的文档；
- 验证修复没有改变事实内容；
- 生成 canonical 结构和审核结果。

```text
单个解析器输出
  → Adapter（当前临时，未来接上游统一层）
  → Quality Repair Agent
  → optimized.md
  → canonical_document.json
  → quality_report.json
  → package_manifest.json
```

质量 Agent 不负责比较多个解析器，也不负责再次调用解析器。

## 输入与适配

正式输入将是上游统一文档包。统一层尚未完成时，开发期通过 Adapter 接收当前不同解析器的输出：

```text
MinerU JSON ─┐
Docling JSON ├→ DocumentPackageView → Quality Repair Agent
fallback JSON┘
```

Agent 只依赖统一质量视图，不依赖解析器私有对象。视图至少包含：

- blocks、顺序、类型、文本和 Markdown；
- headings、tables、cells、span 和关系；
- assets、page、bbox 和 source locator；
- 稳定 ID、parser provenance 和能力信息；
- 原始/当前 revision 和质量问题上下文。

上游统一输出完成后，只替换 Adapter，Agent 和验证器不需要重写。

## Agent 工作循环

```text
加载单个文档包
  → 读取摘要、目录和局部上下文
  → LLM 主动发现格式/结构问题
  → 输出结构化修复候选
  → Schema、内容和来源校验
  → 重建 canonical 和审核结果
  → 规则/Gate 复检
  → 通过则提交
  → 不通过则反馈给 LLM 继续修复
  → 无改善、超预算或无法安全解释则人工复核
```

坏情况不要求提前穷举；合格状态必须能够验证。LLM 可以改变格式和结构，但不能修改正文事实、数字、单位、公式、代码、URL、页码、bbox 或来源 ID。

## 三个业务输出

### `optimized.md`

修复后的 Markdown，供 LLMwiki 检索、展示和后续开发使用。

### `canonical_document.json`

带结构绑定的 JSON，包括：

- 稳定 block；
- 标题父子关系；
- 表格网格、合并单元格、column path 和 row key；
- 跨页续表关系；
- 引用、图片、图注和脚注关系；
- 页码、bbox、来源定位和 provenance。

### `quality_report.json`

审核文件，逐文档、逐 block/table/reference/asset 给出：

```text
auto_usable
manual_review_required
rejected
```

它会说明：

- 哪些区域可以直接使用；
- 哪些区域必须人工复核；
- 哪些修复已经执行；
- 哪些验证通过或失败；
- 还剩哪些风险及其证据。

`package_manifest.json` 记录前三个核心文件的 SHA-256，主要用于完整性校验。

## 现有确定性基础

既有确定性质量能力 已经提供 Agent 所需的基础设施：

- EvidenceContext 和公共证据访问；
- 完整性、来源、标题、引用和表格规则；
- capability matrix 和 Gate 五态；
- 可回放的确定性修复；
- canonical document builder；
- 稳定序列化、manifest、原子写入和篡改检测。

这些规则不需要列举所有文档坏情况，主要负责定义合格状态、保护事实内容和验收 Agent 的修复结果。

## 当前进展

| 能力模块 | 状态 | 内容 |
| --- | --- | --- |
| 基础质量能力 | 已完成 | 契约、规则、Gate、canonical、确定性修复 |
| 质量产物与原子落盘 | 已完成 | 三个业务文件、manifest、原子写入和篡改检测 |
| 单文档质量修复 Agent | 第一阶段完成，持续开发 | Agno Agent、Skills、Tools、页面模式、结构化 Patch、关系/资源 Patch、候选验证和审核输出 |
| 上游统一文档包联调与交付 | 待办 | 接入上游正式统一文档包和多文档联调 |

当前测试基线：`260 passed, 1 xfailed`。

## 代码入口

```python
from quality import run_quality

# 确定性检查路径：不调用 LLM
package = run_quality(parsed_document)
```

单文档 Agent 入口为：

```python
from quality import run_quality_repair
from quality.agent import build_deepseek_model, build_quality_repair_agent

# 入口层创建唯一 toolbox，并把它交给同一份 Agent session
model = build_deepseek_model()
package = run_quality_repair(
    document_package,
    config=config,
    agent_factory=lambda toolbox: build_quality_repair_agent(model, toolbox),
)
```

生产调用如果需要区分 Provider、超时、Schema、Validator 和 no-progress 终态，使用
兼容新增的 detailed 入口；`session_id` 同时写入执行结果和 QualityReport 指标：

```python
from quality import run_quality_repair_detailed
from quality.agent import RepairAgentConfig

execution = run_quality_repair_detailed(
    document_package,
    config=config,
    agent_config=RepairAgentConfig(session_id="upstream-job-id"),
    agent_factory=lambda toolbox: build_quality_repair_agent(model, toolbox),
)
package = execution.package
print(execution.session_id, execution.accepted, execution.attempts)
```

上游统一文档包可以通过同一个稳定入口加载。加载器会读取包内的
`parsed_document.json`，按需注入 `assets/` sidecar，并校验资源引用、路径、大小和
SHA-256；质量层不会直接读取解析器私有对象：

```python
from document_parser import load_document_package

parsed_document = load_document_package("document_package")
```

超大文档可显式启用页面模式；runtime 会先构建全篇索引，再逐页发出进度事件：

```python
from quality.agent import RepairAgentConfig

paged_config = RepairAgentConfig(
    mode="paged",
    progress_callback=lambda event: print(
        event.completed_pages, "/", event.total_pages, event.status
    ),
)
package = run_quality_repair(
    document_package,
    config=config,
    agent_config=paged_config,
    agent_factory=lambda toolbox: build_quality_repair_agent(model, toolbox),
)
```


MCP 可以作为工具传输层，但核心 Agent、验证器和事务逻辑不依赖 MCP 运行时。多文档并行由上游分别调用这个单文档入口。

## 开发命令

首次准备开发环境时安装 dev extra；生产按需选择 Agent、MarkItDown 或 Docling extra：

```powershell
.venv\Scripts\python.exe -m pip install --editable ".[dev]"
.venv\Scripts\python.exe -m pip install ".[agent,markitdown]"
.venv\Scripts\python.exe -m pip install ".[docling]"
```

测试命令：

```powershell
python -m pytest tests/test_contract_examples.py -q
python -m pytest tests/quality/unit -q
python -m pytest tests/quality/contract -q
python -m pytest tests/quality/integration -q
python -m pytest tests/quality/golden -q
```

## 目录约定

```text
quality/
├─ agent/          # 单文档 Agent、上下文、DeepSeek 配置和 fake client
│  ├─ skills/      # 业务质量修复 playbook
│  └─ tools/       # 读取、页面上下文、验证和质量工具
├─ rules/          # 已知不变量与确定性检查
├─ repairs/        # 可回放的确定性修复能力
├─ gates/          # capability 和最终 Gate
├─ builders/       # Markdown/canonical/review 构建
└─ packaging/      # 序列化、manifest 和原子落盘
```

## 安全边界

- LLM 不能调用任意 Python、Shell 或文件系统写入；
- 修复前后必须保持事实内容和来源定位；
- 验证失败时保留原 revision 并回滚；
- `auto_usable` 必须有验证证据，不能只相信 LLM 的 confidence；
- 无法安全判断的区域必须进入人工复核；
- 规则、LLM 和上游解析器的职责不能混在一起。

详细约定见：

- [质量修复 Agent Spec](specs/001-quality-layer-implementation/spec.md)
- [Agno Agent 详细设计](specs/001-quality-layer-implementation/agno-agent-design.md)
- [当前质量优化 Agent 设计](docs/quality-agent-design.md)
- [质量层进展](docs/quality-layer-progress.md)
- [质量输入需求](docs/quality_input_requirements.md)
- [质量契约决策](docs/quality-decisions.md)
- [三方协作分工](docs/开发分工.md)
- [公共契约模型](core/contracts.py)
