# ADR 0005 — PostgreSQL, S3/MinIO e limites de SSRF

## Contexto

O fluxo precisa de persistência transacional, arquivos grandes fora do banco e
proteção contra requisições a endereços internos.

## Decisão

- PostgreSQL + SQLAlchemy 2 async + Alembic; IDs UUID; JSONB para metadados de
  uso e avisos.
- Arquivos enviados vão para storage S3-compatible, com MinIO no Compose e bucket
  criado por job idempotente. Texto/URL não usam storage.
- URLs são validadas sintaticamente e por DNS antes do enqueue e em cada
  requisição/redirect. IPs privados, loopback, link-local, multicast, reservados
  e hostnames internos são bloqueados.
- Uploads validam extensão, MIME declarado e assinatura real antes da conversão.
- O schema é squashado em `001_simplified`; volumes de versões anteriores devem
  ser recriados com `docker compose down -v`.

## Limitações conhecidas

- A validação por DNS não elimina rebinding entre a resolução e a conexão; uma
  defesa completa exigiria fixar o IP no socket.
- Não há navegador headless, execução de JavaScript, bypass de paywall nem
  antimalware.
- A regra global não tem histórico de versões; o snapshot fica em cada análise.
