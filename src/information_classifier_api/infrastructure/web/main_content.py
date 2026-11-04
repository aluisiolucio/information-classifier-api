import re

from parsel import Selector

from ...domain.types import JsonObject

_META_KEYS = {
    "description": ["meta[name='description']::attr(content)"],
    "canonical": ["link[rel='canonical']::attr(href)"],
    "published_at": [
        "meta[property='article:published_time']::attr(content)",
        "meta[name='date']::attr(content)",
    ],
    "og_title": ["meta[property='og:title']::attr(content)"],
}
_REMOVE_TAGS = (
    "script, style, noscript, nav, header, footer, aside, form, iframe, svg, "
    "template, button"
)
_WHITESPACE = re.compile(r"\s+")


def select_main_html(html: str) -> tuple[str, list[str]]:
    """Seleciona conteúdo principal e remove navegação/scripts/rodapés."""
    selector = Selector(text=html)
    for node in selector.css(_REMOVE_TAGS):
        node.drop()
    candidate = _best_candidate(selector)
    warnings: list[str] = []
    if candidate is None:
        warnings.append(
            "conteúdo principal não identificado; usando body como fallback"
        )
        candidate = _first_body(selector)
    selected = candidate.get() if candidate is not None else None
    return selected or html, warnings


def _best_candidate(selector: Selector) -> Selector | None:
    for query in ("article", "main", "[role='main']", "#content", ".content"):
        candidates = selector.css(query)
        if candidates:
            return max(candidates, key=lambda item: len(item.get() or ""))
    return None


def _first_body(selector: Selector) -> Selector | None:
    bodies = selector.css("body")
    return bodies[0] if bodies else None


def extract_page_metadata(html: str) -> JsonObject:
    selector = Selector(text=html)
    metadata: JsonObject = {}
    for key, queries in _META_KEYS.items():
        metadata[key] = _first_value(selector, queries)
    metadata["title"] = _clean(selector.css("title::text").get())
    return metadata


def _first_value(selector: Selector, queries: list[str]) -> str | None:
    for query in queries:
        value = selector.css(query).get()
        if value:
            return _clean(value)
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _WHITESPACE.sub(" ", value).strip()
    return cleaned or None
