# information-classifier-api

API assíncrona e aberta para classificar a relevância de um texto, link ou
arquivo de mídia. Cada análise recebe uma das três classes públicas
(`Altamente relevante`, `Relevante`, `Pouco relevante`), uma justificativa curta
e um resumo de até 280 caracteres.

O fluxo é único: a regra global é um prompt editável, o conteúdo é processado em
background e o resultado é consultado pelo identificador da análise. Não há
login, cadastro, rulesets versionados, crawls de domínio nem análises com vários
itens.

A implementação segue Clean Architecture (`domain` → `application` → `adapters` →
`infrastructure`), com FastAPI, PostgreSQL, Redis/Celery, S3/MinIO, Ollama e
Docling. O provedor de classificação é intercambiável: a heurística local roda
sem rede e sem custo; o Ollama no Compose ou qualquer provedor
OpenAI-compatible interpreta o prompt com semântica real.

## Stack

| Componente | Papel |
| --- | --- |
| FastAPI + Pydantic | API em `/v1`, validação e OpenAPI em `/docs` |
| PostgreSQL 16 + SQLAlchemy 2 async + Alembic | análises e regra global |
| Redis 7 + Celery | fila `analysis` e retentativas |
| MinIO/S3 | arquivos enviados |
| Docling | PDF, DOCX, PPTX, imagens, áudio e vídeo |
| httpx + parsel | busca de links, seleção de conteúdo principal e metadados |
| Ollama / OpenAI-compatible | classificação estruturada atrás de `RelevanceProvider` |

## Estrutura

```text
src/information_classifier_api/
├── domain/            # entidades, serviços e Protocols; não importa nada externo
├── application/       # casos de uso, orquestrador, DTOs e limites
├── adapters/          # FastAPI, schemas, dependências e handlers de erro
└── infrastructure/    # banco, fila, storage, web, conversão e LLM
tests/unit/            # rápidos, sem I/O externo, com fakes nomeados
tests/integration/     # PostgreSQL via testcontainers
```

## Requisitos

