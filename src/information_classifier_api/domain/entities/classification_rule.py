from dataclasses import dataclass
from datetime import datetime

DEFAULT_RULE_PROMPT = (
    "Classifique o conteúdo conforme a relevância para o objetivo abaixo.\n\n"
    '- "Altamente relevante": notícias sobre tecnologia que tratem '
    "especificamente de inteligência artificial.\n"
    '- "Relevante": notícias sobre tecnologia em geral.\n'
    '- "Pouco relevante": todo o restante.\n\n'
    "Use apenas as três classes públicas e justifique a escolha com "
    "evidências do conteúdo."
)


@dataclass(frozen=True)
class ClassificationRule:
    """Regra global usada para classificar cada análise."""

    prompt: str
    updated_at: datetime | None = None
