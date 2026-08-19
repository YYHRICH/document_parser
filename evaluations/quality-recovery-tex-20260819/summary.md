# 真实双解析器质量恢复评测结果

| 文档 | 解析器 | Agent | 变更 | 解析标记 | 恢复后标记 | 解析事实 | 恢复后事实 | 质量状态 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| trace-structure | mineru | accepted | False | 8/8 | 8/8 | 5/7 | 5/7 | manual_review_required |
| trace-structure | docling | accepted | True | 8/8 | 8/8 | 4/7 | 4/7 | pass |
| trace-tables | mineru | accepted | True | 10/10 | 10/10 | 5/6 | 5/6 | manual_review_required |
| trace-tables | docling | accepted | True | 10/10 | 10/10 | 5/6 | 5/6 | manual_review_required |
| trace-layout | mineru | accepted | False | 7/8 | 7/8 | 4/5 | 4/5 | manual_review_required |
| trace-layout | docling | accepted | True | 8/8 | 8/8 | 5/5 | 5/5 | pass |

说明：恢复后召回率不能高于解析阶段缺失事实的上限；质量 Agent 只允许修复格式/结构，
不会猜测并补写解析器已经丢失的正文事实。详细 attempts、diff 和四件套见 `quality/`。