- **Docker + Docker Compose** para executar a stack completa e os testes de integração
- Python 3.13+ e [uv](https://docs.astral.sh/uv/) apenas para desenvolvimento local e testes

## Executar somente com Docker Compose

Este é o caminho recomendado para rodar a aplicação: não é necessário instalar
Python nem `uv` no host, apenas Docker e Docker Compose.

```bash
cp .env.example .env   # recomendado; o Compose já possui defaults locais
docker compose up --build -d
docker compose ps      # aguarde api e worker "healthy"
```

O primeiro `up` baixa as imagens, constrói a imagem da aplicação com Docling e
baixa o modelo do Ollama. Os próximos usam cache e volumes persistentes; depois
da primeira construção, `docker compose up -d` sobe sem rebuild.

Teste rápido depois que `api` e `worker` ficarem `healthy`:

```bash
curl -s http://localhost:8000/health/ready

curl -s -X POST http://localhost:8000/v1/analyses \
  -F 'text=Notícia de tecnologia sobre inteligência artificial.'

# copie o analysis_id retornado e consulte:
curl -s http://localhost:8000/v1/analyses/<analysis_id>
```

Serviços criados:

- `postgres`, `redis`, `minio` e `bucket-init` (bucket idempotente)
- `ollama` e `ollama-init` (pull idempotente do modelo `LLM_MODEL`)
- `migrate` (Alembic `upgrade head`, roda uma vez e encerra)
- `api` em `http://localhost:8000`
- `worker` único, consumindo a fila `analysis`

O Compose usa `depends_on` com `service_healthy`/`service_completed_successfully`,
então API e worker só sobem depois do banco, broker, bucket, modelo do Ollama e
migrações. A API expõe `GET /health/live` e `GET /health/ready`; o healthcheck do
container usa `/health/live`.

> **Migração de versões anteriores:** o schema foi simplificado para
> `001_simplified` e não é compatível com o schema antigo. Se você já tinha
> volumes do projeto, rode `docker compose down -v` antes do primeiro `up`.

O Docker Hub removeu as imagens oficiais `minio/minio` e `minio/mc`. O Compose
usa o espelho `elestio/minio` fixado por digest, que empacota o binário oficial
do MinIO e o cliente `mc`.

Para encerrar preservando dados:

```bash
docker compose down
```

Os volumes `postgres_data`, `redis_data`, `minio_data`, `ollama_models` e
`model_cache` sobrevivem ao `down`. O `model_cache` guarda os modelos de OCR/ASR
baixados pelo worker. Use `docker compose down -v` apenas quando quiser apagar
tudo.

### LLM local com Ollama

O Compose sobe o `ollama` e o `ollama-init`, que baixa `LLM_MODEL`
(`llama3.2:1b` por padrão) de forma idempotente. O modelo fica no volume
`ollama_models` e a API/worker falam com ele por
`http://ollama:11434/v1`, sem depender de chave externa.

```bash
docker compose exec ollama ollama list
docker compose exec ollama ollama run llama3.2:1b "Responda apenas OK"
```

O Ollama do Compose publica a porta `11435` no host para não conflitar com um
Ollama já instalado em `11434`. Para usar o do Compose pela CLI do host:

```bash
OLLAMA_HOST=http://localhost:11435 ollama list
```

Para trocar o modelo, ajuste `LLM_MODEL` no `.env` e recrie o pull e os
consumidores:

```bash
docker compose up -d --force-recreate ollama-init api worker
```

Em CPU, a primeira classificação pode demorar enquanto o modelo é carregado;
`LLM_TIMEOUT_SECONDS=300` cobre esse período. Para voltar à heurística, use
`LLM_PROVIDER=heuristic` (os serviços Ollama continuam no ar, mas não são
usados).

## Desenvolvimento local

```bash
uv sync
cp .env.example .env
uv run poe migrate
uv run poe run
```

O `.env.example` aponta `LLM_BASE_URL` para o serviço `ollama` do Compose. Para
rodar a API no host usando um Ollama instalado no host, ajuste
`LLM_BASE_URL=http://localhost:11434/v1`; para não usar LLM, defina
`LLM_PROVIDER=heuristic`.

Texto e Markdown funcionam só com as dependências base. Para processar PDFs,
imagens, áudio e vídeo no host, instale o extra pesado:

```bash
uv sync --extra docling
```

Para processar trabalho de verdade fora do Compose, suba PostgreSQL, Redis e
MinIO e inicie o worker:

```bash
docker compose up -d postgres redis minio bucket-init
uv run poe migrate
uv run poe worker
```

`uv run poe migrate` e `uv run poe worker` usam `DATABASE_URL`/`REDIS_URL` do
`.env`. `STORAGE_BACKEND=memory` serve para texto e URL; uploads de arquivo
exigem storage compartilhado entre API e worker.

## Configuração

Toda configuração passa por `infrastructure/config/settings.py` e é validada na
inicialização. As variáveis mais relevantes estão em `.env.example`:

| Grupo | Variáveis |
| --- | --- |
| Aplicação | `ENVIRONMENT`, `API_PORT`, `LOG_LEVEL`, `CORS_ORIGINS` |
| Banco/fila | `DATABASE_URL`, `REDIS_URL`, `CELERY_*`, `ANALYSIS_SOFT_TIME_LIMIT_SECONDS` |
| Storage | `STORAGE_BACKEND` (`s3` ou `memory`), `S3_*` |
| LLM | `LLM_PROVIDER` (`heuristic` ou `openai`), `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` |
| Ollama | `OLLAMA_HOST_PORT`, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_KEEP_ALIVE` |
| Limites | `MAX_UPLOAD_BYTES`, `MAX_TEXT_CHARS`, `MAX_EXTRACTED_CHARS`, `PROMPT_MAX_CHARS`, `MAX_RULE_PROMPT_CHARS` |
| Web | `WEB_FETCH_TIMEOUT_SECONDS`, `WEB_FETCH_MAX_RESPONSE_BYTES`, `WEB_FETCH_MAX_REDIRECTS`, `ALLOWED_URL_PORTS` |
| Áudio/vídeo | `ASR_MODEL` (`small` por padrão), `ASR_LANGUAGE` (vazio detecta automaticamente) |

Com `LLM_PROVIDER=openai`, `LLM_MODEL` e `LLM_API_KEY` são obrigatórios e a
chamada é HTTP compatível com a API OpenAI. O Ollama ignora a chave, mas exige um
valor não vazio (o Compose usa `ollama`). Com `LLM_PROVIDER=heuristic`, nenhum
modelo é consultado e o fluxo roda sem rede.

## API

Todas as rotas de negócio ficam em `/v1` e são públicas.

### Criar uma análise

`POST /v1/analyses` é `multipart/form-data` e aceita **exatamente uma** origem:
`file`, `url` ou `text`.

```bash
# Texto
curl -s -X POST http://localhost:8000/v1/analyses \
  -F 'text=Notícia de tecnologia sobre inteligência artificial.'

# Link
curl -s -X POST http://localhost:8000/v1/analyses \
  -F 'url=https://example.com/noticia'

# Arquivo (imagem, áudio, PDF, DOCX, PPTX, TXT, Markdown etc.)
curl -s -X POST http://localhost:8000/v1/analyses \
  -F 'file=@captura.png;type=image/png'
```

Resposta `202`:

```json
{
  "analysis_id": "uuid",
  "status": "queued",
  "status_url": "/v1/analyses/uuid"
}
```

Se nenhuma ou mais de uma origem for enviada, a API responde `400`. Arquivo com
extensão/MIME/assinatura inválida responde `415`; payload acima de
`MAX_UPLOAD_BYTES` responde `413`.

### Consultar o resultado

```bash
curl -s http://localhost:8000/v1/analyses/<analysis_id>
```

Estados possíveis: `queued`, `processing`, `completed` e `failed`. Em `completed`:

```json
{
  "analysis_id": "uuid",
  "status": "completed",
  "input_type": "text",
  "source": {"url": null, "filename": null, "media_type": null},
  "title": "Notícia de tecnologia",
  "classification": "Altamente relevante",
  "reason": "O conteúdo trata de tecnologia e cita inteligência artificial.",
  "summary": "Avanço de IA transforma o setor de tecnologia.",
  "warnings": [],
  "model_name": "heuristic-v2",
  "created_at": "2026-10-23T12:00:00Z",
  "started_at": "2026-10-23T12:00:01Z",
  "completed_at": "2026-10-23T12:00:02Z",
  "error": null
}
```

Em `failed`, `error.code` traz um código estável (por exemplo
`extraction_failed`, `invalid_provider_output` ou `provider_unavailable`) e
`error.message` uma descrição curta. Análise inexistente responde `404`.

### Regra global

A regra é um prompt único usado pelas próximas análises. Cada análise guarda um
snapshot do prompt no momento da criação; editar a regra não altera análises já
enfileiradas.

```bash
curl -s http://localhost:8000/v1/rule

curl -s -X PUT http://localhost:8000/v1/rule \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Classifique o conteúdo conforme a relevância para o objetivo abaixo.\n\n- \"Altamente relevante\": notícias sobre tecnologia que tratem especificamente de inteligência artificial.\n- \"Relevante\": notícias sobre tecnologia em geral.\n- \"Pouco relevante\": todo o restante.\n\nUse apenas as três classes públicas e justifique a escolha com evidências do conteúdo."
  }'
