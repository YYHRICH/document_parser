"""文档解析共享协议、格式转换抽象与完整性校验。"""

from .converter import ConversionResult, DocumentConverter, LegacyOfficeConverter
from .document_package import (
    DocumentPackageValidationError,
    load_document_package,
    write_document_package,
    validate_parsed_document_integrity,
)

__all__ = [
    "ConversionResult",
    "DocumentConverter",
    "DocumentPackageValidationError",
    "LegacyOfficeConverter",
    "load_document_package",
    "write_document_package",
    "validate_parsed_document_integrity",
]
