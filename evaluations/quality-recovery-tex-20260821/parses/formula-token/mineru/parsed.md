# 公式符号保真测试TRACE-F-DOC-001 | Source: TEX-FORMULA-20260821-V1

## 1 固定事实 TRACE-F-SEC-101

记录编号为 FORMULA-42，日期为 2026-08-21，预算为 EUR 4,321.09。本页测试比较符号、正负号、分数和上下标的保留。

## 1.1 数学表达式 TRACE-F-EQ-111

$$
\begin{array} { c } { { s c o r e \leq 0 . 8 7 5 , } } \\ { { } } \\ { { x \neq y , } } \end{array}
$$

$$
\begin{array} { r } { d e l t a \geq 0 . 1 2 5 , } \\ { z = \pm 0 . 0 5 } \end{array}\tag{1}
$$

(TRACE-F-EQ-111)

约束函数为 $\begin{array} { r } { f ( t ) = \frac { t ^ { 2 } + 1 } { t + 1 } } \end{array}$ ，并且 $n \in \mathbb { N }$

表 1: 符号核对表 TRACE-F-TABLE-121
<table><tr><td>标记</td><td>条件</td><td>值</td></tr><tr><td>FORMULA-42</td><td>score ≤ 0.875</td><td>EUR 4,321.09</td></tr><tr><td>TRACE-F-TABLE-121</td><td>delta ≥ 0.125</td><td>±0.05</td></tr></table>

## 2 跨页结论 TRACE-F-END-201

结论要求保留 score  0.875、delta  0.125、x = y 和 0.05。任何公式无法解析时必须使用占位符并提示下游，而不是生成未经证实的公式。