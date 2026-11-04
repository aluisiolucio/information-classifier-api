from typing import Protocol
from uuid import UUID

from ..entities.analysis import Analysis


class AnalysisRepository(Protocol):
    async def add(self, analysis: Analysis) -> None: ...

    async def get_by_id(self, analysis_id: UUID) -> Analysis | None: ...

    async def update(self, analysis: Analysis) -> None: ...
