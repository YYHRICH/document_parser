# Document Parser

`document_parser` 是知识中心统一的文档解析模块。它负责接收文件字节、完成必要的
格式标准化，并输出稳定的 `ParsedDocument`；Wiki 构建和业务批处理不属于本模块。

当前解析器固定为 Microsoft MarkItDown，对外 ID 为
`microsoft.markitdown`。业务代码只应从模块顶层导入公开类型：

```python
from modules.document_parser import DocumentParserGateway
```

## 处理流程

```text
原始文件
  → SimpleSourceInspector       识别扩展名和基础文件特征
  → DocumentConverter          必要时统一旧格式
      .doc → .docx
      .ppt → .pptx
  → MarkItDownParser           转换为 Markdown
  → block_builder              生成统一文档块
  → ParsedDocument             恢复原文件名和 file_type 后返回
```

格式转换位于 `core/`，MarkItDown 实现不包含 LibreOffice、Word 或 PowerPoint
逻辑。这样更换解析器时可以继续复用转换层，增加新转换器时也不需要修改
MarkItDown。

## 目录结构

```text
document_parser/
├─ __init__.py                    # 模块公开入口
├─ core/
│  ├─ contracts.py               # ParseRequest、ParsedDocument 等稳定协议
│  ├─ converter.py               # 格式转换抽象和旧版 Office 实现
│  ├─ gateway.py                 # 转换、解析和结果恢复的统一编排入口
│  └─ inspector.py               # 轻量文件特征识别
└─ parsers/
   └─ markitdown/
      ├─ markitdown.py           # MarkItDown 原生格式解析
      └─ block_builder.py         # Markdown 标题和段落切块
```

## 快速调用

```python
import mimetypes
from pathlib import Path

from modules.document_parser import DocumentParserGateway

source = Path("document.doc")
gateway = DocumentParserGateway.from_environment()
try:
    document = gateway.parse_file(
        source,
        file_type=mimetypes.guess_type(source.name)[0]
        or "application/octet-stream",
    )
finally:
    gateway.close()

print(document.markdown)
print(document.provenance.parse_duration_ms)
```

调用方可以直接提交 `.doc` 或 `.ppt`，不需要提前转换。临时转换文件会自动清理，
原文件不会被覆盖。

## 支持格式

MarkItDown 原生处理：

- PDF：`.pdf`
- Office：`.docx`、`.pptx`、`.xlsx`、`.xls`
- 文本和网页：`.md`、`.txt`、`.html`、`.htm`
- 结构化文本：`.csv`、`.json`、`.xml`
- 其他：`.zip`、`.epub`

core 转换层补充：

- `.doc → .docx`
- `.ppt → .pptx`

最终能力列表由 Gateway 合并，因此 `list_parsers()` 会同时返回原生格式和可转换
格式。

## 旧版 Office 转换

`LegacyOfficeConverter` 的选择顺序为：

1. 使用 `LIBREOFFICE_PATH` 指定的 LibreOffice。
2. 从系统 `PATH` 查找 `soffice` 或 `libreoffice`。
3. 检查 Windows、macOS 和 Linux 的标准安装位置。
4. Windows 未找到 LibreOffice 时，回退到 Microsoft Word 或 PowerPoint。

推荐部署 LibreOffice。Windows、Linux 和 macOS 的项目安装脚本都会在缺少它时
自动安装：

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

```bash
# Linux / macOS
bash ./install.sh
```

如果使用非标准安装目录，可以设置：

```text
LIBREOFFICE_PATH=/path/to/soffice
```

Windows 的 Microsoft Office 回退依赖 `pywin32`，已经通过 `pyproject.toml` 的
平台条件安装。

## ParsedDocument 主要字段

| 字段 | 作用 |
|---|---|
| `document_id` | 单次解析结果 ID |
| `filename` | 原始文件名；旧格式转换后仍保留原名称 |
| `file_type` | 标准文件类型，例如 `application/pdf` |
| `markdown` | Wiki 构建可直接使用的完整正文 |
| `blocks` | 按标题和段落拆分的结构化内容 |
| `assets` | 图片或附件；当前 MarkItDown 通常返回空列表 |
| `confidence` | 转换结果的基础有效性信息，不是业务质量偏好 |
| `provenance` | 解析器版本、转换方式、参数和耗时 |
| `schema_version` | 跨模块协议版本 |

### 耗时字段

耗时都位于 `document.provenance`：

| 字段 | 统计范围 |
|---|---|
| `format_conversion_duration_ms` | `.doc/.ppt` 转成新版格式的耗时；原生格式为 0 |
| `markitdown_duration_ms` | MarkItDown 生成 Markdown 的耗时 |
| `parse_duration_ms` | 前两段合计，不包括上传、排队、Wiki 构建和结果保存 |

旧版 Office 转换需要启动办公套件，冷启动通常是主要耗时。模块保持无状态，不在
这里缓存转换结果；若业务存在重复文件，应在 API 或业务层按文件哈希去重。

## 示例验证

```powershell
# 先修改文件顶部参数，再直接运行
python .\examples\document_parser\run_document_parser.py
```

文件顶部的 `EXECUTION_MODE` 选择 `batch/async`，`INPUT_MODE` 选择
`list/folder`；其他明文参数包括 `CONCURRENCY`、`RECURSIVE`、`DOCUMENT_LIST`、
`DOCUMENT_FOLDER` 和 `OUTPUT_DIRECTORY`。列表只放一个 Path 就是单文件验证。

顺序和异步调度统一复用 `parse_and_save()`。异步模式使用 `asyncio.to_thread`
调用同步公开入口，每个任务持有独立 Gateway；每份文档解析完成后立即写入 Markdown
和 JSON，不等待整个批次结束，因此不改变文档解析模块的单文档、无状态职责。

## 扩展方式

新增解析前格式转换时：

1. 在 `core/converter.py` 中实现 `DocumentConverter`。
2. 声明 `source_formats`。
3. 返回包含目标扩展名、转换器 ID 和耗时的 `ConversionResult`。
4. 将实现注入 `DocumentParserGateway(converters=(...))`。

新增或替换解析器时，应继续输出 `ParsedDocument`，并保持业务层只依赖
`DocumentParserGateway`。第三方对象、临时路径和厂商私有结果不能直接向外暴露。

## 维护约束

- 文档解析模块不包含 Wiki 构建、Query 或批量业务逻辑。
- 解析质量偏好由上层业务决定，不进入解析协议。
- 转换层只标准化文件格式，不生成 Markdown。
- MarkItDown 只处理原生格式，不直接调用 Office 软件。
- 第三方转换在受控子进程中运行，单文件失败不能锁死 API worker。
- 修改稳定字段含义时必须同步提升 `ParsedDocument.schema_version`。
