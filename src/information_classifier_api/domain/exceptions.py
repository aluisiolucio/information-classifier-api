"""Falhas de negócio esperadas. Nenhuma mensagem deve conter segredos."""


class DomainError(Exception):
    """Base para erros recuperáveis de domínio."""


class ResourceNotFoundError(DomainError):
    """Recurso inexistente."""


class AnalysisNotFoundError(ResourceNotFoundError):
    def __init__(self, analysis_id: object) -> None:
        super().__init__(f"análise não encontrada: {analysis_id}")


class DomainValidationError(DomainError):
    """Entrada válida no transporte, mas inválida para o domínio."""


class InvalidUploadError(DomainValidationError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"upload inválido: {reason}")


class UnsupportedMediaTypeError(DomainValidationError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"tipo de mídia não aceito: {detail}")


class PayloadTooLargeError(DomainValidationError):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"payload de {size} bytes excede o limite de {limit} bytes")


class UrlBlockedError(DomainValidationError):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"URL bloqueada ({reason}): {url!r}")


class ProcessingError(DomainError):
    """Erro de processamento com código estável para persistência."""

    code = "processing_error"
    permanent = False

    def __init__(self, message: str) -> None:
        super().__init__(message)


class PermanentProcessingError(ProcessingError):
    """Erro que não deve ser repetido (formato inválido, conteúdo proibido)."""

    permanent = True


class TransientProcessingError(ProcessingError):
    """Erro potencialmente recuperável (rede, provedor, storage)."""

    permanent = False


class ProviderUnavailableError(TransientProcessingError):
    code = "provider_unavailable"


class ProviderConfigurationError(PermanentProcessingError):
    code = "provider_misconfigured"


class ProviderOutputError(PermanentProcessingError):
    code = "invalid_provider_output"


class ExtractionError(PermanentProcessingError):
    code = "extraction_failed"


class UnsupportedSourceTypeError(PermanentProcessingError):
    code = "unsupported_source_type"


class WebFetchError(TransientProcessingError):
    code = "web_fetch_failed"


class StorageUnavailableError(TransientProcessingError):
    code = "storage_unavailable"


class TaskDispatchError(DomainError):
    def __init__(self, topic: str, detail: str) -> None:
        super().__init__(f"falha ao enfileirar '{topic}': {detail}")
