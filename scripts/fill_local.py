"""Interactive fill against the local mock sites.

Wraps the real ATS plugins so http://localhost:5173/<ats>/<case> URLs route
to them, then runs the standard extract → plan → fill pipeline.
Usage:
  PYTHONPATH=src:. uv run python scripts/fill_local.py ashby/basic
"""
from __future__ import annotations

import re
import sys
from typing import Any

from auto_job_apply.logging import logger
from auto_job_apply.services import ats_registry
from auto_job_apply.services.ats_registry import register


class _LocalPlugin:
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


def register_local_plugins() -> None:
    ats_registry._ensure_plugins_loaded()
    for name in ("ashby", "greenhouse", "lever"):
        mod = __import__(f"auto_job_apply.services.ats.{name}", fromlist=["x"])
        singleton = getattr(mod, "plugin", None)
        register(_LocalPlugin(name, singleton))
    logger.info("registered localhost plugin wrappers")


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else "ashby/basic"
    register_local_plugins()
    from auto_job_apply.services.extractor import extract
    from auto_job_apply.graphs.planner import plan_answers
    from auto_job_apply.services.filler import fill

    app_id = case.replace("/", "-")
    url = f"http://localhost:5173/{case}"
    form = extract(url, application_id=app_id)
    plan = plan_answers(form)
    fill(url, plan, app_id)
    print(f"\nfilled {app_id} — review at http://localhost:8000/applications/{app_id}")
