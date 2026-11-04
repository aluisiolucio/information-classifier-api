import asyncio
import importlib
import tempfile
from pathlib import Path
from types import ModuleType

from ....domain.exceptions import ExtractionError
from ....domain.interfaces.document_converter import (
    ConversionResult,
    DocumentConverter,
)
from ....domain.services.text_normalizer import extract_title

try:
    _docling = importlib.import_module("docling.document_converter")
except ImportError:  # pragma: no cover - extra opcional
    _docling = None


class DoclingMarkdownConverter(DocumentConverter):
    """Converte documentos, imagens, áudio e vídeo em Markdown via Docling.

    O `DocumentConverter` é criado sob demanda e usado de forma serializada,
    pois não há garantia documentada de segurança para uso concorrente do
    modelo. Chamadas de CPU rodam fora do event loop.

    >>> converter = DoclingMarkdownConverter(asr_model="small")  # doctest: +SKIP
    """

    def __init__(
        self, asr_model: str = "small", asr_language: str | None = None
    ) -> None:
        self._asr_model = asr_model
        self._asr_language = asr_language or None
        self._converter = None
        self._lock = asyncio.Lock()

    async def convert_file(self, path: str, media_type: str) -> ConversionResult:
        return await self._convert_path(path, media_type)

    async def convert_html(self, html: str, source_uri: str) -> ConversionResult:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        ) as handle:
            handle.write(html)
            path = Path(handle.name)
        try:
            return await self._convert_path(str(path), "text/html")
        finally:
            path.unlink(missing_ok=True)

    async def _convert_path(self, path: str, media_type: str) -> ConversionResult:
        _require_docling()
        async with self._lock:
            result = await asyncio.to_thread(self._convert_sync, path)
        markdown = result.document.export_to_markdown()
        if not markdown.strip():
            raise ExtractionError(
                f"Docling produziu Markdown vazio para {media_type!r}"
            )
        return ConversionResult(
            markdown=markdown,
            title=extract_title(markdown),
            metadata={
                "converter": "docling",
                "media_type": media_type,
                "page_count": len(getattr(result.document, "pages", {}) or {}),
            },
        )

    def _convert_sync(self, path: str):
        converter_module = _require_docling()
        if self._converter is None:
            self._converter = _create_converter(
                converter_module, self._asr_model, self._asr_language
            )
        try:
            return self._converter.convert(path)
        except Exception as exc:
            detail = str(exc)[:200]
            raise ExtractionError(
                f"falha na conversão Docling de {Path(path).suffix!r}: "
                f"{type(exc).__name__}: {detail}{_dependency_hint(exc)}"
            ) from exc


def _create_converter(
    converter_module: ModuleType, asr_model: str, asr_language: str | None
):
    asr_specs = importlib.import_module("docling.datamodel.asr_model_specs")
    pipeline_options = importlib.import_module("docling.datamodel.pipeline_options")
    whisper_options = _whisper_options(asr_specs, asr_model, asr_language)
    return _build_converter(converter_module, pipeline_options, whisper_options)


def _whisper_options(asr_specs: ModuleType, asr_model: str, asr_language: str | None):
    return asr_specs.InlineAsrNativeWhisperOptions(
        repo_id=asr_model,
        language=asr_language,
        verbose=False,
    )


def _build_converter(
    converter_module: ModuleType,
    pipeline_options: ModuleType,
    whisper_options: object,
):
    format_options = {
        converter_module.InputFormat.AUDIO: converter_module.AudioFormatOption(
            pipeline_options=pipeline_options.AsrPipelineOptions(
                asr_options=whisper_options
            )
        ),
        converter_module.InputFormat.VIDEO: converter_module.VideoFormatOption(
            pipeline_options=pipeline_options.VideoPipelineOptions(
                asr_options=whisper_options
            )
        ),
    }
    return converter_module.DocumentConverter(format_options=format_options)


def _require_docling() -> ModuleType:
    if _docling is None:
        raise ExtractionError(
            "Docling não instalado; instale o extra 'docling' "
            "(uv sync --extra docling) para processar este formato"
        )
    return _docling


def _dependency_hint(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, (ImportError, ModuleNotFoundError)) or "whisper" in message:
        return (
            "; para áudio/vídeo instale o extra 'asr' "
            "(uv sync --extra docling, que inclui docling[asr])"
        )
    return ""
