# 质量 Agent Review 缺陷与后续开发台账

> 状态：待团队评审与排期  
> 记录日期：2026-08-18  
> 当前分支：`feature/quality-layer`  
> 当前测试基线：`249 passed, 1 xfailed`  
> 范围：单文档质量修复 Agent、统一文档包、打包发布与工程可靠性

## 1. 使用规则

本台账将 review 结果分成三类：

- **已复现 Bug**：已经通过最小用例确认，修复前不建议扩大真实文档自动放行范围；
- **发布阻塞项**：源码模式可运行，但安装、部署或对外调用存在缺口；
- **后续工程项**：不是当前逻辑错误，但会影响批量运行、联调和生产维护。

状态建议使用：`open`、`deciding`、`in_progress`、`verified`、`closed`。
修复代码提交时，应在对应条目补充 PR/commit、测试和最终决策，不要只修改状态。

## 2. 总览

| ID | 类型 | 优先级 | 状态 | 主题 |
| --- | --- | --- | --- | --- |
| QA-BUG-001 | 已复现 Bug | P0 | verified | 事实指纹忽略日期分隔符、数学运算符等可见符号 |
| QA-BUG-002 | 已复现 Bug | P0 | verified | 根 Markdown 与 block Markdown 可产生不一致 |
| QA-BUG-003 | 已复现 Bug | P1 | verified | 整篇 no-op 候选仍会提交自引用 revision |
| QA-PKG-001 | 发布阻塞项 | P1 | verified | wheel 可能遗漏 Agent 子包、Skill Markdown 和依赖元数据 |
| QA-OBS-001 | 发布阻塞项 | P1 | verified | 公共修复入口丢弃每轮验证和模型错误详情 |
| QA-ENG-001 | 后续工程项 | P1 | open | Gateway 仍固定为 MarkItDown，尚无 Parser Adapter 注册表 |
| QA-ENG-002 | 后续工程项 | P1 | open | 长文档缺少 checkpoint、断点恢复和安全重试 |
| QA-ENG-003 | 后续工程项 | P2 | open | 文档包资源缺少大小限制并存在重复整文件读取 |
| QA-ENG-004 | 后续工程项 | P1 | open | 缺少 CI、wheel 安装测试和可选真实 LLM 评测入口 |
| QA-DATA-001 | 数据阻塞项 | P1 | open | 四个 golden 样本标注冲突仍以 xfail 登记 |

## 3. 已复现 Bug

### QA-BUG-001：事实指纹忽略可见符号变化

**状态**：`verified`（2026-08-18，本地完整测试通过）。

**原位置**：`quality/agent/validator.py` 的 `_TOKEN_RE` 与
`content_fingerprint()`。

**修复前行为**：Validator 只提取 URL、英文标识符、数字和连续中文，Markdown
标记与大量标点、运算符都会被忽略。

**已复现结果**：

```text
content_fingerprint("Date 2026-08-18")
== content_fingerprint("Date 2026/08/18")       # True

content_fingerprint("x = a+b")
== content_fingerprint("x = a-b")               # True
```

**影响**：候选可能在 Validator 通过的情况下改变日期表达、数学关系、货币符号、
比较符号或业务标点，违反“数字、日期、公式和事实内容不可修改”的安全边界。

**可选修法**：

1. 扩充 `_TOKEN_RE`，把常见标点和运算符加入指纹。改动小，但容易继续漏掉新符号；
2. 使用 Markdown AST 提取可见文本，要求修复前后可见文本逐字符一致，仅忽略明确的
   Markdown 结构标记和允许的空白变化；
3. 建立分层保护：URL、日期、数字单位、inline code、代码块、公式分别精确提取并比较，
   再对普通可见文本做规范化比较。

**建议方向**：采用方案 2 + 3；方案 1 只能作为临时止血。

**实施结果**：新增 `quality/agent/markdown_semantics.py`，使用
`markdown-it-py` 提取规范化可见文本，并分别保护代码、HTML、链接、图片和公式
扩展 token；正文 block 与表格单元格均改用版本化 `sem-v2` 指纹。新增日期、
运算符、比较符、货币、代码、URL、HTML、图片、公式和表格标点回归测试。

**验证结果**：`244 passed, 1 xfailed`；`pip check` 通过。

**验收标准**：

- 日期分隔符、正负号、比较符、货币符号、百分号和公式运算符变化必须被拒绝；
- 仅增加标题 `#`、列表标记、合法空行或表格分隔线时仍可通过；
- 增加参数化测试和属性测试，覆盖中英文、代码、URL、日期、单位与公式。

### QA-BUG-002：根 Markdown 与 block Markdown 不同步

**状态**：`verified`（2026-08-18，本地完整测试通过）。

**原位置**：`quality/agent/revision.py` 的
`materialize_revision_candidate()`。

**修复前行为**：`update_block_markdown` 只更新 `blocks[].markdown`；根
`ParsedDocument.markdown` 只有在候选提供 `repaired_markdown` 时才更新。

**已复现结果**：

```text
block-only update_block_markdown candidate accepted = True
materialized block changed                         = True
materialized root markdown unchanged               = True
```

