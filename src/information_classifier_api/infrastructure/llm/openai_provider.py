import asyncio
import json
import re
import time

import httpx

from ...application.services.classification_prompts import (
    SYSTEM_PROMPT,
    build_classification_user_prompt,
    classification_json_schema,
)
from ...domain.entities.provider_contracts import (
    ClassificationProviderResult,
    ClassificationRequest,
)
from ...domain.entities.relevance import SUMMARY_MAX_CHARS, ProviderUsage
from ...domain.exceptions import (
    ProviderConfigurationError,
    ProviderOutputError,
    ProviderUnavailableError,
)
from ...domain.types import JsonObject
from ..config.settings import Settings

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class OpenAiCompatibleProvider:
    """Provedor OpenAI-compatible via HTTP, sem SDK no código de negócio."""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key:
            raise ProviderConfigurationError(
                "LLM_API_KEY vazio; esperado chave quando LLM_PROVIDER=openai"
            )
        self._settings = settings

    async def classify(
        self, request: ClassificationRequest
    ) -> ClassificationProviderResult:
        started = time.monotonic()
        data = await self._complete(
            system=SYSTEM_PROMPT.format(summary_max_chars=SUMMARY_MAX_CHARS),
            user=build_classification_user_prompt(
                rule_prompt=request.rule_prompt,
                content_markdown=request.content_markdown,
                input_type=request.input_type,
                media_type=request.media_type,
                title=request.title,
                source_uri=request.source_uri,
                correction=request.correction,
            ),
            schema=classification_json_schema(),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return ClassificationProviderResult(
            payload=_extract_object(data),
            model_name=str(data.get("model") or self._settings.llm_model),
            usage=_usage(data, duration_ms),
        )

    async def _complete(self, *, system: str, user: str, schema: dict) -> dict:
        body = {
            "model": self._settings.llm_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "classification_result",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        last_error = "sem tentativa"
        for attempt in range(self._settings.llm_max_retries + 1):
            try:
                response = await self._post(body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = type(exc).__name__
                await asyncio.sleep(min(2**attempt, 8))
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = f"HTTP {response.status_code}"
                await asyncio.sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise ProviderConfigurationError(
                    f"provedor retornou HTTP {response.status_code}; "
                    "verifique LLM_MODEL, LLM_BASE_URL e LLM_API_KEY"
                )
            return response.json()
        raise ProviderUnavailableError(
            f"provedor indisponível após {self._settings.llm_max_retries + 1} "
            f"tentativas: {last_error}"
        )

    async def _post(self, body: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self._settings.llm_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(
                f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )


def _extract_object(data: dict) -> JsonObject:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderOutputError(
            "resposta do provedor sem choices[0].message.content"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderOutputError("conteúdo estruturado vazio do provedor")
    cleaned = _JSON_FENCE.sub("", content.strip())
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderOutputError(
            f"JSON inválido do provedor na posição {exc.pos}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderOutputError(
            f"JSON do provedor deve ser objeto, recebido {type(payload).__name__}"
        )
    return payload


def _usage(data: dict, duration_ms: int) -> ProviderUsage:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return ProviderUsage(duration_ms=duration_ms)
    return ProviderUsage(
        input_tokens=_optional_int(usage.get("prompt_tokens")),
        output_tokens=_optional_int(usage.get("completion_tokens")),
        duration_ms=duration_ms,
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
