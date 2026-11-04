from fastapi import APIRouter

from ....domain.entities.classification_rule import ClassificationRule
from ..deps import GetRuleDep, UpdateRuleDep
from .schemas.rule import RuleResponse, UpdateRuleRequest

router = APIRouter(prefix="/rule", tags=["rule"])


@router.get("", response_model=RuleResponse)
async def get_rule(use_case: GetRuleDep) -> RuleResponse:
    return _to_response(await use_case.execute())


@router.put("", response_model=RuleResponse)
async def update_rule(
    payload: UpdateRuleRequest, use_case: UpdateRuleDep
) -> RuleResponse:
    return _to_response(await use_case.execute(payload.prompt))


def _to_response(rule: ClassificationRule) -> RuleResponse:
    return RuleResponse(prompt=rule.prompt, updated_at=rule.updated_at)
