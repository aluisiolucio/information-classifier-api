from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from ..application.orchestrators.analysis_orchestrator import AnalysisOrchestrator
from ..application.processing_limits import ProcessingLimits
from ..application.use_cases.classification_rule import (
    GetClassificationRule,
    UpdateClassificationRule,
)
from ..application.use_cases.fail_analysis import FailAnalysis
from ..application.use_cases.get_analysis import GetAnalysis
from ..application.use_cases.submit_analysis import SubmitAnalysis
from ..domain.interfaces.document_converter import DocumentConverter
from ..domain.interfaces.object_storage import ObjectStorage
from ..domain.interfaces.relevance_provider import RelevanceProvider
from ..domain.interfaces.task_dispatcher import TaskDispatcher
from ..domain.interfaces.url_validator import UrlValidator
from ..domain.interfaces.web_page_fetcher import WebPageFetcher
from ..domain.services.url_policy import UrlPolicy
from .config.settings import Settings, get_settings
from .database.repositories.analysis_repository import (
    SqlAlchemyAnalysisRepository,
)
from .database.repositories.classification_rule_repository import (
    SqlAlchemyClassificationRuleRepository,
)
from .llm.heuristic_provider import HeuristicRelevanceProvider
from .llm.openai_provider import OpenAiCompatibleProvider
from .normalization.docling.converter import DoclingMarkdownConverter
from .queue.dispatcher import CeleryTaskDispatcher
from .storage.memory_storage import InMemoryObjectStorage
from .storage.s3_storage import S3ObjectStorage
from .web.http_fetcher import HttpPageFetcher
from .web.url_validator import DnsUrlValidator


@lru_cache
def _memory_storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


@lru_cache
def _cached_s3_storage(
    endpoint_url: str,
    bucket: str,
    access_key: str,
    secret_key: str,
    region: str,
) -> S3ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=endpoint_url,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
    )


def build_object_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "memory":
        return _memory_storage()
    return _cached_s3_storage(
        settings.s3_endpoint_url,
        settings.s3_bucket,
        settings.s3_access_key,
        settings.s3_secret_key,
        settings.s3_region,
    )


@lru_cache
def build_document_converter() -> DocumentConverter:
    settings = get_settings()
    return DoclingMarkdownConverter(
        asr_model=settings.asr_model,
        asr_language=settings.asr_language or None,
    )


@lru_cache
def build_task_dispatcher() -> TaskDispatcher:
    return CeleryTaskDispatcher()


def build_relevance_provider(settings: Settings) -> RelevanceProvider:
    if settings.llm_provider == "openai":
        return OpenAiCompatibleProvider(settings)
    return HeuristicRelevanceProvider()


def build_url_validator(settings: Settings) -> UrlValidator:
    return DnsUrlValidator(UrlPolicy.from_ports(settings.allowed_url_ports))


def build_web_page_fetcher(settings: Settings) -> WebPageFetcher:
    return HttpPageFetcher(
        url_validator=build_url_validator(settings),
        user_agent=settings.web_fetch_user_agent,
        timeout_seconds=settings.web_fetch_timeout_seconds,
        max_response_bytes=settings.web_fetch_max_response_bytes,
        max_redirects=settings.web_fetch_max_redirects,
    )


def build_processing_limits(settings: Settings) -> ProcessingLimits:
    return ProcessingLimits(
        max_extracted_chars=settings.max_extracted_chars,
        prompt_max_chars=settings.prompt_max_chars,
    )


def build_submit_analysis(session: AsyncSession, settings: Settings) -> SubmitAnalysis:
    return SubmitAnalysis(
        analyses=SqlAlchemyAnalysisRepository(session),
        rules=SqlAlchemyClassificationRuleRepository(session),
        storage=build_object_storage(settings),
        url_validator=build_url_validator(settings),
        max_upload_bytes=settings.max_upload_bytes,
        max_text_chars=settings.max_text_chars,
    )


def build_get_analysis(session: AsyncSession) -> GetAnalysis:
    return GetAnalysis(SqlAlchemyAnalysisRepository(session))


def build_fail_analysis(session: AsyncSession) -> FailAnalysis:
    return FailAnalysis(SqlAlchemyAnalysisRepository(session))


def build_get_rule(session: AsyncSession) -> GetClassificationRule:
    return GetClassificationRule(SqlAlchemyClassificationRuleRepository(session))


def build_update_rule(
    session: AsyncSession, settings: Settings
) -> UpdateClassificationRule:
    return UpdateClassificationRule(
        SqlAlchemyClassificationRuleRepository(session),
        settings.max_rule_prompt_chars,
    )


def build_analysis_orchestrator(
    session: AsyncSession,
    settings: Settings,
    *,
    converter: DocumentConverter | None = None,
    provider: RelevanceProvider | None = None,
    fetcher: WebPageFetcher | None = None,
) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        analyses=SqlAlchemyAnalysisRepository(session),
        storage=build_object_storage(settings),
        converter=converter or build_document_converter(),
        fetcher=fetcher or build_web_page_fetcher(settings),
        provider=provider or build_relevance_provider(settings),
        limits=build_processing_limits(settings),
    )


def reset_wiring_caches() -> None:
    """Limpa singletons de processo; usado por testes de integração."""
    _memory_storage.cache_clear()
    _cached_s3_storage.cache_clear()
    build_document_converter.cache_clear()
    build_task_dispatcher.cache_clear()
