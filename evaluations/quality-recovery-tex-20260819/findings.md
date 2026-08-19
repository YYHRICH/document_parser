# TeX 双解析器真实 Agent 评测结论

> 本文件记录 P0 优化前的首次基线；优化后的真实重测见
> [comparison-p0.md](comparison-p0.md)，首次原始结果保存在 quality-before-p0/。

评测日期：2026-08-19  
评测链路：TeX → XeLaTeX PDF → MinerU Cloud v4 / Docling 2.120.2 → DeepSeek/Agno 质量恢复 Agent

## 总结

- 6 份解析结果中，Agent 返回 `accepted` 3 份，但只有 1 份产生实际变更；另外 2 份是安全 no-op。
- 唯一实际修复发生在 `trace-structure/docling`：6 个标题 block 的层级被恢复，质量状态从
  `manual_review_required` 变为 `pass`。首轮因 `affected_ids` 与实际改动不一致被拒，第二轮通过。
- 另外 3 份因真实模型输出不能转换为约定 JSON schema 而进入 `agent_error`。失败时均保留原
  revision，没有提交半成品。
- 六份样本的 TRACE 标记与关键事实召回均未因 Agent 处理下降；Agent 没有猜测补写解析器已丢失的事实。
- 因此，本轮“有效恢复率”是 1/6，“无事实退化率”是 6/6，“模型结构化输出失败率”是 3/6。

## 分样本结果

| 文档 | 解析器 | 结果 | 实际效果 | 风险/观察 |
| --- | --- | --- | --- | --- |
| trace-structure | MinerU | accepted no-op | 保留原结果 | 公式内容仍在，但 LaTeX 空格导致精确字符串指标偏低；标题层级问题未修复 |
| trace-structure | Docling | accepted, changed | 6 个标题层级被调整，状态变为 pass | 货币值被拆开、URL 被 HTML 转义、公式未解码；Agent 按设计没有补写这些事实 |
| trace-tables | MinerU | agent_error | 原 revision 保留 | 合并表头保留得较好，但质量层报告网格冲突/空单元格；相同 issue_id 重复出现 |
| trace-tables | Docling | rejected → agent_error | 原 revision 保留 | 首轮尝试修改 table-001，但 affected_ids 不匹配；跨页表被拆成两个表对象 |
| trace-layout | MinerU | agent_error | 原 revision 保留 | 双栏标题分离较好，但脚注正文 TRACE-L-FOOT-121 丢失，图、校验和与流程文本粘连 |
| trace-layout | Docling | accepted no-op | 保留原结果 | 脚注和全部事实仍在，但左右栏标题被合并为一个标题，质量门仍要求人工复核 |

## 解析器比较

1. 结构/公式样本中 MinerU 的事实保真优于 Docling；Docling 将预算数值拆成独立段，并输出
   `<!-- formula-not-decoded -->`。
2. 双栏样本中 Docling 的内容完整性优于 MinerU，但阅读结构较差；MinerU 丢失脚注正文，Docling
   则把左右栏两个标题合并。
3. 表格样本中两者都保留了 40 行 TRACE 标记。MinerU 保留 HTML `rowspan/colspan`，Docling 输出
   普通 Markdown 表；两者都把 PDF 中区分负号与范围连接号的 `−20–70 C` 扁平化成 `-20-70 C`。
4. 自动“事实召回”采用保守字符串匹配，LaTeX 数学空格、HTML 实体和拆段会被记为缺失；因此它适合
   做回归告警，不应单独当作语义正确率。

## Agent 行为评价

安全边界表现合格：候选不满足 `affected_ids` 契约时会拒绝，schema 解析失败时不会写入坏 revision，
no-op 也不会创建自引用 revision。实际修复能力仍不稳定，当前主要瓶颈是模型结构化输出，而不是提交层。

最值得优先处理的改进：

1. 为 Agno 输出增加更强的 JSON 提取/修复与一次仅针对 schema 的重试；当前 50% 样本在这里失败。
2. 在 prompt 中提供最小合法 Candidate 示例，并明确 `affected_ids` 必须与 operation 实际改变的 ID 集合完全一致。
3. 将 Agent 变更显式写入质量报告的 repair 审计字段；本轮实际改了 6 个 block，但 `repair_count` 仍为 0，
   只能结合 `execution.json` 与 `markdown.diff` 才能看全。
4. 对 issue 列表按 `issue_id` 去重；MinerU 表格报告中两个相同 issue 各出现两次。
5. 增加符号等价层与跨 block 事实匹配，分别报告“字符级保真”和“语义存在”，避免把公式空格或预算拆段误报为全文丢失。

## 可追溯证据

- `manifest.json`：TeX、PDF、基线文本 SHA-256 与 PDF 层召回。
- `parses/<document>/<parser>/`：解析 Markdown、ParsedDocument、parser_summary；MinerU 目录还保留云端原始 ZIP/JSON。
- `quality/<document>/<parser>/execution.json`：真实 Agent 会话、attempt、拒绝原因、revision 与 fingerprint。
- `quality/<document>/<parser>/markdown.diff`：解析结果与优化结果的实际差异。
- `quality/<document>/<parser>/` 四件套：optimized Markdown、canonical document、quality report、package manifest。
