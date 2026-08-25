"""MinerU 云 API 解析适配器（开发期自建，等朱的正式 Adapter 到位后替换）。

把 MinerU 云 API 的输出转换为公共 ``ParsedDocument 2.2``。

使用流程（官方 v4 API）：
1. POST /file-urls/batch 获取签名上传 URL；
2. PUT 上传文件字节；
3. GET /extract-results/batch/{batch_id} 轮询任务状态；
4. 任务完成后下载 zip，解压读取 full.md 与 content list JSON；
5. 转换为 ParsedDocument。

API key 从环境变量 ``MINERU_API_KEY`` 读取，不写入代码、不写入日志。
"""

from __future__ import annotations

import io
import json
import os
import re
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import requests

from document_parser.domain.model.contracts import (
    DocumentBlock,
    ParsedDocument,
    ParsedTable,
    TableCell,
    BlockKind,
    EvidenceAvailability,
    EvidenceCapability,
    ParseConfidence,
    ParserProvenance,
    RoutingMode,
    SourceAnchor,
)

BASE_URL = "https://mineru.net/api/v4"


class MinerUCloudError(RuntimeError):
    """MinerU 云 API 调用失败。"""


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _require_ok(payload: dict, context: str) -> dict:
    """统一处理业务响应格式，认证失败等网关错误抛出异常。"""
    if not isinstance(payload, dict):
        raise MinerUCloudError(f"{context}: 响应不是 JSON 对象: {payload!r:.200}")
    if payload.get("code") not in (0, None) or payload.get("success") is False:
        raise MinerUCloudError(
            f"{context}: API 返回错误 {payload.get('msgCode', '')} {payload.get('msg', payload)}"
        )
    data = payload.get("data")
    if data is None:
        raise MinerUCloudError(f"{context}: 响应缺少 data 字段: {payload!r:.200}")
    return data


def _get_api_key() -> str:
    api_key = os.environ.get("MINERU_API_KEY", "").strip()
    if not api_key:
        api_key = _load_dotenv().get("MINERU_API_KEY", "").strip()
    if not api_key:
        raise MinerUCloudError(
            "未设置 MINERU_API_KEY（环境变量或仓库根 .env）。请在 mineru.net 申请 token 后配置。"
        )
    return api_key


