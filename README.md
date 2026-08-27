# 文档解析与质量处理平台

这是一个前后端分离的文档解析工作台。它接收 PDF、Office、图片、Markdown、HTML、CSV 和文本等输入，按照文件特征与运行策略选择解析器，把不同解析器的结果归一化为统一文档，再由独立质量层生成可追踪、可验证、可下载的交付包。

项目的重点不是单纯把文件转换成 Markdown，而是保留完整证据链：

```text
上传文件
  → 任务与幂等控制
  → 文件预检与路由决策
  → 解析器执行
  → 统一 ParsedDocument
  → 质量检查与安全修复
  → 质量门禁
  → 原始包 / 优化包 / 质量报告
  → 浏览器查看、定位和下载
```

## 主要能力

- 浏览器上传一个或多个文件，逐文件查看处理状态。
- 自动选择解析器，也可以手动指定解析器。
- 手动选择解析器时不会静默切换到其他解析器；失败会明确记录原因。
- 根据服务端权限决定是否显示“启用云端解析”选项。
- 支持本地解析器和可选的 MinerU 云端解析。
- 解析器结果统一转换为 `ParsedDocument`，质量层不依赖任何解析器私有对象。
- 质量层独立完成完整性、来源、标题、引用、表格和跨页关系检查。
- 对证据充分且风险可控的内容执行确定性修复，并保留修复前后哈希、目标、依据和复检结果。
- 对结构不明确、证据不足或表示冲突的内容保留原文，不通过猜测覆盖原始内容。
- 质量问题、修改记录和关系都保留页面、block、表格或正文行定位信息。
- 相同语义的问题和修改记录会合并，避免把一件问题重复展示成多条人工指令。
- 支持重试、重解析、任务血缘、同源结果比较和幂等请求。
- 支持原始解析包、优化交付包、质量报告和原生产物下载。
- 提供质量层 CLI、契约样例、离线质量基线和可选真实解析器验证。

## 系统边界

```text
┌──────────────────────────────┐
│ 浏览器 / 独立静态前端          │
│ Vite + HTML + JavaScript      │
│ 上传页 / 任务中心 / 文档详情    │
└──────────────┬───────────────┘
               │ HTTP / JSON / 文件下载
               │ /api/*
┌──────────────▼───────────────┐
│ FastAPI 后端                  │
│ 任务、存储、路由、编排、HTTP 投影 │
└──────────────┬───────────────┘
               │ Python 公共契约
┌──────────────▼───────────────┐
│ 解析与质量流水线               │
│ Parser → Normalizer → Quality │
└──────────────────────────────┘
```

前端不导入 Python 模块，后端也不通过模板渲染前端页面。开发时前端和后端由两个独立进程、两个独立端口提供服务；部署时前端可以放在 Nginx、CDN 或其他静态托管上，后端单独作为 API 服务部署。

前端与后端之间的唯一交互是公开 HTTP API：

- 前端通过 `/api/parsers` 读取解析器能力和云端权限。
- 前端通过 `/api/tasks` 创建异步处理任务。
- 前端通过任务接口轮询状态、读取预览和处理记录。
- 前端通过下载接口获取原始解析包或优化文档包。
- 服务端 token、原始文件路径和内部诊断信息不会进入浏览器响应。

## 目录结构

以下目录是当前项目的实际逻辑结构。缓存、构建结果和运行产物不属于源码目录，不应提交到版本库。

