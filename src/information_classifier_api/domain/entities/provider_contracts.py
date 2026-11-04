from dataclasses import dataclass, field

from ..types import JsonObject
from .relevance import ProviderUsage


@dataclass(frozen=True)
class ClassificationRequest:
    """Entrada de alto nível para um provedor de classificação."""

    rule_prompt: str
    content_markdown: str
    input_type: str
    media_type: str | None = None
    title: str | None = None
    source_uri: str | None = None
    correction: str | None = None


@dataclass(frozen=True)
class ClassificationProviderResult:
    payload: JsonObject
    model_name: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)
