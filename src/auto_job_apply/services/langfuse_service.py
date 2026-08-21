"""Langfuse client/factory singletons for LLM calls, graph runs, and eval scores.

Import-safe with no LANGFUSE_* envs: factories return None and log once.
Deps intentionally env-only (no auto_job_apply.config import) to avoid cycles.

Public API:
    get_client() -> Langfuse | None
    get_callback_handler() -> CallbackHandler | None
    score_eval(run_name, item_id, metric, value, comment="")
    flush()
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

logger = logging.getLogger("auto_job_apply.langfuse")

_BASE_URL_ENV_KEYS = ("LANGFUSE_BASE_URL", "LANGFUSE_HOST")


def _env_ready() -> bool:
    """True when both key vars are present in the process env."""
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
        os.environ.get("LANGFUSE_SECRET_KEY")
    )


def _base_url() -> str | None:
    key = next((k for k in _BASE_URL_ENV_KEYS if os.environ.get(k)), None)
    return os.environ.get(key) if key else None


_client: "Langfuse | None" = None
_handler: "CallbackHandler | None" = None
_warned_missing = False


def get_client() -> "Langfuse | None":
    """The process-wide Langfuse client, or None when env is missing."""
    global _client, _warned_missing
    if _client is not None:
        return _client
    if not _env_ready():
        if not _warned_missing:
            logger.info(
                "Langfuse tracing disabled: LANGFUSE_PUBLIC_KEY/SECRET_KEY not set"
            )
            _warned_missing = True
        return None
    from langfuse import Langfuse

    kwargs: dict = {}
    url = _base_url()
    if url:
        kwargs["host"] = url
    _client = Langfuse(**kwargs)
    return _client


def get_callback_handler() -> "CallbackHandler | None":
    """A LangChain/LangGraph-compatible callbacks handler, or None."""
    global _handler
    if _handler is not None:
        return _handler
    if get_client() is None:
        return None
    from langfuse.langchain import CallbackHandler

    _handler = CallbackHandler(
        public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    )
    return _handler


def score_eval(
    run_name: str,
    item_id: str,
    metric: str,
    value: float,
    comment: str = "",
) -> bool:
    """Post one numeric eval score to Langfuse (evals/ lane).

    Parameters are strings naming the run/item plus the metric and its
    value; comment carries reviewer/evaluator prose. Returns True on
    success, False when the client is unavailable or the post failed.
    """
    client = get_client()
    if client is None:
        return False
    try:
        client.api.scores.create(
            name=metric,
            value=value,
            trace_id=item_id,
            comment=comment or None,
        )
        return True
    except Exception:  # pragma: no cover - network-defensive
        logger.exception("score_eval failed for %s/%s", run_name, item_id)
        return False


def flush() -> None:
    """Flush queued events on graceful shutdown."""
    if _client is not None:
        _client.flush()


def reset() -> None:
    """Drop singletons — for tests only."""
    global _client, _handler, _warned_missing
    _client = None
    _handler = None
    _warned_missing = False


__all__ = [
    "get_client",
    "get_callback_handler",
    "score_eval",
    "flush",
    "reset",
]