```text
document_parser/
├─ backend/                         # FastAPI 入口、任务、存储、下载和 HTTP 投影
│  ├─ app.py                        # HTTP API 路由与生命周期装配
│  ├─ main.py                       # Uvicorn ASGI 入口
│  ├─ schemas.py                    # 浏览器安全的请求/响应模型
│  ├─ storage.py                    # 文件系统持久化、完整性校验和产物读取
│  ├─ tasks.py                      # 任务聚合与文件状态投影
│  ├─ task_endpoints.py             # 多文件任务接口
│  ├─ task_archives.py              # 任务下载包
│  ├─ delivery.py                   # 业务交付准入判断
│  ├─ lineage.py                    # 重试/重解析血缘与同源比较
│  └─ reparse_recommendations.py    # 对外安全的重解析建议
├─ common/                          # 跨模块通用安全工具
├─ composition/                     # 生产组合根：Gateway 与跨层适配器
│  ├─ gateway.py                    # 解析器网关与路由接入
│  └─ reparse_recommendations.py    # ParseJob 到 routing 的组合适配
├─ core/                            # 公共契约、来源检查和文档包
│  ├─ contracts.py                  # ParsedDocument、QualityPackage 等公开模型
│  ├─ inspector.py                  # 上传文件预检
│  ├─ document_package.py            # ParsedDocument 包读写与完整性验证
│  └─ converter.py                   # Office 转换抽象
├─ routing/                         # 文件识别、能力快照、路由策略和云端权限
├─ parsers/                         # 解析器适配器
│  ├─ base.py                       # 适配器基类、原生产物读取和规范化入口
│  ├─ registry.py                   # 解析器注册表
│  ├─ ports.py                      # 解析器端口
│  ├─ markitdown/                   # Microsoft MarkItDown
│  ├─ docling/                      # Docling
│  ├─ mineru/                       # MinerU 本地/云端路径与安全边界
│  ├─ ocr/                          # RapidOCR
│  └─ anydoc/                       # 可选 AnyDoc 本地程序
├─ normalizers/                     # 原生解析结果到 ParsedDocument 的规范化
├─ orchestration/                   # job 状态机、队列、持久化编排和指标
├─ quality/                         # 独立质量层
│  ├─ api.py                        # run_quality、JSON 加载和质量包写出
│  ├─ pipeline.py                   # 规则、修复、复检、门禁和打包流水线
│  ├─ evidence/                     # 证据需求与能力协商
│  ├─ rules/                        # 质量规则
│  ├─ repairs/                      # 修复提案、策略、执行和复检
│  ├─ representations/              # 表格与文档表示清单
│  ├─ gates/                        # 质量门禁
│  ├─ builders/                     # CanonicalDocument 构建
│  └─ packaging/                    # 质量包、清单和哈希
├─ frontend/                        # Vite 多页面前端
│  ├─ index.html                    # 上传页
│  ├─ task-center.html              # 任务中心
│  ├─ document-detail.html          # 文档详情页
│  ├─ workbench.js/.css             # 上传页和任务中心主逻辑
│  ├─ document-detail.js/.css       # 文档详情、预览和修改记录
│  ├─ api-config.js                 # 独立部署时的 API 地址配置
│  ├─ vite.config.js                # 多入口构建和开发代理
│  ├─ assets/                       # 图标和第三方许可说明
│  └─ mockups/                      # 只用于设计评审的静态样例，不是主流程
├─ tests/                           # 自动化测试
│  ├─ api/                          # FastAPI、任务、存储、下载和安全测试
│  ├─ quality/                      # 质量规则、修复、契约和集成测试
│  ├─ e2e/                          # 真实解析器的可选验证
│  ├─ fixtures/                     # 规范化和适配器 fixture
│  └─ test_*.py                     # 公共契约、路由、网关和编排测试
├─ scripts/                         # 手工运行与验证工具
│  ├─ build_document_package.py     # 从 ParsedDocument JSON 构建文档包
│  ├─ run_adapter.py                # 运行单个适配器并写出文档包
│  ├─ run_real_parser_e2e.py        # 真实 Docling/MinerU 验证
│  └─ validate_contract_baseline.py # 固定契约样例校验
├─ benchmarks/                      # 离线质量基线
├─ datasets/                        # 合成/脱敏输入、标注和预期结果
├─ examples/                        # 契约样例和质量层验收用 TeX 样例
├─ docs/                            # 架构、规格、质量、运维和项目记录
│  ├─ architecture/
│  ├─ operations/
│  ├─ product/
│  ├─ project-records/
│  ├─ quality/
│  ├─ specs/
│  └─ assets/
├─ outputs/                         # 本地运行产物，自动生成，不提交
├─ start_frontend.bat               # Windows 一键启动前后端
├─ pyproject.toml                   # Python 包、依赖和打包配置
├─ requirements.txt                 # 直接安装依赖的清单
├─ pytest.ini                       # Pytest 测试目录和导入路径配置
└─ .gitignore                       # 缓存、构建物、密钥和运行产物忽略规则
```

### 不属于源码的目录

以下内容可以在本地重新生成，清理时不应当当作业务源码处理：

- `.venv/`：本地 Python 虚拟环境。为了方便开发保留，但不提交。
- `frontend/node_modules/`：前端依赖安装目录。删除后可用 `npm install` 重建。
- `frontend/dist/`：前端构建结果。
- `build/`、`document_parser.egg-info/`：Python 构建和打包中间物。
- `__pycache__/`、`.pytest_cache/`：解释器和测试缓存。
- `tmp/`：测试或渲染临时文件。
- `output/`、`outputs/`：本地生成的 PDF、任务包、调试结果和 API 存储。

## 端到端处理流程

### 上传和任务

浏览器通过 `POST /api/tasks` 上传一个或多个文件。后端会：

