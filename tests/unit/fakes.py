"""Fakes nomeados para testes de domínio/aplicação, sem I/O externo."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from information_classifier_api.domain.entities.analysis import (
    Analysis,
    AnalysisStatus,
    InputType,
)
from information_classifier_api.domain.entities.classification_rule import (
    ClassificationRule,
)
from information_classifier_api.domain.entities.fetched_page import FetchedPage
from information_classifier_api.domain.entities.provider_contracts import (
    ClassificationProviderResult,
    ClassificationRequest,
)
from information_classifier_api.domain.entities.relevance import ProviderUsage
from information_classifier_api.domain.interfaces.document_converter import (
    ConversionResult,
)
from information_classifier_api.domain.types import JsonObject

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)

DEFAULT_PAYLOAD: JsonObject = {
    "classification": "Relevante",
    "reason": "A notícia trata de tecnologia.",
    "summary": "Nova ferramenta de tecnologia.",
}


def make_analysis(
    *,
    input_type: str = InputType.TEXT,
    status: str = AnalysisStatus.QUEUED,
    rule_prompt: str = "Classifique notícias de tecnologia.",
    source_text: str | None = "# Notícia\n\nConteúdo de tecnologia.",
    source_url: str | None = None,
    source_filename: str | None = None,
    source_media_type: str | None = None,
    storage_key: str | None = None,
    title: str | None = "Notícia",
) -> Analysis:
    return Analysis(
        id=uuid4(),
        input_type=input_type,
        status=status,
        rule_prompt=rule_prompt,
        created_at=NOW,
        source_text=source_text,
        source_url=source_url,
        source_filename=source_filename,
        source_media_type=source_media_type,
        storage_key=storage_key,
        title=title,
    )


class InMemoryAnalysisRepository:
    def __init__(self) -> None:
        self.analyses: dict[UUID, Analysis] = {}

    async def add(self, analysis: Analysis) -> None:
        self.analyses[analysis.id] = analysis

    async def get_by_id(self, analysis_id: UUID) -> Analysis | None:
        return self.analyses.get(analysis_id)

    async def update(self, analysis: Analysis) -> None:
        self.analyses[analysis.id] = analysis


class InMemoryClassificationRuleRepository:
    def __init__(self, rule: ClassificationRule | None = None) -> None:
        self.rule = rule

    async def get(self) -> ClassificationRule | None:
        return self.rule

    async def upsert(self, prompt: str, updated_at: datetime) -> ClassificationRule:
        self.rule = ClassificationRule(prompt=prompt, updated_at=updated_at)
        return self.rule


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise FileNotFoundError(f"objeto não encontrado: {key}")
        return self.objects[key][0]

    async def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)

    async def ensure_bucket(self) -> None:
        return None


class FakeUrlValidator:
    def __init__(
        self, canonical: str | None = None, error: Exception | None = None
    ) -> None:
        self.canonical = canonical
        self.error = error
        self.seen: list[str] = []

    async def validate(self, url: str) -> str:
        self.seen.append(url)
        if self.error is not None:
            raise self.error
        return self.canonical or url


class FakeWebPageFetcher:
    def __init__(
        self,
        page: FetchedPage | None = None,
        error: Exception | None = None,
    ) -> None:
        self.page = page or FetchedPage(
            url="https://example.com/noticia",
            final_url="https://example.com/noticia",
            status_code=200,
            html="<html><body><article>Tecnologia.</article></body></html>",
            title="Notícia",
        )
        self.error = error
        self.seen: list[str] = []

    async def fetch(self, url: str) -> FetchedPage:
        self.seen.append(url)
        if self.error is not None:
            raise self.error
        return self.page


class FakeDocumentConverter:
    def __init__(
        self,
        *,
        file_result: ConversionResult | None = None,
        html_result: ConversionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.file_result = file_result or ConversionResult(markdown="# Documento")
        self.html_result = html_result or ConversionResult(markdown="# Página")
        self.error = error
        self.file_calls: list[tuple[str, str]] = []
        self.html_calls: list[tuple[str, str]] = []

    async def convert_file(self, path: str, media_type: str) -> ConversionResult:
        self.file_calls.append((path, media_type))
        if self.error is not None:
            raise self.error
        return self.file_result

    async def convert_html(self, html: str, source_uri: str) -> ConversionResult:
        self.html_calls.append((html, source_uri))
        if self.error is not None:
            raise self.error
        return self.html_result


class FakeRelevanceProvider:
    def __init__(
        self,
        payloads: list[JsonObject] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payloads = payloads or [DEFAULT_PAYLOAD]
        self.error = error
        self.requests: list[ClassificationRequest] = []

    async def classify(
        self, request: ClassificationRequest
    ) -> ClassificationProviderResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        index = min(len(self.requests) - 1, len(self.payloads) - 1)
        return ClassificationProviderResult(
            payload=self.payloads[index],
            model_name="fake-model",
            usage=ProviderUsage(input_tokens=10, output_tokens=5, duration_ms=1),
        )


class FakeTaskDispatcher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.analyses: list[UUID] = []

    def enqueue_analysis(self, analysis_id: UUID) -> None:
        if self.error is not None:
            raise self.error
        self.analyses.append(analysis_id)
