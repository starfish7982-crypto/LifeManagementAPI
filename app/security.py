"""API key authentication.

A single shared key is enough for a personal service and keeps the surface small.
Two details that matter:

  * Comparison uses `secrets.compare_digest`, not `==`. String equality short-circuits
    on the first differing byte, which leaks key length and prefix through timing.
  * The key is read from settings per request via Depends, so tests can override it.
"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    provided: str | None = Depends(_header),
    settings: Settings = Depends(get_settings),
) -> None:
    if not provided or not secrets.compare_digest(provided, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header",
        )