1. 读取文件并限制单文件大小。
2. 校验文件名、扩展名、内容类型和压缩包解压预算。
3. 解析 `options_json`，只接受公开的路由偏好和云端偏好。
4. 根据 `Idempotency-Key` 判断是否是同一个请求的重放。
5. 为每份文件创建独立 parse job，并把它们聚合到一个 task。
6. 把未完成的 job 放入进程内队列。

任务和 parse job 都持久化到文件系统。服务重启后，未领取的 queued job 会恢复；执行中断的 job 会被标记为可重试的失败，避免把未知的半成品当作成功结果。

### 路由和解析

`DocumentParserGateway` 位于 `composition/`，负责把路由、适配器和规范化连接起来。`core/` 只提供公共契约、转换和文档包能力。解析器能力由运行时探测得到，不能只根据 Python 包是否安装来判断。

当前适配器：

| parser_id | 输入范围 | 网络 | 说明 |
|---|---|---:|---|
| `microsoft.markitdown` | 文本、Markdown、HTML、CSV、JSON、XML、Office、PDF 等 | 否 | 通用本地回退路径 |
| `docling` | PDF、Office、HTML、Markdown、文本等 | 否 | 依赖本地 Docling 环境 |
| `mineru` | PDF、JPG、JPEG、PNG | 可选 | 支持本地运行时或云端服务 |
| `ocr` | JPG、JPEG、PNG | 否 | RapidOCR 本地图像解析 |
| `anydoc` | 旧 Office、CSV 等 | 否 | 依赖本地 AnyDoc 可执行程序 |

路由策略：

- `local_first`：优先使用本地解析器，适合离线开发和默认运行。
- `quality_first`：在允许云端且能力可用时，对复杂图片或 PDF 更倾向于高质量路径。
- 自动路由可以根据能力继续尝试 fallback。
- 手动路由要求请求的解析器与实际选择一致，并关闭静默 fallback。
- 请求不能通过浏览器字段覆盖 token、服务端 URL、信任主机或原生产物目录。

### 统一文档

解析器的私有结果先进入 `normalizers/`，最终交给质量层的只有 `ParsedDocument`。统一文档至少包含：

- 文档身份、文件名、类型、大小和来源哈希；
- Markdown 正文；
- 有稳定身份的 blocks 和阅读顺序；
- 标题层级、页码、bbox 和来源锚点；
- 表格、单元格、资源和 OCR span；
- 原生产物引用及 SHA-256；
- 解析器、模型、参数、耗时和 fallback 记录；
- 每项证据能力的状态、粒度和缺失原因。

缺失的证据必须声明为 `partial`、`unavailable` 或 `failed`，不能用猜测值填充。

### 质量层和交付

质量层入口是：

```python
from quality import run_quality

quality_package = run_quality(parsed_document)
```

它只依赖 `core/contracts.py` 中的公共契约，不读取路由状态、不调用解析器、不依赖 FastAPI、不访问浏览器，也不需要 LLM。

质量包保存原始文档和优化结果的并行关系：

```text
ParsedDocument
  ├─ document.md                  # 原始/规范化正文
  ├─ parsed_document.json         # 统一文档与来源证据
  ├─ native/                      # 解析器原生产物
  └─ assets/                      # 图片及其他资源

QualityPackage
  ├─ optimized.md                 # 安全修复后的正文
  ├─ canonical_document.json      # 规范化 block、关系、表格绑定
  ├─ quality_report.json          # 问题、修复、能力和门禁
  └─ package_manifest.json        # 核心文件哈希
```

## 质量层说明

### 检查范围

| 检查领域 | 规则 | 关注内容 |
|---|---|---|
| 内容完整性 | `QL-CONT-001`、`QL-CONT-002`、`QL-CONT-003` | block 是否存在、顺序是否冲突、类型和内容是否一致 |
| 来源证据 | `QL-PROV-001` 至 `QL-PROV-004` | block 来源、锚点、原生产物和能力缺失原因 |
| 标题结构 | `QL-HDG-001`、`QL-HDG-004` | 标题字段、编号层级、父子关系和层级不确定性 |
| 引用绑定 | `QL-REF-001`、`QL-REF-004` | 参考索引、正文 marker、引用关系和缺失编号 |
| 表格结构 | `QL-TBL-004`、`QL-TBL-006` | 完整列路径、行键、字段绑定和来源 |
| 跨页表格 | `QL-TBL-007`、`QL-TBL-008` | 续表关系、表头继承和列结构漂移 |

质量状态为：

- `pass`：没有阻断问题，证据和门禁满足放行条件。
- `pass_with_warnings`：可以交付，但报告中保留提醒。
- `manual_review_required`：内容可生成，但存在需要人工确认的结构或关系。
- `reparse_required`：当前解析证据不足，报告会给出重解析建议。
- `rejected`：质量或完整性风险不允许交付。

