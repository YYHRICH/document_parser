# P0 优化前后真实 Agent 对比

本次重测使用与首次评测完全相同的 3 份 PDF、6 份 ParsedDocument、真实 DeepSeek/Agno 和两轮预算。
首次结果保存在 quality-before-p0/ 与 summary-before-p0.*。

## 结果

| 指标 | 优化前 | P0 优化后 |
| --- | ---: | ---: |
| Agent accepted | 3/6 | 6/6 |
| 第一轮直接 accepted | 2/6 | 6/6 |
| schema/agent_error | 3/6 | 0/6 |
| 实际产生结构/表格变更 | 1/6 | 4/6 |
| 事实召回下降 | 0/6 | 0/6 |

## 实际变化

- trace-structure/docling：标题层级修复，6 个 block 变化，质量状态保持为 pass。
- trace-tables/mineru：实际修改 table-001 的表格结构；根 Markdown 文本不变，但质量 issue 从 4 个降为 2 个。
- trace-tables/docling：3 个标题 block 变化，质量 issue 从 1 个降为 0 个。
- trace-layout/docling：4 个标题 block 变化，质量状态从 manual_review_required 变为 pass。
- trace-structure/mineru、trace-layout/mineru：安全 no-op，保留原 revision。

所有实际变更的 candidate_content_fingerprint 与 source fingerprint 一致；没有模型补写或修改事实文本。

## 仍需继续优化

Agno 日志仍会出现 Failed to parse cleaned JSON，但本轮内置候选提取最终成功，因此没有进入
agent_error。这说明结构化输出稳定性已从“失败即终止”改善为“可恢复”，但还可以继续减少模型输出中
重复 JSON/额外内容。

表格 MinerU 的 issue 仍有 2 个，主要是解析器生成的网格冲突和空单元格，下一步应实现表格增量
layout Patch，而不是让模型重写整张表。

## 代码验证

- 全量测试：265 passed，1 xfailed。
- 评测脚本的 changed 指标已修正为同时统计 Markdown、block、table、relation 和 asset 变化；
  表格 Patch 不再因根 Markdown 不变而被误报为 no-op。
