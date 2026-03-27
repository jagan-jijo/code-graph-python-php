from __future__ import annotations

from ai.base import BaseModelAdapter
from ai.ollama_adapter import OllamaNativeAdapter
from ai.openwebui_adapter import OpenWebUIAdapter
from ai.openai_adapter import OpenAICompatibleAdapter
from models.project import ModelConfig, ModelProviderType, build_default_model_config


def _resolve_config(config: ModelConfig) -> ModelConfig:
    if config.base_url and (config.api_key is not None):
        return config

    defaults = build_default_model_config(config.provider_type)
    return ModelConfig(
        provider_type=config.provider_type,
        base_url=config.base_url or defaults.base_url,
        api_key=config.api_key if config.api_key not in (None, "") else defaults.api_key,
        remote_send_policy=config.remote_send_policy,
        planner_model=config.planner_model,
        code_model=config.code_model,
        query_model=config.query_model,
    )


def create_adapter(config: ModelConfig) -> BaseModelAdapter:
    resolved = _resolve_config(config)
    if resolved.provider_type == ModelProviderType.OLLAMA_NATIVE:
        return OllamaNativeAdapter(resolved.base_url, resolved.api_key)
    if resolved.provider_type == ModelProviderType.OPENWEBUI:
        return OpenWebUIAdapter(resolved.base_url, resolved.api_key)
    return OpenAICompatibleAdapter(resolved.base_url.rstrip("/") + "/v1", resolved.api_key)


__all__ = [
    "BaseModelAdapter",
    "OllamaNativeAdapter",
    "OpenWebUIAdapter",
    "OpenAICompatibleAdapter",
    "create_adapter",
]