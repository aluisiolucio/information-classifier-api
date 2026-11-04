from typing import cast
from uuid import uuid4

import pytest

from information_classifier_api.application.dto import (
    AnalysisInput,
    SubmitFileAnalysis,
    SubmitTextAnalysis,
    SubmitUrlAnalysis,
)
from information_classifier_api.application.use_cases.classification_rule import (
    GetClassificationRule,
    UpdateClassificationRule,
)
from information_classifier_api.application.use_cases.fail_analysis import (
    FailAnalysis,
)
from information_classifier_api.application.use_cases.get_analysis import (
    GetAnalysis,
)
from information_classifier_api.application.use_cases.submit_analysis import (
    SubmitAnalysis,
)
from information_classifier_api.domain.entities.analysis import (
    AnalysisStatus,
    InputType,
)
from information_classifier_api.domain.entities.classification_rule import (
    DEFAULT_RULE_PROMPT,
    ClassificationRule,
)
from information_classifier_api.domain.exceptions import (
    AnalysisNotFoundError,
    DomainValidationError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from tests.unit.fakes import (
    FakeUrlValidator,
    InMemoryAnalysisRepository,
    InMemoryClassificationRuleRepository,
    InMemoryObjectStorage,
)


def _submitter(
    *,
    rules: InMemoryClassificationRuleRepository | None = None,
    validator: FakeUrlValidator | None = None,
    storage: InMemoryObjectStorage | None = None,
    max_upload_bytes: int = 1024,
    max_text_chars: int = 1000,
) -> SubmitAnalysis:
    return SubmitAnalysis(
        analyses=InMemoryAnalysisRepository(),
        rules=rules or InMemoryClassificationRuleRepository(),
        storage=storage or InMemoryObjectStorage(),
        url_validator=validator or FakeUrlValidator(),
        max_upload_bytes=max_upload_bytes,
        max_text_chars=max_text_chars,
    )


async def test_submit_text_snapshots_rule_prompt_and_normalizes_text() -> None:
    rules = InMemoryClassificationRuleRepository(
        ClassificationRule(prompt="Regra personalizada")
    )
    submitter = _submitter(rules=rules)
    analysis = await submitter.execute(
        SubmitTextAnalysis(text="  # Título\r\n\r\n\r\nTecnologia.  ")
    )
    assert analysis.status == AnalysisStatus.QUEUED
    assert analysis.input_type == InputType.TEXT
    assert analysis.rule_prompt == "Regra personalizada"
    assert analysis.source_text == "# Título\n\nTecnologia."
    assert analysis.title == "Título"


async def test_submit_text_uses_default_rule_when_absent() -> None:
    analysis = await _submitter().execute(SubmitTextAnalysis(text="conteúdo"))
    assert analysis.rule_prompt == DEFAULT_RULE_PROMPT


async def test_submit_text_rejects_text_over_limit() -> None:
    with pytest.raises(DomainValidationError, match="MAX_TEXT_CHARS=3"):
        await _submitter(max_text_chars=3).execute(SubmitTextAnalysis(text="abcd"))


async def test_submit_url_stores_canonical_url() -> None:
    validator = FakeUrlValidator(canonical="https://example.com/noticia")
    analysis = await _submitter(validator=validator).execute(
        SubmitUrlAnalysis(url="HTTPS://EXAMPLE.COM/noticia#x")
    )
    assert validator.seen == ["HTTPS://EXAMPLE.COM/noticia#x"]
    assert analysis.input_type == InputType.URL
    assert analysis.source_url == "https://example.com/noticia"


async def test_submit_file_validates_and_stores_object() -> None:
    storage = InMemoryObjectStorage()
    analysis = await _submitter(storage=storage).execute(
        SubmitFileAnalysis(
            filename="../../nota.txt",
            declared_media_type="text/plain",
            data=b"conteudo",
        )
    )
    assert analysis.input_type == InputType.FILE
    assert analysis.source_filename == "nota.txt"
    assert analysis.source_media_type == "text/plain"
    assert analysis.storage_key == f"uploads/{analysis.id}/nota.txt"
    assert storage.objects[analysis.storage_key] == (b"conteudo", "text/plain")


async def test_submit_file_rejects_payload_over_limit() -> None:
    with pytest.raises(PayloadTooLargeError, match="excede"):
        await _submitter(max_upload_bytes=2).execute(
            SubmitFileAnalysis(
                filename="nota.txt",
                declared_media_type="text/plain",
                data=b"abc",
            )
        )


async def test_submit_file_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="\\.exe"):
        await _submitter().execute(
            SubmitFileAnalysis(
                filename="virus.exe",
                declared_media_type="application/octet-stream",
                data=b"MZ",
            )
        )


async def test_submit_rejects_unknown_input_type() -> None:
    with pytest.raises(DomainValidationError, match="origem não suportada"):
        await _submitter().execute(cast(AnalysisInput, "texto"))


async def test_get_analysis_returns_existing_and_raises_for_missing() -> None:
    analyses = InMemoryAnalysisRepository()
    submitter = SubmitAnalysis(
        analyses=analyses,
        rules=InMemoryClassificationRuleRepository(),
        storage=InMemoryObjectStorage(),
        url_validator=FakeUrlValidator(),
        max_upload_bytes=1024,
        max_text_chars=1000,
    )
    created = await submitter.execute(SubmitTextAnalysis(text="conteúdo"))
    assert await GetAnalysis(analyses).execute(created.id) == created
    with pytest.raises(AnalysisNotFoundError):
        await GetAnalysis(analyses).execute(uuid4())


async def test_fail_analysis_sanitizes_message_and_is_idempotent() -> None:
    analyses = InMemoryAnalysisRepository()
    submitter = SubmitAnalysis(
        analyses=analyses,
        rules=InMemoryClassificationRuleRepository(),
        storage=InMemoryObjectStorage(),
        url_validator=FakeUrlValidator(),
        max_upload_bytes=1024,
        max_text_chars=1000,
    )
    created = await submitter.execute(SubmitTextAnalysis(text="conteúdo"))
    failed = await FailAnalysis(analyses).execute(
        created.id, "provider_unavailable", "falha\n na   rede"
    )
    assert failed.status == AnalysisStatus.FAILED
    assert failed.error_message == "falha na rede"
    again = await FailAnalysis(analyses).execute(created.id, "outro", "ignorado")
    assert again.error_code == "provider_unavailable"


async def test_get_rule_returns_default_when_absent() -> None:
    rule = await GetClassificationRule(InMemoryClassificationRuleRepository()).execute()
    assert rule.prompt == DEFAULT_RULE_PROMPT


async def test_update_rule_trims_prompt_and_persists() -> None:
    rules = InMemoryClassificationRuleRepository()
    updated = await UpdateClassificationRule(rules, max_prompt_chars=100).execute(
        "  Nova regra  "
    )
    assert updated.prompt == "Nova regra"
    assert updated.updated_at is not None
    assert (await rules.get()) == updated


async def test_update_rule_rejects_empty_or_too_long_prompt() -> None:
    use_case = UpdateClassificationRule(
        InMemoryClassificationRuleRepository(), max_prompt_chars=5
    )
    with pytest.raises(DomainValidationError, match="vazia"):
        await use_case.execute("   ")
    with pytest.raises(DomainValidationError, match="MAX_RULE_PROMPT_CHARS=5"):
        await use_case.execute("123456")
