from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RuleResponse(BaseModel):
    prompt: str
    updated_at: datetime | None = None


class UpdateRuleRequest(BaseModel):
    prompt: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")
