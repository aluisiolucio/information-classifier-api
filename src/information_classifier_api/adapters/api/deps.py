from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.use_cases.classification_rule import (
    GetClassificationRule,
    UpdateClassificationRule,
)
from ...application.use_cases.fail_analysis import FailAnalysis
from ...application.use_cases.get_analysis import GetAnalysis
from ...application.use_cases.submit_analysis import SubmitAnalysis
from ...domain.interfaces.task_dispatcher import TaskDispatcher
from ...infrastructure.config.settings import Settings, get_settings
from ...infrastructure.database.session import get_session
from ...infrastructure.health import ReadinessChecker
from ...infrastructure.wiring import (
    build_fail_analysis,
    build_get_analysis,
    build_get_rule,
    build_submit_analysis,
    build_task_dispatcher,
    build_update_rule,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_submit_analysis_use_case(
    session: SessionDep, settings: SettingsDep
) -> SubmitAnalysis:
    return build_submit_analysis(session, settings)


def get_get_analysis_use_case(session: SessionDep) -> GetAnalysis:
    return build_get_analysis(session)


def get_fail_analysis_use_case(session: SessionDep) -> FailAnalysis:
    return build_fail_analysis(session)


def get_get_rule_use_case(session: SessionDep) -> GetClassificationRule:
    return build_get_rule(session)


def get_update_rule_use_case(
    session: SessionDep, settings: SettingsDep
) -> UpdateClassificationRule:
    return build_update_rule(session, settings)


def get_task_dispatcher() -> TaskDispatcher:
    return build_task_dispatcher()


def get_readiness_checker(settings: SettingsDep) -> ReadinessChecker:
    return ReadinessChecker(settings)


SubmitAnalysisDep = Annotated[SubmitAnalysis, Depends(get_submit_analysis_use_case)]
GetAnalysisDep = Annotated[GetAnalysis, Depends(get_get_analysis_use_case)]
FailAnalysisDep = Annotated[FailAnalysis, Depends(get_fail_analysis_use_case)]
GetRuleDep = Annotated[GetClassificationRule, Depends(get_get_rule_use_case)]
UpdateRuleDep = Annotated[UpdateClassificationRule, Depends(get_update_rule_use_case)]
TaskDispatcherDep = Annotated[TaskDispatcher, Depends(get_task_dispatcher)]
ReadinessCheckerDep = Annotated[ReadinessChecker, Depends(get_readiness_checker)]
