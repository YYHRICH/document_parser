"""文档解析内部协议、格式转换抽象与网关。"""

from .converter import ConversionResult, DocumentConverter, LegacyOfficeConverter
from .package_loader import (
    DocumentPackageError,
    DocumentPackageAdapter,
    DocumentPackageLoader,
    load_document_package,
)

__all__ = [
    "ConversionResult",
    "DocumentConverter",
    "DocumentPackageError",
    "DocumentPackageAdapter",
    "DocumentPackageLoader",
    "LegacyOfficeConverter",
    "load_document_package",
]