```

Com essa regra, uma notícia de tecnologia em geral tende a `Relevante`; a mesma
notícia quando trata de IA tende a `Altamente relevante`. A heurística local
interpreta cláusulas com “relevante”/“altamente relevante” por palavras-chave;
para prompts livres com semântica real, configure `LLM_PROVIDER=openai`.

### Health

- `GET /health/live` → processo HTTP vivo.
- `GET /health/ready` → verifica PostgreSQL, Redis e storage; responde `503`
  com a lista de dependências com falha quando alguma não está pronta.

## Formatos aceitos

| Categoria | Extensões |
| --- | --- |
| Texto | `.txt`, `.md` |
| Documentos | `.pdf`, `.docx`, `.pptx` |
| Imagens/prints | `.png`, `.jpg`, `.jpeg`, `.webp` |
| Áudio | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac` |
| Vídeo | `.mp4`, `.webm`, `.mov` |

Texto e Markdown são lidos diretamente. Os demais formatos passam pelo Docling;
áudio e vídeo usam ASR (Whisper `small` por padrão, configurável em `ASR_MODEL`)
e exigem o extra `docling` com `docling[asr]`, já instalado na imagem Docker.
Links são buscados com `httpx`, validados contra SSRF (esquema, host, porta,
credenciais, DNS público e cada redirect) e têm o conteúdo principal extraído
com `parsel` antes da conversão.

