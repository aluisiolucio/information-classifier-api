import time
from uuid import uuid4

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

log = structlog.get_logger()
_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_CHARS = 64


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlaciona logs por request sem registrar corpo, query ou tokens."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = _request_id(request)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=_elapsed_ms(started),
            )
            raise
        response.headers[_REQUEST_ID_HEADER] = request_id
        log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=_elapsed_ms(started),
        )
        return response


def _request_id(request: Request) -> str:
    supplied = request.headers.get(_REQUEST_ID_HEADER, "").strip()
    if supplied and len(supplied) <= _MAX_REQUEST_ID_CHARS:
        return supplied
    return uuid4().hex


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
