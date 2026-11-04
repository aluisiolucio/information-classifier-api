import httpx
import structlog

from ...domain.entities.fetched_page import FetchedPage
from ...domain.exceptions import ExtractionError, WebFetchError
from ...domain.interfaces.url_validator import UrlValidator
from ...domain.interfaces.web_page_fetcher import WebPageFetcher
from ...domain.types import JsonObject
from .main_content import extract_page_metadata, select_main_html

log = structlog.get_logger()

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class HttpPageFetcher(WebPageFetcher):
    """Busca uma URL com validação SSRF, limite de bytes e redirects manuais."""

    def __init__(
        self,
        *,
        url_validator: UrlValidator,
        user_agent: str,
        timeout_seconds: int,
        max_response_bytes: int,
        max_redirects: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._validator = url_validator
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._transport = transport

    async def fetch(self, url: str) -> FetchedPage:
        current = await self._validator.validate(url)
        for _ in range(self._max_redirects + 1):
            response = await self._get(current)
            if response.status_code in _REDIRECT_STATUSES:
                current = await self._redirect_target(current, response)
                continue
            return self._page(current, response)
        raise WebFetchError(
            f"URL {url!r} excedeu {self._max_redirects} redirecionamentos"
        )

    async def _get(self, url: str) -> httpx.Response:
        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                async with client.stream(
                    "GET", url, headers={"User-Agent": self._user_agent}
                ) as response:
                    content = await _read_limited(
                        response, self._max_response_bytes, url
                    )
                    return httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=content,
                        request=response.request,
                    )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise WebFetchError(
                f"falha ao buscar {url!r}: {type(exc).__name__}"
            ) from exc

    async def _redirect_target(self, current: str, response: httpx.Response) -> str:
        location = response.headers.get("location")
        if not location:
            raise WebFetchError(
                f"redirect HTTP {response.status_code} de {current!r} sem Location"
            )
        target = str(httpx.URL(current).join(location))
        return await self._validator.validate(target)

    def _page(self, url: str, response: httpx.Response) -> FetchedPage:
        if response.status_code >= 400:
            return FetchedPage(
                url=url,
                final_url=url,
                status_code=response.status_code,
                html="",
                metadata={"content_type": response.headers.get("content-type")},
            )
        _ensure_html(url, response)
        html = response.text
        selected_html, warnings = select_main_html(html)
        metadata = extract_page_metadata(html)
        title = _metadata_text(metadata, "title") or _metadata_text(
            metadata, "og_title"
        )
        log.info(
            "web_page_fetched",
            url=url,
            status_code=response.status_code,
            chars=len(selected_html),
        )
        return FetchedPage(
            url=url,
            final_url=url,
            status_code=response.status_code,
            html=selected_html,
            title=title,
            metadata=metadata,
            warnings=warnings,
        )


async def _read_limited(response: httpx.Response, limit: int, url: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise ExtractionError(
                f"resposta de {url!r} excede WEB_FETCH_MAX_RESPONSE_BYTES={limit} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _metadata_text(metadata: JsonObject, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _ensure_html(url: str, response: httpx.Response) -> None:
    content_type = response.headers.get("content-type", "").lower()
    if "html" in content_type or "xml" in content_type:
        return
    if response.text.lstrip().startswith("<"):
        return
    raise ExtractionError(
        f"URL {url!r} retornou content-type {content_type!r}; esperado HTML"
    )
