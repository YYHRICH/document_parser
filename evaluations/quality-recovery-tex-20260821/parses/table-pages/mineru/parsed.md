# 跨页网格表格测试

TRACE-T-DOC-001 | Source: TEX-TABLE-20260821-V1

## 1 表头与固定事实 TRACE-T-CAP-101

批次 TABLE-ALPHA 和 TABLE-BETA 必须保持可追溯，报告日期为 2026-08-21。

表 1: 汇总表
<table><tr><td rowspan="2">批次</td><td rowspan="2">日期</td><td colspan="2">指标</td></tr><tr><td>精度</td><td>成本</td></tr><tr><td>TABLE-ALPHA</td><td>2026-08-21</td><td>99.875%</td><td>USD 2,450.00</td></tr><tr><td>TABLE-BETA</td><td>2026-08-21</td><td>98.250%</td><td>USD 1,125.50</td></tr></table>

## 2 长表 TRACE-T-R03

表 2: 跨页明细
<table><tr><td>标记</td><td>批次</td><td>测量值</td><td>说明</td></tr><tr><td>TRACE-T-R01</td><td>TABLE-ALPHA</td><td>0.03125 mm</td><td>保留五位小数。</td></tr><tr><td>TRACE-T-R02</td><td>TABLE-BETA</td><td>4-20 mA</td><td>保留范围。</td></tr><tr><td>TRACE-T-R03</td><td>TABLE-ALPHA</td><td>A+B=C</td><td>运算符是事实。</td></tr><tr><td>TRACE-T-R04</td><td>TABLE-BETA</td><td>7/16 in</td><td>保留尺寸。</td></tr><tr><td>TRACE-T-R05</td><td>TABLE-ALPHA</td><td>1.2500 kg</td><td>保留尾随零。</td></tr><tr><td>TRACE-T-R06</td><td>TABLE-BETA</td><td>USD 2,450.00</td><td>保留货币。</td></tr><tr><td>TRACE-T-R07</td><td>TABLE-ALPHA</td><td>0.005%</td><td>保留百分号。</td></tr><tr><td>TRACE-T-R08</td><td>TABLE-BETA</td><td>2026-08-21</td><td>保留日期。</td></tr><tr><td>TRACE-T-R09</td><td>TABLE-ALPHA</td><td>2.25 mm</td><td>页面边界前记录。</td></tr><tr><td>TRACE-T-R10</td><td>TABLE-BETA</td><td>3.50 mm</td><td>跨页后记录。</td></tr><tr><td>TRACE-T-R11</td><td>TABLE-ALPHA</td><td>4.75 mm</td><td>继续追踪。</td></tr><tr><td>TRACE-T-R12</td><td>TABLE-BETA</td><td>6.00 mm</td><td>继续追踪。</td></tr><tr><td>TRACE-T-R13</td><td>TABLE-ALPHA</td><td>8.125 mm</td><td>继续追踪。</td></tr><tr><td>TRACE-T-R14</td><td>TABLE-BETA</td><td>9.250 mm</td><td>继续追踪。</td></tr><tr><td>TRACE-T-R15</td><td>TABLE-ALPHA</td><td>10.375 mm</td><td>继续追踪。</td></tr><tr><td>TRACE-T-R16</td><td>TABLE-BETA</td><td>11.500 mm</td><td>最后一行可追踪。</td></tr></table>

## 3 总结 TRACE-T-END-201

最终结论仍需保留 TABLE-ALPHA、TABLE-BETA、0.03125 mm、USD 2,450.00 和 A+B=C。