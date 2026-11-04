# ADR 0006 — Fluxo ponta a ponta da análise assíncrona

## Contexto

A API e o worker são processos separados, com responsabilidades e tempos de vida
diferentes. As decisões já estão registradas em ADRs específicas — camadas
(0001), fila e idempotência (0002), extração (0003), provedor (0004) e
persistência/SSRF (0005) —, mas não havia um mapa único do caminho percorrido
por uma análise, do `POST` até o resultado consultado.

O sistema tem quatro fronteiras:

- a API grava no PostgreSQL, mas não executa extração nem classificação;
- o Redis transporta a tarefa, mas não é a fonte da verdade do resultado;
- o worker processa, mas não expõe HTTP;
- o Celery garante reentrega, mas não garante execução exatamente uma vez.

## Decisão

Manter a separação entre **controle** (API) e **execução** (worker), usando o
identificador da análise como único contrato entre os processos:

- a API valida a entrada, persiste a análise como `queued` e publica apenas o
  `analysis_id` na fila `analysis`;
- o worker consome a fila, extrai o conteúdo, classifica e persiste o resultado;
- o PostgreSQL é a fonte da verdade para status e resultado;
- o Redis é apenas o transporte entre API e worker;
- o MinIO/S3 guarda os arquivos enviados;
- o provedor de classificação é acessado exclusivamente pelo worker.

A API nunca baixa uma URL, converte um PDF, executa OCR/ASR ou chama o Ollama.
O worker nunca recebe uma requisição HTTP.

## Visão de componentes

```text
cliente
  │ POST /v1/analyses
  ▼
┌──────────────────┐   commit    ┌────────────────────┐
│ API (uvicorn)    │────────────▶│ PostgreSQL         │
│ valida + grava   │             │ analyses + rule    │
│ e enfileira      │             └────────────────────┘
└────────┬─────────┘
         │ enqueue (analysis_id)
         ▼
┌──────────────────┐
│ Redis            │
│ fila "analysis"  │
└────────┬─────────┘
         │ consume
         ▼
┌──────────────────┐
│ Worker (Celery)  │
│ extrai/classifica│
└────────┬─────────┘
         ├──▶ MinIO/S3 (arquivo enviado)
         ├──▶ Docling (PDF, imagem, áudio, vídeo)
         └──▶ Ollama / OpenAI-compatible

cliente
  │ GET /v1/analyses/{id} (polling)
  ▼
┌──────────────────┐   leitura   ┌────────────────────┐
│ API (uvicorn)    │────────────▶│ PostgreSQL         │
└──────────────────┘             └────────────────────┘
```

| Componente | Responsabilidade | Não faz |
| --- | --- | --- |
| API (`uvicorn`) | validar entrada, tirar snapshot da regra, persistir `queued`, enfileirar, consultar status, servir `/docs` e health checks | extração, conversão, OCR/ASR, chamada ao LLM |
| Worker (`celery`) | consumir a fila, extrair conteúdo, classificar, persistir `completed`/`failed` | aceitar HTTP, servir API, decidir regra global |
| Redis | broker da fila `analysis` | guardar o resultado oficial da análise |
| PostgreSQL | análises, regra global, status e resultado | transportar tarefas |
| MinIO/S3 | bytes dos arquivos enviados, endereçados por `storage_key` | armazenar texto de URL ou regra |
| Docling | conversão de PDF, DOCX, PPTX, imagem, áudio e vídeo | classificação |
| Ollama / OpenAI-compatible | classificação semântica atrás de `RelevanceProvider` | validação da entrada ou persistência |

## Fluxo passo a passo

### 1. Submissão na API

`POST /v1/analyses` é `multipart/form-data` e aceita exatamente uma origem:
`text`, `url` ou `file`. A API valida antes de criar qualquer análise:

| Origem | Validação | Campo persistido |
| --- | --- | --- |
| `text` | normalização para Markdown e `MAX_TEXT_CHARS` | `source_text` |
| `url` | `UrlPolicy` (esquema, host, porta, credenciais) + DNS público; URL canônica | `source_url` |
| `file` | `MAX_UPLOAD_BYTES`, extensão, MIME declarado e assinatura real | `storage_key` + metadados |

