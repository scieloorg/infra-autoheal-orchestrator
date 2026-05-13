from __future__ import annotations

import httpx


async def post_webhook(url: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload)
