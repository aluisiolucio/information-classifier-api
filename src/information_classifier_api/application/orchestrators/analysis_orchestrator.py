import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from pydantic import ValidationError

from ...domain.entities.analysis import (
    TERMINAL_STATUSES,
    Analysis,
    InputType,
)
from ...domain.entities.provider_contracts import (
    ClassificationProviderResult,
    ClassificationRequest,
)
from ...domain.entities.relevance import AnalysisResult, ProviderUsage
from ...domain.exceptions import (
    AnalysisNotFoundError,
    DomainValidationError,
    ExtractionError,
    PermanentProcessingError,
    ProviderOutputError,
    UnsupportedSourceTypeError,
)
from ...domain.interfaces.analysis_repository import AnalysisRepository
from ...domain.interfaces.document_converter import (
    ConversionResult,
    DocumentConverter,
)
from ...domain.interfaces.object_storage import ObjectStorage
from ...domain.interfaces.relevance_provider import RelevanceProvider
from ...domain.interfaces.web_page_fetcher import WebPageFetcher
from ...domain.services.error_messages import sanitize_error_message
from ...domain.services.text_normalizer import (
    extract_title,
    normalize_text_to_markdown,
)
from ..processing_limits import ProcessingLimits
from ..services.classification_prompts import (
    PROMPT_VERSION,
)

log = structlog.get_logger()

_MEDIA_SUFFIX = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        ".docx"
    ),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        ".pptx"
    ),
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
_TEXT_MEDIA_TYPES = frozenset({"text/plain", "text/markdown"})


@dataclass(frozen=True)
class ExtractedContent:
    markdown: str
    title: str | None
    warnings: list[str]


