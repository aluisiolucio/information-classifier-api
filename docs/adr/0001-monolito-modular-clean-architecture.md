# ADR 0001 — Monólito modular em Clean Architecture

## Contexto

O fluxo precisa aceitar mídias variadas, executar trabalho pesado fora da
requisição HTTP e manter o deploy simples.

## Decisão

Manter um monólito modular com as camadas `domain` → `application` → `adapters` →
`infrastructure`:

- `domain` contém entidades, serviços e `Protocol`s, sem imports externos.
- `application` orquestra casos de uso e depende apenas de `domain`.
- `adapters` expõe HTTP/FastAPI e traduz transporte para comandos.
- `infrastructure` implementa banco, fila, storage, web, conversão e LLM.

API e worker compartilham a mesma imagem, mas rodam em processos separados. Há
apenas um worker, consumindo a fila `analysis`.

## Consequências

- Trocar Docling, S3 ou provedor de LLM não altera regras de negócio.
- O deploy continua simples: uma imagem, dois comandos (`api` e `worker`).
- Acoplamentos indevidos são detectáveis por imports entre camadas e revisão.
