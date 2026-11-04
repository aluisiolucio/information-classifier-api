from dataclasses import dataclass, field
from typing import Protocol

from ..types import JsonObject


@dataclass(frozen=True)
class ConversionResult:
    """Saída normalizada de um conversor de documentos."""

    markdown: str
    title: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    media_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DocumentConverter(Protocol):
    """Converte arquivo/HTML em Markdown sem expor SDKs ao código de negócio."""

    async def convert_file(self, path: str, media_type: str) -> ConversionResult: ...

    async def convert_html(self, html: str, source_uri: str) -> ConversionResult: ...
