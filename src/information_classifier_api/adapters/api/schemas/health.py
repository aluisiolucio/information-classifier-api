from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    failed: list[str]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "ready", "failed": []},
        }
    )
