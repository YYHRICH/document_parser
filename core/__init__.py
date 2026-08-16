"""文档解析内部协议、格式转换抽象与网关。"""

from .converter import ConversionResult, DocumentConverter, LegacyOfficeConverter

__all__ = ["ConversionResult", "DocumentConverter", "LegacyOfficeConverter"]
