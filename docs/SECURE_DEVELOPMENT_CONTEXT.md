# Secure Development Context

Resumo operacional para futuras sessões do Codex, derivado do contexto SciELO/FapUNIFESP NSI.04 informado pelo usuário. O documento original foi marcado como interno; por isso este arquivo registra apenas guardrails práticos para o projeto, sem copiar a política completa.

## Guardrails

- Separar ambientes de desenvolvimento, teste, homologação e produção.
- Aplicar menor privilégio para usuários, processos, SSH, banco, Proxmox e tokens.
- Nunca versionar segredos, senhas, tokens, chaves privadas, hostnames reais ou dados sensíveis.
- Usar variáveis injetadas ou gerenciador de segredos para credenciais.
- Não registrar tokens, senhas, chaves ou dados sensíveis em logs.
- Usar HTTPS e comunicação interna protegida, preferencialmente VPN ou mTLS para integrações sensíveis.
- Usar queries parametrizadas para acesso a banco.
- Evitar criptografia obsoleta: MD5, SHA1, DES, 3DES, RC4, RC2, MD4 e modo ECB.
- Verificar dependências contra CVEs antes de releases quando viável.
- Documentar decisões relevantes de segurança.

## Aplicação Neste Projeto

- `POST /webhook/alertmanager` deve permanecer autenticado por `ORCH_WEBHOOK_TOKEN`.
- Comparação de token deve continuar usando comparação segura contra timing attacks.
- SSH deve permanecer com chave pública e senha desabilitada por padrão.
- Comandos remotos devem permanecer allowlisted em código.
- Payloads do Alertmanager nunca podem montar comandos.
- Circuit breaker deve rodar antes de ações de restart/reboot.
- Toda ação deve gerar auditoria sem segredos.
- Reboot Proxmox deve permanecer protegido por múltiplas pré-condições.
- Docker deve rodar como usuário não-root.
- `.env.example`, `docker-compose.yml`, configs e testes devem usar valores genéricos.
- SQLite é aceitável no MVP; produção deve avaliar armazenamento protegido, retenção e PostgreSQL com usuário DML mínimo.

## Checklist Antes de Commit

- Sem segredos em código, docs, YAML, compose ou testes.
- Sem nomes reais de infraestrutura em arquivos públicos, salvo pedido explícito.
- Entradas externas validadas por Pydantic ou equivalente.
- SQL parametrizado.
- Falhas de autenticação fecham por padrão.
- Testes cobrem autenticação, allowlist, circuit breaker e caminhos bloqueados.
- Logs/auditoria têm rastreabilidade sem vazamento de segredo.