质量层不会把所有问题都变成人工核对指令。一个问题的处理原则是：

1. 同一文档、同一规则、同一目标和同一证据的重复发现先合并。
2. 页面、block、表格或正文行放入同一条问题的定位证据中。
3. 能确定修复的内容进入自动修复白名单。
4. 只能确认“存在异常”但不能确认正确答案的内容保留原文并降级为相应质量状态。
5. 跨页续表作为关系和证据处理，不把每一页重复生成一条相同警告。
6. 引用、标题和表格绑定必须带稳定 ID 和来源证据；证据不足时不能伪装为 `verified`。

### 自动修复白名单

当前自动修复仅覆盖确定性、可回滚、前置哈希匹配且可以复检的场景：

| 修复规则 | 内容 | 不能做什么 |
|---|---|---|
| `QL-RPR-001` | 清理不影响语义的行尾空白 | 不修改 Markdown 硬换行和代码围栏语义 |
| `QL-RPR-002` | 修正 Markdown 表格分隔行的列数和对齐 | 不猜测缺失单元格的业务内容 |
| `QL-RPR-003` | 把结构完整、无 `rowspan`/`colspan` 的 HTML 表格转换为 Markdown | 不把复杂合并表格强行展开 |

每条 `applied_repair` 必须包含：

- 中文标题和说明；
- 修复规则 ID；
- 目标 block 或 table；
- 页码、正文行或来源锚点；
- 修复前后内容摘要和 SHA-256；
- 使用的证据与策略；
- 重新运行受影响规则后的验证结果。

### 表格和跨页处理

- 无合并单元格、HTML 结构完整且表示一致的表格可以自动规范化。
- 含 `rowspan` 或 `colspan` 的表格保留原始 HTML、cells 和来源，不进行有损覆盖。
- 表示冲突、目标不唯一、HTML 不完整或列路径无法确认时，不执行自动修改。
- 跨页续表只在相邻页、结构证据和表头信息满足条件时建立关系。
- 列结构漂移会记录两端表格、页码、差异原因和证据，不把两个表误合成一个。

## Windows 快速开始

### 准备环境

要求：

- Python 3.11 或更高版本；
- Node.js 18 或更高版本；
- Windows PowerShell；
- 若使用特定解析器，还需要对应的本地运行时或系统依赖。

从项目根目录执行：

```powershell
cd E:\zgyd_document\document_parser

# 使用现有虚拟环境安装服务端和测试依赖
.\.venv\Scripts\python.exe -m pip install -e ".[server,test]"

# 如需安装所有可选解析器
.\.venv\Scripts\python.exe -m pip install -e ".[all-parsers,server,test]"

# 安装前端依赖
cd frontend
npm install
cd ..
```

如果还没有 `.venv`，先用 Python 创建虚拟环境，再执行上面的安装命令：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[server,test]"
```

### 一键启动

```powershell
cd E:\zgyd_document\document_parser
.\start_frontend.bat
```

启动脚本会：

1. 读取根目录 `.env`；
2. 检查 Python、Uvicorn、Vite 和前端依赖；
3. 启动或复用后端 API；
4. 启动 Vite 开发服务器；
5. 等待健康检查和前端页面就绪；
6. 打开浏览器。

默认地址：

| 服务 | 地址 |
|---|---|
| 后端 API | `http://127.0.0.1:8011` |
| 前端 | `http://127.0.0.1:5174` |
| 健康检查 | `http://127.0.0.1:8011/api/health` |
| FastAPI 文档 | `http://127.0.0.1:8011/docs` |

健康检查成功时返回：

```json
{"status": "ok"}
```

### 端口冲突

启动脚本支持通过环境变量覆盖端口：

```powershell
$env:DOCUMENT_PARSER_PORT = "8012"
$env:FRONTEND_PORT = "5175"
$env:VITE_DEV_API_ORIGIN = "http://127.0.0.1:8012"
.\start_frontend.bat
```

如果只手动启动前端，后端不在默认端口时必须设置 `VITE_DEV_API_ORIGIN`，否则 Vite 的 `/api` 代理仍会指向默认后端地址。

### 手动启动

后端终端：

```powershell
cd E:\zgyd_document\document_parser
$env:PYTHONPATH = "$PWD;$PWD\.."
.\.venv\Scripts\python.exe -m uvicorn document_parser.backend.main:app `
  --app-dir .. --host 127.0.0.1 --port 8011
