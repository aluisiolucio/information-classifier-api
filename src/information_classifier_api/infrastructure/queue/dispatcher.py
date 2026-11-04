from uuid import UUID

from ...domain.exceptions import TaskDispatchError
from ...domain.interfaces.task_dispatcher import TaskDispatcher

TASK_ANALYZE = "information_classifier_api.infrastructure.queue.tasks.analyze_analysis"


class CeleryTaskDispatcher(TaskDispatcher):
    """Adaptador de filas. A aplicação só conhece `TaskDispatcher`."""

    def enqueue_analysis(self, analysis_id: UUID) -> None:
        from .celery_app import celery_app

        try:
            celery_app.send_task(
                TASK_ANALYZE,
                args=[str(analysis_id)],
                queue="analysis",
            )
        except Exception as exc:
            raise TaskDispatchError(TASK_ANALYZE, type(exc).__name__) from exc