class AnalysisOrchestrator:
    """Processa uma análise: extrai o conteúdo, aplica a regra e persiste o resultado.

    Tarefas podem ser reexecutadas: estados terminais são ignorados. Erros
    permanentes viram `failed`; transitórios sobem para o worker retentar.

    >>> AnalysisOrchestrator(  # doctest: +SKIP
    ...     analyses=analyses, storage=storage, converter=converter,
    ...     fetcher=fetcher, provider=provider, limits=limits,
    ... )
    """

    def __init__(
        self,
        *,
        analyses: AnalysisRepository,
        storage: ObjectStorage,
        converter: DocumentConverter,
        fetcher: WebPageFetcher,
        provider: RelevanceProvider,
        limits: ProcessingLimits,
    ) -> None:
        self._analyses = analyses
        self._storage = storage
        self._converter = converter
        self._fetcher = fetcher
        self._provider = provider
        self._limits = limits

    async def process(self, analysis_id: UUID) -> Analysis:
        analysis = await self._load(analysis_id)
        if analysis.status in TERMINAL_STATUSES:
            return analysis
        analysis = analysis.start()
        await self._analyses.update(analysis)
        try:
            content = await self._extract(analysis)
            result, model_name, usage, warnings = await self._classify(
                analysis, content.markdown
            )
        except (PermanentProcessingError, DomainValidationError) as exc:
            return await self._fail(analysis, _error_code(exc), str(exc))
        completed = analysis.complete(
            result=result,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            usage=usage,
            warnings=[*content.warnings, *warnings],
            title=content.title,
        )
        await self._analyses.update(completed)
        log.info(
            "analysis_completed",
            analysis_id=str(analysis.id),
            input_type=analysis.input_type,
            classification=completed.classification,
        )
        return completed

    async def _load(self, analysis_id: UUID) -> Analysis:
        analysis = await self._analyses.get_by_id(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(analysis_id)
        return analysis

    async def _extract(self, analysis: Analysis) -> ExtractedContent:
        if analysis.input_type == InputType.TEXT:
            return self._extract_text(analysis)
        if analysis.input_type == InputType.URL:
            return await self._extract_url(analysis)
        if analysis.input_type == InputType.FILE:
            return await self._extract_file(analysis)
        raise UnsupportedSourceTypeError(
            f"input_type {analysis.input_type!r} não suportado; "
            "esperado 'text', 'url' ou 'file'"
        )

    def _extract_text(self, analysis: Analysis) -> ExtractedContent:
        if not analysis.source_text:
            raise ExtractionError(
                f"análise {analysis.id} sem source_text; esperado texto não vazio"
            )
        try:
            markdown = normalize_text_to_markdown(analysis.source_text)
        except DomainValidationError as exc:
            raise ExtractionError(str(exc)) from exc
        return self._finish_extraction(
            markdown, title=extract_title(markdown), warnings=[]
        )

    async def _extract_url(self, analysis: Analysis) -> ExtractedContent:
        if not analysis.source_url:
            raise ExtractionError(
                f"análise {analysis.id} sem source_url; esperado URL válida"
            )
        page = await self._fetcher.fetch(analysis.source_url)
        if page.status_code >= 400:
            raise ExtractionError(
                f"página retornou HTTP {page.status_code}; esperado status < 400"
            )
        if not page.html.strip():
            raise ExtractionError(
                f"página {page.final_url!r} não retornou HTML; esperado conteúdo"
            )
        conversion = await self._converter.convert_html(page.html, page.final_url)
        return self._finish_extraction(
            conversion.markdown,
            title=conversion.title or page.title,
            warnings=[*page.warnings, *conversion.warnings],
        )

    async def _extract_file(self, analysis: Analysis) -> ExtractedContent:
        if not analysis.storage_key:
            raise ExtractionError(
                f"análise {analysis.id} sem storage_key; esperado arquivo enviado"
            )
        media_type = analysis.source_media_type
        if media_type in _TEXT_MEDIA_TYPES:
            data = await self._storage.get_object(analysis.storage_key)
            return self._extract_plain_file(data, analysis)
        suffix = _MEDIA_SUFFIX.get(media_type or "")
        if media_type is None or suffix is None:
            raise UnsupportedSourceTypeError(
                f"media type {media_type!r} sem conversor; "
                f"esperado um de {sorted(_MEDIA_SUFFIX)}"
            )
        data = await self._storage.get_object(analysis.storage_key)
        conversion = await self._convert_bytes(data, suffix, media_type)
        return self._finish_extraction(
            conversion.markdown,
            title=conversion.title or analysis.source_filename,
            warnings=conversion.warnings,
        )

    def _extract_plain_file(self, data: bytes, analysis: Analysis) -> ExtractedContent:
        try:
            raw_text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExtractionError(
                f"arquivo {analysis.source_filename!r} não é UTF-8 válido "
                f"(byte {exc.start})"
            ) from exc
        try:
            markdown = normalize_text_to_markdown(raw_text)
        except DomainValidationError as exc:
            raise ExtractionError(str(exc)) from exc
        return self._finish_extraction(
            markdown,
            title=extract_title(markdown) or analysis.source_filename,
            warnings=[],
        )

    async def _convert_bytes(
        self, data: bytes, suffix: str, media_type: str
    ) -> ConversionResult:
        with tempfile.TemporaryDirectory(prefix="classifier-") as directory:
            path = Path(directory) / f"source{suffix}"
            path.write_bytes(data)
            return await self._converter.convert_file(str(path), media_type)

    def _finish_extraction(
        self, markdown: str, *, title: str | None, warnings: list[str]
    ) -> ExtractedContent:
        limited, truncation = self._limit_markdown(markdown)
        return ExtractedContent(
            markdown=limited,
            title=title,
            warnings=[*warnings, *truncation],
        )

    def _limit_markdown(self, markdown: str) -> tuple[str, list[str]]:
        if not markdown.strip():
            raise ExtractionError("conversão produziu conteúdo vazio")
        limit = self._limits.max_extracted_chars
        if len(markdown) <= limit:
            return markdown, []
        cut = markdown.rfind("\n\n", 0, limit)
        cut = cut if cut > 0 else limit
        return markdown[:cut].rstrip(), [
            f"conteúdo truncado em {cut} caracteres para respeitar "
            f"MAX_EXTRACTED_CHARS={limit}"
        ]

    async def _classify(
        self, analysis: Analysis, markdown: str
    ) -> tuple[AnalysisResult, str, ProviderUsage, list[str]]:
        prompt_markdown, warnings = self._fit_prompt(markdown)
        response = await self._provider.classify(
            self._request(analysis, prompt_markdown, correction=None)
        )
        try:
            result = self._validate(response)
        except (ValidationError, ValueError) as exc:
            result, response = await self._repair(analysis, prompt_markdown, exc)
        return result, response.model_name, response.usage, warnings

    def _fit_prompt(self, markdown: str) -> tuple[str, list[str]]:
        limit = self._limits.prompt_max_chars
        if len(markdown) <= limit:
            return markdown, []
        cut = markdown.rfind("\n\n", 0, limit)
        cut = cut if cut > 0 else limit
        return markdown[:cut].rstrip(), [
            f"conteúdo enviado ao provedor truncado em {cut} caracteres para "
            f"respeitar PROMPT_MAX_CHARS={limit}"
        ]

    async def _repair(
        self, analysis: Analysis, markdown: str, first_error: Exception
    ) -> tuple[AnalysisResult, ClassificationProviderResult]:
        correction = (
            "A resposta anterior foi inválida: "
            f"{sanitize_error_message(str(first_error))}. "
            "Retorne JSON estrito com classification, reason e summary."
        )
        response = await self._provider.classify(
            self._request(analysis, markdown, correction=correction)
        )
        try:
            return self._validate(response), response
        except (ValidationError, ValueError) as exc:
            raise ProviderOutputError(
                f"resposta inválida após reparo: {sanitize_error_message(str(exc))}"
            ) from exc

    def _request(
        self, analysis: Analysis, markdown: str, *, correction: str | None
    ) -> ClassificationRequest:
        return ClassificationRequest(
            rule_prompt=analysis.rule_prompt,
            content_markdown=markdown,
            input_type=analysis.input_type,
            media_type=analysis.source_media_type,
            title=analysis.title,
            source_uri=analysis.source_url,
            correction=correction,
        )

    def _validate(self, response: ClassificationProviderResult) -> AnalysisResult:
        return AnalysisResult.model_validate(response.payload)

    async def _fail(
        self, analysis: Analysis, error_code: str, error_message: str
    ) -> Analysis:
        failed = analysis.fail(
            error_code=error_code,
            error_message=sanitize_error_message(error_message),
        )
        await self._analyses.update(failed)
        log.warning(
            "analysis_failed",
            analysis_id=str(analysis.id),
            code=error_code,
        )
        return failed


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) else "validation_failed"
