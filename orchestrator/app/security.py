from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def verify_webhook_token(
    authorization: str | None = Header(default=None),
    x_webhook_token: str | None = Header(default=None),
) -> None:
    configured_token = get_settings().webhook_token
    if configured_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="webhook token is not configured",
        )

    expected = configured_token.get_secret_value()
    supplied = _extract_bearer_token(authorization) or x_webhook_token
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid webhook token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _extract_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token
