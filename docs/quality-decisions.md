# 质量层契约决策记录

> 状态：已确认（2026-08-17 会议）
> 范围：feature/quality-layer 开发前置决策，来源 QUALITY_LAYER_IMPLEMENTATION_SPEC.md §2
> 规则：本文件为质量层实现决策的唯一记录；新增决策需在此登记后再实施。

## 已确认决策

| ID | 主题 | 决策 | 备注 |
| --- | --- | --- | --- |
| D-01 | sdp-004 两份 column_path 标注冲突 | **以采购版为准**：`annotations/quality/golden.jsonl` 为人工事实源，`expected/golden/quality_expectations.jsonl` 由其生成，加 CI 一致性测试防漂移 | 采购字段版本与文件名 procurement_table_positive.pdf 一致；待数据负责人最终确认 |
| D-02 | sdp-005 `expected_state: mixed`（Gate 无此枚举） | 最终 Gate 统一为 **manual_review_required** | 内部 binding 状态可 mixed；将来有合法重解析映射时可升 reparse_required |
| D-03 | 能力不适用（如无表格文档）的表达 | **内部处理，不改契约**：内部计算 applicability，不适用能力输出 `unavailable` + evidence 说明 not applicable，**不阻塞准入** | 公共契约暂不加 `not_applicable` 枚举 |
| D-04 | `quality_report.artifacts` 是否含自身哈希 | **不含**：artifacts 只放其他产物哈希（input/optimized.md/canonical）；自身哈希只进 manifest；禁止递归自哈希 | 哈希顺序见 SPEC §10.3 |
| D-05 | LLM 调用统计是否进公共报告 | **不进公共报告**：suggestion 计数只进内部日志和测试结果 | 将来需要展示再走三人评审加字段 |
| D-06 | `reparse_recommendation.parser_id` 合法值 | 开发期**用真实可用的 parser ID（docling/mineru，自跑验证可用性）**；无合法 ID 时不构造伪推荐，保持人工复核并记录配置缺口 | 正式 parser catalog 以张提供为准（M7 联调） |
| D-07 | canonical block content 策略 | **默认保留输入 markdown 原文**，只有白名单修复才产生变化 | 未确认的格式优化全部 no-op |
| D-08 | 未修复 info issue 与 Gate | **info 不阻塞**：仅 warning 及以上未修复才触发 pass_with_warnings | 产品展示约定变化时调整，需 Gate 配置显式固定 |
| D-09 | TableCell 无唯一 ID | **坐标组合身份**：`(table_id, start_row, start_col)` 为临时稳定身份，列入向朱确认清单 | 朱提供 cell_id 后直接替换，不改外部逻辑 |
| D-10 | LLM 辅助开发阶段 | **MVP-A 纯规则先行，MVP-B 加可关闭 LLM advisor** | LLM 不作为 golden 正例通过的必要条件 |
| D-11 | 实现规格文档去向 | **提交进仓库**：`QUALITY_LAYER_IMPLEMENTATION_SPEC.md` 移至 `specs/` 下提交 | 作为实施规格供团队评审 |
| D-12 | 开发 fixtures 来源 | **真实解析 + 合成**：MinerU/Docling 真实解析 sdp-004~007 生成 ParsedDocument fixtures 为主，合成 fixtures 补异常场景（no-op/reparse/rejected） | 不干等朱；真实 fixtures 到位后替换数据层 |

## 待确认（需要其他成员）

| ID | 主题 | 等待谁 | 当前处理 |
| --- | --- | --- | --- |
| D-13 | TableCell 是否增加 cell_id 字段 | 朱 | 用 D-09 临时方案，不阻塞 |
| D-14 | parser catalog 与 reparse options 映射 | 张 | 无合法 ID 时不出 reparse_required |
| D-15 | info 是否阻塞（产品展示约定） | 三人 | 按 D-08 执行，变更需评审 |
