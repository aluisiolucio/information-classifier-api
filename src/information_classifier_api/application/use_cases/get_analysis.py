from uuid import UUID

from ...domain.entities.analysis import Analysis
from ...domain.exceptions import AnalysisNotFoundError
from ...domain.interfaces.analysis_repository import AnalysisRepository


class GetAnalysis:
    """Retorna uma análise existente; inexistente vira 404."""

    def __init__(self, analyses: AnalysisRepository) -> None:
        self._analyses = analyses

    async def execute(self, analysis_id: UUID) -> Analysis:
        analysis = await self._analyses.get_by_id(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(analysis_id)
        return analysis
