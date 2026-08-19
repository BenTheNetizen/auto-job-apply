from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auto_job_apply.config import settings
from auto_job_apply.logging import logger

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


logger.info("FastAPI server configured")

__all__ = ["server"]
