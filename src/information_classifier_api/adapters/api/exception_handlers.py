import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ...domain.exceptions import (
    DomainError,
    DomainValidationError,
    PayloadTooLargeError,
    PermanentProcessingError,
    ProviderUnavailableError,
    ResourceNotFoundError,
    StorageUnavailableError,
    TaskDispatchError,
    TransientProcessingError,
    UnsupportedMediaTypeError,
)

log = structlog.get_logger()

_STATUS_BY_TYPE: tuple[tuple[type[Exception], int], ...] = (
    (ResourceNotFoundError, status.HTTP_404_NOT_FOUND),
    (PayloadTooLargeError, status.HTTP_413_CONTENT_TOO_LARGE),
    (UnsupportedMediaTypeError, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    (DomainValidationError, status.HTTP_400_BAD_REQUEST),
    (ProviderUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (StorageUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (TransientProcessingError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (PermanentProcessingError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (TaskDispatchError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (DomainError, status.HTTP_400_BAD_REQUEST),
)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=_status_for(exc),
        content={"detail": str(exc)},
    )


def _status_for(exc: Exception) -> int:
    for error_type, status_code in _STATUS_BY_TYPE:
        if isinstance(exc, error_type):
            return status_code
    return status.HTTP_400_BAD_REQUEST


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception(
        "unhandled_error",
        method=request.method,
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "erro interno inesperado"},
    )