```

前端终端：

```powershell
cd E:\zgyd_document\document_parser\frontend
npm run dev -- --host 127.0.0.1 --port 5174
```

## 配置

### 根目录 `.env`

`.env` 只放本机配置，不提交 token 和密钥。启动脚本会读取它；已经存在的进程环境变量优先。

| 变量 | 默认或说明 |
|---|---|
| `DOCUMENT_PARSER_ALLOW_CLOUD` | 默认 `false`；是否允许服务端使用云端解析 |
| `DOCUMENT_PARSER_ROUTE_PROFILE` | `local_first` 或 `quality_first` |
| `DOCUMENT_PARSER_LIBREOFFICE_AVAILABLE` | 默认 `false`；是否声明 LibreOffice 能力可用 |
| `MINERU_API_TOKEN` | MinerU 服务端 token，仅后端读取 |
| `MINERU_API_BASE_URL` | MinerU API 地址 |
| `MINERU_API_TRUSTED_HOSTS` | 云端提交结果跳转和下载的信任主机，逗号分隔 |
| `MINERU_TASK_TIMEOUT_SECONDS` | MinerU 任务等待超时 |
| `MINERU_DOWNLOAD_TIMEOUT_SECONDS` | MinerU 结果下载超时 |
| `MINERU_MAX_REDIRECTS` | MinerU 下载最大跳转次数 |
| `DOCLING_EXECUTABLE` | Docling 可执行程序路径；为空时自动探测 |
| `ANYDOC_EXECUTABLE` | AnyDoc 可执行程序路径；为空时自动探测 |
| `LIBREOFFICE_PATH` | LibreOffice 安装路径，可选 |
| `DOCUMENT_PARSER_FRONTEND_ORIGINS` | 独立部署前端的 CORS origin，逗号分隔 |

启动脚本兼容旧的 `MINERU_API_KEY` 名称，但新配置应使用 `MINERU_API_TOKEN`。

### 前端 `.env`

前端配置文件为 `frontend/.env.example` 的同类文件：

| 变量 | 作用 |
|---|---|
| `VITE_API_BASE_URL` | 构建时写入浏览器的后端 API 根地址；同源或开发代理时留空 |
| `VITE_DEV_API_ORIGIN` | Vite 开发服务器的 `/api` 代理目标 |

前端环境变量会进入浏览器构建产物，不能放 token、密码或任何服务端秘密。

### 云端解析显示规则

云端解析是服务端权限，不是前端自行决定的开关：

```powershell
$env:DOCUMENT_PARSER_ALLOW_CLOUD = "true"
$env:MINERU_API_TOKEN = "<server-token>"
$env:DOCUMENT_PARSER_ROUTE_PROFILE = "quality_first"
.\start_frontend.bat
```

重启后端后检查：

```powershell
curl.exe http://127.0.0.1:8011/api/parsers
```

响应中的 `selection_policy.cloud_parsers_enabled` 为 `true` 时，上传页才显示并启用“启用云端解析”。前端勾选只表示用户希望使用云端，最终是否能用仍由后端策略、token、解析器能力和请求参数共同决定。

## API

接口可以在 `/docs` 查看 OpenAPI 交互文档。浏览器主流程使用任务接口；`/api/jobs` 和 `/api/parses` 主要用于编程调用和兼容旧客户端。

### 基础接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/parsers` | 解析器能力、不可用原因和云端策略 |
| `GET` | `/api/metrics` | 只读任务运行汇总 |

### 浏览器任务接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/tasks` | 上传一个或多个文件并创建任务 |
| `GET` | `/api/tasks/{task_id}` | 获取任务和文件状态 |
| `GET` | `/api/tasks/{task_id}/events` | 获取任务状态事件 |
| `GET` | `/api/tasks/{task_id}/files/{task_file_id}` | 获取单文件详情、质量摘要、问题和修改记录 |
| `GET` | `/api/tasks/{task_id}/files/{task_file_id}/preview?view=original` | 原始预览 |
| `GET` | `/api/tasks/{task_id}/files/{task_file_id}/preview?view=optimized` | 优化预览 |
| `POST` | `/api/tasks/{task_id}/files/{task_file_id}/retry` | 重试失败文件 |
| `POST` | `/api/tasks/{task_id}/files/{task_file_id}/reparse` | 使用新的解析选择重解析 |
| `GET` | `/api/tasks/{task_id}/downloads/original` | 下载原始解析包 |
| `GET` | `/api/tasks/{task_id}/downloads/optimized` | 下载优化后文档包 |

创建任务时使用 multipart form：

- `files`：一个或多个上传文件；
- `parser_id`：可选的解析器 ID；
- `options_json`：可选，例如 `{"allow_cloud": false, "route_profile": "local_first"}`；
- `Idempotency-Key`：建议由客户端提供，用于安全重放。

示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8011/api/tasks" `
  -H "Idempotency-Key: readme-task-demo" `
  -F "files=@.\datasets\shared-dev-v1\files\technical_report_references_positive.pdf" `
  -F 'options_json={"allow_cloud":false,"route_profile":"local_first"}'
