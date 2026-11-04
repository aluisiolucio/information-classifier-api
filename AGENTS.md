# AGENTS.md

## Estilo de código

- Funções: 4 a 20 linhas. Divida se passar disso.
- Arquivos: até 500 linhas. Divida por responsabilidade.
- Uma coisa por função, uma responsabilidade por módulo (SRP).
- Nomes: específicos e únicos. Evite `data`, `handler`, `manager`.
  Prefira nomes que retornem menos de 5 ocorrências num grep no repositório.
- Tipos: explícitos, checados com `ty`. Nada de `Any`, `dict`/`list` sem tipar o
  conteúdo, ou função sem type hints.
- Sem duplicação de código. Extraia lógica compartilhada para uma função/módulo.
- Prefira *early return* a ifs aninhados. Máximo de 2 níveis de indentação.
- Mensagens de exceção devem incluir o valor problemático e o formato esperado.
  Não inclua secrets, senhas ou tokens completos.

## Comentários

- Mantenha os comentários já existentes. Não remova em refatorações — eles carregam
  intenção e histórico.
- Escreva o PORQUÊ, não o QUÊ. Evite `# incrementa o contador` acima de `i += 1`.
- Docstrings em funções/métodos públicos: intenção + um exemplo de uso.
- Referencie número de issue / SHA de commit quando uma linha existir por causa de um
  bug específico ou de uma restrição externa.

## Testes

- Testes: `uv run poe test` (ou `uv run pytest`). Unitários: `uv run poe test-unit`.
- Integração usa **testcontainers** (`PostgresContainer`, `driver="psycopg"` — nunca
  o default `psycopg2`). Requer Docker.
- Toda função nova ganha um teste. Correção de bug ganha teste de regressão.
- Mocke I/O externo (banco, filesystem, HTTP) com classes fake nomeadas — os
  `Protocol`s de `domain/interfaces/` existem justamente para isso — nunca com stubs
  inline.
- Testes devem ser F.I.R.S.T: rápidos, independentes, repetíveis, auto-verificáveis e
  feitos a tempo.
- Na variação síncrona, use `TestClient` do FastAPI; na assíncrona, `httpx.AsyncClient`
  + `pytest-asyncio`.

## Dependências

- Injete dependências via construtor/parâmetro, usando `Depends()` do FastAPI — nunca
  por import global.
- Envolva bibliotecas de terceiros atrás de uma interface fina de propriedade do
  projeto: no boilerplate, isso é exatamente o papel dos `Protocol`s em
  `domain/interfaces/`, implementados em `infrastructure/`.
- Autenticação: access JWT (`TokenService`) + refresh opaco persistido
  (`RefreshTokenRepository`, hash SHA-256). Rotação no refresh; reuso revoga a família.
- Erros de domínio que precisam manter alterações já feitas herdam de
  `CommitRequiredError`; a dependência de sessão faz commit antes de propagar.
  É isso que garante que o reuso de refresh revogue a família de forma persistente.

## Docker Compose e Ollama

- O caminho suportado para a stack completa é `docker compose up --build -d`;
  ele não deve exigir Python nem `uv` no host.
- O Compose sobe `ollama` e `ollama-init`; mantenha o pull idempotente e o modelo
  no volume `ollama_models`.
- Dentro do Compose, `LLM_BASE_URL=http://ollama:11434/v1`. Fora dele, use
  `http://localhost:11434/v1`.
- Ao mudar `LLM_MODEL`, recrie o pull e os consumidores:
  `docker compose up -d --force-recreate ollama-init api worker`.
- `.env` nunca é versionado; `.env.example` contém apenas placeholders.

## Changelog e documentação

- Mudanças visíveis ao usuário entram em `CHANGELOG.md` (formato Keep a Changelog).
- Se o fluxo de execução ou configuração mudar, atualize o README e este arquivo.

## Estrutura

- Siga a Clean Architecture do projeto: `domain` → `application` → `adapters` →
  `infrastructure`. Não misture responsabilidades entre camadas — `domain` não importa
  nada de fora, `application` só conhece `domain` e seus `Protocol`s, `adapters` chama
  `application`, `infrastructure` implementa os `Protocol`s.
- Prefira módulos pequenos e focados a arquivos "deus".
- Caminhos previsíveis: `domain/entities`, `domain/interfaces`,
  `application/use_cases`, `adapters/api/v1`, `infrastructure/database`,
  `infrastructure/config`, `infrastructure/logging`, `infrastructure/auth`.

## CRUD de exemplo

- Com `include_crud=true`, o projeto nasce com uma entidade e um CRUD completo.
  O nome da entidade define as classes; o plural define a rota e a tabela; o
  módulo derivado define arquivos, variáveis e atributos.
- Os campos vêm de `resource_fields`. A v1 suporta `str`, `text`, `int`, `float`,
  `bool`, `datetime` e `uuid`, com `required` e `max_length` (apenas strings).
- Mantenha o fluxo `domain` → `application` → `adapters` → `infrastructure`
  também ao evoluir o CRUD: entidade e `Protocol` no domínio, use cases na
  aplicação, schemas/rotas nos adapters e SQLAlchemy na infraestrutura.
- `PATCH` usa `model_dump(exclude_unset=True)`: campo omitido não muda, opcional
  aceita `null` e obrigatório com `null` retorna 422.
- Com `include_crud=false`, não existem entidade, use cases, rota, tabela ou
  testes do CRUD; auth e health continuam disponíveis.

## Formatação

- Use o formatter padrão do projeto: `ruff format` (lint com `ruff check --fix`).
  Tarefas: `uv run poe lint` / `uv run poe format`. Não discuta estilo além disso.
- Typecheck: `uv run poe typecheck` (`ty`).

## Logging

- JSON estruturado ao logar para debug/observabilidade, via `structlog`.
- Texto plano só em saída de CLI voltada ao usuário (ex: mensagens das tarefas Poe).
