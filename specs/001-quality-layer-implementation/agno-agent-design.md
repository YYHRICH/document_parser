# 基于 Agno 的单文档质量修复 Agent 设计 Spec

> 状态：Draft v0.1
> 适用分支：`feature/quality-layer`
> 设计对象：单文档质量修复 Agent
> 选定框架：Agno
> 当前阶段：只定义设计，不搭建实现

## 1. 设计目标

本设计定义一个处理单个统一文档包的质量修复 Agent。Agent 接收上游解析结果经 Adapter 转换后的统一质量文档视图，主动发现格式和结构问题，生成修复后的文档候选，接受确定性验证器反馈并迭代，最终输出：

```text
optimized.md
canonical_document.json
quality_report.json
package_manifest.json
```

其中前三个是 LLMwiki 负责人和下游开发使用的业务文件，manifest 用于完整性校验。

### 1.1 核心判断

- 坏情况无法穷举，不把所有异常写成规则；
- 好状态可以枚举，由 Schema、内容不变量、来源约束、结构验证和 Gate 定义；
- LLM 负责主动检查、理解和修复；
- 确定性代码负责提供上下文、验证候选、生成产物、回滚和结束 Agent；
- LLM 的输出永远是不可信候选，不能直接作为最终事实；
- 多文档并行、队列和重试由上游负责，本 Agent 一次只处理一个文档。

### 1.2 非目标

- 不在 Agent 内选择或重新调用解析器；
- 不比较多个解析器结果；
- 不实现多 Agent、Team 或跨文档协作；
- 不允许 LLM 修改正文事实、数字、单位、日期、公式、代码、URL、页码、bbox 或原始 ID；
- 不允许 LLM 执行任意 Python、Shell、网络请求或文件系统操作；
- 不把 LLM 的自由文本直接当作 Markdown、canonical JSON 或审核结论。

## 2. 为什么选择 Agno

Agno 的 `Agent.run()` 能够完成模型请求、工具调用和工具结果回传的循环，并支持 Pydantic 结构化输出。它提供 session state 和数据库持久化，也支持暂停后继续运行以及 MCP 工具包装。

设计依据：

