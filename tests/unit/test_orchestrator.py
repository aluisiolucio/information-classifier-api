from pathlib import Path
from uuid import uuid4

import pytest

from information_classifier_api.application.orchestrators.analysis_orchestrator import (
    AnalysisOrchestrator,
)
from information_classifier_api.application.processing_limits import ProcessingLimits
from information_classifier_api.application.services.classification_prompts import (
    PROMPT_VERSION,
)
from information_classifier_api.domain.entities.analysis import (
    AnalysisStatus,
    InputType,
)
from information_classifier_api.domain.entities.fetched_page import FetchedPage
from information_classifier_api.domain.exceptions import (
    AnalysisNotFoundError,
    ExtractionError,
    ProviderOutputError,
    UnsupportedSourceTypeError,
    WebFetchError,
)
from information_classifier_api.domain.interfaces.document_converter import (
    ConversionResult,
)
from information_classifier_api.domain.types import JsonObject
from tests.unit.fakes import (
    DEFAULT_PAYLOAD,
    FakeDocumentConverter,
    FakeRelevanceProvider,
    FakeWebPageFetcher,
    InMemoryAnalysisRepository,
    InMemoryObjectStorage,
    make_analysis,
)


def _orchestrator(
    *,
    analyses: InMemoryAnalysisRepository | None = None,
    storage: InMemoryObjectStorage | None = None,
    converter: FakeDocumentConverter | None = None,
    fetcher: FakeWebPageFetcher | None = None,
    provider: FakeRelevanceProvider | None = None,
    max_extracted_chars: int = 1000,
    prompt_max_chars: int = 1000,
) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        analyses=analyses or InMemoryAnalysisRepository(),
        storage=storage or InMemoryObjectStorage(),
        converter=converter or FakeDocumentConverter(),
        fetcher=fetcher or FakeWebPageFetcher(),
        provider=provider or FakeRelevanceProvider(),
        limits=ProcessingLimits(
            max_extracted_chars=max_extracted_chars,
            prompt_max_chars=prompt_max_chars,
        ),
    )


async def test_process_text_completes_and_persists_result() -> None:
    analyses = InMemoryAnalysisRepository()
    provider = FakeRelevanceProvider()
    analysis = make_analysis(source_text="# Título\n\nNotícia de tecnologia.")
    await analyses.add(analysis)
    completed = await _orchestrator(analyses=analyses, provider=provider).process(
        analysis.id
    )
    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.classification == "Relevante"
    assert completed.reason == "A notícia trata de tecnologia."
    assert completed.summary == "Nova ferramenta de tecnologia."
    assert completed.model_name == "fake-model"
    assert completed.prompt_version == PROMPT_VERSION
    assert completed.title == "Título"
    assert provider.requests[0].rule_prompt == analysis.rule_prompt
    assert (await analyses.get_by_id(analysis.id)) == completed


async def test_process_url_fetches_and_converts_html() -> None:
    analyses = InMemoryAnalysisRepository()
    page = FetchedPage(
        url="https://example.com/noticia",
        final_url="https://example.com/noticia",
        status_code=200,
        html="<html><article>Texto</article></html>",
        title="Título da página",
        warnings=["aviso da página"],
    )
    converter = FakeDocumentConverter(
        html_result=ConversionResult(
            markdown="# Página\n\nNotícia de tecnologia.",
            title="Página",
            warnings=["aviso do conversor"],
        )
    )
    analysis = make_analysis(
        input_type=InputType.URL,
        source_text=None,
        source_url="https://example.com/noticia",
        title=None,
    )
    await analyses.add(analysis)
    completed = await _orchestrator(
        analyses=analyses, converter=converter, fetcher=FakeWebPageFetcher(page)
    ).process(analysis.id)
    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.title == "Página"
    assert converter.html_calls == [(page.html, page.final_url)]
    assert completed.warnings == ["aviso da página", "aviso do conversor"]


async def test_process_file_writes_bytes_with_media_suffix() -> None:
    analyses = InMemoryAnalysisRepository()
    storage = InMemoryObjectStorage()
    storage.objects["uploads/a/audio.mp3"] = (b"ID3audio", "audio/mpeg")
    converter = FakeDocumentConverter(
        file_result=ConversionResult(markdown="# Transcrição\n\nTecnologia.")
    )
    analysis = make_analysis(
        input_type=InputType.FILE,
        source_text=None,
        source_filename="audio.mp3",
        source_media_type="audio/mpeg",
        storage_key="uploads/a/audio.mp3",
        title=None,
    )
    await analyses.add(analysis)
    completed = await _orchestrator(
        analyses=analyses, storage=storage, converter=converter
    ).process(analysis.id)
    assert completed.status == AnalysisStatus.COMPLETED
    path, media_type = converter.file_calls[0]
    assert Path(path).suffix == ".mp3"
    assert media_type == "audio/mpeg"
    assert completed.title == "audio.mp3"


async def test_process_file_rejects_media_type_without_converter() -> None:
    analyses = InMemoryAnalysisRepository()
    analysis = make_analysis(
        input_type=InputType.FILE,
        source_text=None,
        source_filename="arquivo.bin",
        source_media_type="application/x-desconhecido",
        storage_key="uploads/a/arquivo.bin",
    )
    await analyses.add(analysis)
    failed = await _orchestrator(analyses=analyses).process(analysis.id)
    assert failed.status == AnalysisStatus.FAILED
    assert failed.error_code == UnsupportedSourceTypeError.code


