"""路由阶段的可观察错误。"""


class RoutingError(ValueError):
    """所有可预期路由错误的基类。"""


class UnsupportedFormatError(RoutingError):
    """输入格式不在已验证路由表中。"""


class UnknownParserError(RoutingError):
    """调用方指定了未注册的解析器。"""


class ParserUnavailableError(RoutingError):
    """候选解析器在当前环境不可执行。"""


class CloudParserForbiddenError(RoutingError):
    """任务禁止云端处理，但指定了解析器云服务。"""


class ReparseRejectedError(RoutingError):
    """重新解析建议无效或会形成循环。"""
