# 文档质量层实现规格

> 输入：统一层生成的 `ParsedDocument`
> 输出：`optimized.md`、`structure.json`、`quality_issues.json`

## 1. 目标

质量层负责检查并安全修复单个统一文档包，为 Wiki 提供可阅读正文、可查询结构和可执行的问题状态。

质量层必须做到：

- 只依赖统一领域契约，不读取解析器私有对象；
- 修复前诊断，修复后重新检查；
- 只执行有明确证据、确定性且幂等的白名单修复；
- 保存表格真实网格、来源、视图范围和字段绑定；
- 明确区分已修复、尚未修复、需要人工复核、需要重新解析和拒绝交付；
- 不伪造正文、数字、公式、单元格坐标、页面位置或来源关系。

## 2. 非目标

- 不负责选择解析模型；
- 不调用解析器重新解析文件；
- 不负责多文档队列、重试或文件生命周期监测；
- 不使用生成式模型改写事实内容；
- 不由 Markdown 反向猜测复杂表格的真实结构；
- 不负责 Wiki 的切块、召回和问答。

## 3. DDD 边界

```text
app/use_cases.py
  → domain/quality/pipeline.py
      → evidence/      证据上下文
      → rules/         质量检查
      → repairs/       白名单修复
      → gates/         能力和准入判定
      → builders/      规范文档图构建
  → infra/quality_packaging/
      → 三文件序列化、引用校验和原子写入
```

领域层不能依赖 HTTP、数据库、文件系统、具体解析器 SDK 或外部模型运行时。

## 4. 统一输入要求

### 4.1 文档与块

`ParsedDocument` 至少提供：

- 稳定 `document_id`；
- 文档 Markdown；
- 有序 blocks；
- block 类型、内容和来源锚点；
- 表格、资源和能力声明。

解析器未提供的证据必须保持缺失，不能用正文或默认值冒充。

### 4.2 表格

`ParsedTable` 应尽可能提供：

- `table_id` 与对应 `block_id`；
- `cells`、逻辑行列数和 `row_span/col_span`；
- origin/covered 逻辑网格；
- 表头行、行头列和嵌套父子关系；
- 页码、工作表、范围和单元格来源定位；
- 全量行、可见行、隐藏行和筛选状态；
- 原始值、显示值、规范值、值类型和公式。

Excel 行列与解析网格能够安全对齐时，适配器可补充 A1 坐标。无法对齐时不得伪造坐标，质量层生成 `table_source_mapping` 人工复核项。

## 5. 质量流水线

```text
ParsedDocument
  → 建立 EvidenceContext
  → 执行修复前诊断
  → 应用确定性白名单修复
  → 在修复后文档上重新执行规则
  → 去重问题事实
  → 构建能力矩阵
  → 构建 CanonicalDocument
  → 执行 Gate
  → 生成三文件
```

规范结构、质量报告和优化 Markdown 必须基于同一个修复后文档生成。

## 6. 表格质量规则

| 规则 | 检查内容 |
|---|---|
| `QL-TBL-001` | 单元格坐标与 span 合法性 |
| `QL-TBL-002` | 网格占位冲突、越界和空洞 |
| `QL-TBL-003` | 表格是否缺少可用结构 |
| `QL-TBL-004` | 多级表头和完整列路径 |
| `QL-TBL-005` | 行路径与行键来源 |
| `QL-TBL-006` | 表格字段绑定及单元格引用 |
| `QL-TBL-007` | 跨页续表候选及证据状态 |
| `QL-TBL-008` | 跨页列结构漂移 |
| `QL-TBL-009` | 文档 Markdown、表格 block、表格 Markdown 与逻辑网格的一致性 |
| `QL-TBL-010` | 全量/可见/隐藏行对账、A1 定位和嵌套父子引用 |

复杂合并单元格必须在 JSON 中保留一个 origin 单元格以及 covered 槽位对 origin 的引用。Markdown 只是可读表示，不承担真实结构。

伪嵌套表缺少可靠子表边界时，保留单元格文本并标记人工复核，不自动拆分。

## 7. 白名单修复

