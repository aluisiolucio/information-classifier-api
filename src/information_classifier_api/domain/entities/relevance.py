from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

SUMMARY_MAX_CHARS = 280


class Relevance(StrEnum):
    """Classes públicas de relevância."""

    HIGH = "Altamente relevante"
    RELEVANT = "Relevante"
    LOW = "Pouco relevante"


class AnalysisResult(BaseModel):
    """Resultado validado de uma análise, pronto para persistência.

    >>> AnalysisResult(
    ...     classification="Relevante",
    ...     reason="A notícia trata de tecnologia.",
    ...     summary="Nova ferramenta de tecnologia.",
    ... )
    """

    classification: Relevance
    reason: str = Field(min_length=1, max_length=1_000)
    summary: str = Field(min_length=1, max_length=SUMMARY_MAX_CHARS)

    @field_validator("reason", "summary")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("campo textual não pode ser vazio")
        return stripped


class ProviderUsage(BaseModel):
    """Consumo informado pelo provedor, quando disponível."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
