# 四模型真实数据集质量审查与自动修复报告

> 本报告记录当前质量层对四种解析器保存结果的全量回放，以及一份使用 MinerU 原生证据完成的正式双文件质量包演示。所有统计均来自项目内的回放产物和质量流水线输出，不使用人工猜测或未记录的数字。
> 本次全量重跑产物位于 `artifacts/dataset-quality-replay-20260902/`，回放日期为 2026-09-02。

## 摘要

本轮审查的目标不是简单比较“哪个模型解析成功率高”，而是验证解析结果能否经过统一层和质量层后安全交给 Wiki。审查覆盖 AnyDoc、Docling、MarkItDown 和 MinerU 四种模型，输入是已经保存到本地的数据集解析结果。

核心结果如下：

- 当前四模型解析结果对应 224 条源文件记录；四种模型共保存 777 个可回放的 Markdown 输出单元。原始全量目录另有 210 条属于其他数据类别，当前结果集没有对应输出。
- 756 个输出单元非空，21 个为空；质量回放没有发生脚本错误。
- 172 个输出单元被质量层改写，产生 1,450 次白名单修复操作。
- 1,309 个 MinerU HTML 表格被转换为 Markdown；另外 2 个表格因无法安全定位正文表格块而拒绝替换。
- 自动修复只改变可证明的格式表示和空白，不补写 OCR 内容、不猜测缺失正文、不臆造表格单元格。
- 质量层的正式下游交付仍然只有 optimized.md 和 quality_package.json；全量回放的 JSONL、汇总 JSON 和报告只用于实验分析。

本轮结果支持以下判断：MinerU 是当前数据中复杂 PDF、扫描件和表格证据最丰富的来源，但必须经过 HTML 表格转换、资产完整性和标题结构检查；Docling 的版面与来源证据较强，但本次配置下表格网格和空结果仍需关注；AnyDoc 和 MarkItDown 能提供可用正文，但统一证据不足时只能降级交付。

## 1. 审查范围与数据

### 1.1 数据位置

原始四模型解析结果位于：

~~~text
S:\桌面\zyjt_sx\data\dataset
~~~

模型结果目录为：

~~~text
res_anydoc/
res_docling/
res_markitdown/
res_minerU/
~~~

数据集的 224 份逻辑文档来自四类业务集合：

| 数据集合 | 逻辑文档数 |
|---|---:|
| 图文回答数据集源文件 | 50 |
| 多文档多段知识数据集源文件 | 31 |
| 文档单点知识数据集源文件 | 118 |
| 模糊回答数据集源文件 | 25 |
| 合计 | 224 |

### 1.2 本轮回放的输出单元

不同模型的输出数量不等于 224 的简单四倍，因为模型可能失败、输出为空，或者没有形成可回放的主 Markdown：

| 模型 | 输出单元 | 非空 | 空 | 占全部回放单元 |
|---|---:|---:|---:|---:|
| AnyDoc | 191 | 191 | 0 | 24.6% |
| Docling | 175 | 174 | 1 | 22.5% |
| MarkItDown | 187 | 167 | 20 | 24.1% |
| MinerU | 224 | 224 | 0 | 28.8% |
| 合计 | 777 | 756 | 21 | 100% |

本报告中的“输出单元”是模型结果目录中实际被扫描到的一个 Markdown 交付单元，不代表源文件数量，也不代表最终 Wiki 文档数量。

### 1.4 原始源文件与四模型结果的逐文件对齐

为了判断“同一个文件四个模型谁能解析、谁不能解析”，本轮另外读取了原始目录 `S:\桌面\zyjt_sx\data\全量数据源文件`，并以“数据集类别 + 原始文件名”作为主键，与 `dataset/res_*` 下的模型结果进行对齐。该审计不重新调用解析器，也不修改任何输入文件。

原始全量目录共有 434 条文件记录：

| 范围 | 文件夹 | 文件数 | 本轮处理方式 |
|---|---|---:|---|
| 四模型结果覆盖的类别 | 图文回答、 多文档多段知识、 文档单点知识、 模糊回答 | 224 | 纳入四模型逐文件能力比较 |
| 其他源数据类别 | 单表查询、多表查询、无关=全部 | 210 | 仅记录为范围外，不计入模型成功/失败率 |

因此，四模型能力统计的分母是 224，而不是原始目录的 434。210 条范围外文件不是某一个模型的解析失败；它们在当前四个模型结果目录中都没有对应输出。完整的 434 行矩阵，以及 82 条存在模型差异的逐文件清单，见 [source-model-capability-matrix.md](source-model-capability-matrix.md)。

