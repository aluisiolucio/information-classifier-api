# syntax=docker/dockerfile:1.7
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# O usuário é criado antes da instalação para que o `uv sync` já escreva com o
# dono final. Um `chown -R` depois duplicaria todo o virtualenv em outra camada.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app \
    && chown appuser:appuser /app

USER appuser
WORKDIR /app

# Camada de dependências separada do código para aproveitar o cache de build.
COPY --chown=appuser:appuser pyproject.toml uv.lock README.md alembic.ini ./
RUN uv sync --frozen --no-dev --extra docling --no-install-project \
    && rm -rf /home/appuser/.cache/uv

COPY --chown=appuser:appuser src ./src
RUN uv sync --frozen --no-dev --extra docling --no-editable \
    && rm -rf /home/appuser/.cache/uv

EXPOSE 8000

CMD ["uvicorn", "information_classifier_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
