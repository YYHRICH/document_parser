# 开发环境搭建指南（换机/新环境）

> 适用：`feature/quality-layer` 分支开发（质量层）
> 更新：2026-08-18 ｜ 已验证环境：Windows 10 + Python 3.11.15

## 1. 拉取代码

```bash
git clone https://github.com/YYHRICH/document_parser.git
cd document_parser
git checkout feature/quality-layer
```

**注意**：本机若配置了 Clash 等代理（`http.proxy=127.0.0.1:7890`），代理未运行时
push/pull 会报 TLS 错误，绕过方式：

```bash
git -c http.proxy= -c https.proxy= push origin feature/quality-layer
```

## 2. 虚拟环境与依赖

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

requirements.txt 已包含：pydantic / markitdown / pywin32 / requests / pdfplumber / pytest。
（`pdfplumber`、`requests` 为 tools/ 解析工具链依赖；docling 为可选，见第 4 节。）

将仓库安装为可编辑包，确保无论 checkout 目录叫什么都可以使用 `document_parser` 导入：

```powershell
.venv/Scripts/python.exe -m pip install --editable . --no-deps --no-build-isolation
```

## 3. API 密钥（.env，不入库）

在仓库根目录创建 `.env`（`.gitignore` 已排除）：

```
MINERU_API_KEY=<你的 MinerU 云 API token>
LLM_API_KEY=<预留>
LLM_API_BASE=<预留>
LLM_MODEL=<预留>
```

MinerU token 申请：https://mineru.net/apiManage/token

## 4. 可选：本地 docling 解析器

MinerU 云 API + pdfplumber 兜底已满足开发；docling 本地解析需要特殊环境
（本机验证过的组合），不需要时跳过本节。

```bash
# a. 在纯英文路径建 venv（docling C++ 层读不了中文路径）
python -m venv C:/dp_env
C:/dp_env/Scripts/python.exe -m pip install docling torch==2.7.1 torchvision==0.22.1

# b. torch 2.13.0 在 Windows 有 c10.dll 加载 bug，必须固定 2.7.1（同上已固定）
# c. 运行任何 docling 命令需禁用 JIT（本机无 MSVC 编译器）：
#    TORCH_COMPILE_DISABLE=1
```

若项目在中文路径下，需要英文 junction 指向 venv（在**当前机器**验证过）：

```powershell
# 管理员权限（或普通 PowerShell 均可建 junction）
New-Item -ItemType Junction -Path C:\dp_venv_link -Target <项目根>\.venv
# 然后所有 docling 相关命令用 C:\dp_venv_link\Scripts\python.exe 运行
```

## 5. 验证

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
# 期望：167 passed, 1 xfailed（xfailed 为 golden 标注冲突显式登记，正常）
```

## 6. 常用命令

```powershell
# 回归测试
python -m pytest tests/ -q

# 重新生成全部 fixtures（需 .env 配置 MINERU_API_KEY）
python -m tools.make_fixtures --parser mineru --samples all
python -m tools.make_fixtures --parser fallback --samples all

# 单样例
python -m tools.make_fixtures --parser mineru --samples sdp-004

# 运行质量流水线
python -c "from document_parser.core.contracts import ParsedDocument; from quality import run_quality; doc = ParsedDocument.model_validate_json(open('tests/quality/fixtures/parsed_documents/sdp-004-mineru.json', encoding='utf-8').read()); print(run_quality(doc).quality_report.state)"
```

## 7. 换机交接清单

| 项目 | 是否入库 | 新机器操作 |
| --- | --- | --- |
| 代码（含 32 个 fixtures） | ✅ 已入库 | clone + checkout 即可 |
| 虚拟环境 .venv | ❌ 不入库 | 按第 2 节重建 |
| API 密钥 .env | ❌ 不入库 | 按第 3 节配置（key 需要自己带上/重新申请） |
| docling 特殊环境 | ❌ 不入库 | 需要时按第 4 节配置（可跳过） |
| 测试结果基线 | ✅ 代码内 | 第 5 节验证（167 passed） |

## 8. 开发协议速查

- 分支：只改 `feature/quality-layer`；公共契约（core/contracts.py）变更需三人评审
- 提交：小步勤提交、`feat(quality):` 风格、**默认不 push**
- 红线：不伪造证据、no-op 合法、verified 必须有证据、LLM 建议最高 inferred
- 决策记录：../quality/quality-decisions.md（D-01~D-16）
- 进展报告：../quality/quality-layer-progress.md