在 224 条已对齐源文件中，`成功` 的定义是“该模型存在非空 Markdown”；`空输出` 是解析状态成功但 Markdown 为空；`失败` 是解析状态为错误。统计如下：

| 模型 | 已对齐源文件 | 成功（非空） | 空输出 | 失败 | 非空成功率 |
|---|---:|---:|---:|---:|---:|
| AnyDoc | 224 | 191 | 0 | 33 | 85.27% |
| Docling | 224 | 174 | 1 | 49 | 77.68% |
| MarkItDown | 224 | 167 | 20 | 37 | 74.55% |
| MinerU | 224 | 224 | 0 | 0 | 100.00% |

同一个源文件的四模型状态组合如下：

| AnyDoc | Docling | MarkItDown | MinerU | 文件数 | 占 224 条 |
|---|---|---|---|---:|---:|
| 成功 | 成功 | 成功 | 成功 | 142 | 63.39% |
| 成功 | 失败 | 失败 | 成功 | 36 | 16.07% |
| 失败 | 成功 | 空输出 | 成功 | 19 | 8.48% |
| 成功 | 失败 | 成功 | 成功 | 13 | 5.80% |
| 失败 | 成功 | 成功 | 成功 | 12 | 5.36% |
| 失败 | 成功 | 失败 | 成功 | 1 | 0.45% |
| 失败 | 空输出 | 空输出 | 成功 | 1 | 0.45% |
| 合计 |  |  |  | 224 | 100.00% |

结论是：142/224（63.39%）的源文件四模型均能产出非空 Markdown；82/224（36.61%）存在至少一个模型失败或空输出。82 条差异中 MinerU 均有非空结果，但这只说明输出可用性最高，不等同于字符级、表格级或语义级准确率最高。

按文件格式看，差异主要集中在 PDF 和旧 Office 格式：

| 格式 | 文件数 | AnyDoc | Docling | MarkItDown | MinerU |
|---|---:|---|---|---|---|
| .doc | 34 | 34 成功 | 34 失败 | 34 失败 | 34 成功 |
| .docx | 49 | 49 成功 | 49 成功 | 49 成功 | 49 成功 |
| .pdf | 125 | 92 成功、33 失败 | 124 成功、1 空输出 | 104 成功、20 空输出、1 失败 | 125 成功 |
| .ppt | 2 | 2 成功 | 2 失败 | 2 失败 | 2 成功 |
| .xls | 13 | 13 成功 | 13 失败 | 13 成功 | 13 成功 |
| .xlsx | 1 | 1 成功 | 1 成功 | 1 成功 | 1 成功 |

失败原因的可解释归因如下：AnyDoc 的 33 个失败包括 23 个 `unsupported` 和 10 个 `malformed`；Docling 的 49 个失败全部落在 `.doc`、`.xls`、`.ppt`；MarkItDown 的 37 个失败包括 34 个 `.doc`、2 个 `.ppt` 和 1 个 PDF，另有 20 个 PDF 状态成功但内容为空。完整文件名、模型状态和失败原因已写入逐文件矩阵，不用汇总数字替代具体记录。

### 1.3 回放口径和限制

本轮全量回放使用 tools/replay_quality_on_dataset.py，对保存的 Markdown 逐文件构造最小统一对象，再调用真实质量流水线：

1. 读取 Markdown；
2. 按标题、段落和 HTML 表格构造稳定 block；
3. 为 HTML 表格构造最小表格对象；
4. 执行修复前诊断；
5. 应用质量层白名单修复；
6. 修复后重新诊断并生成质量门结论；
7. 记录逐文件质量摘要。

这是一种 markdown_only 回放，输入目录是只读的，没有把结果写回原始数据集。回放没有伪造以下证据：

- 页码和 bbox；
- 图片二进制及完整 assets；
- OCR span 和 OCR 置信度；
- 原生 table cell 坐标；
- 跨页 source-map；
- 解析器原生关系对象。

因此，回放中的 evidence_availability、provenance、表格字段绑定等问题，部分反映的是回放证据范围，而不一定是原模型正文错误。全量回放也没有落盘每份正式质量包；正式双文件质量包的结构在第 7 节用真实 MinerU 原生输出单独验证。

## 2. DDD 分层中的实际执行位置

本次审查没有把数据集读取、修复规则和文件写入混在一起，执行边界保持 DDD 和 Ports and Adapters 结构：

