from typing import Protocol
from uuid import UUID


class TaskDispatcher(Protocol):
    def enqueue_analysis(self, analysis_id: UUID) -> None: ...
