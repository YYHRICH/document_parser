# 双栏与对象关系测试 TRACE-L-DOC-001 | Source: TEX-LAYOUT-20260819-V1

## 1 左栏起点 TRACE-L-COL-A01

阅读顺序声明为 READ-A-B-C-D。A 段必须先于B 段，随后进入右栏的 C 段与 D 段。本段包含条件$\alpha \leq \beta + 0 . 0 5$ ，不等号与小数必须保留。

## 1.1 对象说明

下面的框模拟独立图形对象。它不携带外部资源，但图注与对象必须保持邻接关系。

TRACE-L-FIG-101Figure checksum 7F3A-91C2Flow: INPUT VERIFY OUTPUT图 1：验证流程 TRACE-L-CAP-111

对象校验使用固定 checksum，不得把字符 F、A、C与数字混淆。

## 2 右栏起点 TRACE-L-COL-B01

C 段延续阅读顺序。这里包含脚注引用<sup>1</sup>，脚注标记应与脚注正文建立关系，而不是并入相邻标题。

## 2.1 约束公式

$$
\alpha \leq \beta + 0 . 0 5
$$

(TRACE-L-EQ-131)

D 段完成 READ-A-B-C-D。页面底部的 Page tokenPL-42 是重复页脚事实，可标记为版面噪声，但不得擅自改写其字符。

## 3 引用与附录 TRACE-L-REF-201

正式引用：Doe, J. (2026), Traceable Layout Recovery, DOI 10.5555/trace.2026.0819。

图、图注、脚注、公式与引用必须通过已有对象和来源证据建立关系。

本页再次出现运行页眉与 Page token PL-42，用于检测重复页眉页脚的解析行为。