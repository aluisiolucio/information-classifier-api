from dataclasses import dataclass, field

from ..types import JsonObject


@dataclass(frozen=True)
class FetchedPage:
    """Página obtida de uma URL antes da conversão para Markdown."""

    url: str
    final_url: str
    status_code: int
    html: str
    title: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
