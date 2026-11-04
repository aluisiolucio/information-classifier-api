from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .....domain.entities.relevance import Relevance


class CreateAnalysisResponse(BaseModel):
    analysis_id: UUID
    status: str
    status_url: str


class AnalysisSource(BaseModel):
    url: str | None = None
    filename: str | None = None
    media_type: str | None = None


class AnalysisError(BaseModel):
    code: str
    message: str


class AnalysisResponse(BaseModel):
    analysis_id: UUID
    status: str
    input_type: str
    source: AnalysisSource
    title: str | None = None
    classification: Relevance | None = None
    reason: str | None = None
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    model_name: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: AnalysisError | None = None
