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
          "instance": "app-node-01.example.local",
          "action": "restart_apache"
        }
      }
    ]
  }'
```

## Docker

```bash
cp .env.example .env
openssl rand -hex 32
# edite ORCH_WEBHOOK_TOKEN e SSH_PRIVATE_KEY_PATH no .env
docker compose up --build
```

## Configuração

Hosts: `orchestrator/config/hosts.yaml`

Políticas: `orchestrator/config/policies.yaml`

Exemplo:

```yaml
limits:
  restart_service:
    max_attempts: 2
    window_minutes: 15

  reboot_vm:
    max_attempts: 1
    window_minutes: 60

reboot_preconditions:
  min_alert_age_minutes: 5
```

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
          "instance": "app-node-01.example.local",
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
ssh-copy-id -i ~/.ssh/infra_autoheal_ed25519.pub rundeck@app-node-01.example.local
ssh-copy-id -i ~/.ssh/infra_autoheal_ed25519.pub rundeck@db-node-01.example.local
```

Crie o `known_hosts` usado pelo container:

```bash
ssh-keyscan -H app-node-01.example.local db-node-01.example.local > orchestrator/config/known_hosts
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

- alerta `HostUnreachable` ou alias equivalente está ativo pelo tempo configurado em `reboot_preconditions.min_alert_age_minutes`
- host está mapeado em `hosts.yaml`
- alerta traz confirmação explícita `node_exporter_down=true`
- alerta traz confirmação explícita `blackbox_unavailable=true`
- SSH está indisponível
- blackbox HTTP/TCP está indisponível
- circuit breaker permite a ação

O limite padrão é 1 reboot por VM em 60 minutos. O tempo mínimo padrão do alerta antes de reboot é 5 minutos.

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

Configuração via `.env`:

```env
ORCH_OPENSEARCH__ENABLED=true
ORCH_OPENSEARCH__HOSTS=["https://opensearch.example.local:9200"]
ORCH_OPENSEARCH__USERNAME=infra-autoheal-writer
ORCH_OPENSEARCH__PASSWORD=change-me
ORCH_OPENSEARCH__VERIFY_CERTS=true
ORCH_OPENSEARCH__INDEX_PREFIX=infra-incidents
ORCH_OPENSEARCH__MAX_FIELD_LENGTH=8192
```

O usuário do OpenSearch deve seguir menor privilégio, com permissão apenas para criar/indexar documentos em:

```text
infra-incidents-*
```

Cada documento inclui:

- `timestamp`
- `correlation_id`
- `host`
- `alertname`
- `action`
- `status`
- decisão do roteador e motivo
- motivo de bloqueio, quando houver
- comandos executados com `exit_code`, `stdout` e `stderr`
- validação pós-ação
- evidências coletadas
- resposta Proxmox, quando aplicável

Saídas de comando são truncadas por `ORCH_OPENSEARCH__MAX_FIELD_LENGTH` e passam por redação básica de tokens, senhas, secrets, API keys, Authorization Bearer e chaves privadas. O SQLite continua sendo a trilha local obrigatória; falha ao indexar no OpenSearch é registrada em log e não bloqueia o auto-healing.

Consulta por `correlation_id`:

```json
GET infra-incidents-*/_search
{
  "query": {
    "term": {
      "correlation_id.keyword": "ddf828bc-bb66-44bd-9be5-faf6b8d87bfb"
    }
  }
}
```

## Slack

Opcionalmente, o orquestrador pode enviar notificações para Slack via Incoming Webhook.

Configuração via `.env`:

```env
ORCH_SLACK__ENABLED=true
ORCH_SLACK__WEBHOOK_URL=https://hooks.slack.com/services/...
ORCH_SLACK__TIMEOUT_SECONDS=5
```

Eventos enviados:

- início de ação automática, após roteamento e circuit breaker liberarem a execução
- resultado final da ação, com sucesso/falha e duração aproximada
- bloqueio da automação, incluindo circuit breaker e precondições de segurança

Exemplo de início:

```text
🚨 Autoheal iniciado
Host: node02-submission.scielo.org
Alerta: MySQLDown
Ação: restart_mariadb
Correlation ID: abc-123
```

Exemplo de sucesso:

```text
✅ Autoheal concluído
Host: node02-submission.scielo.org
Ação: restart_mariadb
Validação: sucesso
Duração: 8s
Correlation ID: abc-123
```

Exemplo de falha:

```text
❌ Autoheal falhou
Host: node02-submission.scielo.org
Ação: restart_mariadb
Motivo: validação falhou
Próximo passo: intervenção humana
Duração: 8s
Correlation ID: abc-123
```

Exemplo de bloqueio:

```text
⚠️ Autoheal bloqueado por circuit breaker
Host: mysql.scielo.org
Alerta: MySQLDown
Ação: restart_mariadb
Motivo: circuit breaker open: 2/2 attempts for mariadb in 15m
Correlation ID: abc-123
```

Falha ao enviar notificação ao Slack é registrada em log e não bloqueia o auto-healing nem a auditoria SQLite/OpenSearch. Trate a URL do webhook como segredo e injete via `.env` ou secret do ambiente.

## Testes

```bash
cd orchestrator
pytest
```

Os testes usam fakes para SSH, HTTP e Proxmox e cobrem os critérios de aceite principais.

## Reuso com Codex

Este repositório versiona uma skill do Codex em:

```text
.codex/skills/infra-autoheal-orchestrator
.codex/skills/db-permission-auditor
.codex/skills/secure-sdlc
.codex/skills/audit-log-generator
.codex/skills/crypto-standards
.codex/skills/secret-detection
.codex/skills/secure-code-review
```

Para instalar em outra máquina:

```bash
mkdir -p ~/.codex/skills
cp -R .codex/skills/infra-autoheal-orchestrator ~/.codex/skills/
cp -R .codex/skills/db-permission-auditor ~/.codex/skills/
cp -R .codex/skills/secure-sdlc ~/.codex/skills/
cp -R .codex/skills/audit-log-generator ~/.codex/skills/
cp -R .codex/skills/crypto-standards ~/.codex/skills/
cp -R .codex/skills/secret-detection ~/.codex/skills/
cp -R .codex/skills/secure-code-review ~/.codex/skills/
```

Depois, em uma nova sessão do Codex:

```text
Use a skill infra-autoheal-orchestrator para trabalhar neste projeto.
```

Também há um contexto curto em `docs/CODEX_CONTEXT.md` para sessões sem instalação da skill.

O contexto de desenvolvimento seguro fica em `docs/SECURE_DEVELOPMENT_CONTEXT.md` e também é referenciado pela skill versionada.

A skill `db-permission-auditor` deve ser usada para revisar usuários, permissões,
GRANTs, strings de conexão e configurações de banco conforme menor privilégio.

A skill `secure-sdlc` deve ser usada para checklists e artefatos de segurança por
fase do ciclo de desenvolvimento, como requisitos, testes, deploy e GMUD.

A skill `audit-log-generator` deve ser usada para instrumentar ou revisar logs
de auditoria em endpoints, autenticação, operações CRUD, jobs e acessos restritos,
sem registrar segredos ou dados sensíveis.

A skill `crypto-standards` deve ser usada para escolher ou revisar algoritmos de
hash, criptografia, TLS, JWT, tokens, assinaturas digitais e chaves, bloqueando
algoritmos obsoletos como MD5, SHA1, DES, 3DES, RC4 e ECB.

A skill `secret-detection` deve ser usada antes de commits, push, PRs e revisões
para detectar segredos, credenciais, tokens, chaves privadas, `.env` versionado e
configurações inseguras.

A skill `secure-code-review` deve ser usada para revisão de segurança de código,
features, PRs e diffs, cobrindo injeção, autenticação, XSS, controle de acesso,
validação de entrada, criptografia, configuração e logging inseguro.

## Exemplos

- `examples/alertmanager.yml`
- `examples/prometheus-rules.yml`
