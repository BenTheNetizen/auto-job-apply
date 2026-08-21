from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auto_job_apply.config import settings
from auto_job_apply.errors import SubmissionError
from auto_job_apply.logging import logger
from auto_job_apply.services import review as review_service

server = FastAPI(title="auto_job_apply")

_cors = settings.get("API.cors", ["*"])
server.add_middleware(
    CORSMiddleware,
    allow_origins=list(_cors) if _cors else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@server.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --- review API (review-api-cli leaf) ------------------------------------


class FieldEdit(BaseModel):
    field_key: str
    value: str


class ConfirmBody(BaseModel):
    learn_from_edits: bool = False


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@server.get("/applications")
def list_applications(status: str | None = None) -> dict[str, Any]:
    rows = review_service.list_applications(status=status)
    return {"applications": [r.model_dump(mode="json") for r in rows]}


@server.get("/applications/{app_id}")
def get_application(app_id: str) -> dict[str, Any]:
    try:
        row = review_service.get_application(app_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    detail = row.model_dump(mode="json")
    detail["artifacts"] = _artifact_paths(app_id)
    return detail


def _artifact_paths(app_id: str) -> list[str]:
    from auto_job_apply.utils.artifacts import artifact_dir

    directory = artifact_dir(app_id)
    if not directory.is_dir():
        return []
    return sorted(str(p) for p in directory.iterdir() if p.is_file())


@server.patch("/applications/{app_id}/fields")
def edit_field(app_id: str, body: FieldEdit) -> dict[str, Any]:
    try:
        row = review_service.edit_field(app_id, body.field_key, body.value)
    except KeyError as exc:
        raise _not_found(exc) from exc
    return row.model_dump(mode="json")


@server.post("/applications/{app_id}/confirm")
def confirm_application(app_id: str, body: ConfirmBody | None = None) -> dict[str, Any]:
    try:
        row = review_service.confirm_application(
            app_id, learn_from_edits=(body.learn_from_edits if body else False)
        )
    except KeyError as exc:
        raise _not_found(exc) from exc
    except SubmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return row.model_dump(mode="json")


@server.post("/applications/{app_id}/submit")
def submit_application(app_id: str) -> dict[str, Any]:
    try:
        row = review_service.submit_application(app_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except SubmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return row.model_dump(mode="json")


logger.info("FastAPI server configured")

__all__ = ["server"]
