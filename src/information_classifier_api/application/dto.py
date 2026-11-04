from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SubmitTextAnalysis:
    text: str


@dataclass(frozen=True)
class SubmitUrlAnalysis:
    url: str


@dataclass(frozen=True)
class SubmitFileAnalysis:
    filename: str
    declared_media_type: str | None
    data: bytes


type AnalysisInput = SubmitTextAnalysis | SubmitUrlAnalysis | SubmitFileAnalysis


@dataclass(frozen=True)
class RuleView:
    prompt: str
    updated_at: datetime | None