async def test_process_repairs_invalid_provider_output_once() -> None:
    provider = FakeRelevanceProvider(
        payloads=[
            {"classification": "Inválida", "reason": "", "summary": ""},
            DEFAULT_PAYLOAD,
        ]
    )
    analysis = make_analysis()
    analyses = InMemoryAnalysisRepository()
    await analyses.add(analysis)
    completed = await _orchestrator(analyses=analyses, provider=provider).process(
        analysis.id
    )
    assert completed.status == AnalysisStatus.COMPLETED
    assert len(provider.requests) == 2
    assert provider.requests[1].correction is not None
    assert "resposta anterior foi inválida" in provider.requests[1].correction


async def test_process_fails_when_repair_also_returns_invalid_output() -> None:
    invalid: JsonObject = {
        "classification": "Inválida",
        "reason": "",
        "summary": "",
    }
    provider = FakeRelevanceProvider(payloads=[invalid, invalid])
    analysis = make_analysis()
    analyses = InMemoryAnalysisRepository()
    await analyses.add(analysis)
    failed = await _orchestrator(analyses=analyses, provider=provider).process(
        analysis.id
    )
    assert failed.status == AnalysisStatus.FAILED
    assert failed.error_code == ProviderOutputError.code


async def test_process_marks_permanent_extraction_error_as_failed() -> None:
    fetcher = FakeWebPageFetcher(error=ExtractionError("HTML inválido"))
    analysis = make_analysis(
        input_type=InputType.URL,
        source_text=None,
        source_url="https://example.com/",
    )
    analyses = InMemoryAnalysisRepository()
    await analyses.add(analysis)
    failed = await _orchestrator(analyses=analyses, fetcher=fetcher).process(
        analysis.id
    )
    assert failed.status == AnalysisStatus.FAILED
    assert failed.error_code == ExtractionError.code


async def test_process_lets_transient_errors_propagate_for_retry() -> None:
    fetcher = FakeWebPageFetcher(error=WebFetchError("rede indisponível"))
    analysis = make_analysis(
        input_type=InputType.URL,
        source_text=None,
        source_url="https://example.com/",
    )
    analyses = InMemoryAnalysisRepository()
    await analyses.add(analysis)
    with pytest.raises(WebFetchError):
        await _orchestrator(analyses=analyses, fetcher=fetcher).process(analysis.id)
    stored = await analyses.get_by_id(analysis.id)
    assert stored is not None
    assert stored.status == AnalysisStatus.PROCESSING


async def test_process_ignores_terminal_analysis() -> None:
    provider = FakeRelevanceProvider()
    analysis = make_analysis(status=AnalysisStatus.COMPLETED)
    analyses = InMemoryAnalysisRepository()
    await analyses.add(analysis)
    result = await _orchestrator(analyses=analyses, provider=provider).process(
        analysis.id
    )
    assert result == analysis
    assert provider.requests == []


async def test_process_truncates_extracted_and_prompt_content() -> None:
    provider = FakeRelevanceProvider()
    analysis = make_analysis(source_text="palavra " * 20)
    analyses = InMemoryAnalysisRepository()
    await analyses.add(analysis)
    completed = await _orchestrator(
        analyses=analyses,
        provider=provider,
        max_extracted_chars=50,
        prompt_max_chars=20,
    ).process(analysis.id)
    assert completed.status == AnalysisStatus.COMPLETED
    assert any("MAX_EXTRACTED_CHARS=50" in item for item in completed.warnings)
    assert any("PROMPT_MAX_CHARS=20" in item for item in completed.warnings)
    assert len(provider.requests[0].content_markdown) <= 20


async def test_process_fails_when_conversion_returns_empty_markdown() -> None:
    converter = FakeDocumentConverter(file_result=ConversionResult(markdown="   "))
    analysis = make_analysis(
        input_type=InputType.FILE,
        source_text=None,
        source_filename="imagem.png",
        source_media_type="image/png",
        storage_key="uploads/a/imagem.png",
    )
    analyses = InMemoryAnalysisRepository()
    storage = InMemoryObjectStorage()
    storage.objects["uploads/a/imagem.png"] = (b"png", "image/png")
    await analyses.add(analysis)
    failed = await _orchestrator(
        analyses=analyses, storage=storage, converter=converter
    ).process(analysis.id)
    assert failed.status == AnalysisStatus.FAILED
    assert failed.error_code == ExtractionError.code


async def test_process_extracts_uploaded_text_file_without_converter() -> None:
    converter = FakeDocumentConverter()
    analysis = make_analysis(
        input_type=InputType.FILE,
        source_text=None,
        source_filename="nota.txt",
        source_media_type="text/plain",
        storage_key="uploads/a/nota.txt",
    )
    analyses = InMemoryAnalysisRepository()
    storage = InMemoryObjectStorage()
    storage.objects["uploads/a/nota.txt"] = (
        b"  # Titulo\r\n\r\n\r\nTexto de tecnologia.  ",
        "text/plain",
    )
    await analyses.add(analysis)
    completed = await _orchestrator(
        analyses=analyses, storage=storage, converter=converter
    ).process(analysis.id)
    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.title == "Titulo"
    assert converter.file_calls == []


async def test_process_raises_for_unknown_analysis() -> None:
    with pytest.raises(AnalysisNotFoundError):
        await _orchestrator().process(uuid4())