**影响**：Agent 和 Validator 可以报告修复成功，但最终 `optimized.md` 仍保留旧内容；
后续索引读取根 Markdown 与结构化消费者读取 blocks 时会得到不同版本。

**可选修法**：

1. 暂时禁止 document scope 的 block-only 内容 Patch，要求同时提交
   `repaired_markdown`，并校验两者变化一致；
2. 由宿主根据 block 顺序和边界元数据确定性重建根 Markdown；
3. 为 block 增加根 Markdown span/segment 身份，Patch 只作用于 span，根文档和 block
   从同一 revision 投影生成。

**实施结果**：新增 `quality/agent/markdown_projection.py`，通过
`markdown-it-py Token.map` 将 block 精确内容映射到根 Markdown source span。
`update_block_markdown`、标题层级、移动和删除操作由宿主同步修改根 Markdown；
不能精确映射或不独占 source token 的操作 fail closed。根 Markdown 中未被 block
覆盖的间隙保持原样；冲突的 `repaired_markdown` 与 block operation 会被拒绝。
纯 `repaired_markdown` 只允许修改 Markdown token 之间的间隙。

32 份现有 parsed-document 夹具共 1272 个 blocks，当前可建立 1016 个精确内容
span（79.9%），其中 715 个独占完整 source token（56.2%）；其余 block 不做模糊
回写，自动候选会被拒绝并转人工。

**兼容决策**：解析器产生“重复 blocks、根 Markdown 只有一份”时，删除未映射的完全
重复副本只修改 blocks；宿主会在删除后重新投影，确认剩余副本仍由根 Markdown 表示。

**验证结果**：`249 passed, 1 xfailed`；`pip check` 与
`git diff --check` 通过。

**验收标准**：

- 任意 accepted candidate 生成后，根 Markdown 与 block 投影一致；
- block-only Patch 不得静默产生两个内容版本；
- `optimized.md` 必须真实包含已接受的格式修复；
- 增加根/块双向一致性测试和连续两次修复的幂等测试。

### QA-BUG-003：整篇 no-op 会提交自引用 revision

**状态**：`verified`（2026-08-19，本地完整测试通过）。

**原位置**：`quality/agent/runtime.py` 的 `_run_document_repair()`；页面模式已有不同处理。

**原行为**：document 模式只判断 `validation.accepted` 就执行 commit，没有在 commit 前
判断 `validation.no_progress`。

**已复现结果**：

```text
no-op validation accepted          = True
no-op validation no_progress       = True
committed revision ID unchanged    = True
parent_revision_id == revision_id  = True
```

**影响**：revision 图出现自引用节点，审计、缓存、重放和未来持久化 checkpoint 都可能错误。

**实现结果**：document 模式已对齐 paged 模式：accepted + no_progress 视为正常完成，
但不调用 `commit_revision()`；保留原 revision ID，并在质量指标中记录
`stop_reason=no_progress`。`QualityToolbox.commit_revision()` 对直接 no-op 调用返回
`status=unchanged`，`InMemoryRevisionStore.commit()` 也会拒绝同 digest 提交，防止其他
调用路径重新形成自引用。

新增整篇运行时、工具箱直接提交和底层 store 三层回归测试，并保留分页 no-op 一致性测试。

**验证结果**：`252 passed, 1 xfailed`；`py_compile`、`pip check` 与
`git diff --check` 通过。

**验收标准**：

- no-op 不创建 revision；
- accepted no-op 仍可正常生成 QualityPackage；
- revision 不允许自身作为 parent；
- document 和 paged 模式行为一致。

## 4. 发布阻塞项

### QA-PKG-001：安装包元数据不完整

**状态**：`verified`（2026-08-19，wheel 构建和隔离 smoke 通过）。

**原位置**：`pyproject.toml`、`quality/agent/skills/catalog.py`。

**原问题**：当前 `tool.setuptools.packages` 显式列表未包含
`quality.agent.tools`、`quality.agent.skills`；Skill 文本以 `.md` 文件形式从安装目录读取，
但没有声明 package data。`[project]` 也没有 runtime dependencies。

**影响**：源码目录和 editable 安装中的测试可以通过，但正式 wheel 可能在导入 tools 或加载
Skill 时失败；直接 `pip install` 也不会自动安装运行依赖。

**实现结果**：

- 补齐 `quality.agent.tools`、`quality.agent.skills` 包，并声明 Skill Markdown package data；
- Skill 加载改用 `importlib.resources`，不依赖源码目录路径；
- 核心依赖迁入 `[project.dependencies]`，提供 `agent`、`markitdown`、`docling`、`dev` extras；
- 新增真实 wheel 构建、METADATA/文件清单检查和隔离目录公共入口 smoke test。

项目同时发布 `document_parser` 与顶级 `quality` 两个命名空间，继续保留显式包映射，
由 wheel 内容回归测试防止未来新增子包再次遗漏。

**验证结果**：wheel 包含 Tools、Skills 和全部 Markdown；从 wheel 隔离目录可导入公共模块、
加载 Skill 并运行最小 Agent 闭环。完整测试 `260 passed, 1 xfailed`。