| 层 | 本次承担的职责 | 对应位置 |
|---|---|---|
| 领域层 | 统一模型、质量规则、修复注册表、canonical 构建、能力矩阵和质量门 | domain/model、domain/quality |
| 应用层 | 接收 ParsedDocument，调用质量流水线，返回 QualityPackage | app/use_cases.py、domain/quality/pipeline.py |
| 基础设施层 | 解析器 Adapter、统一文档包读取、双文件质量包写入 | infra/parsers、infra/packaging、infra/quality_packaging |
| 触发层 | HTTP、CLI 和脚本入口 | trigger、tools/replay_quality_on_dataset.py |
| 下游 Wiki | 只消费最终双文件，不参与质量判断 | 仓库外系统 |

质量规则不直接读取 MinerU 或 Docling 私有对象。解析器先通过 Adapter 归一到 ParsedDocument，质量层再基于统一字段和真实 evidence 执行规则。HTML 表格修复规则虽然主要命中 MinerU，是因为 MinerU 的统一输入保留了 HTML 表格证据，而不是因为质量层硬编码了某个模型分支。

## 3. 全量质量审查结果

### 3.1 总体统计

| 模型 | 改写单元 | 修复总数 | 修复规则 | 修复前问题数 | 修复后仍有问题 | 修复后消失的问题 | 拒绝修复 | 最终状态 |
|---|---:|---:|---|---:|---:|---:|---:|---|
| AnyDoc | 3 | 3 | QL-RPR-002=3 | 1,370 | 1,370 | 0 | 0 | 189 带警告通过，2 拒绝 |
| Docling | 30 | 30 | QL-RPR-001=30 | 1,389 | 1,389 | 0 | 0 | 169 带警告通过，6 拒绝 |
| MarkItDown | 6 | 6 | QL-RPR-002=6 | 1,205 | 1,205 | 0 | 0 | 149 带警告通过，38 拒绝 |
| MinerU | 133 | 1,411 | QL-RPR-001=102；QL-RPR-003=1,309 | 2,216 | — | 2,611 | 2 | 219 带警告通过，5 拒绝 |
| 合计 | 172 | 1,450 | 三类规则 | 6,180 | — | 2,611 | 2 | 726 带警告通过，51 拒绝 |

注：MinerU 的“修复后仍有问题”在汇总中不是直接可加的单一文档数，因此表中不填入未经重算的总数。问题数是 issue 实例数，不是坏文档数；一张表格修复可以同时消除表示问题和结构问题。AnyDoc、Docling、MarkItDown 的格式改写已发生，但当前回放的 issue fingerprint 没有把这些改写映射成 resolved_issues，所以“修复总数”和“修复后消失的问题数”不能简单等同。

### 3.2 质量状态分布

| 模型 | 带警告通过 | 拒绝 | 合计 |
|---|---:|---:|---:|
| AnyDoc | 189 | 2 | 191 |
| Docling | 169 | 6 | 175 |
| MarkItDown | 149 | 38 | 187 |
| MinerU | 219 | 5 | 224 |
| 合计 | 726 | 51 | 777 |

当前回放的质量门只输出最终可交付或不可交付状态，不把“人工复核”作为 Wiki 交付文件类型。证据不足会通过 warning、reparse 或 rejected 表达，具体由质量门配置决定。

### 3.3 问题类别汇总

| 问题类别 | AnyDoc | Docling | MarkItDown | MinerU |
|---|---:|---:|---:|---:|
| asset_integrity | 2 | 110 | 6 | 106 |
| content_completeness | 0 | 1 | 20 | 0 |
| content_readability | 2 | 5 | 12 | 3 |
| evidence_availability | 955 | 875 | 935 | 1,580 |
| heading_structure | 220 | 224 | 65 | 290 |
| provenance | 191 | 174 | 167 | 224 |
| repair_rejected | 0 | 0 | 0 | 2 |
| table_representation | 0 | 0 | 0 | 2 |
| table_structure | 0 | 0 | 0 | 9 |
| 合计问题实例 | 1,370 | 1,389 | 1,205 | 2,216 |

其中大量 evidence_availability 和 provenance 是 markdown_only 回放未携带原生页级证据导致的限制，不能直接解读为模型正文有同等数量的内容错误。

## 4. 质量层实际修复了什么

### 4.1 QL-RPR-001：清理行尾空白

该规则逐行去除 Markdown 行尾多余空格，保留正文字符、段落顺序、标题文本、图片链接和表格内容不变。

本轮执行情况：

