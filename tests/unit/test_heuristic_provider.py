import pytest

from information_classifier_api.domain.entities.classification_rule import (
    DEFAULT_RULE_PROMPT,
)
from information_classifier_api.domain.entities.provider_contracts import (
    ClassificationRequest,
)
from information_classifier_api.infrastructure.llm.heuristic_provider import (
    HeuristicRelevanceProvider,
)


def _request(rule_prompt: str, content: str) -> ClassificationRequest:
    return ClassificationRequest(
        rule_prompt=rule_prompt,
        content_markdown=content,
        input_type="text",
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Notícia de tecnologia: nova ferramenta chega ao mercado.", "Relevante"),
        (
            "Notícia de tecnologia: avanço de inteligência artificial "
            "transforma o setor.",
            "Altamente relevante",
        ),
        ("Receita de bolo de chocolate para o fim de semana.", "Pouco relevante"),
    ],
)
async def test_default_rule_classifies_technology_and_ai(
    content: str, expected: str
) -> None:
    provider = HeuristicRelevanceProvider()
    result = await provider.classify(_request(DEFAULT_RULE_PROMPT, content))
    assert result.payload["classification"] == expected


async def test_matching_ignores_accents_in_rule_and_content() -> None:
    provider = HeuristicRelevanceProvider()
    result = await provider.classify(
        _request(
            DEFAULT_RULE_PROMPT,
            "Noticia de tecnologia sobre inteligencia artificial.",
        )
    )
    assert result.payload["classification"] == "Altamente relevante"


async def test_custom_rule_extracts_clauses_by_level() -> None:
    rule = (
        '"Altamente relevante": notícias sobre inteligência artificial. '
        '"Relevante": notícias sobre tecnologia. '
        '"Pouco relevante": todo o restante.'
    )
    provider = HeuristicRelevanceProvider()
    high = await provider.classify(
        _request(rule, "Avanço de inteligência artificial no mercado.")
    )
    relevant = await provider.classify(
        _request(rule, "Nova ferramenta de tecnologia disponível.")
    )
    assert high.payload["classification"] == "Altamente relevante"
    assert relevant.payload["classification"] == "Relevante"


async def test_custom_rule_accepts_quoted_terms() -> None:
    rule = (
        '"Altamente relevante": conteúdo com "ação comercial". '
        '"Relevante": conteúdo com "campanha".'
    )
    provider = HeuristicRelevanceProvider()
    result = await provider.classify(
        _request(rule, "O concorrente anunciou uma ação comercial agressiva.")
    )
    assert result.payload["classification"] == "Altamente relevante"
    assert "ação comercial" in str(result.payload["reason"])


async def test_rule_without_criteria_uses_fallback_terms() -> None:
    provider = HeuristicRelevanceProvider()
    result = await provider.classify(
        _request(
            "Classifique conteúdo sobre concorrência.",
            "A concorrência lançou um produto.",
        )
    )
    assert result.payload["classification"] == "Relevante"


async def test_summary_respects_max_chars_and_is_not_empty() -> None:
    provider = HeuristicRelevanceProvider()
    content = "# Título\n\n" + ("Frase de tecnologia. " * 40)
    result = await provider.classify(_request(DEFAULT_RULE_PROMPT, content))
    summary = str(result.payload["summary"])
    assert 0 < len(summary) <= 280
    assert result.payload["classification"] == "Relevante"


async def test_summary_ignores_html_comments_from_video_pipeline() -> None:
    provider = HeuristicRelevanceProvider()
    result = await provider.classify(
        _request(
            DEFAULT_RULE_PROMPT,
            "<!-- image -->\n\nNotícia de tecnologia sobre inteligência artificial.",
        )
    )
    summary = str(result.payload["summary"])
    assert summary == "Notícia de tecnologia sobre inteligência artificial."
    assert "<!--" not in summary


async def test_reason_is_limited_to_one_thousand_chars() -> None:
    provider = HeuristicRelevanceProvider()
    result = await provider.classify(_request(DEFAULT_RULE_PROMPT, "tecnologia " * 200))
    assert len(str(result.payload["reason"])) <= 1000
