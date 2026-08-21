"""Prompt templates and page-context helpers for the answer planner.

The planner never performs network I/O: the job-page text (when available)
comes from the extractor's snapshot HTML, passed in by the caller. Org and
role context are derived deterministically from the application URL and that
page text so every short-answer draft can embed them.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

FIELD_ANSWER_PROMPT = """\
You are filling out one field of a job application on behalf of the applicant.

Job context:
- Organization: {org}
- Role: {role}

Applicant profile (authoritative answers):
{profile_block}

Field to answer:
- Label: {label}
- Type: {ftype}
- Required: {required}
{options_block}
Rules:
- Answer ONLY this field. Do not include the label or any explanation.
- For select/radio/checkbox fields, the answer MUST be exactly one of the \
listed options (for checkbox-group, pipe-separate multiple options with `|`).
- For short-answer/free-text fields, write a concise, specific answer (2-4 \
sentences) that references the organization ({org}), the role ({role}), and \
the applicant's background from the profile. Speak in first person as the \
applicant ({full_name}).
- If you cannot produce a confident answer, return an empty string for \
"value" and set "confidence" to 0.
- Set "confidence" in [0, 1] honestly: 1.0 only when the answer comes \
directly from the profile.
"""

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Separators ATS job boards commonly use between role title and org name in
# <title>, e.g. "Senior Engineer – Acme" or "Acme | Senior Engineer".
_TITLE_SEP_RE = re.compile(r"\s+[–—\-|·]\s+")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def org_from_url(url: str) -> str:
    """Org slug from an ATS application URL (first path segment).

    jobs.ashbyhq.com/<org>/<id>, boards.greenhouse.io/<org>/jobs/<id>,
    jobs.lever.co/<org>/<id> all put the org in the first path segment.
    """
    path = urlparse(url).path.strip("/")
    return path.split("/")[0] if path else ""


def role_from_page_text(page_text: str | None, org: str = "") -> str:
    """Best-effort role title scraped from snapshot HTML (<title>, then <h1>)."""
    if not page_text:
        return ""
    for pattern in (_TITLE_RE, _H1_RE):
        m = pattern.search(page_text)
        if not m:
            continue
        title = _clean(m.group(1))
        if not title:
            continue
        parts = [p.strip() for p in _TITLE_SEP_RE.split(title) if p.strip()]
        if len(parts) > 1 and org:
            non_org = [p for p in parts if p.lower() != org.lower()]
            if non_org:
                return non_org[0]
        return title
    return ""


def page_context(url: str, page_text: str | None) -> tuple[str, str]:
    """(org, role) context for prompt packing."""
    org = org_from_url(url)
    return org, role_from_page_text(page_text, org)


def build_field_prompt(
    *,
    label: str,
    ftype: str,
    required: bool,
    options: list[str] | None,
    profile_answers: dict[str, str],
    org: str,
    role: str,
    full_name: str,
) -> str:
    """Render the per-field drafting prompt."""
    profile_block = (
        "\n".join(f"- {k}: {v}" for k, v in sorted(profile_answers.items()))
        if profile_answers
        else "- (none available)"
    )
    options_block = (
        "- Options: " + ", ".join(options) + "\n" if options else ""
    )
    return FIELD_ANSWER_PROMPT.format(
        org=org or "(unknown)",
        role=role or "(unknown)",
        profile_block=profile_block,
        label=label,
        ftype=ftype,
        required="yes" if required else "no",
        options_block=options_block,
        full_name=full_name or "the applicant",
    )


__all__ = [
    "FIELD_ANSWER_PROMPT",
    "build_field_prompt",
    "org_from_url",
    "page_context",
    "role_from_page_text",
]
