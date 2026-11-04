from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ....domain.entities.analysis import Analysis
from ..models.analysis import AnalysisModel


def _to_entity(model: AnalysisModel) -> Analysis:
    return Analysis(
        id=model.id,
        input_type=model.input_type,
        status=model.status,
        rule_prompt=model.rule_prompt,
        created_at=model.created_at,
        source_text=model.source_text,
        source_url=model.source_url,
        source_filename=model.source_filename,
        source_media_type=model.source_media_type,
        storage_key=model.storage_key,
        title=model.title,
        classification=model.classification,
        reason=model.reason,
        summary=model.summary,
        warnings=list(model.warnings),
        model_name=model.model_name,
        prompt_version=model.prompt_version,
        usage_metadata=model.usage_metadata,
        error_code=model.error_code,
        error_message=model.error_message,
        started_at=model.started_at,
        completed_at=model.completed_at,
    )


def _new_model(analysis: Analysis) -> AnalysisModel:
    return AnalysisModel(
        id=analysis.id,
        input_type=analysis.input_type,
        status=analysis.status,
        rule_prompt=analysis.rule_prompt,
        source_text=analysis.source_text,
        source_url=analysis.source_url,
        source_filename=analysis.source_filename,
        source_media_type=analysis.source_media_type,
        storage_key=analysis.storage_key,
        title=analysis.title,
        warnings=analysis.warnings,
        created_at=analysis.created_at,
        started_at=analysis.started_at,
        completed_at=analysis.completed_at,
    )


def _apply(model: AnalysisModel, analysis: Analysis) -> None:
    model.status = analysis.status
    model.title = analysis.title
    model.classification = analysis.classification
    model.reason = analysis.reason
    model.summary = analysis.summary
    model.warnings = analysis.warnings
    model.model_name = analysis.model_name
    model.prompt_version = analysis.prompt_version
    model.usage_metadata = analysis.usage_metadata
    model.error_code = analysis.error_code
    model.error_message = analysis.error_message
    model.started_at = analysis.started_at
    model.completed_at = analysis.completed_at


class SqlAlchemyAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, analysis: Analysis) -> None:
        self._session.add(_new_model(analysis))
        await self._session.flush()

    async def get_by_id(self, analysis_id: UUID) -> Analysis | None:
        model = await self._session.get(AnalysisModel, analysis_id)
        return _to_entity(model) if model else None

    async def update(self, analysis: Analysis) -> None:
        model = await self._session.get(AnalysisModel, analysis.id)
        if model is None:
            return
        _apply(model, analysis)
        await self._session.flush()
