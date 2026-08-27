"""统一归一化层。

每个解析器先把各自的原始输出转换为这里的中间包，再落成
``ParsedDocument`` 和统一文档包。
"""

from .api import (
    NativeResultNormalizer,
    NormalizationContext,
    NormalizationFacade,
    normalize_native_result,
    normalize_to_parsed_document,
)
from .bundle import (
    available_capability,
    failed_capability,
    NORMALIZATION_NAMESPACE,
    ParserNormalizationBundle,
    make_stable_block_id,
    make_stable_document_id,
    make_stable_table_id,
    partial_capability,
    stable_uuid,
    unavailable_capability,
)

__all__ = [
    "NativeResultNormalizer",
    "NormalizationContext",
    "NormalizationFacade",
    "NORMALIZATION_NAMESPACE",
    "normalize_native_result",
    "normalize_to_parsed_document",
    "ParserNormalizationBundle",
    "available_capability",
    "failed_capability",
    "make_stable_block_id",
    "make_stable_document_id",
    "make_stable_table_id",
    "partial_capability",
    "stable_uuid",
    "unavailable_capability",
]
