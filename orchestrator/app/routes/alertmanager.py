from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_orchestrator
from app.models import AlertmanagerPayload, AlertProcessResponse
from app.runner import Orchestrator
from app.security import verify_webhook_token

router = APIRouter(
    prefix="/webhook",
    tags=["alertmanager"],
    dependencies=[Depends(verify_webhook_token)],
)


@router.post("/alertmanager", response_model=AlertProcessResponse)
async def alertmanager_webhook(
    payload: AlertmanagerPayload,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> AlertProcessResponse:
    results = []
    for alert in payload.alerts:
        if payload.status == "resolved":
            continue
        results.append(await orchestrator.process_alert(alert))

    correlation_id = results[0].decision.correlation_id if results else "none"
    return AlertProcessResponse(correlation_id=correlation_id, processed=len(results), results=results)
