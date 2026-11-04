from datetime import datetime
from typing import Protocol

from ..entities.classification_rule import ClassificationRule


class ClassificationRuleRepository(Protocol):
    async def get(self) -> ClassificationRule | None: ...

    async def upsert(self, prompt: str, updated_at: datetime) -> ClassificationRule: ...
