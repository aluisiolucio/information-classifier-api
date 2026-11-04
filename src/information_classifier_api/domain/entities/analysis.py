from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

from ..types import JsonObject
from .relevance import AnalysisResult, ProviderUsage


class AnalysisStatus:
    """Estados públicos de uma análise assíncrona."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class InputType:
    """Origem única aceita por uma análise."""

    TEXT = "text"
    URL = "url"
    FILE = "file"


TERMINAL_STATUSES = frozenset({AnalysisStatus.COMPLETED, AnalysisStatus.FAILED})


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Analysis:
    """Solicitação de classificação de uma única origem.

    O prompt da regra é copiado para a análise no momento da criação; mudanças
    posteriores na regra global não alteram análises já enfileiradas.
    """

    id: UUID
    input_type: str
    status: str
    rule_prompt: str
    created_at: datetime
    source_text: str | None = None
    source_url: str | None = None
    source_filename: str | None = None
    source_media_type: str | None = None
    storage_key: str | None = None
    title: str | None = None
    classification: str | None = None
    reason: str | None = None
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    model_name: str | None = None
    prompt_version: str | None = None
    usage_metadata: JsonObject | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self, now: datetime | None = None) -> "Analysis":
        return replace(
            self,
            status=AnalysisStatus.PROCESSING,
            started_at=self.started_at or now or utc_now(),
            error_code=None,
            error_message=None,
        )

    def complete(
        self,
        *,
        result: AnalysisResult,
        model_name: str,
        prompt_version: str,
        usage: ProviderUsage,
        warnings: list[str],
        title: str | None = None,
        now: datetime | None = None,
    ) -> "Analysis":
        return replace(
            self,
            status=AnalysisStatus.COMPLETED,
            classification=result.classification.value,
            reason=result.reason,
            summary=result.summary,
            title=title or self.title,
            warnings=warnings,
            model_name=model_name,
            prompt_version=prompt_version,
            usage_metadata=usage.model_dump(exclude_none=True),
            completed_at=now or utc_now(),
            error_code=None,
            error_message=None,
        )

    def fail(
        self,
        *,
        error_code: str,
        error_message: str,
        now: datetime | None = None,
    ) -> "Analysis":
        return replace(
            self,
            status=AnalysisStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            completed_at=now or utc_now(),
        )