## Fluxo assíncrono

1. A API valida a origem, grava a análise e o snapshot da regra e responde `202`.
2. O dispatcher publica `analyze_analysis` na fila `analysis`.
3. O worker extrai o conteúdo:
   - texto/Markdown direto;
   - link via `httpx` + `parsel` + Docling;
   - arquivo via storage + Docling (ou leitura direta de texto).
4. O provedor classifica o conteúdo com o prompt da regra.
5. O resultado validado (`classification`, `reason`, `summary`) é persistido.

O pipeline é idempotente: análises em estado terminal são ignoradas em uma
reexecução. Erros transitórios usam retry com backoff; erros permanentes marcam a
análise como `failed` com `error_code` estável. Se a resposta do provedor vier
inválida, o orquestrador tenta um único reparo antes de falhar.

## Testes

```bash
uv run poe lint
uv run poe format
uv run poe typecheck
uv run poe test-unit         # rápido, sem Docker
uv run poe test-integration  # testcontainers + PostgreSQL
uv run poe test              # tudo, com cobertura mínima de 75%
```

Os testes de integração usam `PostgresContainer(..., driver="psycopg")` e sobem
as migrações Alembic desde um banco vazio. I/O externo é substituído por classes
fake nomeadas (`FakeDocumentConverter`, `FakeWebPageFetcher`,
`FakeRelevanceProvider`, `InMemoryObjectStorage`, etc.). Docling real não é
obrigatório no host.

## Changelog

As mudanças notáveis estão em [CHANGELOG.md](CHANGELOG.md).

## Decisões arquiteturais

- [ADR 0001 — Monólito modular em Clean Architecture](docs/adr/0001-monolito-modular-clean-architecture.md)
- [ADR 0002 — Análise assíncrona e idempotência](docs/adr/0002-analise-assincrona-e-idempotencia.md)
- [ADR 0003 — Docling, texto direto e links](docs/adr/0003-docling-texto-e-links.md)
- [ADR 0004 — Regra global e provedor](docs/adr/0004-regra-global-e-provedor.md)
- [ADR 0005 — PostgreSQL, S3/MinIO e SSRF](docs/adr/0005-postgres-s3-minio-e-ssrf.md)

## Limitações conhecidas

- A heurística é determinística e baseada em palavras-chave; qualidade de
  produção exige um provedor LLM.
- Ollama em CPU é mais lento que a heurística; modelos pequenos podem devolver
  JSON inválido e acionar a correção ou marcar a análise como `failed`.
- A validação SSRF por DNS não elimina rebinding entre resolução e conexão; uma
  defesa completa exigiria fixar o IP usado na conexão.
- Não há navegador headless nem execução de JavaScript.
- A primeira conversão de imagem/áudio/vídeo baixa modelos de OCR/ASR; o volume
  `model_cache` evita downloads repetidos entre recriações do worker.
- Docling, PyTorch e FFmpeg aumentam o tamanho da imagem; o build inicial pode
  demorar bastante.
