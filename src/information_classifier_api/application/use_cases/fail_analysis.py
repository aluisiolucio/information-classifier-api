from uuid import UUID

from ...domain.entities.analysis import TERMINAL_STATUSES, Analysis
from ...domain.exceptions import AnalysisNotFoundError
from ...domain.interfaces.analysis_repository import AnalysisRepository
from ...domain.services.error_messages import sanitize_error_message


class FailAnalysis:
    """Marca uma análise não terminal como falha, de forma idempotente."""

    def __init__(self, analyses: AnalysisRepository) -> None:
        self._analyses = analyses

    async def execute(
        self, analysis_id: UUID, error_code: str, error_message: str
    ) -> Analysis:
        analysis = await self._analyses.get_by_id(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(analysis_id)
        if analysis.status in TERMINAL_STATUSES:
            return analysis
        failed = analysis.fail(
            error_code=error_code,
            error_message=sanitize_error_message(error_message),
        )
        await self._analyses.update(failed)
        return failed
