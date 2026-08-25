"""内置解析器。

当前生产链路只注册 MarkItDown；Docling、MinerU、OCR 先保留骨架入口，后续逐步接入。
"""

from .docling import DoclingParser
from .anydoc import AnyDocParser
from .markitdown import MarkItDownParser
from .mineru import MinerUParser
from .ocr import OcrParser
from .registry import build_parser_registry, get_parser, iter_parser_capabilities

__all__ = [
    "AnyDocParser",
    "DoclingParser",
    "MarkItDownParser",
    "MinerUParser",
    "OcrParser",
    "build_parser_registry",
    "get_parser",
    "iter_parser_capabilities",
]
