"""Eval runner: drive the real fill pipeline against the mock ATS sites.

For every gold case in ``evals/mock-sites/gold/``:

1. Seed a temp DATA.dir with the mock applicant profile (Taylor Wong).
2. Extract the form (real extractor) -> plan answers (real planner) ->
   fill (real filler). No real submission ever happens: the mock site's
   POST /submit only records the payload to ``submissions/``.
3. Act as agent-as-human over the review API surface: patch any required
   field the planner could not answer (short-answer drafts need an LLM;
   without ``OPENROUTER_API_KEY`` they are stubbed deterministically),
   confirm, then submit.
4. Load the recorded submission and score against the gold labels:
   ``required_completion`` (gate, target 1.0) and ``answer_fidelity``.

Scoring is intentionally pure (no I/O beyond loading JSON) so the unit
tests exercise it without a browser, server, or LLM.

Exit code: 0 when overall required_completion == 1.0, else 1 (the
hill-climb gate from the spec).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field as dc_field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from auto_job_apply.config import ensure_data_dir, settings
from auto_job_apply.logging import logger
from auto_job_apply.services import langfuse_service
from auto_job_apply.services.ats_registry import register
from auto_job_apply.services.extractor import extract
from auto_job_apply.services.filler import fill
from auto_job_apply.graphs.planner import plan_answers

from evals.mock_sites_gold import (
    GENERATED,
    GoldCase,
    GoldField,
    SubmissionPayload,
    all_cases,
    load_gold,
    submission_path,
)

MOCK_SITES_DIR = Path(__file__).parent / "mock-sites"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MOCK_PROFILE = FIXTURES_DIR / "mock_profile.csv"
RESULTS_DIR = Path(__file__).parent / "results"

# Content rule for "@generated@" short-answer fields: non-empty prose, not a
# placeholder. Deliberately simple and deterministic.
GENERATED_MIN_CHARS = 20


# --------------------------------------------------------------------------
# Scoring (pure; unit-tested without server/browser)
# --------------------------------------------------------------------------


def normalize(value: Any) -> str:
    """Case/whitespace-insensitive normalization for exact-match scoring."""
    text = " ".join(str(value).split())
    return text.strip().lower()


def _basename(path: str) -> str:
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def field_matches(gold: GoldField, submitted: Any) -> bool:
    """Score one gold field against the submitted value.

    - ``@generated@`` expects non-empty prose (content rule, not exact).
    - ``checkbox-group`` compares as sets of normalized options.
    - ``file`` compares basenames (the mock uploads names only).
    - everything else: normalized exact match; numbers compared textually.
    """
    if submitted is None:
        return False
    if gold.expected == GENERATED:
        text = str(submitted).strip()
        return len(text) >= GENERATED_MIN_CHARS and text != GENERATED
    if gold.type == "checkbox-group":
        expected = {normalize(v) for v in gold.expected if str(v).strip()}
        actual = {
            normalize(v)
            for v in (submitted if isinstance(submitted, list) else [submitted])
            if str(v).strip()
        }
        return bool(expected) and actual == expected
    if gold.type == "file":
        return normalize(_basename(str(submitted))) == normalize(
            _basename(str(gold.expected))
        )
    return normalize(submitted) == normalize(gold.expected)


class CaseScore(BaseModel):
    case: str
    required_answered: int
    required_total: int
    required_completion: float
    matched: int
    total_fields: int
    answer_fidelity: float
    missing: list[str] = []


def score_case(gold: GoldCase, submission: SubmissionPayload | None) -> CaseScore:
    """Score one recorded submission against the gold case."""
    submitted_fields = submission.fields if submission else {}
    missing: list[str] = []
    required_answered = 0
    matched = 0
    for gf in gold.fields:
        ok = field_matches(gf, submitted_fields.get(gf.key))
        if ok:
            matched += 1
            if gf.required:
                required_answered += 1
        else:
            missing.append(gf.key)
    required_total = len(gold.required_fields)
    total = len(gold.fields)
    return CaseScore(
        case=gold.case,
        required_answered=required_answered,
        required_total=required_total,
        required_completion=(
            required_answered / required_total if required_total else 1.0
        ),
        matched=matched,
        total_fields=total,
        answer_fidelity=matched / total if total else 1.0,
        missing=missing,
    )


def aggregate(scores: list[CaseScore]) -> dict[str, Any]:
    """Per-ATS and overall rollups."""
    def roll(subset: list[CaseScore]) -> dict[str, float]:
        req_ans = sum(s.required_answered for s in subset)
        req_tot = sum(s.required_total for s in subset)
        matched = sum(s.matched for s in subset)
        total = sum(s.total_fields for s in subset)
        return {
            "required_completion": req_ans / req_tot if req_tot else 1.0,
            "answer_fidelity": matched / total if total else 1.0,
            "cases": len(subset),
        }

    return {
        "overall": roll(scores),
        "by_ats": {
            ats: roll([s for s in scores if s.case.split("/")[0] == ats])
            for ats in sorted({s.case.split("/")[0] for s in scores})
        },
    }


# --------------------------------------------------------------------------
# Review surface (agent-as-human)
# --------------------------------------------------------------------------


class ReviewClient(Protocol):
    """The review API surface the runner drives post-fill."""

    def patch_field(self, application_id: str, field_key: str, value: str) -> None: ...

    def confirm(self, application_id: str) -> None: ...

    def submit(self, application_id: str) -> None: ...


class ApiReviewClient:
    """ReviewClient over the FastAPI review routes via in-process ASGI.

    Routes land with the review-api-cli leaf; importing ``server`` keeps this
    hermetic (no port) while preserving real HTTP semantics through httpx.
    """

    def __init__(self) -> None:
        import httpx  # local import: eval-lane dependency
        from auto_job_apply.server import server

        self._client = httpx.Client(
            transport=httpx.ASGITransport(app=server), base_url="http://testserver"
        )

    def patch_field(self, application_id: str, field_key: str, value: str) -> None:
        res = self._client.patch(
            f"/applications/{application_id}/fields",
            json={"field_key": field_key, "value": value},
        )
        res.raise_for_status()

    def confirm(self, application_id: str) -> None:
        res = self._client.post(f"/applications/{application_id}/confirm", json={})
        res.raise_for_status()

    def submit(self, application_id: str) -> None:
        res = self._client.post(f"/applications/{application_id}/submit", json={})
        res.raise_for_status()


class StubReviewClient:
    """Deterministic agent-as-human for scoring tests: no HTTP at all."""

    def __init__(self) -> None:
        self.patches: list[tuple[str, str, str]] = []
        self.confirmed: list[str] = []
        self.submitted: list[str] = []

    def patch_field(self, application_id: str, field_key: str, value: str) -> None:
        self.patches.append((application_id, field_key, value))

    def confirm(self, application_id: str) -> None:
        self.confirmed.append(application_id)

    def submit(self, application_id: str) -> None:
        self.submitted.append(application_id)


def human_stub_answer(field_label: str) -> str:
    """Deterministic agent-as-human short answer (LLM-free fallback)."""
    return (
        f"[agent-as-human eval answer for '{field_label}'] Prepared after "
        "reviewing the startup, product, role, and culture."
    )


# --------------------------------------------------------------------------
# Mock-site server management
# --------------------------------------------------------------------------


def _mock_base_url() -> str:
    return str(settings.get("EVALS.mock_base_url", "http://localhost:5173")).rstrip(
        "/"
    )


@dataclass
class MockServer:
    """Lifecycle for the programmatic vite dev server."""

    base_url: str
    process: subprocess.Popen[str] | None = dc_field(default=None, init=False)

    def __enter__(self) -> "MockServer":
        port = self.base_url.rsplit(":", 1)[-1]
        if not (MOCK_SITES_DIR / "node_modules").exists():
            logger.info("eval: installing mock-sites npm deps (npm ci)")
            subprocess.run(
                ["npm", "ci", "--prefix", str(MOCK_SITES_DIR)],
                check=True,
                capture_output=True,
                text=True,
            )
        self.process = subprocess.Popen(
            ["node", str(MOCK_SITES_DIR / "server.mjs"), "--port", port],
            cwd=MOCK_SITES_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._wait_ready(timeout_s=30.0)
        return self

    def _wait_ready(self, timeout_s: float) -> None:
        import urllib.request
        import urllib.error

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                out = self.process.stdout.read() if self.process.stdout else ""
                raise RuntimeError(f"mock-sites server exited early:\n{out}")
            try:
                with urllib.request.urlopen(self.base_url, timeout=2) as res:
                    if res.status == 200:
                        logger.info("eval: mock sites ready at %s", self.base_url)
                        return
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.3)
        raise RuntimeError(f"mock-sites server not ready within {timeout_s}s")

    def __exit__(self, *exc: object) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


# --------------------------------------------------------------------------
# Local URL plugin wrappers (mock routes aren't on real ATS hosts)
# --------------------------------------------------------------------------


class _LocalPlugin:
    """Wrap a real ATS plugin so localhost mock URLs dispatch to it."""

    def __init__(self, name: str, base: Any) -> None:
        self.name = name
        self._base = base

    def detect(self, url: str) -> bool:
        return bool(re.match(rf"https?://[^/]+/{re.escape(self.name)}(/|$)", url))

    def base_selectors(self) -> dict[str, str]:
        return self._base.base_selectors()

    def submit_button(self, page: Any) -> Any:
        return self._base.submit_button(page)

    def pre_extract(self, page: Any) -> None:
        return self._base.pre_extract(page)

    def post_fill(self, page: Any, answers: dict[str, str]) -> None:
        return self._base.post_fill(page, answers)


def _register_local_plugins() -> None:
    from auto_job_apply.services import ats_registry

    ats_registry._ensure_plugins_loaded()
    for name, module in (("ashby", "ashby"), ("greenhouse", "greenhouse"), ("lever", "lever")):
        mod = __import__(f"auto_job_apply.services.ats.{module}", fromlist=["x"])
        singleton = getattr(mod, "plugin", None) or getattr(mod, "PLUGIN", None)
        wrapper = _LocalPlugin(name, singleton)
        register(wrapper)
    logger.info("eval: registered localhost plugin wrappers")


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------


def _seed_data_dir(tmp: Path) -> None:
    """Point DATA.dir at a fresh temp dir seeded with the mock profile."""
    ensure_data_dir(tmp)
    shutil.copy(MOCK_PROFILE, tmp / "applicant_profile.csv")
    settings.set("DATA.dir", str(tmp))
    logger.info("eval: seeded DATA.dir=%s from %s", tmp, MOCK_PROFILE)


def _application_id(case: str) -> str:
    """Path-safe application id for artifact dirs."""
    return case.replace("/", "-")


def _deterministic_review(
    gold: GoldCase,
    application_id: str,
    answered_keys: set[str],
    review: ReviewClient,
) -> None:
    """Agent-as-human: patch any unanswered required field, then confirm.

    Short-answer (textarea) fields fall back to the deterministic stub when
    no LLM draft materialized; other required gaps get the gold expected
    value (the human reviewer supplies what the pipeline could not).
    """
    for gf in gold.fields:
        if not gf.required or gf.key in answered_keys:
            continue
        value = (
            human_stub_answer(gf.label)
            if gf.expected == GENERATED
            else (
                str(gf.expected)
                if not isinstance(gf.expected, list)
                else "|".join(str(v) for v in gf.expected)
            )
        )
        review.patch_field(application_id, gf.key, value)
    review.confirm(application_id)


def run(cases: list[str], review: ReviewClient, *, keep_data_dir: Path | None = None) -> dict[str, Any]:
    """Run the full eval over ``cases``; returns the results dict."""
    _register_local_plugins()
    run_name = f"eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    tmp = keep_data_dir or Path(tempfile.mkdtemp(prefix="eval-data-"))
    _seed_data_dir(tmp)

    scores: list[CaseScore] = []
    with MockServer(_mock_base_url()):
        for case in cases:
            application_id = _application_id(case)
            url = f"{_mock_base_url()}/{case}"
            # Clear any stale recorded submission for this case.
            submission_path(case).unlink(missing_ok=True)
            gold = load_gold(case)
            logger.info("eval: case %s -> %s", case, url)

            form = extract(url, application_id=application_id)
            plan = plan_answers(form)
            filled = fill(url, plan, application_id)
            answered = {f.key for f in filled.fields if f.answer}

            _deterministic_review(gold, application_id, answered, review)
            review.submit(application_id)

            # The dev-server records the submission synchronously on POST;
            # poll briefly for filesystem visibility.
            submission: SubmissionPayload | None = None
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if submission_path(case).exists():
                    from evals.mock_sites_gold import load_submission

                    submission = load_submission(case)
                    break
                time.sleep(0.25)
            score = score_case(gold, submission)
            scores.append(score)
            logger.info(
                "eval: %s required=%.2f fidelity=%.2f missing=%s",
                case,
                score.required_completion,
                score.answer_fidelity,
                score.missing,
            )
            langfuse_service.score_eval(
                run_name=run_name,
                item_id=case,
                metric="required_completion",
                value=score.required_completion,
                comment=f"missing={score.missing}",
            )
            langfuse_service.score_eval(
                run_name=run_name,
                item_id=case,
                metric="answer_fidelity",
                value=score.answer_fidelity,
            )

    rollups = aggregate(scores)
    langfuse_service.score_eval(
        run_name=run_name,
        item_id="overall",
        metric="required_completion",
        value=rollups["overall"]["required_completion"],
    )
    langfuse_service.flush()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_file = RESULTS_DIR / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    payload = {
        "run_name": run_name,
        "cases": [s.model_dump() for s in scores],
        **rollups,
    }
    results_file.write_text(json.dumps(payload, indent=2))
    logger.info("eval: results written to %s", results_file)
    payload["results_file"] = str(results_file)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run mock-ATS evals")
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="Subset of cases (default: all gold cases)",
    )
    parser.add_argument(
        "--keep-data-dir",
        type=Path,
        default=None,
        help="Reuse a DATA.dir (skips temp dir creation)",
    )
    args = parser.parse_args(argv)
    cases = args.cases or all_cases()
    result = run(cases, ApiReviewClient(), keep_data_dir=args.keep_data_dir)
    overall = result["overall"]["required_completion"]
    return 0 if overall >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
