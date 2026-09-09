# 质量层契约决策记录

> 状态：已确认（2026-08-17 会议）
> 范围：feature/quality-layer 开发前置决策，来源 QUALITY_LAYER_IMPLEMENTATION_SPEC.md §2
> 规则：本文件为质量层实现决策的唯一记录；新增决策需在此登记后再实施。

## 已确认决策

| ID | 主题 | 决策 | 备注 |
| --- | --- | --- | --- |
| D-01 | sdp-004 两份 column_path 标注冲突 | **以采购版为准**：`annotations/quality/golden.jsonl` 为人工事实源，`expected/golden/quality_expectations.jsonl` 由其生成，加 CI 一致性测试防漂移 | 采购字段版本与文件名 procurement_table_positive.pdf 一致；待数据负责人最终确认 |
| D-02 | sdp-005 `expected_state: mixed`（Gate 无此枚举） | 文档级 Gate 统一为 **pass_with_warnings**、**reparse_required** 或 **rejected**；问题和绑定允许单独标记 **manual_review_required** | 文档可以交付，但下游必须按问题状态过滤不确定绑定 |
| D-03 | 能力不适用（如无表格文档）的表达 | **内部处理，不改契约**：内部计算 applicability，不适用能力输出 `unavailable` + evidence 说明 not applicable，**不阻塞准入** | 公共契约暂不加 `not_applicable` 枚举 |
| D-04 | 质量结果是否保存产物哈希 | **不保存**：固定交付 `optimized.md`、`structure.json` 和 `quality_issues.json`；大表追加 `table_index.sqlite3` | JSON 不包含 manifest 或哈希 |
| D-06 | `reparse_recommendation.parser_id` 合法值 | 开发期**用真实可用的 parser ID（docling/mineru，自跑验证可用性）**；无合法 ID 时不构造伪推荐，直接 rejected | 正式 parser catalog 以张提供为准（M7 联调） |
| D-07 | canonical block content 策略 | **默认保留输入 markdown 原文**，只有白名单修复才产生变化 | 未确认的格式优化全部 no-op |
| D-08 | 未修复 info issue 与 Gate | **info 不阻塞**：仅 warning 及以上未修复才触发 pass_with_warnings | 产品展示约定变化时调整，需 Gate 配置显式固定 |
| D-09 | TableCell 无唯一 ID | **坐标组合身份**：`(table_id, start_row, start_col)` 为临时稳定身份，列入向朱确认清单 | 朱提供 cell_id 后直接替换，不改外部逻辑 |
| D-11 | 实现规格文档去向 | **提交进仓库**：`QUALITY_LAYER_IMPLEMENTATION_SPEC.md` 移至 `specs/` 下提交 | 作为实施规格供团队评审 |
| D-12 | 开发 fixtures 来源 | **真实解析 + 合成**：MinerU/Docling 真实解析 sdp-004~007 生成 ParsedDocument fixtures 为主，合成 fixtures 补异常场景（no-op/reparse/rejected） | 不干等朱；真实 fixtures 到位后替换数据层 |

## 待确认（需要其他成员）

| ID | 主题 | 等待谁 | 当前处理 |
| --- | --- | --- | --- |
| D-13 | TableCell 是否增加 cell_id 字段 | 朱 | 用 D-09 临时方案，不阻塞 |
| D-14 | parser catalog 与 reparse options 映射 | 张 | 无合法 ID 时不出 reparse_required |
| D-15 | info 是否阻塞（产品展示约定） | 三人 | 按 D-08 执行，变更需评审 |
| D-16 | golden 标注漂移：M0 一致性测试发现 **4 个 golden 样本两份标注均未同步**（sdp-004 column_path；sdp-005 must_produce+expected_state；sdp-006 must_produce 多 heading_level；sdp-007 must_produce+forbidden） | 数据负责人（团队） | 已登记 KNOWN_CONFLICTS，CI xfail 显式可见；annotations 为事实源，expected 需由其重新生成 |