def _load_dotenv() -> dict[str, str]:
    """轻量读取仓库根 .env（不引入 python-dotenv 依赖）。"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def upload_file(
    source: Path,
    *,
    api_key: str | None = None,
    is_ocr: bool = False,
    model_version: str = "pipeline",
    enable_formula: bool = True,
    enable_table: bool = True,
    timeout: int = 120,
) -> str:
    """上传单个文件，返回 batch_id。

    官方流程：POST /file-urls/batch 获取签名 URL，再 PUT 上传。
    """
    api_key = api_key or _get_api_key()
    headers = _auth_headers(api_key)
    files_payload = [
        {
            "name": source.name,
            "is_ocr": is_ocr,
            "model_version": model_version,
        }
    ]
    body = {
        "enable_formula": enable_formula,
        "enable_table": enable_table,
        "files": files_payload,
    }
    resp = requests.post(
        f"{BASE_URL}/file-urls/batch",
        json=body,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = _require_ok(resp.json(), "获取上传 URL")

    batch_id = data.get("batch_id")
    if not batch_id:
        raise MinerUCloudError(f"响应缺少 batch_id: {data!r:.200}")
    file_urls = data.get("file_urls") or []
    # 实测：file_urls 是字符串列表（签名上传 URL），不是 dict 列表
    upload_url = None
    for item in file_urls:
        if isinstance(item, str):
            upload_url = item
            break
        if isinstance(item, dict) and item.get("file_name") == source.name:
            upload_url = item.get("upload_url") or item.get("file_url")
            break
    if not upload_url:
        raise MinerUCloudError(f"响应缺少 {source.name} 的上传地址: {data!r:.400}")

    # 官方要求 PUT 上传时不带 Content-Type
    with source.open("rb") as fh:
        put_headers = {"Authorization": f"Bearer {api_key}"}
        put_resp = requests.put(upload_url, data=fh, headers=put_headers, timeout=timeout * 2)
        if put_resp.status_code not in (200, 201, 204):
            raise MinerUCloudError(
                f"上传失败 status={put_resp.status_code}: {put_resp.text[:200]}"
            )
    return batch_id


def poll_batch(
    batch_id: str,
    *,
    api_key: str | None = None,
    poll_interval: float = 3.0,
    max_wait_seconds: float = 600.0,
) -> dict:
    """轮询批量任务直到全部完成或失败，返回单个结果条目。"""
    api_key = api_key or _get_api_key()
    headers = _auth_headers(api_key)
    deadline = time.monotonic() + max_wait_seconds
    while True:
        resp = requests.get(
            f"{BASE_URL}/extract-results/batch/{batch_id}",
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = _require_ok(resp.json(), "查询任务状态")
        # 实测响应字段为 extract_result（兼容 results 旧字段）
        results = data.get("extract_result") or data.get("results") or []
        if results:
            result = results[0]
            state = (result.get("state") or "").lower()
            if state == "done":
                return result
            if state in {"failed", "cancelled"}:
                raise MinerUCloudError(
                    f"解析任务失败: {result.get('err_msg') or result}"
                )
        if time.monotonic() >= deadline:
            raise MinerUCloudError(f"等待任务完成超时（>{max_wait_seconds}s），batch_id={batch_id}")
        time.sleep(poll_interval)


def download_and_extract(
    result: dict,
    *,
    work_dir: Path,
    timeout: int = 300,
    retries: int = 4,
) -> Path:
    """下载结果 zip 并解压到 work_dir，返回解压目录。

    网络不稳时自动重试（SSL 断连常见）。
    """
    zip_url = result.get("full_zip_url")
    if not zip_url:
        raise MinerUCloudError(f"结果缺少 full_zip_url: {result!r:.200}")
    extract_dir = work_dir / "mineru_output"
    extract_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extract_dir / "result.zip"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            _download_with_curl(zip_url, zip_path, timeout=timeout)
            break
        except MinerUCloudError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2.0 * attempt)
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        raise MinerUCloudError(
            f"下载结果 zip 失败（{retries} 次尝试）: {last_error}"
        )
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    return extract_dir


def _download_with_curl(url: str, dest: Path, timeout: int) -> None:
    """用系统 curl 下载（本机 OpenSSL 栈与 CDN 协商不稳，requests 直连失败）。

    优先 curl.exe（Windows 10+ 自带）；失败时退回 requests。
    """
    import shutil
    import subprocess

    curl = shutil.which("curl")
    if curl:
        result = subprocess.run(
            [curl, "-sS", "-L", "-m", str(timeout), "-o", str(dest), url],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            return
    # 兜底：requests 直连
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def _find_content_list(extract_dir: Path) -> dict | None:
    """在解压目录中查找 MinerU 的 content list JSON。"""
    for candidate in (
        extract_dir / "content_list.json",
        extract_dir / "full_content_list.json",
    ):
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    # 深度不超过 3 层的递归查找
    for path in sorted(extract_dir.rglob("*.json")):
        if "content" in path.name:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return None


def _find_markdown(extract_dir: Path) -> str | None:
    for candidate in (extract_dir / "full.md", extract_dir / "full.md.txt"):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    for path in sorted(extract_dir.rglob("*.md")):
        if "full" in path.name or path.parent == extract_dir:
            return path.read_text(encoding="utf-8")
    return None


def _content_list_to_blocks(content_list: list[dict]) -> tuple[list[DocumentBlock], list[ParsedTable]]:
    """把 MinerU 云 API 的 content list 转成统一 blocks 和 tables。

    实测结构（2026-08，v4 API）：
      {"type": "text", "text": ..., "text_level": 1|2|None, "bbox": [x0,y0,x1,y1], "page_idx": 0}
      {"type": "table", "img_path": ..., "table_caption": [...], "table_footnote": [...],
       "table_body": "<table><tr><td rowspan=.. colspan=..>..", "bbox": ..., "page_idx": 0}
      {"type": "page_number"|"footer"|"image", ...}
    """
    blocks: list[DocumentBlock] = []
    tables: list[ParsedTable] = []
    table_seq = 0
    for order_index, item in enumerate(content_list):
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        page_number = _page_number(item.get("page_idx"))
        text = item.get("text") or ""
        source_block_id = item.get("id") or f"mineru-content-{order_index + 1:04d}"
        anchor = SourceAnchor(
            page_number=page_number,
            bbox=_bbox_tuple(item.get("bbox")),
            bbox_granularity="block" if item.get("bbox") else None,
        )

        if kind == "table":
            table_seq += 1
            table_id = f"table-{table_seq:03d}"
            html = item.get("table_body") or ""
            cells = _table_html_to_cells(html) if html else []
            table_md = _cells_to_markdown(cells) or item.get("table_content") or ""
            block = DocumentBlock(
                id=uuid4(),
                source_block_id=source_block_id,
                order_index=order_index,
                kind=BlockKind.TABLE,
                text=table_md,
                markdown=table_md,
                anchor=anchor,
                metadata={
                    "table_id": table_id,
                    "caption": item.get("table_caption"),
                    "footnote": item.get("table_footnote"),
                    "img_path": item.get("img_path"),
                },
            )
            blocks.append(block)
            tables.append(
                ParsedTable(
                    table_id=table_id,
                    block_id=block.id,
                    html=html or None,
                    markdown=table_md or None,
                    caption="".join(item.get("table_caption") or []) or None,
                    image_path=item.get("img_path"),
                    page_number=page_number,
                    bbox=_bbox_tuple(item.get("bbox")),
                    num_rows=max((c.start_row + c.row_span for c in cells), default=0) if cells else None,
                    num_cols=max((c.start_col + c.col_span for c in cells), default=0) if cells else None,
                    cells=cells,
                    metadata={"parser": "mineru-cloud", "source": "table_body_html"},
                )
            )
            continue

        if kind == "image":
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=source_block_id,
                    order_index=order_index,
                    kind=BlockKind.IMAGE,
                    text=None,
                    markdown=f"![{item.get('img_path') or ''}]({item.get('img_path') or ''})",
                    anchor=anchor,
                    metadata={"img_path": item.get("img_path")},
                )
            )
            continue

        if kind in {"formula", "interline_equation"}:
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=source_block_id,
                    order_index=order_index,
                    kind=BlockKind.FORMULA,
                    text=text,
                    markdown=text,
                    anchor=anchor,
                )
            )
            continue

        if kind == "page_number":
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=source_block_id,
                    order_index=order_index,
                    kind=BlockKind.PAGE_NUMBER,
                    text=text,
                    markdown=text,
                    anchor=anchor,
                )
            )
            continue

        if kind == "footer":
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=source_block_id,
                    order_index=order_index,
                    kind=BlockKind.FOOTER,
                    text=text,
                    markdown=text,
                    anchor=anchor,
                )
            )
            continue

        # 默认 text：MinerU text_level 语义为 1=章标题、2=节标题（实测），映射 heading_level
        heading_level = _mineru_text_level_to_heading(item.get("text_level"))
        blocks.append(
            DocumentBlock(
                id=uuid4(),
                source_block_id=source_block_id,
                order_index=order_index,
                kind=BlockKind.HEADING if heading_level else BlockKind.PARAGRAPH,
                text=text,
                heading_level=heading_level,
                markdown=text,
                anchor=anchor,
            )
        )
    return blocks, tables


def _page_number(page_idx) -> int | None:
    return page_idx + 1 if isinstance(page_idx, int) else None


def _bbox_tuple(bbox) -> tuple[float, float, float, float] | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        return tuple(float(v) for v in bbox)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _mineru_text_level_to_heading(text_level) -> int | None:
    """MinerU text_level -> heading_level 映射（实测 1=章、2=节；0 视为文档标题）。"""
    if not isinstance(text_level, int) or text_level <= 0:
        return None
    return text_level


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _markdown_heading_level(text: str) -> int | None:
    """从 MinerU 输出的 markdown 文本行首 # 判断标题层级。"""
    if not text:
        return None
    first_line = text.strip().splitlines()[0]
    match = _HEADING_RE.match(first_line)
    return len(match.group(1)) if match else None


