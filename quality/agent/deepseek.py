"""DeepSeek 的 Agno/OpenAI-compatible 模型配置。

密钥只从环境变量读取，模块不会打印或记录密钥内容。默认模型使用
DeepSeek 当前 OpenAI-compatible API 提供的 ``deepseek-v4-flash``；项目的
``LLM_MODEL`` 可以覆盖该默认值，便于在服务端切换模型而无需改代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class LLMConfigurationError(RuntimeError):
    """LLM 配置缺失或不合法。"""


@dataclass(frozen=True)
class DeepSeekConfig:
    """构造 DeepSeek OpenAI-compatible client 所需的非敏感配置。"""

    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


def load_deepseek_config(
    environ: Mapping[str, str] | None = None,
    *,
    load_dotenv_file: bool = True,
) -> DeepSeekConfig:
    """从 ``.env``/环境变量加载 DeepSeek 配置。

    项目约定使用 ``LLM_API_KEY``、``LLM_API_BASE`` 和 ``LLM_MODEL``，同时
    兼容常见的 ``DEEPSEEK_API_KEY`` 命名。测试可传入 mapping，避免读取
    机器上的真实密钥。
    """

    if environ is None:
        if load_dotenv_file:
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:  # pragma: no cover - dotenv 是运行时依赖
                pass
        environ = os.environ

    api_key = (environ.get("LLM_API_KEY") or environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "未配置 LLM_API_KEY（或 DEEPSEEK_API_KEY），无法创建 DeepSeek Agent。"
        )

    base_url = (
        environ.get("LLM_API_BASE")
        or environ.get("DEEPSEEK_API_BASE")
        or "https://api.deepseek.com"
    ).strip().rstrip("/")
    model = (environ.get("LLM_MODEL") or "deepseek-v4-flash").strip()
    if not base_url or not model:
        raise LLMConfigurationError("LLM_API_BASE 和 LLM_MODEL 不能为空。")

    return DeepSeekConfig(api_key=api_key, base_url=base_url, model=model)


def build_deepseek_model(config: DeepSeekConfig | None = None):
    """创建可直接传给 ``build_quality_repair_agent`` 的 Agno 模型。"""

    try:
        from agno.models.openai import OpenAIChat
    except ImportError as exc:  # pragma: no cover - 依赖缺失时才触发
        raise LLMConfigurationError(
            "缺少 Agno/OpenAI provider 依赖，请安装 requirements.txt。"
        ) from exc

    selected = config or load_deepseek_config()
    return OpenAIChat(
        id=selected.model,
        api_key=selected.api_key,
        base_url=selected.base_url,
        # DeepSeek 的 OpenAI-compatible API 支持 JSON 输出；关闭严格 JSON
        # Schema 约束，避免把 Pydantic schema 当成不兼容的 provider 特性。
        strict_output=False,
        # DeepSeek 不接受 OpenAI 新版的 developer role。
        role_map={
            "system": "system",
            "user": "user",
            "assistant": "assistant",
            "tool": "tool",
            "model": "assistant",
        },
        # DeepSeek 文档保证 json_object；不要发送 OpenAI 专有的 json_schema。
        request_params={"response_format": {"type": "json_object"}},
        # V4 默认开启 thinking；关闭后避免 Agno 工具轮次缺少 reasoning_content。
        extra_body={"thinking": {"type": "disabled"}},
        timeout=60.0,
        max_retries=0,
        retry_with_guidance=False,
        retry_with_guidance_limit=0,
    )


__all__ = [
    "DeepSeekConfig",
    "LLMConfigurationError",
    "build_deepseek_model",
    "load_deepseek_config",
]