Para arquivo, os bytes são enviados ao MinIO/S3 antes de a análise ser
persistida. Para URL, a validação de DNS acontece no aceite e é repetida pelo
fetcher a cada redirect, evitando SSRF por redirecionamento.

### 2. Snapshot da regra

A API lê a regra global de `classification_rule`. Se ela ainda não existir, usa
`DEFAULT_RULE_PROMPT`. O prompt é copiado para `analyses.rule_prompt` no momento
da criação.

Isso significa que editar `PUT /v1/rule` depois não altera análises já
enfileiradas: cada trabalho carrega o prompt que valia quando foi aceito.

### 3. Persistência e enfileiramento

A análise é gravada com status `queued` e a transação é commitada **antes** do
enqueue:

```text
INSERT analyses (status='queued', rule_prompt=...)
COMMIT
send_task("...analyze_analysis", args=[str(analysis_id)], queue="analysis")
```

Se o enqueue falhar, a API marca a análise como `failed` com
`task_dispatch_failed` e responde `503`. Não existe outbox transacional nesta
versão: uma queda entre o commit e o enqueue pode deixar uma análise órfã em
`queued` (ver ADR 0002).

### 4. Consumo pelo worker

O worker Celery está inscrito apenas na fila `analysis`. A configuração relevante:

- `task_acks_late=True` e `task_reject_on_worker_lost=True`: se o processo morrer
  durante a tarefa, ela pode ser reentregue;
- `worker_prefetch_multiplier=1`: cada processo pega uma tarefa por vez;
- `--concurrency=1` no Compose: uma análise por worker, por causa do consumo de
  CPU/RAM de Docling e do Ollama;
- `task_ignore_result=True`: o resultado oficial não fica no Redis, e sim no
  PostgreSQL.

A tarefa executa `asyncio.run(_process(analysis_id))`. Como cada tarefa roda em
um event loop novo, o worker cria uma engine e uma sessão SQLAlchemy por
execução, descartando-as ao final.

Ao carregar a análise, o worker primeiro verifica se o status é terminal. Se for
`completed` ou `failed`, retorna sem reprocessar. Essa checagem é o que torna a
reentrega do Celery idempotente do ponto de vista de negócio.

Depois, chama `analysis.start()` e segue para a extração.

### 5. Extração do conteúdo

O caminho depende do tipo de entrada:

| `input_type` | Caminho no worker |
| --- | --- |
| `text` | normalização direta para Markdown |
| `url` | validação SSRF, `httpx`, seleção de conteúdo principal com `parsel`, conversão de HTML com Docling |
| `file` texto | leitura do MinIO/S3 e decodificação UTF-8 |
| `file` mídia | leitura do MinIO/S3, arquivo temporário e conversão pelo Docling |

O worker aplica `MAX_EXTRACTED_CHARS` e `PROMPT_MAX_CHARS`, truncando em limites
de parágrafo e adicionando warnings ao resultado. Conteúdo vazio após a
conversão é falha permanente de extração.

### 6. Classificação

O worker monta o prompt com três blocos separados:

1. regra global (`rule_prompt` copiado na criação);
2. metadados da origem (tipo, mídia, título e URL);
3. conteúdo extraído, marcado como material não confiável.

O provedor é escolhido pela configuração `LLM_PROVIDER`:

- `heuristic`: determinístico, local, sem rede;
- `openai`: HTTP compatível com a API OpenAI, incluindo o Ollama do Compose.

A resposta precisa ser JSON válido e passar por `AnalysisResult`:

- `classification`: uma das três classes públicas;
- `reason`: 1 a 1000 caracteres;
- `summary`: 1 a 280 caracteres.

Se a primeira resposta for inválida, o orquestrador faz **uma** tentativa de
reparo com uma instrução de correção. Se ainda falhar, a análise termina como
`invalid_provider_output`.

O provedor HTTP também tem retry próprio para timeout, erro de transporte,
HTTP 429 e HTTP 5xx. Esgotadas as tentativas, lança `ProviderUnavailableError`,
que é transitório para o Celery.