def _table_html_to_cells(html: str) -> list[TableCell]:
    """解析 MinerU 的 ``table_body`` HTML（带 rowspan/colspan）为 TableCell 网格。"""
    from html.parser import HTMLParser

    class _GridParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.rows: list[list[dict]] = []
            self.current_row: list[dict] | None = None
            self.current_cell: dict | None = None
            self._cell_text: list[str] = []
            self._cell_header = False

        def handle_starttag(self, tag: str, attrs) -> None:
            attr_map = dict(attrs)
            if tag == "tr":
                self.current_row = []
            elif tag in ("td", "th"):
                self.current_cell = {
                    "rowspan": int(attr_map.get("rowspan", "1") or "1"),
                    "colspan": int(attr_map.get("colspan", "1") or "1"),
                    "text": "",
                }
                self._cell_text = []
                self._cell_header = tag == "th"

        def handle_data(self, data: str) -> None:
            if self.current_cell is not None:
                self._cell_text.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag in ("td", "th") and self.current_cell is not None:
                self.current_cell["text"] = "".join(self._cell_text).strip()
                self.current_cell["header"] = self._cell_header
                if self.current_row is not None:
                    self.current_row.append(self.current_cell)
                self.current_cell = None
            elif tag == "tr":
                if self.current_row:
                    self.rows.append(self.current_row)
                self.current_row = None

    parser = _GridParser()
    try:
        parser.feed(html)
    except Exception:
        return []

    cells: list[TableCell] = []
    for row_idx, row in enumerate(parser.rows):
        col_idx = 0
        for raw in row:
            # 占位推进：colspan>1 时后续格要跳过已占用的列
            cells.append(
                TableCell(
                    text=raw["text"],
                    start_row=row_idx,
                    start_col=col_idx,
                    row_span=max(1, raw["rowspan"]),
                    col_span=max(1, raw["colspan"]),
                    column_header=raw["header"] or row_idx == 0,
                    row_header=False,
                    bbox=None,
                )
            )
            col_idx += max(1, raw["colspan"])
    return cells


