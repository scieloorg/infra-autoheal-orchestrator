# infra-autoheal-orchestrator

Orquestrador Python/FastAPI para auto-healing seguro de infraestrutura a partir de alertas do Alertmanager.

O MVP implementa:

- endpoint `POST /webhook/alertmanager`
- allowlist obrigatória de ações: `restart_apache`, `restart_mariadb`, `collect_evidence`, `reboot_vm`
- roteamento fixo por alerta/host, sem comandos vindos do payload
- SSH seguro com comandos allowlisted
- circuit breaker em SQLite
- validação pós-ação por HTTP e `mysqladmin ping`
- coleta de evidências Linux
- reboot de VM via API Proxmox protegido por pré-condições
- auditoria completa em SQLite e logs JSON
- função opcional para indexar incidentes no OpenSearch

## Arquitetura

```text
Prometheus/Alertmanager
-> FastAPI /webhook/alertmanager
-> RunbookRouter + allowlist
-> CircuitBreaker
-> SSHExecutor ou ProxmoxClient
-> validação pós-ação
-> SQLite/OpenSearch/logs JSON
```

## Segurança operacional

O serviço nunca executa comandos arbitrários vindos do alerta. O payload pode informar `action`, mas isso só é aceito quando coincide com o runbook local configurado para o `alertname`.

Os comandos permitidos ficam em `orchestrator/app/actions/ssh.py`. A configuração define nomes de serviço por host, mas não define comandos.

Para produção, configure `sudoers` para o usuário `rundeck` permitindo apenas:

```text
/bin/systemctl restart httpd
/bin/systemctl is-active httpd
/bin/systemctl restart mariadb
/bin/systemctl is-active mariadb
```

## Executar localmente

```bash
cd orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Teste de saúde:

```bash
curl http://127.0.0.1:8000/healthz
```

Exemplo de alerta:

```bash
curl -X POST http://127.0.0.1:8000/webhook/alertmanager \
  -H 'Content-Type: application/json' \
  -d '{
    "status": "firing",
    "alerts": [
      {
        "labels": {
          "alertname": "ApacheDown",
          "instance": "node01-submission.scielo.org",
          "action": "restart_apache"
        }
      }
    ]
  }'
```

## Docker

```bash
cd orchestrator
docker compose up --build
```

## Configuração

Hosts: `orchestrator/config/hosts.yaml`

Políticas: `orchestrator/config/policies.yaml`

Variáveis úteis:

- `ORCH_HOSTS_CONFIG_PATH`
- `ORCH_POLICIES_CONFIG_PATH`
- `ORCH_SQLITE_PATH`
- `ORCH_LOG_LEVEL`
- `ORCH_WEBHOOK_TOKEN`
- `ORCH_SSH__PRIVATE_KEY_PATH`
- `ORCH_SSH__KNOWN_HOSTS_PATH`
- `ORCH_SSH__PASSWORD_AUTH=false`
- `ORCH_PROXMOX__BASE_URL`
- `ORCH_PROXMOX__TOKEN_ID`
- `ORCH_PROXMOX__TOKEN_SECRET`
- `ORCH_PROXMOX__VERIFY_TLS`

## Token do webhook

O endpoint `POST /webhook/alertmanager` exige token. Se `ORCH_WEBHOOK_TOKEN`
não estiver configurado, o endpoint falha fechado com `503`.

Use um valor longo e aleatório:

```bash
export ORCH_WEBHOOK_TOKEN="$(openssl rand -hex 32)"
```

Chamando a API:

```bash
curl -X POST http://127.0.0.1:8000/webhook/alertmanager \
  -H "Authorization: Bearer $ORCH_WEBHOOK_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "status": "firing",
    "alerts": [
      {
        "labels": {
          "alertname": "ApacheDown",
          "instance": "node01-submission.scielo.org",
          "action": "restart_apache"
        }
      }
    ]
  }'
```

Se o Alertmanager não puder enviar header customizado diretamente na sua versão,
coloque um proxy interno na frente do orquestrador para injetar o header
`Authorization` ou `X-Webhook-Token`. Não exponha esse endpoint sem autenticação.

## SSH com chave pública

O orquestrador usa autenticação SSH por chave. A chave pública deve estar no
`~rundeck/.ssh/authorized_keys` dos servidores, e o serviço deve receber o
caminho da chave privada correspondente.

Exemplo para gerar uma chave dedicada:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/infra_autoheal_ed25519 -C infra-autoheal-orchestrator
ssh-copy-id -i ~/.ssh/infra_autoheal_ed25519.pub rundeck@node01-submission.scielo.org
ssh-copy-id -i ~/.ssh/infra_autoheal_ed25519.pub rundeck@mysql.scielo.org
```

Crie o `known_hosts` usado pelo container:

```bash
ssh-keyscan -H node01-submission.scielo.org mysql.scielo.org > orchestrator/config/known_hosts
```

Rodando localmente:

```bash
export ORCH_SSH__PRIVATE_KEY_PATH="$HOME/.ssh/infra_autoheal_ed25519"
export ORCH_SSH__KNOWN_HOSTS_PATH="$(pwd)/config/known_hosts"
export ORCH_SSH__PASSWORD_AUTH=false
uvicorn app.main:app --reload
```

No Docker, o `docker-compose.yml` monta a chave como secret em
`/run/secrets/ssh_autoheal_key`. Ajuste o caminho em `secrets.ssh_autoheal_key.file`
caso use outro nome.

## Reboot via Proxmox

A ação `reboot_vm` só roda quando:

- alerta `HostUnreachable` está ativo por pelo menos 5 minutos
- host está mapeado em `hosts.yaml`
- SSH está indisponível
- blackbox HTTP/TCP está indisponível
- circuit breaker permite a ação

O limite padrão é 1 reboot por VM em 60 minutos.

## Auditoria

Cada alerta processado gera registro em SQLite contendo:

- timestamp
- correlation_id
- alertname
- host
- ação escolhida
- comandos executados
- stdout/stderr
- código de saída
- validação
- status `success`, `failed`, `blocked` ou `ignored`
- motivo de bloqueio
- evidências coletadas

## OpenSearch

Quando habilitado por configuração, os documentos são indexados em:

```text
infra-incidents-YYYY.MM.DD
```

## Testes

```bash
cd orchestrator
pytest
```

Os testes usam fakes para SSH, HTTP e Proxmox e cobrem os critérios de aceite principais.

## Exemplos

- `examples/alertmanager.yml`
- `examples/prometheus-rules.yml`
