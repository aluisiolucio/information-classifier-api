import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from information_classifier_api.adapters.api.deps import get_task_dispatcher
from information_classifier_api.infrastructure.config.settings import get_settings
from information_classifier_api.infrastructure.database.session import get_session
from information_classifier_api.main import create_app
from tests.unit.fakes import FakeTaskDispatcher


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        yield url


@pytest.fixture(scope="session")
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    db_engine = create_async_engine(postgres_url)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    connection = await engine.connect()
    transaction = await connection.begin()
    db_session = AsyncSession(bind=connection, expire_on_commit=False)
    yield db_session
    await db_session.close()
    await transaction.rollback()
    await connection.close()


@pytest.fixture
def dispatcher() -> FakeTaskDispatcher:
    return FakeTaskDispatcher()


@pytest.fixture
async def app(
    session: AsyncSession, dispatcher: FakeTaskDispatcher
) -> AsyncIterator[FastAPI]:
    os.environ["STORAGE_BACKEND"] = "memory"
    os.environ.setdefault("ENVIRONMENT", "local")
    get_settings.cache_clear()
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client