def _cells_to_markdown(cells: list[TableCell]) -> str:
    """从 cells 网格重建 markdown 表格（不引入单元格合并标记）。"""
    if not cells:
        return ""
    max_row = max(c.start_row + c.row_span for c in cells)
    max_col = max(c.start_col + c.col_span for c in cells)
    grid: list[list[str]] = [[""] * max_col for _ in range(max_row)]
    for cell in cells:
        grid[cell.start_row][cell.start_col] = cell.text
    lines = ["| " + " | ".join(cell or " " for cell in grid[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in grid[0]) + " |")
    for row in grid[1:]:
        lines.append("| " + " | ".join(cell or " " for cell in row) + " |")
    return "\n".join(lines)


def _markdown_table_to_cells(markdown: str) -> list[TableCell]:
    """把 markdown 表格行解析为 ``TableCell`` 网格（尽力而为）。

    MinerU 的 table_content 是普通 markdown 表格，没有行/列 span 信息，
    因此全部按 row_span=1/col_span=1 输出；表头行按第一行处理。
    真正的网格恢复交给质量层 QL-TBL-* 规则。
    """
    rows = [
        line.strip()
        for line in (markdown or "").splitlines()
        if line.strip().startswith("|")
    ]
    # 去掉分隔行 |---|---|
    data_rows = [
        row for row in rows if not re.match(r"^\|[\s:\-|]+\|$", row)
    ]
    if not data_rows:
        return []
    cells: list[TableCell] = []
    for row_idx, row in enumerate(data_rows):
        parts = [part.strip() for part in row.strip().strip("|").split("|")]
        for col_idx, part in enumerate(parts):
            cells.append(
                TableCell(
                    text=part,
                    start_row=row_idx,
                    start_col=col_idx,
                    row_span=1,
                    col_span=1,
                    column_header=row_idx == 0,
                    row_header=False,
                    bbox=None,
                )
            )
    return cells


def parse_pdf(
    source: Path,
    *,
    api_key: str | None = None,
    is_ocr: bool = False,
    file_type: str = "application/pdf",
    model_version: str = "pipeline",
    enable_formula: bool = True,
    enable_table: bool = True,
    work_dir: Path | None = None,
) -> ParsedDocument:
    """完整流程：上传 → 轮询 → 下载 → 转换为 ParsedDocument。

    ``work_dir`` 用于保存中间产物（zip 解压目录），便于排查；默认使用
    系统临时目录。
    """
    api_key = api_key or _get_api_key()
    import tempfile
    from uuid import uuid4

    work_dir = work_dir or Path(tempfile.mkdtemp(prefix="mineru_cloud_"))
    source = Path(source)

    batch_id = upload_file(
        source,
        api_key=api_key,
        is_ocr=is_ocr,
        model_version=model_version,
        enable_formula=enable_formula,
        enable_table=enable_table,
    )
    result = poll_batch(batch_id, api_key=api_key)
    extract_dir = download_and_extract(result, work_dir=work_dir)

    markdown = _find_markdown(extract_dir)
    if markdown is None:
        raise MinerUCloudError(f"解压结果中找不到 markdown 文件: {sorted(p.name for p in extract_dir.rglob('*'))}")

    content_list = _find_content_list(extract_dir)
    if content_list is None:
        # 没有 content list 时，从 markdown 兜底生成 blocks
        blocks, tables = _markdown_to_blocks(markdown)
    else:
        blocks, tables = _content_list_to_blocks(content_list if isinstance(content_list, list) else content_list.get("content_list", []))

    has_bbox = any(b.anchor.bbox for b in blocks)
    capabilities = {
        "page_bbox": EvidenceCapability(
            state=EvidenceAvailability.AVAILABLE if has_bbox else EvidenceAvailability.PARTIAL,
            granularity="block" if has_bbox else None,
            reason=None if has_bbox else "部分条目缺少 bbox。",
        ),
        "table_cells": EvidenceCapability(
            state=EvidenceAvailability.AVAILABLE if any(t.cells for t in tables) else EvidenceAvailability.PARTIAL,
            granularity="cell_with_span" if any(t.cells for t in tables) else "markdown_only",
            reason=None
            if any(t.cells for t in tables)
            else "表格未提供 cells 网格，只有 markdown。",
        ),
        "ocr_confidence": EvidenceCapability(
            state=(
                EvidenceAvailability.AVAILABLE
                if is_ocr
                else EvidenceAvailability.UNAVAILABLE
            ),
            reason=None if is_ocr else "本次未启用 OCR。",
        ),
    }

    source_bytes = source.read_bytes()
    provenance = ParserProvenance(
        parser_id="mineru-cloud",
        requested_parser_id="mineru",
        routing_mode=RoutingMode.AUTO,
        model=model_version,
        version="v4",
        parameters={
            "is_ocr": is_ocr,
            "model_version": model_version,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
        },
    )
    return ParsedDocument(
        document_id=uuid4(),
        filename=source.name,
        file_type=file_type,
        source_size_bytes=len(source_bytes),
        source_sha256=_sha256(source_bytes),
        markdown=markdown,
        blocks=blocks,
        tables=tables,
        confidence=ParseConfidence(text=0.9, layout=0.8, reading_order=0.8, table=0.7, overall=0.8),
        provenance=provenance,
        capabilities=capabilities,
        warnings=[],
    )


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _markdown_to_blocks(markdown: str) -> tuple[list[DocumentBlock], list[ParsedTable]]:
    """content list 缺失时的兜底：按 markdown 行解析出 blocks。"""
    from uuid import uuid4

    blocks: list[DocumentBlock] = []
    tables: list[ParsedTable] = []
    table_seq = 0
    for order_index, raw_line in enumerate(markdown.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=f"md-line-{order_index}",
                    order_index=order_index,
                    kind=BlockKind.HEADING,
                    text=match.group(2).strip(),
                    heading_level=level,
                    markdown=line,
                    anchor=SourceAnchor(),
                )
            )
        elif line.startswith("|"):
            # 收集表格行
            table_lines = []
            while order_index < len(markdown.splitlines()) and markdown.splitlines()[order_index].strip().startswith("|"):
                table_lines.append(markdown.splitlines()[order_index].strip())
                order_index += 1
            table_md = "\n".join(table_lines)
            table_seq += 1
            table_id = f"table-{table_seq:03d}"
            block = DocumentBlock(
                id=uuid4(),
                source_block_id=f"md-table-{order_index}",
                order_index=order_index,
                kind=BlockKind.TABLE,
                text=table_md,
                markdown=table_md,
                anchor=SourceAnchor(),
                metadata={"table_id": table_id},
            )
            blocks.append(block)
            tables.append(
                ParsedTable(
                    table_id=table_id,
                    block_id=block.id,
                    markdown=table_md,
                    cells=_markdown_table_to_cells(table_md),
                    metadata={"parser": "mineru-cloud-md-fallback"},
                )
            )
        else:
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=f"md-line-{order_index}",
                    order_index=order_index,
                    kind=BlockKind.PARAGRAPH,
                    text=line,
                    markdown=line,
                    anchor=SourceAnchor(),
                )
            )
    return blocks, tables