```

返回 `task_id` 后轮询：

```powershell
curl.exe "http://127.0.0.1:8011/api/tasks/<task_id>"
curl.exe "http://127.0.0.1:8011/api/tasks/<task_id>/events"
```

### Job 兼容接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/jobs` | 单文件异步解析，返回 `202` |
| `GET` | `/api/jobs/{parse_id}` | 查看 job 状态 |
| `GET` | `/api/jobs/{parse_id}/events` | 查看 job 事件 |
| `POST` | `/api/jobs/{parse_id}/retry` | 创建重试子 job |
| `DELETE` | `/api/jobs/{parse_id}` | 取消尚未开始执行的 job |
| `GET` | `/api/jobs/{parse_id}/lineage` | 查看重试/重解析血缘 |
| `GET` | `/api/jobs/compare?left=...&right=...` | 比较同一来源的两个 job |
| `GET` | `/api/jobs/{parse_id}/reparse-recommendations` | 查看重解析建议 |

### 解析结果和质量包接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/parses` | 同步兼容接口；新客户端优先使用异步任务接口 |
| `GET` | `/api/parses/{parse_id}` | 读取 ParsedDocument |
| `GET` | `/api/parses/{parse_id}/quality-package` | 读取 QualityPackage |
| `GET` | `/api/parses/{parse_id}/artifacts` | 列出已注册产物 |
| `GET` | `/api/parses/{parse_id}/artifacts/{artifact_path}` | 读取指定产物 |
| `GET` | `/api/parses/{parse_id}/download` | 下载完整解析包 |
| `GET` | `/api/parses/{parse_id}/delivery` | 下载面向业务的优化交付包 |
| `POST` | `/api/parses/{parse_id}/reparse` | 从持久化原始文件创建重解析子 job |

外部客户端默认不能直接写入质量包。`POST /api/parses/{parse_id}/quality-package` 仅作为受信迁移钩子，在应用显式允许时才开放。

常见状态码：

- `400`：请求参数、上传格式或选项无效；
- `403`：服务端策略禁止当前云端能力；
- `404`：任务、文件或产物不存在；
- `409`：幂等冲突、来源不一致、状态冲突或产物校验失败；
- `413`：超过上传、解压或任务文件数量限制；
- `503`：解析器、能力探测或重解析建议暂时不可用。

默认限制：单文件约 50 MiB，压缩包解压后约 250 MiB，单任务最多 20 份文件。生产环境应在网关增加身份认证、限流、审计和 HTTPS；应用内 CORS 只控制跨源范围，不等于用户认证。

## 前端页面

### 上传页 `frontend/index.html`

- 选择或拖放多个文件；
- 从 `/api/parsers` 加载解析器能力；
- 根据服务端 `cloud_parsers_enabled` 显示云端解析选项；
- 在提交前校验文件数量和选择状态；
- 创建任务后跳转到任务中心。

### 任务中心 `frontend/task-center.html`

- 展示每个文件的排队、解析、质量检查、成功或失败状态；
- 展示质量状态和修复数量；
- 支持刷新、重试和重解析；
- 进入某个文件的文档详情；
- 下载原始解析包或优化文档包。

### 文档详情 `frontend/document-detail.html`

- 切换优化后内容和原始解析；
- 展示质量状态、问题数量和修复数量；
- 展开中文修改记录；
- 显示规则、处理依据和具体定位；
- 点击记录定位到正文行；
- 对没有安全修复的内容显示保留原文和质量提示。

当前三个入口使用 `workbench.js`、`workbench.css`、`document-detail.js` 和 `document-detail.css`。`frontend/mockups/` 是设计评审样例，不是生产入口。

构建前端：

```powershell
cd E:\zgyd_document\document_parser\frontend
npm run build
```

构建结果会写入 `frontend/dist/`，该目录是生成物，验证结束后可以删除。

## 质量层 CLI

质量层可以不启动后端，直接读取一个 `ParsedDocument` JSON：

```powershell
cd E:\zgyd_document\document_parser

# 打印摘要
.\.venv\Scripts\python.exe -m quality `
  --input .\tests\quality\fixtures\parsed_documents\sdp-004-mineru.json

# 打印完整 QualityPackage JSON
.\.venv\Scripts\python.exe -m quality `
  --input .\tests\quality\fixtures\parsed_documents\sdp-004-mineru.json `
  --json

# 查看修复提案、策略、执行、复检和表格审计
.\.venv\Scripts\python.exe -m quality `
  --input .\tests\quality\fixtures\parsed_documents\sdp-001-mineru.json `
  --show-repairs

