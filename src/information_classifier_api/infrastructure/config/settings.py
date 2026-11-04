from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração tipada carregada do ambiente / `.env`.

    Nenhum módulo deve ler `os.environ` diretamente. Limites de recurso ficam
    centralizados aqui e são validados antes de a aplicação aceitar trabalho.

    >>> Settings(  # doctest: +SKIP
    ...     database_url="postgresql+psycopg://x",
    ... )
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "information-classifier-api"
    database_url: str
    environment: Literal["local", "dev", "prod"] = Field(
        default="dev",
        validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV"),
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    api_v1_prefix: str = "/v1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    redis_url: str = "redis://localhost:6379/0"
    celery_task_max_retries: int = Field(default=3, ge=0, le=10)
    celery_retry_backoff_seconds: int = Field(default=5, ge=1)
    analysis_soft_time_limit_seconds: int = Field(default=900, ge=30)

    storage_backend: Literal["s3", "memory"] = "s3"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "information-classifier-api"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"

    llm_provider: Literal["heuristic", "openai"] = "heuristic"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    prompt_max_chars: int = Field(default=24_000, ge=1_000)
    max_upload_bytes: int = Field(default=52_428_800, ge=1)
    max_text_chars: int = Field(default=500_000, ge=1)
    max_extracted_chars: int = Field(default=500_000, ge=1)
    max_rule_prompt_chars: int = Field(default=20_000, ge=100)

    web_fetch_timeout_seconds: int = Field(default=30, ge=1)
    web_fetch_max_response_bytes: int = Field(default=5_242_880, ge=1)
    web_fetch_user_agent: str = "InformationClassifierBot/1.0"
    web_fetch_max_redirects: int = Field(default=5, ge=0, le=10)
    allowed_url_ports: list[int] = Field(default_factory=lambda: [80, 443])

    # Áudio/vídeo: modelo Whisper e idioma. Idioma vazio detecta automaticamente.
    asr_model: str = "small"
    asr_language: str = ""

    log_level: str = "INFO"

    @field_validator("api_v1_prefix")
    @classmethod
    def _normalize_api_prefix(cls, value: str) -> str:
        prefix = value.strip()
        if not prefix.startswith("/"):
            raise ValueError(f"api_v1_prefix deve começar com '/', recebido {value!r}")
        return prefix.rstrip("/") or "/v1"

    @model_validator(mode="after")
    def _validate_resource_limits(self) -> "Settings":
        if not self.allowed_url_ports:
            raise ValueError("allowed_url_ports não pode ser vazio")
        if any(port < 1 or port > 65535 for port in self.allowed_url_ports):
            raise ValueError("allowed_url_ports deve conter portas entre 1 e 65535")
        if self.llm_provider == "openai" and not self.llm_model:
            raise ValueError("LLM_MODEL é obrigatório quando LLM_PROVIDER=openai")
        if self.llm_provider == "openai" and not self.llm_api_key:
            raise ValueError("LLM_API_KEY é obrigatório quando LLM_PROVIDER=openai")
        return self

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
