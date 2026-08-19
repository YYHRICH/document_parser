# 模型选择与路由

本模块把前期实测结论转换为可执行的 `RoutingDecision 1.0`。它只选择解析器，
不执行 Docling、AnyDoc 或 MinerU，也不判断最终质量。

稳定解析器 ID：

- `docling`：Docling，图片或扫描件通过 RapidOCR；
- `anydoc`：AnyDoc，重点处理旧 Office 和现代 Office 回退；
- `mineru`：MinerU 精准解析 API；
- `passthrough`：项目内置 UTF-8 原文直通，仅用于 Markdown/TXT。

公开开关：

- `route_profile=local_first|quality_first`；
- `allow_cloud=true|false`；
- `libreoffice_available=true|false`；
- `parser_id=<稳定 ID>`，非空时进入手动模式且禁止静默 fallback。

Token 通过 `ModelRouter.from_environment(mineru_api_token=...)` 或环境变量
`MINERU_API_TOKEN` 注入，只用于能力检查，不写入决策。
