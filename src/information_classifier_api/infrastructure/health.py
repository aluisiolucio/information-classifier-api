import asyncio

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config.settings import Settings
from .wiring import build_object_storage

_CHECK_TIMEOUT_SECONDS = 3


class ReadinessChecker:
    """Verifica dependências essenciais sem expor detalhes internos ao cliente."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self, session: AsyncSession) -> list[str]:
        failures: list[str] = []
        if not await _safe(self._check_database(session)):
            failures.append("database")
        if not await _safe(self._check_redis()):
            failures.append("redis")
        if not await _safe(self._check_storage()):
            failures.append("storage")
        return failures

    async def _check_database(self, session: AsyncSession) -> bool:
        await session.execute(text("SELECT 1"))
        return True

    async def _check_redis(self) -> bool:
        client = redis.from_url(self._settings.redis_url)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()

    async def _check_storage(self) -> bool:
        if self._settings.storage_backend == "memory":
            return True
        storage = build_object_storage(self._settings)
        await storage.ensure_bucket()
        return True


async def _safe(check) -> bool:
    try:
        return await asyncio.wait_for(check, timeout=_CHECK_TIMEOUT_SECONDS)
    except Exception:
        return False
