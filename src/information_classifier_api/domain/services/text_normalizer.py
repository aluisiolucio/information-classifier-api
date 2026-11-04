import re

from ..exceptions import DomainValidationError

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def normalize_text_to_markdown(raw_text: str) -> str:
    """Normaliza texto direto sem conversão artificial por Docling.

    Preserva parágrafos e conteúdo semântico; ajusta apenas finais de linha,
    espaços externos e linhas em branco excessivas.

    >>> normalize_text_to_markdown("  olá\\r\\n\\r\\n\\r\\nmundo  ")
    'olá\\n\\nmundo'
    """
    if not isinstance(raw_text, str):
        raise DomainValidationError(
            f"texto deve ser str, recebido {type(raw_text).__name__}"
        )
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    lines = [line.rstrip() for line in text.split("\n")]
    normalized = "\n".join(lines).strip()
    normalized = _EXCESS_BLANK_LINES.sub("\n\n", normalized)
    if not normalized:
        raise DomainValidationError("texto não pode ser vazio")
    return normalized


def strip_html_comments(text: str) -> str:
    """Remove comentários HTML, como o `<!-- image -->` emitido pelo Docling."""
    return _HTML_COMMENT.sub(" ", text)


def extract_title(markdown: str, max_chars: int = 200) -> str | None:
    """Usa o primeiro título/linha como título legível, sem markdown decorativo."""
    for line in strip_html_comments(markdown).splitlines():
        candidate = line.strip().lstrip("#").strip()
        if candidate:
            return candidate[:max_chars]
    return None
