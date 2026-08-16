"""文档解析前的统一格式转换抽象。

转换层只负责把解析器不原生支持的旧格式标准化，不生成 Markdown，也不依赖
具体解析器。新增格式时实现 ``DocumentConverter``，由 Gateway 统一编排即可。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversionResult:
    """一次格式标准化的结果及可观测信息。"""

    content: bytes
    extension: str
    converter_id: str
    duration_ms: int


class DocumentConverter(ABC):
    """所有解析前格式转换器必须实现的最小接口。"""

    @property
    @abstractmethod
    def source_formats(self) -> frozenset[str]:
        """返回该转换器可以接收的源文件扩展名。"""

    @abstractmethod
    def convert(self, content: bytes, extension: str) -> ConversionResult:
        """把源文件字节转换成解析器可消费的新格式。"""


class LegacyOfficeConverter(DocumentConverter):
    """统一处理旧版 Word 和 PowerPoint 二进制格式。"""

    TARGET_FORMATS = {".doc": ".docx", ".ppt": ".pptx"}

    @property
    def source_formats(self) -> frozenset[str]:
        return frozenset(self.TARGET_FORMATS)

    def convert(self, content: bytes, extension: str) -> ConversionResult:
        """优先使用跨平台 LibreOffice，Windows 再回退 Microsoft Office。"""

        source_extension = extension.lower()
        target_extension = self.TARGET_FORMATS.get(source_extension)
        if target_extension is None:
            raise ValueError(f"旧版 Office 转换器不支持：{extension}")

        started = time.perf_counter()
        converted, converter_id = self._convert(
            content,
            source_extension=source_extension,
            target_extension=target_extension,
        )
        return ConversionResult(
            content=converted,
            extension=target_extension,
            converter_id=converter_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _convert(
        self,
        content: bytes,
        *,
        source_extension: str,
        target_extension: str,
    ) -> tuple[bytes, str]:
        """在临时目录转换，确保原文件和正式 Vault 都不会被修改。"""

        errors: list[str] = []
        with tempfile.TemporaryDirectory(prefix="document-converter-") as temporary:
            directory = Path(temporary)
            source = directory / f"source{source_extension}"
            target = directory / f"source{target_extension}"
            source.write_bytes(content)

            # LibreOffice 跨平台且通常比冷启动 Microsoft Office 更快，因此优先。
            try:
                if _convert_with_libreoffice(source, target):
                    return target.read_bytes(), "libreoffice"
            except Exception as exc:
                errors.append(f"LibreOffice: {exc}")

            # Word/PowerPoint COM 仅作为 Windows 兼容回退，不作为部署首选。
            if os.name == "nt":
                try:
                    if source_extension == ".doc":
                        _convert_with_word(source, target)
                        converter_id = "microsoft_word"
                    else:
                        _convert_with_powerpoint(source, target)
                        converter_id = "microsoft_powerpoint"
                    return target.read_bytes(), converter_id
                except Exception as exc:
                    errors.append(f"Microsoft Office: {exc}")

        detail = "; ".join(errors) or "未找到可用转换器"
        raise RuntimeError(
            f"旧版 {source_extension} 需要 LibreOffice，或 Windows 上对应的 "
            f"Microsoft Office。转换失败：{detail}"
        )


def _convert_with_libreoffice(source: Path, target: Path) -> bool:
    """调用 LibreOffice headless；未安装时返回 False 以允许平台回退。"""

    executable = _find_libreoffice()
    if executable is None:
        return False
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        [
            executable,
            "--headless",
            "--convert-to",
            target.suffix.lstrip("."),
            "--outdir",
            str(source.parent),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=creation_flags,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(message or f"退出码 {completed.returncode}")
    return True


def _find_libreoffice() -> str | None:
    """按显式配置、PATH、Windows、macOS、Linux 标准位置依次查找。"""

    candidates: list[str | None] = [
        os.getenv("LIBREOFFICE_PATH"),
        shutil.which("soffice"),
        shutil.which("libreoffice"),
    ]
    system = platform.system()
    if system == "Windows":
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.getenv(variable)
            if not root:
                continue
            candidates.extend(
                [
                    str(Path(root) / "LibreOffice/program/soffice.exe"),
                    str(Path(root) / "Programs/LibreOffice/program/soffice.exe"),
                ]
            )
    elif system == "Darwin":
        candidates.extend(
            [
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                str(
                    Path.home()
                    / "Applications/LibreOffice.app/Contents/MacOS/soffice"
                ),
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/bin/soffice",
                "/usr/bin/libreoffice",
                "/usr/local/bin/soffice",
                "/snap/bin/libreoffice",
            ]
        )

    # 支持 LIBREOFFICE_PATH 直接指向可执行文件或其所在目录。
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_dir():
            path = path / ("soffice.exe" if system == "Windows" else "soffice")
        if path.is_file():
            return str(path)
    return None


def _run_office_script(script: str, source: Path, target: Path, name: str) -> None:
    """在独立进程运行 Office COM，避免阻塞 API 的后台 worker。"""

    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        [sys.executable, "-c", script, str(source), str(target)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
        creationflags=creation_flags,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        raise RuntimeError(f"{name} 转换进程退出码 {completed.returncode}")


def _convert_with_word(source: Path, target: Path) -> None:
    """使用 Word COM 将 doc 保存为标准 docx。"""

    script = r"""
import sys
import pythoncom
import win32com.client
source, target = sys.argv[1:3]
pythoncom.CoInitialize()
word = document = None
try:
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = word.Documents.Open(source, ConfirmConversions=False, ReadOnly=True,
        AddToRecentFiles=False, Visible=False, OpenAndRepair=True,
        NoEncodingDialog=True)
    document.SaveAs2(target, FileFormat=16, AddToRecentFiles=False)
finally:
    if document is not None: document.Close(SaveChanges=False)
    if word is not None: word.Quit(SaveChanges=False)
    pythoncom.CoUninitialize()
"""
    _run_office_script(script, source, target, "Word")


def _convert_with_powerpoint(source: Path, target: Path) -> None:
    """使用 PowerPoint COM 将 ppt 保存为标准 pptx。"""

    script = r"""
import sys
import pythoncom
import win32com.client
source, target = sys.argv[1:3]
pythoncom.CoInitialize()
powerpoint = presentation = None
try:
    powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
    presentation = powerpoint.Presentations.Open(source, ReadOnly=True,
        Untitled=False, WithWindow=False)
    presentation.SaveAs(target, 24)
finally:
    if presentation is not None: presentation.Close()
    if powerpoint is not None: powerpoint.Quit()
    pythoncom.CoUninitialize()
"""
    _run_office_script(script, source, target, "PowerPoint")
