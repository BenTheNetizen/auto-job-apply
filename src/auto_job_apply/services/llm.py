"""The single entry point for all LLM calls (OpenRouter back end).

Public API:
    get_llm(role="default") -> ChatOpenAI
    structured(model, schema) -> Runnable  (with_structured_output + fallback)

Every subsystem routes LLM traffic through here so model swaps, per-role
overrides in settings, token/cost logging, and Langfuse tracing stay
centralized. Do NOT construct ChatOpenAI anywhere else.
"""

from __future__ import annotations

import logging
import os
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from auto_job_apply.config import settings
from auto_job_apply.services.langfuse_service import get_callback_handler

logger = logging.getLogger("auto_job_apply.llm")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

T = TypeVar("T", bound=BaseModel)


def _model_for(role: str) -> str:
    """Resolve the model for a role; per-role override or the default."""
    override = settings.get(f"LLM.{role}_model")
    if override:
        return str(override)
    return str(settings.get("LLM.model", "openai/gpt-4.1-mini"))


def _temperature() -> float:
    raw = settings.get("LLM.temperature", 0)
    return float(raw if raw is not None else 0)


def get_llm(role: str = "default") -> ChatOpenAI:
    """Build a ChatOpenAI pinned to OpenRouter with model/temperature from
    settings and the Langfuse callback handler attached (when env present).

    `role` maps to `settings.LLM.<role>_model` for per-role model selection
    (e.g. `planner`, `parser`); falls back to `settings.LLM.model`.
    """
    handler = get_callback_handler()
    callbacks = [handler] if handler is not None else []
    model = _model_for(role)
    logger.info("LLM role=%s model=%s callbacks=%s", role, model, len(callbacks))
    return ChatOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        model=model,
        temperature=_temperature(),
        callbacks=callbacks or None,
    )


def structured(model: BaseChatModel, schema: type[T]) -> Any:
    """A runnable that calls `model` with `schema` as structured output.

    Tries the provider's response_format path first
    (`with_structured_output(schema)`); if the provider rejects it at call
    time, falls back to prompt + PydanticOutputParser. The fallback is
    wrapped so consumers don't need to care which path was taken.
    """
    try:
        # Method binding generally succeeds even when the provider will
        # reject response_format at generate-time; the fallback below
        # catches that.
        return model.with_structured_output(schema)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        pass
    return _prompt_parse_fallback(model, schema)


def _prompt_parse_fallback(model: BaseChatModel, schema: type[T]) -> Any:
    """Prompt+parse fallback runnable for providers without
    structured-output support."""
    parser = PydanticOutputParser(pydantic_object=schema)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You respond ONLY with valid JSON matching this schema.\n"
                "{format_instructions}",
            ),
            ("human", "{payload}"),
        ]
    ).partial(format_instructions=parser.get_format_instructions())
    chain = prompt | model | parser
    logger.info("structured(%s): using prompt+parse fallback", schema.__name__)
    return chain


def log_usage(response: Any) -> None:
    """Log token/cost fields from a ChatOpenAI response if present."""
    meta = getattr(response, "response_metadata", {}) or {}
    usage = meta.get("usage") or {}
    if not usage:
        return
    tokens = usage.get("total_tokens")
    cost = usage.get("cost") or meta.get("cost")
    logger.info("llm usage tokens=%s cost=%s", tokens, cost)


__all__ = [
    "OPENROUTER_BASE_URL",
    "get_llm",
    "structured",
    "log_usage",
]
