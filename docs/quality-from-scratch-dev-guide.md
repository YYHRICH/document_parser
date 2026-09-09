# 质量层扩展开发入口

本文用于说明如何在当前 DDD 架构中扩展质量层。项目只维护一个质量子域：`domain/quality/`。不得新建并行的 `quality_v2`，也不得通过兼容层保留两套质量契约。

## 1. 先判断改动属于哪一层

| 问题类型 | 修改位置 | 说明 |
| --- | --- | --- |
| 解析器私有输出的清洗和映射 | `infra/parsers/<parser>/` | 适配器负责把不同解析器输出归一为 `ParsedDocument` |
| 统一文档结构 | `domain/model/contracts.py` | 直接修改唯一契约，并同步调用方、示例和测试 |
| 质量证据、规则、修复和准入 | `domain/quality/` | 只依赖统一结构，不判断具体解析器名称 |
| 质量包落盘和大表索引 | `infra/quality_packaging/` | 输出三个基础文件；大表按需追加 SQLite 索引 |
| HTTP、CLI 和页面入口 | `trigger/`、`frontend/` | 只调用应用层用例，不复制领域规则 |

完整分层、规则写法和验证方法见 [质量层 DDD 开发指南](quality-layer-ddd-dev-guide.md)，复杂表格和大表设计见 [质量层深化设计](quality-layer-deepening-design.md)。

## 2. 扩展一条质量规则

1. 在 `domain/quality/rules/` 中实现规则，分配唯一的 `QL-<类别>-<序号>` 编号。
2. 规则只读取 `ParsedDocument` 和 `EvidenceContext`，不得导入 `infra`、FastAPI 或具体解析器。
3. 能自动修复的问题，在 `domain/quality/repairs/` 中实现白名单修复；无法确定的内容只报告，不猜测、不补写。
4. 在流水线中注册规则，并保证问题输出携带 `rule_id`、对象定位、问题状态和可解释说明。
5. 在 `tests/quality/unit/` 增加规则单测，在 `tests/quality/integration/` 验证修复前后及最终质量门状态。

## 3. 修改统一契约或交付契约

当前契约不是并行版本：字段需要调整时直接修改现有模型，并一次性同步以下位置：

- `domain/model/contracts.py`；
- `infra/quality_packaging/`；
- `api/` 与自动生成的 `frontend/api-types.ts`；
- `contracts/`、`examples/` 和相关测试；
- README 与下游 Wiki 对接说明。

交付给 Wiki 的基础文件固定为 `optimized.md`、`structure.json`、`quality_issues.json`。存在大表时追加 `table_index.sqlite3`，不得把完整大表强塞进 JSON。

## 4. 外部能力边界

质量层不接入能够直接改写正文或事实数据的通用 LLM Agent，也不保留 `llm_advisor`、`llm_enabled` 一类旁路。确需调用确定性的外部能力时，应先在 `domain/ports.py` 定义职责单一的窄接口，再由 `infra/` 实现并在 `app/bootstrap.py` 注入；外部结果仍须经过规则、修复白名单和质量门。

## 5. 提交前检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\check_dependencies.py
.\.venv\Scripts\python.exe scripts\gen_frontend_types.py
node --check frontend\app.js
git diff --check
```

通过标准是：领域层依赖方向正确；所有质量问题都有规则编号；引用闭合；修复可复检；无法确定的问题明确进入人工复核或重新解析状态；前后端契约一致。
