from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....application.dto import (
    AnalysisInput,
    SubmitFileAnalysis,
    SubmitTextAnalysis,
    SubmitUrlAnalysis,
)
from ....application.use_cases.fail_analysis import FailAnalysis
from ....domain.entities.analysis import Analysis
from ....domain.exceptions import (
    DomainValidationError,
    PayloadTooLargeError,
    TaskDispatchError,
)
from ....domain.interfaces.task_dispatcher import TaskDispatcher
from ..deps import (
    FailAnalysisDep,
    GetAnalysisDep,
    SessionDep,
    SettingsDep,
    SubmitAnalysisDep,
    TaskDispatcherDep,
)
from .schemas.analyses import (
    AnalysisError,
    AnalysisResponse,
    AnalysisSource,
    CreateAnalysisResponse,
)

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post(
    "", response_model=CreateAnalysisResponse, status_code=status.HTTP_202_ACCEPTED
)
async def create_analysis(
    use_case: SubmitAnalysisDep,
    fail_use_case: FailAnalysisDep,
    dispatcher: TaskDispatcherDep,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
) -> CreateAnalysisResponse:
    source = await _source(file, url, text, settings.max_upload_bytes)
    analysis = await use_case.execute(source)
    await session.commit()
    await _dispatch_or_fail(dispatcher, fail_use_case, session, analysis)
    return CreateAnalysisResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        status_url=f"{settings.api_v1_prefix}/analyses/{analysis.id}",
    )


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: UUID, use_case: GetAnalysisDep) -> AnalysisResponse:
    return _to_response(await use_case.execute(analysis_id))


async def _source(
    file: UploadFile | None,
    url: str | None,
    text: str | None,
    max_upload_bytes: int,
) -> AnalysisInput:
    provided = sum(value is not None for value in (file, url, text))
    if provided != 1:
        raise DomainValidationError(
            "envie exatamente uma origem: 'file', 'url' ou 'text'"
        )
    if text is not None:
        return SubmitTextAnalysis(text=text)
    if url is not None:
        return SubmitUrlAnalysis(url=url)
    if file is None:
        raise DomainValidationError("arquivo ausente; esperado campo 'file'")
    data = await file.read(max_upload_bytes + 1)
    if len(data) > max_upload_bytes:
        raise PayloadTooLargeError(len(data), max_upload_bytes)
    return SubmitFileAnalysis(
        filename=file.filename or "",
        declared_media_type=file.content_type,
        data=data,
    )


async def _dispatch_or_fail(
    dispatcher: TaskDispatcher,
    fail_use_case: FailAnalysis,
    session: AsyncSession,
    analysis: Analysis,
) -> None:
    try:
        dispatcher.enqueue_analysis(analysis.id)
    except TaskDispatchError:
        await fail_use_case.execute(
            analysis.id,
            "task_dispatch_failed",
            "não foi possível enfileirar a análise para processamento",
        )
        await session.commit()
        raise


def _to_response(analysis: Analysis) -> AnalysisResponse:
    return AnalysisResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        input_type=analysis.input_type,
        source=AnalysisSource(
            url=analysis.source_url,
            filename=analysis.source_filename,
            media_type=analysis.source_media_type,
        ),
        title=analysis.title,
        classification=analysis.classification,
        reason=analysis.reason,
        summary=analysis.summary,
        warnings=analysis.warnings,
        model_name=analysis.model_name,
        created_at=analysis.created_at,
        started_at=analysis.started_at,
        completed_at=analysis.completed_at,
        error=_error(analysis),
    )


def _error(analysis: Analysis) -> AnalysisError | None:
    if analysis.error_code is None:
        return None
    return AnalysisError(
        code=analysis.error_code,
        message=analysis.error_message or "falha sem detalhes",
    )