| 模型 | 发生改写的文档/单元 | 修复记录 |
|---|---:|---:|
| AnyDoc | 0 | 0 |
| Docling | 30 | 30 |
| MarkItDown | 0 | 0 |
| MinerU | 102 | 102 |
| 合计 | 132 | 132 |

它解决的是 Markdown 表示噪声，不是 OCR 或语义错误。修复记录会写入 applied_repairs，并保留受影响 block 的稳定 ID。

### 4.2 QL-RPR-002：规范 Markdown 表格分隔行

该规则处理已经是管道表格、但分隔行不符合 Markdown 解析要求的情况。它只规范分隔线中的列数量、分隔符和空白，不生成新的表头或数据。

本轮执行情况：

| 模型 | 修复记录 |
|---|---:|
| AnyDoc | 3 |
| Docling | 0 |
| MarkItDown | 6 |
| MinerU | 0 |
| 合计 | 9 |

这类修复对于 Wiki 的文本切块和表格识别有帮助，但不等于恢复了表格的物理网格，也不产生可信的 cell 级来源定位。

### 4.3 QL-RPR-003：HTML 表格转换为 Markdown

这是本轮新增并真正命中的核心修复。MinerU 的 Markdown 中保留了完整 HTML table，虽然内容存在，但 Wiki 直接消费时不利于 Markdown 切分、展示和文本召回。

规则在满足以下条件时才执行：

1. 输入中存在完整、可解析的 table 片段；
2. 质量层能够把该片段对应到一个 ParsedTable 和 table block；
3. 转换器能生成合法 Markdown 表格；
4. 原 HTML 表格内容确实出现在全文 Markdown 中；
5. 替换前后能同步检查表格块和全文内容。

修复动作不是简单的字符串替换，而是同步更新三个位置：

- ParsedTable 的派生 Markdown；
- 对应 table block 的 Markdown 内容；
- 文档根 Markdown 中的 HTML table 片段。

同时保留原始表格 cells、rowspan/colspan 结构和转换证据。合并单元格转换成普通 Markdown 后可能存在表示损失，质量报告会记录该损失，不把转换结果伪装成完全等价的布局表达。

本轮 MinerU 共检测到 1,311 个 HTML 表格候选：

- 1,309 个成功转换；
- 2 个拒绝转换；
- 成功转换分布在 133 个输出单元中。

两个拒绝案例的共同原因是：表格 block 的内容没有出现在文档 Markdown 中，质量层无法安全定位替换位置。因此系统保留原内容并写入 repair_rejected，而不是猜测替换位置。

### 4.4 修复前后复检

每份文档都先诊断，再修复，再重新执行规则。质量报告分别保存：

- issues：复检后仍存在的问题；
- resolved_issues：修复前存在、复检后消失的问题；
- applied_repairs：实际执行的修复；
- rejected_repairs：因证据不足而拒绝的修复。

MinerU 本轮记录 2,611 个已消失问题实例，其中 table_representation 1,309 个、table_structure 1,302 个。一个 HTML 表格修复可以同时消除多个结构诊断，因此 resolved_issues 数量不等于 HTML 表格数量。AnyDoc、Docling 和 MarkItDown 虽然发生了格式改写，但本次回放的 issue fingerprint 没有形成对应 resolved_issues，这属于统计口径限制，不代表改写没有发生。

### 4.5 优化前后的定量差异

回放记录同时保存了输入 Markdown 和优化后 Markdown 的字符数。字符数变化只衡量表示层变化，不能当作内容正确率；尤其 HTML 表格转 Markdown 会删除标签和样式属性，因此字符数下降并不表示数据被删除。

| 模型 | 优化前字符数 | 优化后字符数 | 字符差异 | 发生改写的单元 | 改写比例 |
|---|---:|---:|---:|---:|---:|
| AnyDoc | 4,288,100 | 4,288,156 | +56 | 3/191 | 1.57% |
| Docling | 5,805,029 | 5,804,610 | -419 | 30/175 | 17.14% |
| MarkItDown | 59,566,474 | 59,566,362 | -112 | 6/187 | 3.21% |
| MinerU | 5,728,445 | 4,503,530 | -1,224,915 | 133/224 | 59.38% |
| 合计 | 75,388,048 | 74,162,658 | -1,225,390 | 172/777 | 22.14% |

三类修复的最小变换如下。示例是规则定义层面的表示差异，不是从数据集中摘录的业务内容：

