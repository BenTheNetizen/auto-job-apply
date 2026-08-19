from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from package_name.config import settings
from package_name.logging import logger

server = FastAPI(title="package_name")

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