### 7. Conclusão

Em caso de sucesso, o worker grava:

- status `completed`;
- `classification`, `reason`, `summary` e `title`;
- `warnings` da extração e da classificação;
- `model_name`, `prompt_version` e `usage_metadata`;
- `completed_at`.

Em caso de falha permanente, grava status `failed`, `error_code` estável,
`error_message` sanitizada e `completed_at`.

O commit acontece ao final da tarefa. Em falha transitória, o worker commita o
estado atual antes de relançar a exceção para o Celery agendar o retry.

### 8. Consulta do resultado

O cliente consulta `GET /v1/analyses/{analysis_id}`. A API lê o PostgreSQL e
devolve o status atual; não há cache nem consulta ao worker. Análise inexistente
responde `404`.

O polling é o contrato público: o cliente recebe `202` com `status_url` e consulta
até `completed` ou `failed`.

## Máquina de estados

```text
                 start()
   queued ─────────────────▶ processing ─── complete() ───▶ completed
     │                           │
     │                           └────── fail() ─────────▶ failed
     │
     └── enqueue falhou ──────────────────────────────────▶ failed
         (task_dispatch_failed)
```

| Estado | Quem escreve | Significado | Próximo estado |
| --- | --- | --- | --- |
| `queued` | API | aceita, aguardando o worker | `processing` ou `failed` |
| `processing` | worker | extração/classificação em andamento | `completed` ou `failed` |
| `completed` | worker | resultado validado e persistido | terminal |
| `failed` | worker ou API | erro permanente, dispatch ou esgotamento de retries | terminal |

`completed` e `failed` são terminais. Uma tarefa reentregue depois disso não
altera o resultado.

**Observação operacional:** a transição para `processing` e o resultado são
commitados na mesma transação. Como o commit só ocorre no fim da tarefa (ou
antes de um retry), o polling normalmente vê `queued` e depois `completed`/
`failed`; `processing` fica visível quando uma tentativa anterior já commitou
esse estado. Se for necessário acompanhar o progresso em tempo real, o worker
deve commitar imediatamente após `start()`.

## Tratamento de falhas e retry

| Falha | Onde é detectada | Código | Comportamento |
| --- | --- | --- | --- |
| origem ausente ou duplicada | API | `400` | não cria análise |
| arquivo grande | API | `413` | não cria análise |
| extensão ou MIME incompatíveis | API | `415` | não cria análise |
| arquivo vazio ou assinatura inválida | API | `400` | não cria análise |
| enqueue indisponível | API | `task_dispatch_failed` | análise `failed`, HTTP `503` |
| extração/conversão inválida | worker | `extraction_failed` | falha permanente |
| tipo de mídia sem conversor | worker | `unsupported_source_type` | falha permanente |
| configuração do provedor inválida | worker | `provider_misconfigured` | falha permanente |
| saída inválida após reparo | worker | `invalid_provider_output` | falha permanente |
| URL/rede indisponível | worker | `web_fetch_failed` | falha transitória, retry |
| storage indisponível | worker | `storage_unavailable` | falha transitória, retry |
| provedor indisponível | worker | `provider_unavailable` | falha transitória, retry |
| exceção não prevista | worker | `unexpected_error` | marca `failed` e relança para log |

Falhas transitórias usam até `CELERY_TASK_MAX_RETRIES` retries (3 por padrão),
ou seja, até 4 execuções da tarefa. O intervalo é exponencial, com base em
`CELERY_RETRY_BACKOFF_SECONDS` (5 s), teto de 300 s e jitter. Quando as
tentativas se esgotam, a análise é marcada como `failed` com o código da última
falha.

O Celery também aplica limites de tempo: `ANALYSIS_SOFT_TIME_LIMIT_SECONDS`
(900 s por padrão) e um limite rígido 60 s maior. Uma tarefa que exceda o limite
rígido pode ser interrompida e reentregue conforme a configuração de ack.

## Por que não usar apenas `BackgroundTasks`