| 修复类型 | 优化前 | 优化后 | 解决的问题 |
|---|---|---|---|
| QL-RPR-001 行尾空白清理 | `内容··\\n` | `内容\\n` | 删除 Markdown 行尾空格/制表符噪声，不改变正文字符 |
| QL-RPR-002 表格分隔行规范化 | 表头为 3 列、分隔线只有 2 列 | 补齐为 3 列合法分隔线 | 让下游 Markdown 解析器正确识别管道表格 |
| QL-RPR-003 HTML 表格转 Markdown | `<table>...</table>` | `|列1|列2|` 等管道表格 | 消除 HTML 表示障碍，便于 Wiki 展示、切块和文本召回 |

QL-RPR-003 还会同步更新 ParsedTable、table block 和文档根 Markdown；如果三者无法唯一对齐，则不修改原文并记录拒绝原因。

## 5. 不同模型分别修复了什么

### 5.1 AnyDoc

AnyDoc 有 191 个非空输出单元，质量层实际改写 3 个单元，全部是 QL-RPR-002 Markdown 表格分隔行修复。

质量层没有对 AnyDoc 做以下操作：

- 没有补充页码、bbox 或来源 block；
- 没有从纯 Markdown 猜造物理表格 cells；
- 没有修复 OCR 或扫描 PDF 内容；
- 没有把缺失图片当作存在。

AnyDoc 的主要质量问题统计为：evidence_availability 955、heading_structure 220、provenance 191，另有 2 个 asset_integrity 和 2 个 content_readability 问题。189 个输出带警告通过，2 个被拒绝。这里的证据问题主要源于 Markdown-only 输入无法提供原生定位信息，不应直接等同于 1,370 个正文错误。

结论：AnyDoc 的本轮质量修复以 Markdown 可消费性为主，未改变事实内容；如果 Wiki 需要页级证据、图片资产或复杂表格字段检索，统一层必须补齐这些结构，不能让质量层事后猜测。

### 5.2 Docling

Docling 有 175 个输出单元，其中 174 个非空，质量层改写 30 个单元，全部是 QL-RPR-001 行尾空白清理。1 个空 Markdown 没有被质量层填充，最终作为拒绝条件的一部分保留。

Docling 本轮没有命中 HTML 表格转换，也没有命中 Markdown 表格分隔线修复。它的主要问题统计为：evidence_availability 875、heading_structure 224、provenance 174、asset_integrity 110、content_readability 5 和 content_completeness 1。169 个输出带警告通过，6 个被拒绝。

结论：Docling 的主要价值在于版面、页面和块级来源证据；质量层本轮只清理表示噪声，未对标题层级、表格网格或空结果进行内容猜测。要改善表格能力，应调整 Docling 解析配置或由路由层改用 MinerU，而不是在质量层伪造单元格。

### 5.3 MarkItDown

MarkItDown 有 187 个输出单元，其中 167 个非空，20 个为空。质量层实际改写 6 个单元，全部是 QL-RPR-002 Markdown 表格分隔行修复。

质量层没有把 20 个空输出补成正文，也没有把 data URI 图片推断成可用资源。问题统计为：evidence_availability 935、provenance 167、content_completeness 20、content_readability 12、heading_structure 65 和 asset_integrity 6。149 个输出带警告通过，38 个被拒绝。

结论：MarkItDown 可以作为轻量格式转换器，但空结果和图片 data URI 会直接影响 Wiki 入库。质量层能拦截空内容、报告资源风险，但不能从空 Markdown 恢复原文；需要路由层重新选择解析器或先完成资源外置。

### 5.4 MinerU

MinerU 有 224 个非空输出单元，是四种模型中唯一全部产出非空 Markdown 的模型。质量层改写 133 个单元，共执行 1,411 次修复：

- QL-RPR-001：102 次行尾空白清理；
- QL-RPR-003：1,309 个 HTML 表格转换为 Markdown。

MinerU 的问题统计为：evidence_availability 1,580、heading_structure 290、provenance 224、asset_integrity 106、content_readability 3、table_structure 9、table_representation 2，以及 2 个 repair_rejected。219 个输出带警告通过，5 个被拒绝。

MinerU 的 1,309 个 HTML 表格修复是本轮最重要的质量收益。转换后，优化 Markdown 中不再残留这批 HTML table，表格块和全文内容保持同步，Wiki 可以按 Markdown 表格进行后续切块和索引。质量层没有尝试修复标题语义、跨页续表、OCR 识别错误或缺失图片，因为本轮回放缺乏足够证据。

结论：MinerU 适合当前数据中的扫描 PDF、图文报告和复杂表格，但交付 Wiki 前必须经过表格表示转换、资产完整性检查、标题树检查和分片完整性检查。

