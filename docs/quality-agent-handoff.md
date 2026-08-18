# 文档质量优化 Agent 交接说明

> 当前分支：`feature/quality-layer`  
> 当前远端基线：以 `origin/feature/quality-layer` 最新提交为准  
> 最近验证：`225 passed, 1 xfailed`  
> 适用范围：单文档质量修复 Agent 第一阶段

## 1. 这部分代码负责什么

质量层接收上游解析器转换后的 `ParsedDocument`，由 Agno 驱动的单文档 Agent 判断结构和格式问题，输出结构化修复候选。Agent 不直接写文件；候选必须经过本地 Validator、revision 事务和质量流水线，最后生成 `QualityPackage`。

质量层不负责：

- 选择多个解析器或比较多个解析器结果；
- 多文档并行、队列、任务重试和跨文档关系；
- 补写原文没有的文字、数字、公式、图片或参考文献。

上游统一文档包完成后，主要替换 Adapter，Agent、Tools、Validator 和产物协议保持不变。

## 2. 代码地图

```text
quality/agent/
├─ runtime.py              # Agent 轮次、页面模式、进度事件、终态
├─ agno_adapter.py         # Agno Agent 和结构化输出适配
├─ context.py              # 有界上下文和页面上下文
├─ index.py                # 全文 DocumentIndex / PageIndex
├─ prompts.py              # Prompt 模板和版本
├─ models.py               # Candidate、RepairOperation、RelationPatch
├─ revision.py             # revision 存储和 Patch 物化
├─ validator.py             # 事实、来源、scope 和 Patch 安全校验
├─ skills/                 # 业务判断 playbook，不直接修改文档
└─ tools/
   ├─ document_read.py     # 文档、页面、邻页、表格、资源只读工具
   └─ quality_toolbox.py   # 验证、差异、质量重跑和宿主事务服务
```

兼容入口 `quality/agent/toolbox.py` 只做旧导入路径转发，新的内部代码应优先从 `quality.agent.tools` 导入。

## 3. 常用入口

整篇文档模式：

```python
from quality import run_quality_repair
from quality.agent import build_deepseek_model, build_quality_repair_agent

model = build_deepseek_model()
package = run_quality_repair(
    parsed_document,
    agent_factory=lambda toolbox: build_quality_repair_agent(model, toolbox),
)
```

超大文档页面模式：

```python
from quality.agent import RepairAgentConfig

agent_config = RepairAgentConfig(
    mode="paged",
    progress_callback=lambda event: print(
        event.completed_pages, "/", event.total_pages, event.status
    ),
)
```

默认模式是 `document`，保持现有调用兼容；需要按页显示进度时显式设置 `mode="paged"`。

## 4. 当前 Patch 操作

`RepairedDocumentCandidate.operations` 当前支持：

| 操作 | 用途 | 关键限制 |
| --- | --- | --- |
| `update_block_markdown` | 标题、段落、Markdown 边界 | 事实词元必须保持 |
| `move_block` | 阅读顺序、跨页 block 顺序 | 只能移动已有 block |
| `update_heading_level` | 恢复标题层级 | 只能改层级，不改标题文字 |
| `remove_block` | 删除确定的完全重复 block | Validator 要求重复指纹证据 |
| `replace_table_cells` | 表格网格、span、表头角色 | 不能改 cell 事实文本 |
| `upsert_relation` | 建立已有 block/asset 之间的关系 | 端点必须存在，关系不唯一时人工复核 |
| `remove_relation` | 删除已有错误关系 | 以 tombstone 覆盖规则重新推导结果 |
| `update_asset_references` | 调整资源与已有 block 的归属 | 只改 `referenced_by_block_ids`，不改资源内容/路径 |

关系 Patch 会进入 `DocumentRevision.relation_overrides`，并在 canonical 构建时投影到 `CanonicalDocument.relations`。资源归属 Patch 同时保留在 `ParsedDocument.assets` 的结构字段中。

## 5. 安全边界

必须保持不变：

- 可见事实文本、数字、单位、日期、公式、代码、URL、引用条目；
- 稳定 ID、页码、bbox、source locator 和 provenance；
- 输入中不存在的对象、关系和事实。

Agent 只拥有读取、差异和候选验证工具。`commit_revision`、`rollback_revision` 和最终打包由 runtime 在本地控制。Validator 不通过时，原 revision 保留。

## 6. 换机开发

新机器执行：

```powershell
git clone https://github.com/YYHRICH/document_parser.git
git fetch origin
git switch --track origin/feature/quality-layer
cd document_parser
py -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果已经 clone 仓库：

```powershell
git fetch origin
git switch feature/quality-layer
git pull --ff-only
```

`.env` 不入库，需要自行配置 `LLM_API_KEY`、`LLM_API_BASE` 和 `LLM_MODEL`。不要把密钥写入代码、测试或提交记录。

## 7. 验证命令

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip check
```

当前基线为 `225 passed, 1 xfailed`；唯一 xfail 是已登记的 golden 标注冲突，不是运行环境故障。

## 8. 下一步建议

1. 接入上游正式统一文档包 Adapter；
2. 用真实 DeepSeek 跑百页级文档，记录耗时、token、费用和失败率；
3. 增加缓存、断点恢复和长文档分区合并；
4. 扩充真实文档评测集和人工复核产物；
5. 再考虑 MCP 工具传输和多文档上游调度，不要把这些职责塞回单文档 Agent。

详细设计见：

- [质量 Agent 设计](quality-agent-design.md)
- [实现 Spec](../specs/001-quality-layer-implementation/spec.md)
- [Agno Agent 设计](../specs/001-quality-layer-implementation/agno-agent-design.md)
- [质量层进展](quality-layer-progress.md)
- [质量决策记录](quality-decisions.md)
