from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ....domain.entities.classification_rule import ClassificationRule
from ..models.classification_rule import ClassificationRuleModel

_RULE_ID = 1


class SqlAlchemyClassificationRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> ClassificationRule | None:
        model = await self._session.get(ClassificationRuleModel, _RULE_ID)
        if model is None:
            return None
        return ClassificationRule(prompt=model.prompt, updated_at=model.updated_at)

    async def upsert(self, prompt: str, updated_at: datetime) -> ClassificationRule:
        model = await self._session.get(ClassificationRuleModel, _RULE_ID)
        if model is None:
            model = ClassificationRuleModel(
                id=_RULE_ID, prompt=prompt, updated_at=updated_at
            )
            self._session.add(model)
        else:
            model.prompt = prompt
            model.updated_at = updated_at
        await self._session.flush()
        return ClassificationRule(prompt=prompt, updated_at=updated_at)
