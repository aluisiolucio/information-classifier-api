import asyncio
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ...domain.exceptions import (
    AnalysisNotFoundError,
    PermanentProcessingError,
    TransientProcessingError,
)
from ..config.settings import get_settings
from ..wiring import build_analysis_orchestrator, build_fail_analysis
from .celery_app import celery_app
from .dispatcher import TASK_ANALYZE

log = structlog.get_logger()
_settings = get_settings()


@celery_app.task(
    bind=True,
    name=TASK_ANALYZE,
    max_retries=_settings.celery_task_max_retries,
    soft_time_limit=_settings.analysis_soft_time_limit_seconds,
    time_limit=_settings.analysis_soft_time_limit_seconds + 60,
)
def analyze_analysis(self, analysis_id: str) -> None:
    try:
        asyncio.run(_process(UUID(analysis_id)))
    except TransientProcessingError as exc:
        _retry_or_fail(self, analysis_id, exc)
    except PermanentProcessingError as exc:
        asyncio.run(_fail(UUID(analysis_id), exc.code, str(exc)))
    except AnalysisNotFoundError:
        log.warning("analysis_not_found", analysis_id=analysis_id)
    except Exception as exc:  # noqa: BLE001 - falha inesperada não pode sumir
        log.exception("analysis_task_unexpected_error", analysis_id=analysis_id)
        asyncio.run(_fail(UUID(analysis_id), "unexpected_error", type(exc).__name__))
        raise


@asynccontextmanager
async def _worker_session() -> AsyncGenerator[AsyncSession]:
    """Cria engine por execução: cada tarefa roda em um novo event loop.

    O pool de conexões assíncrono é vinculado ao loop que o criou; reutilizar
    um engine cacheado entre `asyncio.run` sucessivos falharia no worker.
    """
    engine = create_async_engine(_settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _process(analysis_id: UUID) -> None:
    async with _worker_session() as session:
        orchestrator = build_analysis_orchestrator(session, _settings)
        try:
            await orchestrator.process(analysis_id)
        except TransientProcessingError:
            await session.commit()
            raise
        await session.commit()


async def _fail(analysis_id: UUID, code: str, message: str) -> None:
    async with _worker_session() as session:
        await build_fail_analysis(session).execute(analysis_id, code, message)
        await session.commit()


def _retry_or_fail(self, analysis_id: str, exc: TransientProcessingError) -> None:
    if self.request.retries < self.max_retries:
        raise self.retry(exc=exc, countdown=_countdown(self.request.retries))
    log.error("analysis_task_exhausted", analysis_id=analysis_id, code=exc.code)
    asyncio.run(_fail(UUID(analysis_id), exc.code, str(exc)))


def _countdown(retries: int) -> float:
    base = _settings.celery_retry_backoff_seconds * (2**retries)
    return min(base, 300) + random.uniform(0, 3)
