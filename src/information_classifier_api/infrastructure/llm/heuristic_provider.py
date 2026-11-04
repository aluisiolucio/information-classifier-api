import re
import time
import unicodedata
from dataclasses import dataclass

from ...domain.entities.provider_contracts import (
    ClassificationProviderResult,
    ClassificationRequest,
)
from ...domain.entities.relevance import (
    SUMMARY_MAX_CHARS,
    ProviderUsage,
)
from ...domain.services.text_normalizer import strip_html_comments
from ...domain.types import JsonObject

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_MARKERS = re.compile(r"[#*_`>\[\]]")
_CLAUSE_SPLIT = re.compile(r"[.;]\s*|\s+(?:e|mas|porém|entretanto)\s+", re.IGNORECASE)
_VERB_SPLIT = re.compile(r"\s+(?:são|é|for|seja|serão)\s+", re.IGNORECASE)
_LIST_SPLIT = re.compile(r"[,;]|\s+e\s+", re.IGNORECASE)
_RELATIVE_SPLIT = re.compile(r"\bque\b", re.IGNORECASE)
_QUOTED = re.compile(r"[\"“”']([^\"“”']{2,80})[\"“”']")
_CLASS_LABELS = {"altamente relevante", "relevante", "pouco relevante"}
_AFTER_SOBRE = re.compile(
    r"\b(?:sobre|a respeito de|relacionad[oa]s? a)\s+(.+)", re.IGNORECASE
)
_AFTER_DE = re.compile(r"\b(?:de|do|da|das|dos)\s+(.+)", re.IGNORECASE)
_WORD = re.compile(r"[a-zà-ÿ0-9]{4,}", re.IGNORECASE)


