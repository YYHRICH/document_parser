# 质量层开发进展（feature/quality-layer）

> 更新：2026-08-18 ｜ 分支：`feature/quality-layer` ｜ 基线：`main` 冻结接口

## 一、总体状态

| 里程碑 | 状态 | 内容 |
| --- | --- | --- |
| M0 契约冻结与骨架 | ✅ 完成 | D-01~D-16 决策、quality/ 包骨架、内部模型、稳定 ID、Gate 不变量测试 |
| M1 完整流水线 | ✅ 完成 | EvidenceContext、QL-CONT/PROV 规则、能力矩阵、Gate 五态、run_quality 打通 |
| M2 标题树与数字引用 | ✅ 完成 | QL-HDG 树算法 + 层级粒度检测、QL-REF 参考索引 + 唯一性绑定 |
| M3 表格网格与字段绑定 | ✅ 完成 | QL-TBL 网格/多级 column_path/row_key/跨页续表与列漂移（QL-TBL-007/008） |
| M4 白名单修复 | ✅ 完成 | QL-RPR 行尾空白/表格分隔行、幂等、no-op 合法 |
| M5 双文件落盘 | ✅ 完成 | optimized.md + quality_package.json，原子化写入和结构校验 |
| M6 单文档质量修复 Agent | ⬜ 待办 | Agno 运行时、Adapter、修复循环和审核输出 |
| M7 联调交付 | ⬜ 待办 | 朱真实 fixtures、张 parser catalog、golden 验收 |

测试状态：**199 passed + 1 xfailed**（xfailed 为 golden 标注冲突显式登记，D-16）

## 二、已实现能力

### 解析工具链（开发期自建，朱正式 Adapter 到位后只换数据源）

```
tools/
├─ mineru_cloud.py    # MinerU 云 API → ParsedDocument（真实层级/HTML 网格/bbox）
├─ docling_parser.py  # docling 本地（junction + TORCH_COMPILE_DISABLE）→ ParsedDocument
├─ fallback_parser.py # pdfplumber 离线兜底 → ParsedDocument
└─ make_fixtures.py   # 批量生成 tests/quality/fixtures/parsed_documents/
```

32 个真实 fixtures（12 文件 × 三路解析器）已入库。

### 质量流水线（quality/）

```text
ParsedDocument 2.2
  → EvidenceContext（索引 + 能力判定）
  → 15 条规则（CONT/PROV/HDG/REF/TBL/RPR）
  → 能力矩阵（6 项标准能力 + 观测项）
  → Gate 自动决策（唯一裁判）
  → optimized.md + quality_package.json
```

规则清单：

| 规则 | 功能 |
| --- | --- |
| QL-CONT-001~003 | blocks 存在/ID 唯一、order 冲突、kind 一致性 |
| QL-PROV-001~004 | 来源可回溯、bbox 合法、artifact 哈希、capability reason |
| QL-HDG-001/004 | 标题字段、stack 建树 + 层级粒度可疑检测（编号重建 inferred） |
| QL-REF-001/004 | 参考索引恢复（顺序编号）、数字 marker 唯一性绑定 |
| QL-TBL-004/006/007/008 | column_path/row_key/binding、跨页续表与列漂移识别 |
| QL-RPR-001/002 | 行尾空白、表格分隔行修复（幂等） |

### 质量红线（持续遵守）

- 不伪造证据：数字/公式/表头/标题/bbox/来源一律来自 ParsedDocument
- no-op 合法：无修复时不改原文，不产生虚假 applied_repairs
- `verified` 必须有证据；LLM 建议最高 `inferred`（M6）
- 粒度可疑（解析器标题全平）→ 编号重建 → 降级，绝不假装 verified

## 三、真实数据表现（MinerU 云 API / docling）

| 样例 | 结果 |
| --- | --- |
| sdp-004-docling | 表格绑定 64 条（30 verified），多级表头路径 `技术参数/额定电压` 正确 |
| sdp-004-mineru | 绑定全 inferred（无 row_header 标记 → 诚实降级） |
| sdp-005-mineru | 跨页续表：表头一致 → verified；"续行"弱候选 → manual（对应标注 CASE-A/C） |
| sdp-006-docling | 引用绑定 6 条全 verified（正例成立）；标题树粒度可疑 → 全部 inferred |
| sdp-007 | 歧义场景零误绑 |

## 四、使用方式

```python
from document_parser.core.contracts import ParsedDocument
from quality import run_quality

doc = ParsedDocument.model_validate_json(open("fixture.json", encoding="utf-8").read())
pkg = run_quality(doc)
print(pkg.quality_report.state)          # pass / pass_with_warnings / reparse_required / rejected
print(pkg.canonical_document.table_bindings)
```

```powershell
# 回归
python -m pytest tests/ -q

# 重新生成 fixtures（需 .env 配置 MINERU_API_KEY）
python -m tools.make_fixtures --parser mineru --samples all
TORCH_COMPILE_DISABLE=1 C:/dp_venv_link/Scripts/python.exe -m tools.make_fixtures --parser docling --samples all
```

## 五、关键决策（详见 docs/quality-decisions.md）

- D-01：sdp-004 标注以采购版为准（annotations 为事实源）
- D-02：不产生人工复核状态；证据不足以 inferred + warning、reparse_required 或 rejected 表达
- D-03：能力不适用（无表格）不阻塞
- D-07：canonical content 默认保留输入，白名单修复才变
- D-08：info 不阻塞 pass
- D-09：cell 身份 = (table_id, 行, 列) 临时方案，等朱 cell_id
- D-10：确定性规则作为基础和降级路径，M6 接入可关闭的单文档质量修复 Agent
- D-12：fixtures 用真实解析 + 合成
- D-16：4 个 golden 样本两份标注均漂移，已登记 KNOWN_CONFLICTS 待数据负责人

## 六、已知限制（诚实清单）

1. 跨页表格**不合并**：页内绑定保留，跨页关系单独表达（table_continuation），列漂移检测包含表头顺序与可用 cell bbox 几何证据
2. 作者-年份引用（如 (Zhang, 2023)）为二期能力，当前只做数字引用
3. MinerU/docling 标题层级粒度粗（全平）→ 树全部 inferred，需朱的正式 Adapter 数据或编号证据
4. 本地 docling 需英文路径 junction（C:\dp_venv_link）+ TORCH_COMPILE_DISABLE=1
5. golden 期望文件（expected/）与标注（annotations/）未同步，待团队确认后消解
6. reparse_required 需要张提供合法 parser catalog 后才能真实产出

## 七、下一步

1. **M6**：Agno 单文档质量修复 Agent（Fake Agent、候选验证、revision 和审核输出）
2. **M7**：接入朱真实 ParsedDocument、与张确认 reparse catalog、golden 验收
