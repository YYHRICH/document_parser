# Wiki 质量交付契约

质量层交给 Wiki 的物理产物有三个文件：

```text
optimized.md
structure.json
quality_issues.json
```

`optimized.md` 是经过白名单修复后的正文。`structure.json` 保存 canonical document、表格结构、字段绑定和来源定位；`quality_issues.json` 保存问题状态、修复记录、复核项和交付判定。三个文件通过同一个 `document_id` 关联，JSON 不重复保存 Markdown，不包含产物哈希或 manifest。

## JSON 内容

`structure.json`：

```json
{
  "schema_name": "DocumentStructure",
  "document_id": "...",
  "canonical_document": {
    "blocks": [],
    "tables": [
      {
        "table_id": "anydoc-table-0000",
        "block_id": "...",
        "source_locator": {
          "container": "sheet",
          "container_name": "专职单位",
          "range_ref": "A1:K622",
          "provenance_status": "verified"
        },
        "num_rows": 8,
        "num_cols": 11,
        "header_row_indices": [0],
        "title_row_indices": [],
        "header_state": "verified",
        "view_scope": "visible_rows",
        "source_has_filter": true,
        "source_row_count": 622,
        "emitted_row_count": 8,
        "hidden_row_count": 614,
        "cells": [],
        "grid": []
      }
    ],
    "table_bindings": [],
    "relations": [],
    "metadata": {}
  }
}
```

`quality_issues.json`：

```json
{
  "schema_name": "QualityIssues",
  "document_id": "...",
  "review_summary": {
    "repaired_count": 2,
    "manual_review_required_count": 1,
    "uncertain_count": 1,
    "reparse_required_count": 0
  },
  "review_items": [],
  "quality_report": {
    "state": "pass_with_warnings",
    "issues": [],
    "resolved_issues": [],
    "applied_repairs": [],
    "rejected_repairs": [],
    "capability_matrix": {},
    "gate_summary": {},
    "metrics": {}
  }
}
```

## 字段所有权

| 数据 | 生产者 | 说明 |
|---|---|---|
| blocks、tables、table_bindings、relations、source_locator | 统一层与质量层 | Wiki 检索和引用所需的结构化内容 |
| issues、repairs、capabilities、state、metrics、review_items | 质量层 | 诊断、自动修复、人工复核和最终判定 |
| Wiki page、chunk、embedding、索引、召回和答案 | Wiki | 不属于文档解析层 |

## 质量状态

文档级状态包括 `pass`、`pass_with_warnings`、`reparse_required` 和 `rejected`。问题和能力还要分别标记：

- `repaired`：已经自动修复并通过复检；
- `unfixed`：已发现问题但没有安全的自动修复；
- `manual_review_required`：有证据但存在冲突或歧义，需要人工确认；
- `uncertain`：证据不足，质量层无法作出可靠判断；
- `reparse_required`：当前结果缺少完成结构所需的关键证据。

Wiki 应读取 `structure.json` 建立检索结构，再读取 `quality_issues.json` 判断哪些内容可以直接使用、哪些需要显示警告、哪些不能建立高置信字段绑定。

## 表格消费约定

- `tables[].cells` 只保存真实 origin 单元格；合并覆盖位置放在 `tables[].grid`，不会复制成新事实。
- `grid` 中的 `origin.cell_id` 和 `covered.origin_cell_id` 必须能在同一张表的 `cells` 中找到。
- `table_bindings` 保存 `row_path`、`column_path`、`row_cell_ids`、`column_cell_ids` 和 `value_cell_id`，Wiki 不需要再从 Markdown 猜多级表头。
- 合并行头跨越多行时，绑定继承同一个行头源单元格 ID；这表示上下文继承，不表示复制了源单元格。
- `view_scope=visible_rows` 表示当前结构只覆盖筛选后可见行。Wiki 必须结合源行、输出行和隐藏行计数展示范围，不得把隐藏行误报为解析丢失。
- 真嵌套表使用 `parent_table_id` 和 `parent_cell_id`；只有分隔文本、没有子表结构证据的伪嵌套内容会原样保留并进入人工复核。
