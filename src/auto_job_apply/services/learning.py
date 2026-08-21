"""Self-learning store.

Canonicalizes free-form form labels (e.g. "Are you a protected veteran?")
into stable profile keys, then persists approved answers to
applicant_profile.csv via ``services.profile``. Deterministic alias lookup
first; LLM canonicalization only on miss, and only writes ``llm_draft``
rows — elevation to authoritative happens out of this module.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from auto_job_apply.logging import logger
from auto_job_apply.services import profile

if TYPE_CHECKING:
    from auto_job_apply.services.llm import structured as _structured

_ALIASES_PATH = Path(__file__).resolve().parent / "learning_aliases.json"

_ALIASES: dict[str, str] | None = None


def _normalize(label: str) -> str:
    norm = re.sub(r"[\W_]+", " ", label.lower())
    return re.sub(r"\s+", " ", norm).strip()


def _load_aliases() -> dict[str, str]:
    global _ALIASES
    if _ALIASES is None:
        raw: dict[str, list[str]] = json.loads(_ALIASES_PATH.read_text())
        # Map each alias to its canonical key; duplicate aliases keep the first.
        _ALIASES = {
            _normalize(alias): canonical
            for canonical, aliases in raw.items()
            for alias in aliases
        }
    return _ALIASES


def canonicalize(label: str) -> str | None:
    """Map a free-form label to a canonical profile key, or None if unknown.

    Deterministic alias table first; LLM structured fallback on miss.
    The LLM path only *suggests* — callers must still gate writes through
    ``learn`` / a review surface.
    """
    norm = _normalize(label)
    aliases = _load_aliases()
    if norm in aliases:
        return aliases[norm]
    return _canonicalize_via_llm(label)


def _canonicalize_via_llm(label: str) -> str | None:
    # Import lazily: the alias-hit path must never touch the LLM surface,
    # and this module stays importable while services/llm.py is still being
    # built by another chain.
    try:
        from auto_job_apply.services.llm import get_llm
        from auto_job_apply.services.llm import structured as _structured
    except ImportError:
        logger.debug("services.llm not yet available; LLM canonicalization skipped")
        return None

    from pydantic import BaseModel

    class Canonicalization(BaseModel):
        canonical_key: str | None

    runnable = _structured(get_llm(role="learning"), Canonicalization)
    result = runnable.invoke(
        "You map free-form job application field labels to a canonical "
        "snake_case question key. Respond only with the canonical key if a "
        "well-known mapping exists (e.g. 'Are you a protected veteran?' -> "
        "veteran_status); otherwise null.\n\nLabel: " + label
    )
    key = getattr(result, "canonical_key", None)
    return key if isinstance(key, str) else None


def _record_llm_draft(key: str, answer: str, path: str | Path | None = None) -> None:
    # Never clobber a manual/learned authoritative answer; only record when
    # there is nothing authoritative yet. The caller-supplied answer is
    # preserved so the review surface has a proposed value to approve.
    if profile.get_authoritative(key, path) is None:
        profile.set(key, answer, "llm_draft", path)


def learn(label: str, answer: str, source: str = "learned", path: str | Path | None = None) -> None:
    """Persist an approved answer into the profile as authoritative by caller
    choice; with ``source='learned'`` (default) it's immediately authoritative.
    ``source='llm_draft'`` writes a non-authoritative suggestion only."""
    key = canonicalize(label) or _normalize(label).replace(" ", "_")
    if source == "llm_draft":
        _record_llm_draft(key, answer, path)
        return
    profile.set(key, answer, source, path)


def suggest(label: str, path: str | Path | None = None) -> str | None:
    """Authoritative answer for *label*, canonicalized, or None."""
    # Resolve with the same fallback as learn() so previously learned
    # unmapped labels are reachable (round-trip learn → suggest).
    key = canonicalize(label) or _normalize(label).replace(" ", "_")
    return profile.get_authoritative(key, path)


__all__ = ["canonicalize", "learn", "suggest"]