def _fold(text: str) -> str:
    """Remove acentos para comparar termos sem depender de grafia."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


_LEADING = (
    "a ",
    "o ",
    "as ",
    "os ",
    "de ",
    "da ",
    "do ",
    "das ",
    "dos ",
    "em ",
    "na ",
    "no ",
    "nas ",
    "nos ",
    "sobre ",
    "para ",
)
_TRAILING = (
    " em geral",
    " em específico",
    " especificamente",
    " relevantes",
    " relevante",
    " altamente",
    " pouco",
    " são",
    " é",
)
_GENERIC_TERMS = {
    "conteúdo",
    "conteudos",
    "conteúdos",
    "notícia",
    "noticia",
    "notícias",
    "noticias",
    "texto",
    "textos",
    "mídia",
    "midia",
    "mídias",
    "midias",
    "informação",
    "informacao",
    "informações",
    "informacoes",
    "tudo",
    "todo",
    "toda",
    "todos",
    "todas",
    "qualquer",
    "coisa",
    "coisas",
}
_STOPWORDS = {
    "altamente",
    "analise",
    "analisar",
    "classifique",
    "classificar",
    "como",
    "conforme",
    "critério",
    "criterio",
    "critérios",
    "criterios",
    "deve",
    "devem",
    "essa",
    "esse",
    "especificamente",
    "esta",
    "este",
    "geral",
    "isso",
    "para",
    "pela",
    "pelo",
    "pouco",
    "quando",
    "que",
    "regra",
    "relevante",
    "relevantes",
    "seja",
    "ser",
    "sobre",
    "também",
    "tambem",
    "todas",
    "todos",
    "tratem",
    "uma",
}
_FOLDED_GENERIC_TERMS = {_fold(term) for term in _GENERIC_TERMS}
_FOLDED_STOPWORDS = {_fold(term) for term in _STOPWORDS}


@dataclass(frozen=True)
class RuleCriteria:
    high: list[str]
    relevant: list[str]
    fallback: list[str]


class HeuristicRelevanceProvider:
    """Provedor determinístico que interpreta a regra por palavras-chave.

    Não é um LLM: extrai termos de cláusulas com "relevante"/"altamente
    relevante". Em produção configure `LLM_PROVIDER=openai` para interpretar
    prompts livres com semântica real.
    """

    model_name = "heuristic-v2"

    async def classify(
        self, request: ClassificationRequest
    ) -> ClassificationProviderResult:
        started = time.monotonic()
        criteria = _parse_rule(request.rule_prompt)
        content = request.content_markdown
        classification, matched = _classification(criteria, content)
        payload: JsonObject = {
            "classification": classification,
            "summary": _summary(content, SUMMARY_MAX_CHARS),
            "reason": _reason(classification, matched, criteria)[:1000],
        }
        duration_ms = int((time.monotonic() - started) * 1000)
        return ClassificationProviderResult(
            payload=payload,
            model_name=self.model_name,
            usage=ProviderUsage(
                input_tokens=max(1, len(content) // 4),
                output_tokens=max(1, len(str(payload)) // 4),
                duration_ms=duration_ms,
            ),
        )


def _parse_rule(prompt: str) -> RuleCriteria:
    high: list[str] = []
    relevant: list[str] = []
    for clause in _CLAUSE_SPLIT.split(prompt):
        level = _level(clause)
        if level == "high":
            high.extend(_terms(clause))
        elif level == "relevant":
            relevant.extend(_terms(clause))
    if high or relevant:
        return RuleCriteria(_dedupe(high), _dedupe(relevant), [])
    return RuleCriteria([], [], _fallback_terms(prompt))


def _level(clause: str) -> str | None:
    lowered = _fold(clause.lower())
    if "altamente relevante" in lowered:
        return "high"
    if "pouco relevante" in lowered:
        return "low"
    if "relevante" in lowered:
        return "relevant"
    return None


def _terms(clause: str) -> list[str]:
    terms = [
        value
        for value in _QUOTED.findall(clause)
        if value.strip().lower() not in _CLASS_LABELS
    ]
    after_sobre = _AFTER_SOBRE.search(clause)
    after_de = _AFTER_DE.search(clause)
    if after_sobre is not None:
        terms.extend(_phrases(after_sobre.group(1)))
    elif after_de is not None:
        terms.extend(_phrases(after_de.group(1)))
    return _clean_terms(terms)


def _phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for segment in _RELATIVE_SPLIT.split(text):
        phrases.extend(_segment_phrases(segment))
    return phrases


def _segment_phrases(segment: str) -> list[str]:
    before_verb = _VERB_SPLIT.split(segment)[0]
    phrases: list[str] = []
    for part in _LIST_SPLIT.split(before_verb):
        cleaned = part.strip()
        if not cleaned:
            continue
        after_de = _AFTER_DE.search(cleaned)
        if after_de is not None and len(cleaned.split()) > 3:
            phrases.append(after_de.group(1))
            continue
        phrases.append(cleaned)
    return phrases


def _clean_terms(terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    for term in terms:
        candidate = _clean_term(term)
        folded = _fold(candidate)
        if (
            candidate
            and folded not in _FOLDED_GENERIC_TERMS
            and folded not in _FOLDED_STOPWORDS
        ):
            cleaned.append(candidate)
    return _dedupe(cleaned)


def _clean_term(term: str) -> str:
    candidate = term.strip(" \t\n\r.,;:!?()[]{}\"'“”").lower()
    for prefix in _LEADING:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :]
    for suffix in _TRAILING:
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
    return candidate.strip()


def _fallback_terms(prompt: str) -> list[str]:
    words = [
        word.lower() for word in _WORD.findall(prompt) if word.lower() not in _STOPWORDS
    ]
    return _dedupe(words)[:20]


def _matches(content: str, terms: list[str]) -> list[str]:
    lowered = _fold(content.lower())
    return [term for term in terms if term and _fold(term.lower()) in lowered]


def _classification(
    criteria: RuleCriteria,
    content: str,
) -> tuple[str, list[str]]:
    high_matches = _matches(content, criteria.high)
    relevant_matches = _matches(content, criteria.relevant)
    if criteria.high and len(high_matches) == len(criteria.high):
        return "Altamente relevante", high_matches
    if relevant_matches:
        return "Relevante", relevant_matches
    if not criteria.high and not criteria.relevant:
        fallback = _matches(content, criteria.fallback)
        if fallback:
            return "Relevante", fallback
    return "Pouco relevante", []


def _reason(classification: str, matched: list[str], criteria: RuleCriteria) -> str:
    if matched:
        return (
            f"Critério de {classification.lower()} atendido pelos termos: "
            + ", ".join(matched)
            + "."
        )
    if not criteria.high and not criteria.relevant:
        return (
            "A regra não permitiu extrair critérios objetivos; "
            "classificação conservadora como pouco relevante."
        )
    return "Nenhum critério de relevância da regra foi identificado no conteúdo."


def _summary(content: str, max_chars: int) -> str:
    limit = min(max_chars, SUMMARY_MAX_CHARS)
    sentences = _sentences(content)
    if not sentences:
        return "Conteúdo sem texto suficiente para resumo."
    selected = ""
    for sentence in sentences:
        candidate = f"{selected} {sentence}".strip()
        if len(candidate) > limit:
            break
        selected = candidate
    if selected:
        return _strip_intro(selected)
    return _cut_on_boundary(sentences[0], limit)


def _sentences(content: str) -> list[str]:
    plain = _plain_text(content)
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split(plain)
        if sentence.strip()
    ]


def _plain_text(content: str) -> str:
    lines = []
    for line in strip_html_comments(content).splitlines():
        stripped = _MARKDOWN_MARKERS.sub("", line).strip()
        if stripped:
            lines.append(stripped)
    return " ".join(lines)


def _cut_on_boundary(sentence: str, limit: int) -> str:
    if len(sentence) <= limit:
        return sentence
    window = sentence[: limit - 1]
    cut = max(window.rfind(". "), window.rfind("; "), window.rfind(", "))
    if cut > limit // 2:
        return window[: cut + 1].strip()
    space = window.rfind(" ")
    return (window[:space] if space > 0 else window).strip() + "…"


def _strip_intro(text: str) -> str:
    lowered = text.lower()
    for prefix in ("este conteúdo fala sobre", "este texto fala sobre"):
        if lowered.startswith(prefix):
            return text[len(prefix) :].lstrip(" ,:-")
    return text


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
