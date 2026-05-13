from __future__ import annotations

import httpx

from app.models import ValidationResult


class HTTPValidator:
    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    async def check(self, url: str) -> ValidationResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(url)
            return ValidationResult(
                name="http_get",
                success=200 <= response.status_code < 400,
                detail=f"status_code={response.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            return ValidationResult(name="http_get", success=False, detail=str(exc))
