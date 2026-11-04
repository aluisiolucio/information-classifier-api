import gzip
import socket

import httpx
import pytest

from information_classifier_api.domain.exceptions import (
    ExtractionError,
    UrlBlockedError,
    WebFetchError,
)
from information_classifier_api.domain.services.url_policy import UrlPolicy
from information_classifier_api.infrastructure.web.http_fetcher import HttpPageFetcher
from information_classifier_api.infrastructure.web.main_content import (
    extract_page_metadata,
    select_main_html,
)
from information_classifier_api.infrastructure.web.url_validator import DnsUrlValidator
from tests.unit.fakes import FakeUrlValidator

POLICY = UrlPolicy.from_ports([80, 443])
_HTML = (
    "<html><head><title>Notícia</title>"
    "<meta name='description' content='Resumo da notícia'>"
    "<meta property='og:title' content='Título OG'></head>"
    "<body><nav>menu</nav><article><p>Texto principal</p></article>"
    "<footer>rodapé</footer></body></html>"
)


def _fetcher(
    handler,
    *,
    max_response_bytes: int = 100_000,
    max_redirects: int = 5,
) -> HttpPageFetcher:
    return HttpPageFetcher(
        url_validator=FakeUrlValidator(),
        user_agent="tests/1.0",
        timeout_seconds=5,
        max_response_bytes=max_response_bytes,
        max_redirects=max_redirects,
        transport=httpx.MockTransport(handler),
    )


def test_select_main_html_prefers_article_and_removes_boilerplate() -> None:
    selected, warnings = select_main_html(_HTML)
    assert "Texto principal" in selected
    assert "menu" not in selected
    assert "rodapé" not in selected
    assert warnings == []


def test_select_main_html_falls_back_to_body() -> None:
    selected, warnings = select_main_html("<html><body><p>Texto</p></body></html>")
    assert "Texto" in selected
    assert warnings


def test_extract_page_metadata_reads_meta_tags() -> None:
    metadata = extract_page_metadata(_HTML)
    assert metadata["title"] == "Notícia"
    assert metadata["description"] == "Resumo da notícia"
    assert metadata["og_title"] == "Título OG"


async def test_fetch_returns_selected_html_and_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_HTML)

    page = await _fetcher(handler).fetch("https://example.com/noticia")
    assert page.status_code == 200
    assert page.final_url == "https://example.com/noticia"
    assert page.title == "Notícia"
    assert "Texto principal" in page.html
    assert page.metadata["description"] == "Resumo da notícia"


async def test_fetch_decodes_gzip_response_once() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "gzip",
            },
            content=gzip.compress(_HTML.encode()),
        )

    page = await _fetcher(handler).fetch("https://example.com/noticia")
    assert page.status_code == 200
    assert page.title == "Notícia"
    assert "Texto principal" in page.html


async def test_fetch_wraps_invalid_gzip_as_web_fetch_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html",
                "content-encoding": "gzip",
            },
            content=b"isto nao e gzip",
        )

    with pytest.raises(WebFetchError, match="DecodingError"):
        await _fetcher(handler).fetch("https://example.com/quebrado")


async def test_fetch_follows_redirect_after_validation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "/final"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_HTML)

    validator = FakeUrlValidator()
    fetcher = HttpPageFetcher(
        url_validator=validator,
        user_agent="tests/1.0",
        timeout_seconds=5,
        max_response_bytes=100_000,
        max_redirects=2,
        transport=httpx.MockTransport(handler),
    )
    page = await fetcher.fetch("https://example.com/start")
    assert page.final_url == "https://example.com/final"
    assert validator.seen == [
        "https://example.com/start",
        "https://example.com/final",
    ]


async def test_fetch_rejects_redirect_without_location() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    with pytest.raises(WebFetchError, match="sem Location"):
        await _fetcher(handler).fetch("https://example.com/start")


async def test_fetch_rejects_too_many_redirects() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    with pytest.raises(WebFetchError, match="redirecionamentos"):
        await _fetcher(handler, max_redirects=1).fetch("https://example.com/start")


async def test_fetch_returns_http_error_page() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "text/html"})

    page = await _fetcher(handler).fetch("https://example.com/missing")
    assert page.status_code == 404
    assert page.html == ""


async def test_fetch_rejects_non_html_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/json"}, json={"ok": True}
        )

    with pytest.raises(ExtractionError, match="esperado HTML"):
        await _fetcher(handler).fetch("https://example.com/data")


async def test_fetch_rejects_response_over_byte_limit() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="x" * 100
        )

    with pytest.raises(ExtractionError, match="excede"):
        await _fetcher(handler, max_response_bytes=10).fetch("https://example.com/big")


async def test_fetch_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("falha de rede", request=request)

    with pytest.raises(WebFetchError, match="ConnectError"):
        await _fetcher(handler).fetch("https://example.com/")


async def test_dns_validator_accepts_public_address(monkeypatch) -> None:
    monkeypatch.setattr(
        "information_classifier_api.infrastructure.web.url_validator.resolve_addresses",
        lambda host, port: ["93.184.216.34"],
    )
    canonical = await DnsUrlValidator(POLICY).validate("https://example.com/x")
    assert canonical == "https://example.com/x"


async def test_dns_validator_rejects_private_address(monkeypatch) -> None:
    monkeypatch.setattr(
        "information_classifier_api.infrastructure.web.url_validator.resolve_addresses",
        lambda host, port: ["10.0.0.1"],
    )
    with pytest.raises(UrlBlockedError, match="não público"):
        await DnsUrlValidator(POLICY).validate("https://example.com/x")


async def test_dns_validator_rejects_empty_and_failed_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        "information_classifier_api.infrastructure.web.url_validator.resolve_addresses",
        lambda host, port: [],
    )
    with pytest.raises(UrlBlockedError, match="lista vazia"):
        await DnsUrlValidator(POLICY).validate("https://example.com/x")

    def fail(host: str, port: int) -> list[str]:
        raise socket.gaierror(socket.EAI_NONAME, "nome desconhecido")

    monkeypatch.setattr(
        "information_classifier_api.infrastructure.web.url_validator.resolve_addresses",
        fail,
    )
    with pytest.raises(UrlBlockedError, match="não resolveu"):
        await DnsUrlValidator(POLICY).validate("https://example.com/x")
