## 跨页网格表格测试

TRACE-T-DOC-001 | Source: TEX-TABLE-20260821-V1

## 1 表头与固定事实 TRACE-T-CAP-101

批次 TABLE-ALPHA 和 TABLE-BETA 必须保持可追溯，报告日期为 2026-08-21 。

|             | 表 1:       | 汇总表     | 指标           |
|-------------|------------|---------|--------------|
| 批次          | 日期         | 精度      | 成本           |
| TABLE-ALPHA | 2026-08-21 | 99.875% | USD 2,450.00 |
| TABLE-BETA  | 2026-08-21 | 98.250% | USD 1,125.50 |

## 2 长表 TRACE-T-R03

表 2: 跨页明细

| 标记          | 批次          | 测量值          | 说明       |
|-------------|-------------|--------------|----------|
| TRACE-T-R01 | TABLE-ALPHA | 0.03125 mm   | 保留五位小数。  |
| TRACE-T-R02 | TABLE-BETA  | 4-20 mA      | 保留范围。    |
| TRACE-T-R03 | TABLE-ALPHA | A+B=C        | 运算符是事实。  |
| TRACE-T-R04 | TABLE-BETA  | 7/16 in      | 保留尺寸。    |
| TRACE-T-R05 | TABLE-ALPHA | 1.2500 kg    | 保留尾随零。   |
| TRACE-T-R06 | TABLE-BETA  | USD 2,450.00 | 保留货币。    |
| TRACE-T-R07 | TABLE-ALPHA | 0.005%       | 保留百分号。   |
| TRACE-T-R08 | TABLE-BETA  | 2026-08-21   | 保留日期。    |
| TRACE-T-R09 | TABLE-ALPHA | 2.25 mm      | 页面边界前记录。 |
| TRACE-T-R10 | TABLE-BETA  | 3.50 mm      | 跨页后记录。   |
| TRACE-T-R11 | TABLE-ALPHA | 4.75 mm      | 继续追踪。    |
| TRACE-T-R12 | TABLE-BETA  | 6.00 mm      | 继续追踪。    |
| TRACE-T-R13 | TABLE-ALPHA | 8.125 mm     | 继续追踪。    |
| TRACE-T-R14 | TABLE-BETA  | 9.250 mm     | 继续追踪。    |
| TRACE-T-R15 | TABLE-ALPHA | 10.375 mm    | 继续追踪。    |
| TRACE-T-R16 | TABLE-BETA  | 11.500 mm    | 最后一行可追踪。 |

## 3 总结 TRACE-T-END-201

最终结论仍需保留 TABLE-ALPHA 、 TABLE-BETA 、 0.03125 mm 、 USD 2,450.00 和 A+B=C 。