# 写出优化包；目标目录应是新的或明确允许覆盖的目录
.\.venv\Scripts\python.exe -m quality `
  --input .\tests\quality\fixtures\parsed_documents\sdp-004-mineru.json `
  --output-dir .\outputs\quality-debug
```

已有输出目录默认拒绝覆盖，只有明确确认时才使用 `--replace-existing`。

## 脚本工具

```powershell
# 校验三份公共契约样例及它们之间的身份、来源和表格连接
.\.venv\Scripts\python.exe .\scripts\validate_contract_baseline.py

# 从 ParsedDocument JSON 构建统一文档包
.\.venv\Scripts\python.exe .\scripts\build_document_package.py `
  .\examples\contracts\parsed_document.json `
  .\outputs\document-package

# 运行一个适配器并写出文档包
.\.venv\Scripts\python.exe .\scripts\run_adapter.py `
  .\datasets\shared-dev-v1\files\technical_report_references_positive.pdf `
  .\outputs\adapter-run `
  --parser-id docling

# 运行离线质量基线
.\.venv\Scripts\python.exe -m benchmarks.quality_baseline `
  --glob ".\tests\quality\fixtures\parsed_documents\*.json"
```

真实解析器 E2E 是显式选择的运行操作，不会把占位输出当成真实解析证据：

```powershell
# 只做能力和模型预检，不调用解析器
.\.venv\Scripts\python.exe .\scripts\run_real_parser_e2e.py `
  --dry-run

# 使用本地运行时执行指定 PDF；缺少运行时会明确失败或跳过
.\.venv\Scripts\python.exe .\scripts\run_real_parser_e2e.py `
  .\datasets\shared-dev-v1\files\procurement_table_positive.pdf `
  --parser all --mineru-mode local --allow-skips
```

真实云端调用必须由操作者显式配置 token 和服务端云端权限，并注意费用、数据合规和网络安全。

## 测试

### 全量自动化测试

建议使用不写 Python 字节码、不生成 Pytest 缓存的方式运行：

```powershell
cd E:\zgyd_document\document_parser
$env:PYTHONDONTWRITEBYTECODE = "1"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

测试覆盖：

- 公共契约和固定样例；
- 路由策略、能力矩阵和云端权限；
- 解析器适配器和规范化；
- 质量规则、证据协商、稳定 ID、修复和复检；
- 质量门禁、质量包和产物哈希；
- FastAPI 任务、job、重试、重解析、血缘、下载和完整性；
- 前端入口引用和 API 边界；
- 安全路径、URL 跳转和敏感参数过滤；
- 离线质量基线；
- 真实解析器验证脚本的证据判断。

### 定向检查

```powershell
# 契约样例
.\.venv\Scripts\python.exe -m pytest tests\test_contract_examples.py -q -p no:cacheprovider

# 质量层
.\.venv\Scripts\python.exe -m pytest tests\quality -q -p no:cacheprovider

# API 和存储
.\.venv\Scripts\python.exe -m pytest tests\api -q -p no:cacheprovider

# 真实解析器验证逻辑，不代表真的调用本地解析器
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_execution_evidence.py -q -p no:cacheprovider
```

### 浏览器验收路径

启动前后端后，按下面顺序验证：

1. 打开上传页，确认能加载解析器列表。
2. 服务端关闭云端时，确认不显示或禁用“启用云端解析”。
3. 服务端开启云端并重启后端，确认上传页显示云端选项。
4. 上传测试 PDF，确认任务中心显示文件状态并最终进入详情页。
5. 在详情页切换原始内容和优化内容。
6. 查看质量状态、问题、中文修改记录和定位按钮。
7. 对存在安全修复的样例，确认修复记录包含目标、依据和复检信息。
8. 对跨页表格、合并单元格、重复顺序和缺失引用样例，确认同一问题合并展示，原文没有被猜测覆盖。
9. 分别下载原始解析包和优化文档包，并检查其中的 manifest、quality report、canonical document 和原生产物。
10. 修改下载包或质量产物后再次读取，确认完整性校验拒绝被篡改的结果。

## 产物和存储

后端默认把 API 运行数据写入 `outputs/api`。该目录会在第一次运行时创建：

```text
outputs/api/
├─ .jobs/                         # 单个 parse job 的控制面元数据
├─ .tasks/                        # 多文件任务聚合状态
├─ .staging/                      # 上传和提交过程的临时文件
└─ <parse_id>/
   ├─ source/original.<ext>       # 原始上传文件
   ├─ document.md                 # 原始/规范化 Markdown
   ├─ parsed_document.json         # ParsedDocument
   ├─ native/                     # 原生产物
   ├─ assets/                     # 图片和附件
   ├─ optimized.md                # 优化正文
   ├─ canonical_document.json     # 规范化文档图
   ├─ quality_report.json         # 质量问题、修复和门禁
   ├─ package_manifest.json       # 质量包清单与哈希
   ├─ quality_package.json        # 持久化质量包
   ├─ revision.json               # 前端修改记录投影
   └─ artifact_manifest.json      # 外层产物清单
