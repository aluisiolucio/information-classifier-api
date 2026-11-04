# ADR 0002 — Análise assíncrona com Celery e idempotência

## Contexto

O aceite da análise precisa ser rápido (`202`), mas extração e classificação são
pesadas e não podem bloquear a requisição HTTP. Banco e fila não compartilham
transação.

## Decisão

Persistir a análise antes de publicar `analyze_analysis` na fila `analysis`. O
dispatcher tenta publicar imediatamente; se o enqueue falhar, a análise é marcada
como `failed` com `task_dispatch_failed`.

Consumidores são idempotentes: análises em estado terminal são ignoradas. Erros
transitórios usam retry com backoff; erros permanentes marcam a análise como
`failed` com `error_code` estável.

Não há outbox transacional nem beat nesta versão. A simplificação reduz peças
operacionais, ao custo de uma janela pequena em que uma falha de processo após o
commit e antes do enqueue pode deixar a análise em `queued`.

## Consequências

- Entrega é at-least-once; reexecutar uma tarefa não duplica resultados.
- Não há rotina de reenvio automático de análises órfãs.
- O histórico de tentativas fica no broker/worker, não em uma tabela de outbox.