- [Agno Agents](https://docs.agno.com/agents/running-agents)：工具调用循环、结构化输出和暂停/继续；
- [Agno State Management](https://docs.agno.com/state/overview)：session state 与数据库持久化；
- [Agno MCP](https://docs.agno.com/demo-os/mcp)：将 MCP server 工具包装为 Agent 工具。

Agno 只负责 Agent 运行时，不负责判断文档修复是否正确。质量层自己的验证器、revision、回滚、canonical 构建和打包逻辑拥有最终权威。

### 2.1 选型边界

| 能力 | Agno 负责 | 质量层负责 |
| --- | --- | --- |
| LLM 请求与响应 | ✅ |  |
| 类型化工具调用 | ✅ |  |
| `RepairedDocumentCandidate` 输出 | ✅ 协助生成 | ✅ 最终校验 |
| 文档内容与 revision |  | ✅ |
| 内容不变量和来源校验 |  | ✅ |
| 规则、Gate 和审核状态 |  | ✅ |
| commit / rollback |  | ✅ |
| 多文档并行 |  | 上游负责 |
| MCP 连接 | 可选 | 工具协议由质量层定义 |

## 3. 总体架构

```text
上游解析器
  → 临时/正式 DocumentPackageAdapter
  → DocumentPackageView
  → QualityRepairSession
       ├── Agno Agent
       │    ├── document context tools
       │    ├── validation feedback
       │    └── structured candidate output
       ├── DocumentRevisionStore
       ├── Deterministic Validators
       ├── Existing Quality Rules / Gate
       ├── Canonical + Review Builders
       └── M5 Packaging
  → 三个业务文件 + package_manifest.json
```

### 3.1 适配层

当前上游统一输出尚未完成，开发期允许：

```text
MinerU / Docling / fallback / fixture
  → 各自 Adapter
  → DocumentPackageView
```

Agent、工具和验证器不得读取解析器私有对象。正式统一层完成后，增加一个正式 Adapter，Agent 代码不变。

`DocumentPackageView` 至少提供：

- 文档元数据和 `document_id`；
- 稳定 block、顺序、kind、text、markdown；
- heading level、parent/section 相关结构；
- table、cell、row/col/span、header role、caption；
- asset、page、bbox、source locator 和 provenance；
- 原始 Markdown、当前工作版本和内容指纹；
- capability、既有 issue 和 native artifact 引用。

### 3.2 组件职责

#### Agno Agent

- 阅读摘要、目录和局部上下文；
- 决定下一步读取什么；
- 主动识别规则未覆盖的格式问题；
- 生成整篇或局部 `RepairedDocumentCandidate`；
- 根据验证反馈继续修复或主动放弃。

#### 读取工具

- 提供文档内容和结构的只读视图；
- 支持分页、cursor、region ID 和表格完整上下文；
- 不修改 revision，不产生副作用。

#### 验证器

- 检查候选是否符合统一 Schema；
- 检查事实内容、数字、来源和 ID 不变量；
- 调用已有规则和 Gate；
- 生成机器可读反馈和审核结论。

#### Revision Store

- 保存原始 revision 和每轮候选；
- 记录输入/输出哈希、父 revision 和修复原因；
- 提供原子 commit 和 rollback；
- 不把完整文档塞入 Agno session state。

#### Builder / Packaging

- 从被接受的工作文档确定性构建 Markdown、canonical 和 review report；
- 使用 M5 的稳定序列化、manifest 和原子落盘。

## 4. Agno 运行模型

### 4.1 一个文档一个 session

每个文档对应一个独立 session：

```text
session_id = quality:{document_id}:{input_sha256}
```

上游并行处理多个文档时，每个 Agent 使用独立 session。Agent 实例可以共享只读模型配置，但不能共享当前文档、revision 或 mutable working state。

### 4.2 Agno 配置职责

概念配置如下：

```text
Agent
├── model: 由环境配置决定
├── tools: 质量层读取/验证工具
├── output_schema: RepairedDocumentCandidate
├── db: 开发期 SQLite，生产期可替换存储
├── session_id: 当前文档会话
└── instructions: 角色、边界、工具使用和结束条件
```

Agno 的 session state 只保存：

- 当前 `document_id` 和输入 digest；
- 当前 revision 编号；
- Agent 已检查的区域；
- 轮次、预算和最后一次验证摘要；
- repair history 的引用 ID。

完整文档、候选内容和 revision 快照存放在 `DocumentRevisionStore`，不直接存入 session state。

### 4.3 外层修复循环

Agno 负责一次 Agent run 内的工具调用；质量层负责跨轮次的修复循环：

```python
revision = store.open(input_document)
feedback = None

for attempt in range(config.max_rounds):
    context = context_builder.build(revision, feedback)
    result = agno_agent.run(context, session_id=session_id)
    candidate = result.content

    validation = validator.validate(revision, candidate)
    store.record_attempt(revision, candidate, validation)

    if validation.acceptable:
        revision = store.commit(candidate)
        break

    if validation.no_progress or budget.exhausted:
        store.rollback(revision)
        return manual_review(revision, validation)

    feedback = validation.feedback
else:
    return manual_review(revision, feedback)
```

Agno 不拥有最终的 `for` 循环结束权。超时、无改善、内容变化和预算耗尽由质量层强制结束。

## 5. Agent 状态机

```text
INIT
  → LOADED
  → SCANNING
  → CANDIDATE_READY
  → VALIDATING
  ├── COMMITTING → FINALIZED
  ├── RETRYING → SCANNING
  ├── MANUAL_REVIEW
  └── REJECTED
```

### 5.1 状态定义

| 状态 | 含义 |
| --- | --- |
| `INIT` | 创建 session，尚未读取文档 |
| `LOADED` | Adapter 和 revision 已建立 |
| `SCANNING` | Agent 正在读取摘要、区域或表格上下文 |
| `CANDIDATE_READY` | Agno 返回结构化修复候选 |
| `VALIDATING` | Schema、内容、来源和规则验证中 |
| `RETRYING` | 验证失败但仍有预算，准备反馈给 LLM |
| `COMMITTING` | 候选已通过，准备生成最终产物 |
| `FINALIZED` | 三件套和 manifest 已生成 |
| `MANUAL_REVIEW` | 无法安全自动完成，输出人工审核结果 |
| `REJECTED` | 输入或候选无法安全解释 |

### 5.2 状态转换约束

- `CANDIDATE_READY` 不能直接进入 `FINALIZED`；
- 必须经过 `VALIDATING`；
- 只有通过验证的 revision 才能 commit；
- `MANUAL_REVIEW` 和 `REJECTED` 不得生成 `auto_usable`；
- 每个 revision 只能提交一次；
- rollback 后不得继续使用已失效的 candidate。

## 6. LLM 输入和提示设计

### 6.1 系统角色

系统指令应明确：

- 你是单文档格式/结构修复 Agent；
- 当前文档包是唯一事实来源；
- 可以调整格式和结构，不得改变事实内容；
- 规则反馈是验收信息，不是全部问题清单；
- 不确定时保留原结构并标记人工复核；
- 只能通过提供的读取工具获取上下文；
- 最终只能返回 `RepairedDocumentCandidate`，不得返回 Markdown code fence 或任意代码。

### 6.2 上下文层级

大文档不一次性注入全文，采用：

1. 文档摘要、页数、目录和质量概况；
2. 当前待检查的章节或页面窗口；
3. 当前表格的完整 cell 网格和相邻页；
4. 前后 block、caption、脚注和关系上下文；
5. 上一轮 validator feedback；
6. 当前 revision 的局部 diff。

每个上下文块都带稳定 ID 和来源定位，避免 LLM 返回无法定位的修改。

### 6.3 检查覆盖记录

Agent session 记录：

```text
scanned_regions
checked_tables
checked_relations
unresolved_regions
```

它不是“所有问题已经发现”的证明，只用于避免同一轮重复读取和支持长文档进度展示。

## 7. 修复候选契约

### 7.1 候选结构

`RepairedDocumentCandidate` 是内部 Pydantic 模型，至少包含：

```text
schema_version
base_revision
scope
repaired_document 或 repaired_region
affected_ids
lineage
reasoning
evidence_refs
```

`scope` 允许：

```text
document
section
page_range
block_set
table
relation_set
```

### 7.2 整篇和局部候选

- 小文档或全局结构问题：允许返回整篇候选；
- 大文档或局部问题：优先返回 region candidate；
- region candidate 必须声明边界、受影响 ID 和合并关系；
- 质量层负责把 region candidate 合并到当前 revision；
- 合并冲突、缺少 lineage 或影响边界不明确时拒绝候选。

### 7.3 LLM 不负责生成最终三件套

LLM 可以返回修复后的统一文档结构，但最终文件由系统生成：

```text
accepted working document
  → optimized.md
  → canonical_document.json
  → quality_report.json
  → package_manifest.json
```

这样可以保证三个业务文件来自同一 revision，避免 LLM 分别生成三份互相矛盾的结果。

## 8. 工具协议

### 8.1 读取工具

| 工具 | 作用 | 副作用 |
| --- | --- | --- |
| `get_document_summary` | 返回页数、目录、统计、已有问题和修复进度 | 无 |
| `get_document_outline` | 返回标题、section、block 范围和 cursor | 无 |
| `get_region_context` | 读取指定 block/page/section 的局部内容 | 无 |
| `get_table_context` | 返回完整 table grid、cell、span、caption、相邻页 | 无 |
| `get_asset_context` | 读取 asset 元数据和已有来源定位 | 无 |
| `get_revision_digest` | 返回当前 revision 和局部内容指纹 | 无 |

### 8.2 验证工具

| 工具 | 作用 | 调用者 |
| --- | --- | --- |
| `validate_candidate` | 对候选执行 Schema、内容、来源和局部结构检查 | Agent/runtime |
| `rerun_quality_checks` | 执行全局规则、capability 和 Gate | runtime |
| `get_repair_diff` | 生成稳定的结构差异和内容差异 | Agent/runtime |

默认不把 commit、rollback 和 finalize 暴露给 LLM。它们由 runtime 根据验证结果调用，避免模型绕过质量门。

### 8.3 MCP 传输

核心工具实现为 Python 函数和协议，Agno 直接调用本地工具。需要外部 Agent 或独立服务访问时，用 Agno 的 MCP tool wrapper 暴露相同工具。

MCP 只能改变传输方式，不能改变：

- 工具参数 Schema；
- session 隔离；
- 内容不变量；
- revision 事务；
- 验证和回滚行为。

## 9. 验证和审核

### 9.1 验证顺序

1. Candidate Schema 合法；
2. `base_revision` 与当前 revision 匹配；
3. scope、ID、field path 和 lineage 存在；
4. 统一文档结构合法；
5. block/cell 文本、数字、公式、URL 未变化；
6. 原始 ID、source locator、page、bbox 粒度和 provenance 未被伪造；
7. table grid、span、heading tree、relation target 合法；
8. canonical builder 成功；
9. 确定性规则和 Gate 重跑；
10. review report 与 canonical/Markdown 对齐；
11. 通过后才允许 commit。

### 9.2 内容指纹

验证器至少维护两类指纹：

- `source_content_fingerprint`：按稳定 block/cell ID 记录可见文本和事实 token；
- `structure_fingerprint`：记录顺序、kind、heading、span、relation、locator 等结构。

格式修复允许 structure fingerprint 改变，但 source content fingerprint 只能在显式人工批准的未来能力中改变。M6 自动模式不允许改变 source content fingerprint。

### 9.3 审核结果

`quality_report.json` 同时包含：

```text
overall_decision
items[]
repair_history[]
validation_checks[]
human_review_queue[]
remaining_risks[]
```

对象级决定：

```text
auto_usable
manual_review_required
rejected
```

`auto_usable` 必须有验证项通过和证据引用；LLM 的 confidence/reasoning 只能用于解释，不能单独放行。

## 10. 修复预算、重试和缓存

### 10.1 配置项

```text
agent_enabled
max_rounds
max_model_calls
max_tool_calls_per_round
max_context_chars
max_total_tokens
per_call_timeout_ms
total_timeout_ms
no_progress_limit
cache_enabled
cache_ttl_seconds
```

### 10.2 无改善判定

以下任一情况视为无改善：

- validator blocker 集合没有减少；
- 新 revision 的内容指纹不变且没有结构问题减少；
- 同一个 candidate fingerprint 重复出现；
- 新增 blocker 数量超过减少的 blocker 数量且连续达到阈值。

无改善时可再给一次明确反馈；超过 `no_progress_limit` 后进入人工复核。

### 10.3 缓存

缓存 key：

```text
model_id
model_settings_hash
document_id
revision
context_hash
prompt_version
candidate_schema_version
```

缓存结果仍必须重新执行当前 evidence/content hash 验证。错误、超时和预算失败可以使用短 TTL 负缓存，避免同一轮重复调用。

## 11. 长文档策略

### 11.1 扫描方式

- 先生成文档级摘要和目录；
- 按章节或页范围读取；
- 表格必须以完整网格为上下文，不能只给几行；
- 跨页表格读取相邻页和两张表；
- 标题树修复读取祖先链和相邻标题；
- 局部修复后进行全局规则重跑；
- 未检查区域记录在 session state 中。

### 11.2 不把长文档塞进 session state

文档正文、图片、表格和候选 revision 存在外部 revision store。Agno session state 只存引用、进度和摘要。这样可以控制上下文大小，也便于回滚和并发隔离。

## 12. 失败和降级

| 情况 | 处理 |
| --- | --- |
| Agno/LLM 未配置 | 输出确定性审核结果，不调用 Agent |
| 模型超时 | 回滚当前候选，保留上一 revision |
| 输出 Schema 非法 | 给 Agent 一次格式反馈，仍非法则人工复核 |
| 内容指纹变化 | 立即拒绝候选并回滚 |
| ID/lineage 悬空 | 拒绝局部候选，不修改当前 revision |
| Validator 失败但有改善 | 反馈给 Agent，进入下一轮 |
| 连续无改善 | 停止并人工复核 |
| 超过预算 | 停止，输出剩余风险 |
| canonical/package 构建失败 | 回滚，不生成半成品 |
| 工具异常或 MCP 断开 | 使用本地工具重试或安全降级 |

降级不能伪造 `auto_usable`，也不能因为 LLM 不可用而把输入标成 `rejected`，除非输入本身违反契约。

## 13. 安全和权限

- Agent 工具按 session 绑定文档，禁止跨 session 读取或写入；
- 读取工具只读；候选提交只写临时 revision；commit 由 runtime 控制；
- 不允许路径穿越、任意 URL 下载、Shell、Python eval 或动态导入；
- 外部 MCP server 的工具清单必须显式配置，默认拒绝未知工具；
- 日志保存 model、prompt/schema version、tool calls、revision 和验证摘要，不默认保存完整敏感文档；
- 审核文件可记录简短 reasoning，但不把隐藏思维链写入公共产物；
- 所有最终产物由 M5 原子写入器提交。

## 14. 测试计划

### 14.1 单元测试

- Candidate Pydantic Schema；
- region merge 和 lineage；
- 内容/结构 fingerprint；
- revision commit/rollback；
- no-progress 计算；
- review report 汇总；
- 每个工具的输入边界和 session 隔离。

### 14.2 Fake Agent 测试

不调用真实模型，使用 Fake Agno model/Agent 输出：

- 主动发现规则未覆盖的排版问题并返回合法候选；
- 返回合法结构但改动数字，必须拒绝；
- 返回非法 span、悬空 relation、未知 ID，必须拒绝；
- 第一次失败、第二次修复成功；
- 连续返回同一候选，触发 no-progress；
- 超时、非法 JSON、工具异常、预算耗尽；
- 大文档按 region 读取而不是全文注入；
- final 三件套来自同一 revision。

### 14.3 集成测试

- 当前 MinerU/Docling/fallback fixtures 通过各自 Adapter 后运行同一 Agent；
- LLM 关闭时确定性路径结果稳定；
- Agent 修复后规则和 Gate 重新执行；
- manual review 区域和 auto usable 区域都能在 report 中定位；
- packaging manifest 能复算三个业务文件哈希；
- 多文档并发使用不同 session 时不存在状态串扰。

### 14.4 验收标准

M6 设计实现完成必须满足：

- 单文档 Agent 能运行完整的 inspect → candidate → validate → retry/commit loop；
- LLM 能处理规则未穷举的格式问题；
- 自动修复不改变 source content fingerprint；
- 验证失败不能被 LLM 绕过；
- 无改善和超预算能确定性停止；
- 人工复核区域有明确对象、原因和证据；
- 输出三件业务文件和 manifest，来自同一 accepted revision；
- LLM 关闭、超时、非法返回和 MCP 失败不会产生错误放行；
- 既有 M1-M5 回归测试不被破坏。

## 15. 实现顺序（仅设计，不代表当前已搭建）

1. 固定 `DocumentPackageView`、Adapter 和 revision store 接口；
2. 定义 Pydantic candidate、validation feedback 和 review report 模型；
3. 先用 Fake Agent 跑通外层状态机；
4. 接入 Agno 单 Agent、结构化输出和本地 Python 工具；
5. 接入内容/结构指纹、canonical、review 和 M5 packaging；
6. 加入长文档上下文、预算、缓存和 no-progress；
7. 最后提供 MCP wrapper 和上游统一层 Adapter；
8. 用真实解析器 fixtures 和 Golden 做回归。

在第 3 步完成前，不接真实 LLM；在第 5 步完成前，不允许 Agent 自动提交最终文件。