O `BackgroundTasks` do FastAPI executaria a análise no mesmo processo da API,
depois de enviar a resposta. Isso seria suficiente para um protótipo de texto
curto, mas não para este escopo:

- não sobrevive a restart, deploy ou scale down;
- não tem retry, backoff, ack ou limite de tempo;
- não isola CPU/RAM de Docling, PyTorch e modelos de OCR/ASR;
- não permite escalar o processamento separadamente da API;
- com mais de uma réplica da API, cada tarefa fica no processo que a recebeu.

O worker separado custa mais peças operacionais, mas mantém a API responsiva e
permite que o processamento pesado seja reiniciado, observado e escalado de
forma independente. A decisão original está na ADR 0002.

## Garantias e limitações

- A entrega é **at-least-once**, não exactly-once. Uma tarefa pode rodar mais de
  uma vez; a checagem de estado terminal evita duplicar o resultado, mas uma
  chamada externa ao provedor pode ser repetida antes da persistência.
- Não há lock distribuído por análise. Duas entregas simultâneas do mesmo
  `analysis_id` podem executar em paralelo; nesse caso, a última gravação vence
  e chamadas externas podem duplicar.
- Não há outbox transacional nem rotina automática para reenfileirar análises
  órfãs em `queued`.
- Não há endpoint de cancelamento de análise em andamento.
- O Redis é broker, não fonte da verdade. `task_ignore_result=True` deixa claro
  que o resultado oficial está no PostgreSQL.
- Uploads são gravados no S3 antes do commit da análise; uma falha posterior
  pode deixar um objeto órfão sem rotina de limpeza.
- `STORAGE_BACKEND=memory` não funciona com API e worker em processos separados,
  porque cada processo teria seu próprio dicionário em memória.
- A concorrência padrão do worker é 1. Para aumentar a vazão, suba mais
  processos/replicas do worker, observando o consumo de RAM do Ollama e do
  Docling.
- Alterações de código no worker exigem rebuild e restart do container do
  worker; reiniciar apenas a API não atualiza o processamento.
- A ordem de processamento não é garantida; várias análises podem ser
  processadas em paralelo se houver mais de um worker.

## Consequências

- A API responde em milissegundos e permanece disponível durante análises
  longas.
- O processamento pesado fica isolado em um processo com ciclo de vida próprio.
- Retries, limites de tempo e reentrega ficam a cargo do Celery, sem reinventar
  uma fila no código de aplicação.
- O deploy continua simples: uma imagem, dois comandos (`api` e `worker`).
- O custo é operacional: mais containers, mais logs e um modelo de consistência
  eventual entre o aceite e o resultado.
- Diagnósticos precisam considerar quatro lugares: API, Redis, worker e
  PostgreSQL. O `analysis_id` correlaciona os logs da API e do worker; o estado
  final está no PostgreSQL.

## Referências

- [ADR 0001 — Monólito modular em Clean Architecture](0001-monolito-modular-clean-architecture.md)
- [ADR 0002 — Análise assíncrona com Celery e idempotência](0002-analise-assincrona-e-idempotencia.md)
- [ADR 0003 — Docling, texto direto e links](0003-docling-texto-e-links.md)
- [ADR 0004 — Regra global e provedor de classificação intercambiável](0004-regra-global-e-provedor.md)
- [ADR 0005 — PostgreSQL, S3/MinIO e SSRF](0005-postgres-s3-minio-e-ssrf.md)
- `src/information_classifier_api/adapters/api/v1/analyses.py` — entrada HTTP
- `src/information_classifier_api/application/use_cases/submit_analysis.py` — validação e snapshot
- `src/information_classifier_api/infrastructure/queue/dispatcher.py` — enqueue
- `src/information_classifier_api/infrastructure/queue/tasks.py` — tarefa e retry
- `src/information_classifier_api/application/orchestrators/analysis_orchestrator.py` — extração e classificação
- `src/information_classifier_api/infrastructure/web/http_fetcher.py` — fetch de URL
- `src/information_classifier_api/infrastructure/normalization/docling/converter.py` — conversão de mídia
- `src/information_classifier_api/infrastructure/database/models/analysis.py` — tabela `analyses`
