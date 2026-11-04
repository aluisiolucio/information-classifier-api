# Changelog

Todas as mudanças notáveis deste projeto são documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Corrigido

- Links servidos com `Content-Encoding: gzip` deixavam de ser analisados porque
  o corpo já descomprimido era recriado com o header original, provocando
  `DecodingError` no `httpx`. A resposta reconstruída agora remove os headers do
  corpo comprimido, e falhas de decodificação viram `WebFetchError` (retry).

## [0.3.0] - 2026-11-04

Primeira versão pública.

### Adicionado

- API assíncrona em FastAPI para classificar a relevância de texto, URL ou
  arquivo, com estados `queued`, `processing`, `completed` e `failed`.
- Regra global editável em `GET/PUT /v1/rule`, com snapshot do prompt em cada
  análise para preservar o trabalho já enfileirado.
- Provedores intercambiáveis atrás de `RelevanceProvider`: heurística local,
  OpenAI-compatible e Ollama no Docker Compose.
- Pipeline de extração com texto/Markdown direto, `httpx` + `parsel` para links
  e Docling para PDF, DOCX, PPTX, imagens, áudio e vídeo.
- Persistência em PostgreSQL com SQLAlchemy 2 async e migrações Alembic.
- Fila `analysis` com Redis e Celery, retentativas com backoff e idempotência em
  estados terminais.
- Upload de arquivos no MinIO/S3, com bucket criado por job idempotente.
- Execução completa da stack apenas com Docker Compose, incluindo `ollama` e
  `ollama-init` para baixar o modelo local de forma idempotente.
- Health checks `GET /health/live` e `GET /health/ready`.
- Testes unitários com fakes nomeados, testes de integração com testcontainers e
  cobertura mínima de 75% no `uv run poe test`.
- CI no GitHub Actions com lint, typecheck e testes.
- ADRs em `docs/adr/` e documentação de execução, configuração e API no README.

### Alterado

- O `.env.example` passa a apontar para o Ollama do Compose
  (`http://ollama:11434/v1`) e a documentar o uso de `localhost` fora do Compose.
- O Compose publica o Ollama na porta `11435` para não conflitar com uma
  instalação local em `11434`.

### Segurança

- Validação de URLs contra SSRF por esquema, host, porta, credenciais, DNS
  público e cada redirect.
- Validação de extensão, MIME declarado e assinatura real dos arquivos antes da
  conversão.
- `.env` fora do versionamento; `.env.example` contém apenas placeholders.

### Notas

- Ollama em CPU é mais lento que a heurística; modelos pequenos podem devolver
  JSON inválido e acionar a correção ou marcar a análise como `failed`.
- A primeira análise de imagem, áudio ou vídeo baixa modelos de OCR/ASR para o
  volume `model_cache`.
