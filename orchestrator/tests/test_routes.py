from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies import get_orchestrator
from app.main import app
from app.security import verify_webhook_token


class RouteFakeOrchestrator:
    async def process_alert(self, alert):
        from app.models import ActionDecision, ActionExecution, ActionName

        return ActionExecution(
            decision=ActionDecision(
                alertname=alert.labels.alertname,
                host=alert.labels.instance,
                action=ActionName.RESTART_APACHE,
                allowed=True,
                reason="allowed",
            ),
            status="success",
        )


def test_alertmanager_endpoint_accepts_standard_payload():
    app.dependency_overrides[get_orchestrator] = lambda: RouteFakeOrchestrator()
    app.dependency_overrides[verify_webhook_token] = lambda: None
    client = TestClient(app)
    response = client.post(
        "/webhook/alertmanager",
        json={
            "status": "firing",
            "alerts": [
                {
                    "labels": {
                        "alertname": "ApacheDown",
                        "instance": "app-node-01.example.local",
                        "action": "restart_apache",
                    }
                }
            ],
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 1
    assert body["results"][0]["status"] == "success"


def test_alertmanager_endpoint_requires_token_when_not_overridden():
    client = TestClient(app)

    response = client.post(
        "/webhook/alertmanager",
        json={"status": "firing", "alerts": []},
    )

    assert response.status_code == 503
