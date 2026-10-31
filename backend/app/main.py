"""FastAPI application entry point: creates the app and registers its routes."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.github import webhooks

app = FastAPI(title="diffwise")
app.include_router(webhooks.router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", tags=["meta"])
def health() -> HealthResponse:
    """Liveness check: answers as long as the process is running.

    Used by Docker, CI and post-deploy smoke tests. Deliberately does no work
    (no DB or GitHub calls) so it stays fast and never leaks internal details.
    """
    return HealthResponse(status="ok")