### 5.5 基于全量结果的后处理策略调整

本轮结果支持将后处理策略明确为“证据驱动的最小修复”，而不是对所有 Markdown 做统一重写：

1. 固定执行顺序为：修复前诊断 → 白名单修复 → 结构同步 → 修复后复检 → 质量门判定。这样可以区分“实际改写”“问题消失”和“仍需处理”，避免用修复次数冒充质量提升。
2. QL-RPR-001 和 QL-RPR-002 只处理 Markdown 表示噪声；不借助语言模型改写句子、数字、公式、标题或缺失值。
3. QL-RPR-003 只在 HTML 表格、ParsedTable 和 table block 具有唯一证据链时执行；替换定位失败就 rejected，保留原文，不猜测位置。
4. 质量层不补救空 Markdown、OCR 乱码、缺失图片、跨页续表和阅读顺序错误。这些问题需要路由层重新解析或统一层补齐 page/bbox/assets/source-map 后再处理。
5. 模型差异用于路由和评测，不写入质量规则分支。当前数据只说明不同模型触发的修复类型不同，不意味着质量层应该为某个模型复制一套私有逻辑。
6. 全量回放继续采用只读 Markdown-only 模式；正式 Wiki 交付仍由真实 ParsedDocument 生成，且只输出 optimized.md 和 quality_package.json。

## 6. JSON 绑定和 Wiki 交付验证

### 6.1 全量回放的 JSON 记录

全量回放保存了以下三个实验产物：

~~~text
artifacts/dataset-quality-replay-20260902/
├── summary.json
├── report.md
└── document_quality_records.jsonl
~~~

其中：

- summary.json 保存四模型聚合统计；
- report.md 保存回放摘要；
- document_quality_records.jsonl 保存每个输出单元的文档身份、路径、问题分类、修复规则和结果状态。

这些文件用于实验审计，回放脚本没有把 777 份结果逐一写成 Wiki 正式质量包，也没有覆盖原始数据集。因为回放只从 Markdown 构造最小表格对象，没有真实 cell 网格和完整来源证据，所以不以该回放统计细粒度 table_bindings。

### 6.2 正式质量包的绑定验证

为了验证 JSON 绑定确实能够被 Wiki 消费，另外使用真实 MinerU 原生输出对《2024年天猫618童装整体销售复盘-28页》执行了统一层和质量层：

~~~text
artifacts/quality-demo-mineru-童装/quality_package/
├── optimized.md
└── quality_package.json
~~~

该正式质量包包含：

| 对象 | 数量 |
|---|---:|
| canonical blocks | 347 |
| table_bindings | 320 |
| relations | 92 |
| applied_repairs | 7 |
| unresolved issues | 1 |
| rejected repairs | 0 |
| 最终状态 | pass_with_warnings |

三处 document_id 保持一致：质量包根对象、canonical_document 和 quality_report。表格绑定至少保留以下关系：

~~~text
table_id
  -> block_id
  -> row_key
  -> column_path
  -> value
  -> source_locator
  -> status
~~~

该样本的 320 条字段绑定均为 inferred，而不是 verified。这是因为样本具备表级页码和 bbox，但部分单元格没有独立 bbox；质量层保留绑定候选供 Wiki 检索，同时明确证据强度，不把推断绑定伪装成完全验证事实。

### 6.3 双文件内容一致性

样本质量包验证了以下约束：

- optimized.md 中原来的 6 个 HTML table 已转换为 Markdown；
- optimized.md 不再残留 HTML table；
- quality_package.json 不重复保存 optimized_markdown；
- quality_package.json 不包含产物哈希和 package manifest；
- canonical blocks 使用修复后的 Markdown 内容；
- table_bindings 和 relations 的 block/table ID 均能回到 canonical_document；
- 质量包目录只包含 optimized.md 和 quality_package.json。

## 7. 本轮没有自动修复的内容

质量层的设计重点是“可证明地修复”，不是尽可能多地改写。以下问题本轮只诊断或拦截，没有自动改正文：

### 7.1 空 Markdown

Docling 有 1 个空输出，MarkItDown 有 20 个空输出。质量层没有生成替代正文，避免把空结果误变成假内容；这些结果应由路由层触发重新解析。

### 7.2 OCR、乱码和语义内容

质量层没有根据上下文重写 OCR 文字、修正年份和数字、补齐缺失段落或恢复图片中的文字。没有真实 OCR span、原始页面或人工标注时，任何自动补写都可能制造事实错误。