**验收标准**：安装 wheel 后无需仓库源码路径即可导入所有公共模块、加载 Skill 并运行最小
Agent 测试。

### QA-OBS-001：公共入口丢失修复执行详情

**状态**：`verified`（2026-08-19，本地完整测试通过）。

**原位置**：`quality/api.py::run_quality_repair()`、`quality/agent/runtime.py::RepairExecution`。

**原问题**：runtime 已保存 `attempts` 和模型异常，但公共入口只返回
`run_repair(...).package`。调用方无法区分模型超时、Provider 错误、Schema 错误、Validator
拒绝或无进展停止。

**实现结果**：保留 `run_quality_repair() -> QualityPackage` 的兼容行为，新增
`run_quality_repair_detailed() -> RepairExecution`。执行结果包含每轮 `attempts`、最终 revision、
成功状态和可由上游注入或自动生成的 `session_id`；同一 session ID 也写入 QualityReport 指标。

模型侧错误划分为 `agent_timeout`、`provider_error`、`candidate_schema_error` 和
`agent_error`，Validator 自身故障单独标记为 `validator_error`；公共结果只保留异常类型，
不保留异常消息或 Provider 响应正文。Validator 拒绝、accepted no-progress 等状态继续通过
`CandidateValidation` 和稳定质量指标表达。

**验证结果**：兼容入口、detailed 入口、session 传播、四类错误中的超时/Provider/Schema/通用
Agent/Validator 分类及敏感异常消息脱敏均有回归测试；完整测试 `260 passed, 1 xfailed`。

**验收标准**：生产调用方能够明确判断失败发生在哪一层，并能关联同一次文档 session；日志不得
包含 API key、完整敏感正文或未脱敏 Provider 响应。

## 5. 后续工程与数据项

### QA-ENG-001：Parser Adapter 注册与联调

`core/gateway.py` 仍固定使用 MarkItDown。需要定义稳定 `ParserAdapter` 协议、注册表和路由连接，
接入 Docling、MinerU、OCR 与统一文档包。当前工作区新增的
`core/package_loader.py` 是统一包输入的第一步，但尚未提交，也尚未接入 Gateway。

### QA-ENG-002：长文档恢复与安全重试

当前已有 paged 模式，但没有跨进程 checkpoint、断点恢复、页面结果合并记录和缓存。模型层
`max_retries=0`，网络瞬断、429 或可恢复 5xx 会直接转人工。建议由宿主实现有限指数退避、
幂等请求键和页面级持久化，不把事务重试交给 LLM 自行决定。

### QA-ENG-003：文档包资源边界

`core/package_loader.py` 会将 sidecar 完整读入内存，并在验证阶段再次读取比较。需要增加包总大小、
单资源大小、资源数量和 JSON 大小限制；哈希改为流式计算。若未来支持百页扫描件，建议评审
`DocumentAsset.content: bytes` 是否继续作为强制内嵌字段。

### QA-ENG-004：CI 与真实 LLM 评测

当前没有仓库 CI 配置，也没有 wheel 安装、lint、类型检查和覆盖率门槛。真实 DeepSeek 已完成一次
人工 smoke test，但应增加可选的 `live_llm` 测试组：固定 fixture、固定预算、明确超时，记录候选
通过率、Validator 拒绝率、耗时、token 与费用；普通离线 CI 不依赖真实密钥。

### QA-DATA-001：golden 标注冲突

`sdp-004`～`sdp-007` 的四个冲突仍由 `KNOWN_CONFLICTS` 和 xfail 登记。需要数据负责人确认单一
事实源并重新生成 expected；解决后必须移除 xfail 和 D-16 临时登记。

## 6. 建议实施批次

### 批次 A：安全不变量

1. QA-BUG-001 事实保护；
2. QA-BUG-002 根/块一致性；
3. QA-BUG-003 no-op revision；
4. 对应回归、属性和对抗测试。

完成批次 A 前，真实 LLM 建议继续限制在评测或人工复核流程，不扩大自动放行范围。

### 批次 B：可安装与可诊断

1. QA-PKG-001 wheel 与依赖；
2. QA-OBS-001 detailed execution；
3. QA-ENG-004 CI 基线。

### 批次 C：联调和规模化

1. QA-ENG-001 Adapter 注册与路由；
2. QA-ENG-002 checkpoint、恢复和安全重试；
3. QA-ENG-003 大资源边界；
4. QA-DATA-001 golden 验收；
5. 百页真实文档评测。

## 7. 待团队决定

| 决策 | 选项 | 建议 |
| --- | --- | --- |
| 事实一致性主方案 | 扩正则 / AST 可见文本 / 分层保护 | AST + 分层保护 |
| 根与 block 的事实源 | 根 Markdown / blocks / span revision | 短期双向校验，长期 span revision |
| 公共 API 兼容方式 | 修改返回值 / 新增 detailed API | 新增 detailed API |
| Provider 重试位置 | Agno/OpenAI client / 宿主 runtime | 宿主 runtime |
| 资源传输 | 全内嵌 / sidecar 全加载 / 惰性资源句柄 | 当前兼容 sidecar，后续评审惰性句柄 |