| 规则 | 修复内容 | 安全边界 |
|---|---|---|
| `QL-RPR-001` | 清理行尾空格 | 不改变正文字符和段落语义 |
| `QL-RPR-002` | 规范 Markdown 表格分隔行 | 不猜测列数和单元格内容 |
| `QL-RPR-003` | HTML 表格转换为 Markdown | 必须唯一定位表格 block；转换失败保留原文 |
| `QL-RPR-004` | 恢复 Excel 单元格内部换行 | 只使用原始单元格值；必须同步结构单元格、表格 Markdown、block 和全文 |

修复必须满足：

- 同一输入重复执行不会产生新变化；
- 只有实际变化才生成 `AppliedRepair`；
- 每条修复记录规则、受影响对象、前后内容、参数和证据引用；
- 任何表示无法安全同步时拒绝修复，原内容保持不变；
- 不补写隐藏行，不猜测公式结果，不复制合并单元格为多个事实单元格。

## 8. 规范输出

### 8.1 `optimized.md`

保存修复后的可阅读正文，供 Wiki 展示和文本检索。

### 8.2 `structure.json`

只保存规范文档结构：

- `canonical_document.blocks`；
- `canonical_document.tables`；
- `canonical_document.table_bindings`；
- `canonical_document.relations`；
- 来源定位和证据状态。

表格字段绑定由以下内容组成：

- 表格和文档块 ID；
- 行路径与行单元格 ID；
- 完整列路径与表头单元格 ID；
- 值和值单元格 ID；
- 工作表、A1 坐标、页面或 bbox；
- `verified`、`inferred` 或 `manual_review_required` 状态。

输出前必须验证：

- block、table 和 cell ID 唯一；
- 表格引用的 block 存在；
- origin/covered 槽位引用的 cell 存在；
- 嵌套表的父表和父单元格存在；
- binding 引用的表格、block 和所有 cell 存在；
- relation 两端 block 存在。

### 8.3 `quality_issues.json`

只保存质量状态：

- 修复后仍存在的问题；
- 修复前存在、修复后消失的问题；
- 已应用和被拒绝的修复；
- 能力矩阵；
- 质量门结论；
- 表格问题与通用文档问题的独立统计。

三份文件使用同一个 `document_id`，结构 JSON 和问题 JSON 不重复保存正文，也不保存 manifest 或产物哈希。

## 9. 问题状态

| 状态 | 含义 | 下游动作 |
|---|---|---|
| `repaired` | 已被安全修复并通过复检 | 正常使用 |
| `unfixed` | 问题仍存在但不属于强制人工项 | 按警告策略处理 |
| `manual_review_required` | 证据不足或结构歧义 | 提交人工复核，不建立高置信绑定 |
| `reparse_required` | 当前解析结果不足，需要重新解析 | 返回路由层 |
| `rejected` | 存在不可接受风险 | 禁止交付 Wiki |

报告分别统计各种状态。同一问题事实即使被多个规则入口观察到，也只能计算一次。

## 10. 能力矩阵

标准能力包括：

- 正文完整性；
- 标题树可靠性；
- 表格网格可靠性；
- 表格结构可靠性；
- 表格视图范围可靠性；
- 表格表示可靠性；
- 表格字段绑定可靠性；
- 来源可靠性；
- 非表格关系可靠性。

`verified` 必须附带能够定位到 block、table、cell 或来源字段的证据引用。没有表格的文档中，表格能力应标记为不适用的 unavailable，不能成为阻断项。

## 11. 质量门

优先级如下：

```text
rejected
  > reparse_required
  > pass_with_warnings
  > pass
```

- 明确为 rejected 的问题或能力直接拒绝交付；
- reparse_required 必须提供合法、可执行的重新解析建议，否则转 rejected；
- warning、inferred 或 manual_review_required 产生带警告交付；
- info 是否影响 pass 由 Gate 配置决定；
- critical 问题不能得到 pass 或 pass_with_warnings。

## 12. 验收要求

- 统一输入缺少证据时不制造默认事实；
- HTML 表格转换同步更新全文、block 和表格对象；
- Excel 换行修复只使用源单元格证据；
- 合并单元格、可见视图和嵌套表在 JSON 中保持明确语义；
- 无效父子关系、字段绑定和关系端点不会进入最终结构；
- 人工复核关系不会被降级成普通推断；
- 问题状态和统计一致；
- 三文件职责分离且内部引用闭合；
- Wiki 可以只依赖三份交付文件，不需要重新解析原始解析器输出。