### 7.3 标题语义和阅读顺序

质量层可以发现标题层级、父节点和阅读顺序证据不足，但不会把普通段落强行改成标题，也不会在双栏文档中凭经验重排正文。统一层需要提供真实 order_index、heading_level、section_path 和页级证据。

### 7.4 跨页续表、列漂移和复杂合并单元格

HTML 表格转换只处理表示层，不负责猜测跨页表格是否属于同一张表，也不负责修复列漂移。rowspan/colspan 转成普通 Markdown 后可能有表示损失，该损失会保留在质量报告中。

### 7.5 图片资产和 data URI

全量回放能报告图片引用缺失和 data URI 风险，但没有在 Markdown-only 模式下伪造 assets。图片外置需要统一层交付真实文件、相对路径、引用 block 和来源信息后再执行。

### 7.6 解析器不支持的格式

质量层不会把 Docling 或 MarkItDown 对旧 DOC、PPT 等格式的失败改成成功。格式转换和模型选择属于路由层/解析层职责。

## 8. 对三层架构的指导

### 8.1 路由层

- 不能只看扩展名和 parser success；
- 对扫描 PDF、无文本层 PDF 和空输出优先选择具备 OCR 的解析器；
- 对复杂表格和图文报告优先选择能保留 cells、page、bbox 的解析器；
- 发现分片缺失、页码不连续或结果为空时，应发起重新解析；
- 路由结论需要记录实际解析器和回退历史，供质量报告解释。

### 8.2 文档解析与统一层

- 每个 Adapter 都必须输出同一种 ParsedDocument；
- 必须保留 blocks、tables、assets、anchors、provenance 和 capabilities，不能只交 Markdown；
- MinerU 的 HTML 表格应在统一层保留 HTML、cells、span、bbox 和原始 block；
- 统一层要把图片和附件变成可校验的 assets，并保证 Markdown 引用闭合；
- 超长文档应合并分片并保留 part_id、页范围和全局顺序；
- 统一层不应替质量层预先生成最终 canonical bindings，但必须交付生成绑定所需的真实证据。

### 8.3 质量层

- 以确定性规则和白名单修复为基础；
- 先诊断、再最小修复、再复检；
- 每条修复必须能关联到受影响 block/table；
- 无法安全定位时必须 rejected，不得猜替换位置；
- 通过 capability_matrix 区分 verified、inferred 和 unavailable；
- 输出只包含 optimized.md 和 quality_package.json。

### 8.4 Wiki 层

Wiki 只读取两个质量文件：

1. 以 optimized.md 做全文索引、章节切分和文本召回；
2. 以 quality_package.json 读取 blocks、table_bindings、relations、来源定位和质量状态；
3. 对 inferred 绑定保留证据等级，不应当作无条件事实；
4. 不读取解析器私有 JSON，不绕过质量门直接消费原始 Markdown。

### 8.5 数据评测层

评测层可读取质量包、Wiki 召回结果和问答轨迹，评估：

- 文档是否成功入库；
- 章节和表格召回是否命中；
- 来源定位是否正确；
- inferred/verified 证据是否影响答案可信度；
- 不同解析器结果进入 Wiki 后的召回和问答差异。

评测结果只用于比较和迭代，不修改生产质量包。

## 9. 当前能力边界总结

| 能力 | AnyDoc | Docling | MarkItDown | MinerU |
|---|---|---|---|---|
| 普通正文输出 | 可用 | 可用 | 可用 | 可用 |
| 空结果风险 | 低 | 1 个空输出 | 20 个空输出 | 低 |
| 扫描/OCR | 弱 | 取决于配置 | 弱 | 当前最强 |
| 页码和 bbox | 低 | 强 | 低 | 强 |
| 图片资产 | 弱 | 较强 | data URI 风险 | 较强，但需统一层闭合 |
| 物理表格网格 | 弱 | 有，但本次配置不稳定 | 弱 | 当前最丰富 |
| HTML 表格风险 | 无明显命中 | 无明显命中 | 无明显命中 | 本轮核心修复对象 |
| 适合的路由位置 | 普通正文、旧 Office 兜底 | 版面和来源证据 | 轻量格式转换 | 扫描件、图文和复杂表格 |

这些结论是当前数据集、当前解析配置和当前统一适配器的结果，不等同于四种模型的理论上限。

## 10. 局限性与后续验证

本轮是结构与质量规则审查，不是带人工真值的字符级精度实验，因此不能从这些结果直接推出 OCR 字符准确率、表格单元格准确率或最终问答准确率。尤其需要注意：

