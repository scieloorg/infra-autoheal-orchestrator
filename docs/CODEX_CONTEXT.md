# Codex Context: infra-autoheal-orchestrator

Use this as the short project memory for future sessions.

## Local Path

```text
/Users/rondinelisaad/Downloads/repo-scielo/infra-autoheal-orchestrator
```

## Purpose

Python 3.12+ FastAPI service for safe infrastructure auto-healing from Alertmanager webhooks. It routes alerts to allowlisted runbooks, executes SSH actions with fixed commands, validates recovery, stores SQLite audit evidence, and optionally calls Proxmox/OpenSearch.

## Non-Negotiable Safety Rules

- Follow the secure development context summarized in `docs/SECURE_DEVELOPMENT_CONTEXT.md`.
- Never run arbitrary commands from alert payloads.
- Keep actions allowlisted: `restart_apache`, `restart_mariadb`, `collect_evidence`, `reboot_vm`.
- Require `ORCH_WEBHOOK_TOKEN` for `POST /webhook/alertmanager`.
- Keep SSH public-key auth and password auth disabled by default.
- Keep circuit breakers before action execution.
- Keep post-action validation and SQLite audit records.
- Keep Proxmox reboot gated by multiple unavailable checks and active alert duration.

## Important Files

- `orchestrator/app/main.py`: FastAPI app.
- `orchestrator/app/security.py`: webhook token auth.
- `orchestrator/app/runner.py`: orchestration flow.
- `orchestrator/app/rules/router.py`: alert/action/host routing.
- `orchestrator/app/rules/policies.py`: circuit breaker.
- `orchestrator/app/actions/ssh.py`: command allowlist.
- `orchestrator/app/actions/apache.py`: Apache runbook.
- `orchestrator/app/actions/mariadb.py`: MariaDB runbook.
- `orchestrator/app/actions/proxmox.py`: protected reboot action.
- `orchestrator/app/storage/events.py`: audit events.
- `orchestrator/app/storage/state.py`: circuit state.
- `orchestrator/config/hosts.yaml`: generic host config.
- `orchestrator/config/policies.yaml`: limits/timeouts.
- `docker-compose.yml`: root compose.
- `.env.example`: compose env template.
- `docs/SECURE_DEVELOPMENT_CONTEXT.md`: secure development guardrails for future sessions.

## Generic Host Names

Use generic names in repo docs/tests/config:

- `app-node-01.example.local`
- `db-node-01.example.local`

Do not reintroduce real hostnames unless explicitly requested.

## Validate

From `orchestrator/`:

```bash
.venv/bin/python -m pytest -p no:cacheprovider
.venv/bin/python -m ruff check . --no-cache
```

## Docker

From repo root:

```bash
cp .env.example .env
docker compose up --build
```

Required env values:

- `ORCH_WEBHOOK_TOKEN`
- `SSH_PRIVATE_KEY_PATH`

If SQLite fails with `unable to open database file`, the `/app/data` volume likely has bad ownership. Recreate the local volume with `docker compose down -v`, understanding it deletes local SQLite audit data.
