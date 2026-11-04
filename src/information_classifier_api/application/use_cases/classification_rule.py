from datetime import UTC, datetime

from ...domain.entities.classification_rule import (
    DEFAULT_RULE_PROMPT,
    ClassificationRule,
)
from ...domain.exceptions import DomainValidationError
from ...domain.interfaces.classification_rule_repository import (
    ClassificationRuleRepository,
)


class GetClassificationRule:
    """Retorna a regra global, usando o prompt padrão quando ainda não existe."""

    def __init__(self, rules: ClassificationRuleRepository) -> None:
        self._rules = rules

    async def execute(self) -> ClassificationRule:
        rule = await self._rules.get()
        return rule or ClassificationRule(prompt=DEFAULT_RULE_PROMPT)


class UpdateClassificationRule:
    """Valida e substitui a regra global usada pelas próximas análises."""

    def __init__(
        self, rules: ClassificationRuleRepository, max_prompt_chars: int
    ) -> None:
        self._rules = rules
        self._max_prompt_chars = max_prompt_chars

    async def execute(self, prompt: str) -> ClassificationRule:
        normalized = _normalize_prompt(prompt, self._max_prompt_chars)
        return await self._rules.upsert(normalized, datetime.now(UTC))


def _normalize_prompt(prompt: str, max_prompt_chars: int) -> str:
    stripped = prompt.strip()
    if not stripped:
        raise DomainValidationError(
            "regra não pode ser vazia; esperado prompt com ao menos 1 caractere"
        )
    if len(stripped) > max_prompt_chars:
        raise DomainValidationError(
            f"regra com {len(stripped)} caracteres excede "
            f"MAX_RULE_PROMPT_CHARS={max_prompt_chars}"
        )
    return stripped