- markdown_only 回放没有完整 page/bbox/cell/assets 证据；
- 同一个逻辑源文档在不同模型下可能没有同样的输出单元；
- 字符数、block 数和修复次数不能单独代表内容正确率；
- quality issue 是问题实例，不是去重后的文档数；
- 质量层的 resolved_issues 依赖修复前后 fingerprint，不能直接与 applied_repairs 相加；
- 本轮没有使用目标问答标签选择模型或修复规则。

建议的下一轮验证顺序：

1. 对同一批真实原生 ParsedDocument 重新运行四模型质量流水线；
2. 为普通正文、扫描正文、复杂表格、图片说明和多栏阅读顺序建立人工标注子集；
3. 增加正文覆盖率、标题层级准确率、阅读顺序准确率和表格 cell 准确率；
4. 检查图片资产闭合、data URI 外置、source-map 覆盖和分片页码连续性；
5. 将 Wiki 入库率、表格字段召回率、来源定位准确率和问答结果纳入数据评测层。

## 11. 可复现实验产物

全量回放工具：

~~~powershell
cd S:\Agent_study\wiki\document_parser
.\.venv\Scripts\python.exe tools\replay_quality_on_dataset.py --results-root S:\桌面\zyjt_sx\data\dataset --output-dir artifacts\dataset-quality-replay-20260902
~~~

源文件—模型逐文件对齐审计：

~~~powershell
cd S:\Agent_study\wiki\document_parser
.\.venv\Scripts\python.exe tools\audit_source_output_fidelity.py --source-root S:\桌面\zyjt_sx\data\全量数据源文件 --results-root S:\桌面\zyjt_sx\data\dataset --output-dir artifacts\source-output-fidelity-20260902
.\.venv\Scripts\python.exe tools\build_source_model_capability_matrix.py --source-root S:\桌面\zyjt_sx\data\全量数据源文件 --audit-jsonl artifacts\source-output-fidelity-20260902\document_metrics.jsonl --markdown-output docs\source-model-capability-matrix.md --jsonl-output artifacts\source-output-fidelity-20260902\source_model_capability_matrix.jsonl --csv-output artifacts\source-output-fidelity-20260902\source_model_capability_matrix.csv
~~~

本轮使用的证据文件：

- artifacts/dataset-quality-replay-20260902/summary.json
- artifacts/dataset-quality-replay-20260902/report.md
- artifacts/dataset-quality-replay-20260902/document_quality_records.jsonl
- artifacts/source-output-fidelity-20260902/document_metrics.jsonl
- artifacts/source-output-fidelity-20260902/summary.json
- artifacts/source-output-fidelity-20260902/source_model_capability_matrix.jsonl
- artifacts/source-output-fidelity-20260902/source_model_capability_matrix.csv
- docs/source-model-capability-matrix.md
- artifacts/quality-demo-mineru-童装/quality_package/optimized.md
- artifacts/quality-demo-mineru-童装/quality_package/quality_package.json

原始数据集为只读输入，本轮没有覆盖或移动其中任何文件。

## 12. 结论

本轮质量审查证明，质量层已经能够对四种解析器结果执行统一的、证据驱动的安全修复：

1. 对格式噪声执行行尾空白和 Markdown 表格分隔线规范化；
2. 对可定位的 MinerU HTML table 执行 HTML 到 Markdown 的确定性转换；
3. 在修复前后分别诊断，保留未解决问题、已应用修复和拒绝修复；
4. 在具备原生表格证据时生成 table_bindings 和文档关系；
5. 用质量门决定结果能否交给 Wiki；
6. 最终只向 Wiki 交付 optimized.md 和 quality_package.json。

不同模型的修复重点不同：AnyDoc 和 MarkItDown 主要是 Markdown 表格表示修复，Docling 主要是行尾空白清理，MinerU 同时承担行尾空白清理和大规模 HTML 表格转换。质量层没有把模型结果强行改成同一种“看起来完整”的内容，而是保留证据差异并把不确定性写入质量报告。

因此，推荐继续保持：

~~~text
模型路由
  -> 文档解析
  -> 结构统一
  -> 质量诊断与安全修复
  -> 双文件 Wiki 交付
  -> Wiki 问答
  -> 数据评测
~~~

统一层负责提供真实结构和来源证据，质量层负责安全修复和准入判断，Wiki 负责消费质量包，评测层负责测量下游效果。这个职责划分与当前 DDD 目录和端口边界一致，不需要把 Wiki 逻辑或评测逻辑耦合进质量规则。
