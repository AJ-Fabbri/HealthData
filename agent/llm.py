"""
LLM provider factory supporting LM Studio and Anthropic.

LM Studio exposes an OpenAI-compatible REST API at http://localhost:1234/v1
by default. No real API key is required - any non-empty string works.

Anthropic uses the official API via langchain_anthropic. Set ANTHROPIC_API_KEY
in the environment before use.

Usage
-----
    from agent.llm import build_llm

    # LM Studio (default)
    llm = build_llm()
    llm = build_llm(model="lmstudio-community/meta-llama-3.1-8b-instruct")
    llm = build_llm(base_url="http://192.168.1.50:1234/v1")

    # Anthropic
    llm = build_llm(provider="anthropic")
    llm = build_llm(provider="anthropic", model="claude-opus-4-7")
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

LM_STUDIO_DEFAULT_URL = "http://localhost:1234/v1"
LM_STUDIO_API_KEY = "lm-studio"

ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"


def build_llm(
    provider: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.3,
    **kwargs,
) -> BaseChatModel:
    """
    Return a LangChain chat model for the requested provider.

    Parameters
    ----------
    provider : str, optional
        "lmstudio" (default) or "anthropic".
        Falls back to env var LLM_PROVIDER, then "lmstudio".
    base_url : str, optional
        LM Studio only. Override the API base URL.
        Falls back to env var LM_STUDIO_BASE_URL, then localhost default.
    model : str, optional
        Model identifier. For LM Studio falls back to LM_STUDIO_MODEL env var
        then "local-model". For Anthropic falls back to ANTHROPIC_MODEL env var
        then claude-sonnet-4-6.
    temperature : float
        Sampling temperature; 0.0 for deterministic tool calls (recommended).
    **kwargs
        Forwarded to the underlying chat model constructor.
    """
    resolved_provider = (
        provider
        or os.environ.get("LLM_PROVIDER")
        or "lmstudio"
    ).lower()

    if resolved_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # lazy import

        resolved_model = (
            model
            or os.environ.get("ANTHROPIC_MODEL")
            or ANTHROPIC_DEFAULT_MODEL
        )
        resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        return ChatAnthropic(
            model=resolved_model,
            api_key=resolved_api_key,
            temperature=temperature,
            **kwargs,
        )

    # Default: LM Studio
    resolved_url = (
        base_url
        or os.environ.get("LM_STUDIO_BASE_URL")
        or LM_STUDIO_DEFAULT_URL
    )
    resolved_model = (
        model
        or os.environ.get("LM_STUDIO_MODEL")
        or "local-model"
    )
    return ChatOpenAI(
        base_url=resolved_url,
        api_key=LM_STUDIO_API_KEY,
        model=resolved_model,
        temperature=temperature,
        **kwargs,
    )