```

完整解析包和业务交付包有不同用途：

- 原始解析包用于调试、追踪和复现，可能包含原生产物和诊断证据。
- 优化文档包用于下游业务消费，包含优化正文、规范化文档、质量报告和必要元数据。
- 质量状态不是简单的“有问题/没问题”布尔值；它决定交付提示、是否需要重解析，以及前端应该如何引导用户。

## 公共契约和修改规则

公共契约的唯一事实源是 `core/contracts.py`。模块边界如下：

- 路由层生产 `RoutingDecision`。
- 解析器和规范化层生产 `ParsedDocument`。
- 质量层消费 `ParsedDocument`，生产 `QualityPackage`。
- 后端只负责编排、持久化、校验和 HTTP 投影。
- 前端只消费公开 API，不读取内部文件系统和 Python 对象。

修改公共字段时，必须同时检查：

1. `core/contracts.py`；
2. `examples/contracts/` 固定样例；
3. 对应测试；
4. 后端响应投影；
5. 前端字段兼容；
6. `docs/specs/` 和相关架构说明。

质量规则和修复规则的 ID 是稳定标识，不应为了改文案而更换。新增修复必须先证明：

- 目标是唯一且可以精确定位；
- 前置内容哈希仍然匹配；
- 修复不会猜测业务内容；
- 修复后重新运行受影响规则能够得到稳定结果；
- 失败时原始内容仍然可以恢复。

## 故障排查

### 前端页面打开但接口失败

确认后端健康检查：

```powershell
curl.exe http://127.0.0.1:8011/api/health
```

如果前端端口或后端端口被占用，重新设置 `FRONTEND_PORT`、`DOCUMENT_PARSER_PORT` 和 `VITE_DEV_API_ORIGIN`。手动启动 Vite 时尤其要检查代理目标。

### 云端选项不显示

依次确认：

1. 根目录 `.env` 中 `DOCUMENT_PARSER_ALLOW_CLOUD=true`；
2. `MINERU_API_TOKEN` 已配置在后端进程环境，而不是前端环境；
3. 修改配置后已重启后端；
4. `/api/parsers` 的 `selection_policy.cloud_parsers_enabled` 为 `true`；
5. 浏览器没有缓存旧页面，必要时刷新页面。

### 质量层没有自动修改

先区分三种情况：

- 输入没有命中自动修复白名单，原文保持不变是正确行为；
- 证据能力不足或目标不唯一，系统应生成质量提示而不是猜测修改；
- 输入确实包含行尾空白、可安全对齐的表格分隔线或简单 HTML 表格时，才可能产生 `applied_repairs`。

建议直接使用质量层 CLI 的 `--show-repairs` 查看提案、策略、执行和复检，而不是只看前端摘要。

### 任务被标记失败

查看任务的公开状态和事件接口。后端不会把内部路径、token 或原始异常堆栈直接返回给浏览器；需要详细诊断时检查服务端日志和本地任务包。可重试的失败会带有 `retryable=true`，来源完整性失败、策略拒绝和不支持格式通常不能通过重试解决。

### 清理本地生成物

以下命令只适用于确认不需要保留本地运行结果时：

```powershell
# 只删除可重新生成的本地目录；不要删除 .venv 和 node_modules
.\.venv\Scripts\python.exe -c "from pathlib import Path; import shutil; root=Path.cwd(); [shutil.rmtree(root/n, ignore_errors=True) for n in ['build','document_parser.egg-info','output','outputs','tmp','frontend/dist']]"
```

如果需要保留某次任务结果或验收报告，请先复制到项目外的归档位置。源码、测试 fixture、合成数据和 `docs/` 不属于清理范围。

## 文档入口

- `docs/README.md`：文档索引。
- `docs/architecture/`：系统边界、契约和解析器接入设计。
- `docs/quality/`：质量规则、修复策略和质量层工作记录。
- `docs/operations/`：环境配置、真实解析器和端到端运行说明。
- `docs/specs/`：规格和协作契约。
- `docs/project-records/`：项目记录和验证报告。
- `examples/quality-layer-showcase.tex`：用于展示质量层修复、跨页表格、引用和来源证据的 TeX 测试文件。
- `examples/contracts/`：路由、统一文档和质量包固定样例。

README 只描述当前代码的使用边界和运行方式；具体实现以源码、测试和 `core/contracts.py` 为准。所有本地生成物都可以重新生成，不应把它们当作项目源码或发布内容。
