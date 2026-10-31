"""HTTP endpoint that receives GitHub webhooks."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.github.signature import is_valid_signature

# GitHub caps webhook payloads at 25 MB; anything bigger is not from GitHub.
MAX_BODY_BYTES = 25 * 1024 * 1024

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookAck(BaseModel):
    status: str


async def read_limited_body(request: Request) -> bytes:
    """Read the body in chunks, refusing it as soon as it exceeds the size limit.

    Checking while streaming (not just the Content-Length header, which a client
    can omit or fake) stops a huge request from filling the server's memory.
    """
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Payload too large")
    return bytes(body)


async def verified_body(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> bytes:
    """FastAPI dependency: return the raw body, or reject the request with 401."""
    body = await read_limited_body(request)
    secret = settings.github_webhook_secret.get_secret_value()
    if not is_valid_signature(body, x_hub_signature_256, secret):
        # Same generic message for every failure: don't tell attackers what was wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    return body


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verified_body)],
)
async def receive_github_webhook() -> WebhookAck:
    """Accept a verified GitHub webhook. Processing the event comes in a later step."""
    return WebhookAck(status="accepted")
