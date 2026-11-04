import io
import zipfile

import pytest
from pydantic import ValidationError

from information_classifier_api.application.services.classification_prompts import (
    PROMPT_VERSION,
    build_classification_user_prompt,
    classification_json_schema,
)
from information_classifier_api.domain.entities.analysis import (
    TERMINAL_STATUSES,
    AnalysisStatus,
)
from information_classifier_api.domain.entities.classification_rule import (
    DEFAULT_RULE_PROMPT,
)
from information_classifier_api.domain.entities.relevance import (
    AnalysisResult,
    ProviderUsage,
    Relevance,
)
from information_classifier_api.domain.exceptions import (
    DomainValidationError,
    InvalidUploadError,
    UnsupportedMediaTypeError,
    UrlBlockedError,
)
from information_classifier_api.domain.services.text_normalizer import (
    extract_title,
    normalize_text_to_markdown,
    strip_html_comments,
)
from information_classifier_api.domain.services.upload_validator import (
    sanitize_filename,
    validate_upload,
)
from information_classifier_api.domain.services.url_policy import (
    UrlPolicy,
    ensure_public_ip,
)
from information_classifier_api.infrastructure.config.settings import Settings
from tests.unit.fakes import make_analysis

POLICY = UrlPolicy.from_ports([80, 443])


def test_relevance_has_exactly_three_public_classes() -> None:
    assert [item.value for item in Relevance] == [
        "Altamente relevante",
        "Relevante",
        "Pouco relevante",
    ]


def test_analysis_result_validates_classification_and_texts() -> None:
    result = AnalysisResult(
        classification="Relevante",
        reason="  A notícia trata de tecnologia.  ",
        summary="  Nova ferramenta.  ",
    )
    assert result.reason == "A notícia trata de tecnologia."
    assert result.summary == "Nova ferramenta."


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {"classification": "Outra", "reason": "ok", "summary": "ok"},
            "classification",
        ),
        ({"classification": "Relevante", "reason": " ", "summary": "ok"}, "reason"),
        ({"classification": "Relevante", "reason": "ok", "summary": " "}, "summary"),
        (
            {
                "classification": "Relevante",
                "reason": "ok",
                "summary": "x" * 281,
            },
            "summary",
        ),
    ],
)
def test_analysis_result_rejects_invalid_payload(
    payload: dict[str, str], field: str
) -> None:
    with pytest.raises(ValidationError, match=field):
        AnalysisResult.model_validate(payload)


def test_analysis_transitions_between_states() -> None:
    analysis = make_analysis()
    started = analysis.start()
    assert started.status == AnalysisStatus.PROCESSING
    assert started.started_at is not None
    completed = started.complete(
        result=AnalysisResult(
            classification="Relevante",
            reason="Tecnologia.",
            summary="Ferramenta nova.",
        ),
        model_name="fake",
        prompt_version=PROMPT_VERSION,
        usage=ProviderUsage(input_tokens=10, output_tokens=5),
        warnings=["aviso"],
    )
    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.classification == "Relevante"
    assert completed.summary == "Ferramenta nova."
    assert completed.completed_at is not None
    assert completed.title == "Notícia"
    assert completed.warnings == ["aviso"]


def test_analysis_fail_marks_terminal_state() -> None:
    failed = make_analysis().fail(error_code="x", error_message="falhou")
    assert failed.status == AnalysisStatus.FAILED
    assert failed.error_code == "x"
    assert failed.error_message == "falhou"
    assert failed.completed_at is not None
    assert failed.status in TERMINAL_STATUSES


def test_normalize_text_to_markdown_cleans_control_chars_and_blank_lines() -> None:
    normalized = normalize_text_to_markdown("  olá\r\n\r\n\r\nmundo\x00  ")
    assert normalized == "olá\n\nmundo"


def test_normalize_text_rejects_empty_text() -> None:
    with pytest.raises(DomainValidationError, match="vazio"):
        normalize_text_to_markdown("   \n ")


def test_extract_title_uses_first_non_empty_line() -> None:
    assert extract_title("\n## Título\n\ncorpo") == "Título"
    assert extract_title("   \n") is None


def test_extract_title_skips_html_comments_from_docling() -> None:
    assert extract_title("<!-- image -->\n\n## Título\n\ncorpo") == "Título"
    assert extract_title("<!-- image -->") is None
    assert strip_html_comments("antes <!-- image --> depois") == "antes   depois"


def test_sanitize_filename_removes_paths_and_control_chars() -> None:
    assert sanitize_filename("../../nota\x00.txt") == "nota.txt"


@pytest.mark.parametrize(
    ("filename", "media_type", "data", "expected"),
    [
        ("nota.txt", "text/plain", b"oi", "text/plain"),
        ("nota.md", "text/markdown", b"# oi", "text/markdown"),
        ("audio.mp3", "audio/mpeg", b"ID3dados", "audio/mpeg"),
        ("audio.wav", "audio/wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav"),
        ("imagem.png", "image/png", b"\x89PNG\r\n\x1a\nresto", "image/png"),
        ("doc.pdf", "application/pdf", b"%PDF-1.7", "application/pdf"),
    ],
)
def test_validate_upload_accepts_supported_signatures(
    filename: str, media_type: str, data: bytes, expected: str
) -> None:
    upload = validate_upload(
        filename=filename, declared_media_type=media_type, data=data
    )
    assert upload.media_type == expected
    assert upload.filename == filename


def test_validate_upload_accepts_docx_ooxml() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<xml/>")
    upload = validate_upload(
        filename="documento.docx",
        declared_media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        data=buffer.getvalue(),
    )
    assert upload.media_type.endswith("wordprocessingml.document")


def test_validate_upload_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="\\.exe"):
        validate_upload(
            filename="virus.exe",
            declared_media_type="application/octet-stream",
            data=b"MZ",
        )


def test_validate_upload_rejects_empty_file_and_mismatched_type() -> None:
    with pytest.raises(InvalidUploadError, match="vazio"):
        validate_upload(filename="nota.txt", declared_media_type="text/plain", data=b"")
    with pytest.raises(UnsupportedMediaTypeError, match="diverge"):
        validate_upload(
            filename="nota.txt",
            declared_media_type="application/pdf",
            data=b"oi",
        )


def test_validate_upload_rejects_nul_bytes_in_text() -> None:
    with pytest.raises(InvalidUploadError, match="NUL"):
        validate_upload(
            filename="nota.txt",
            declared_media_type="text/plain",
            data=b"oi\x00",
        )


def test_url_policy_canonicalizes_public_urls() -> None:
    assert POLICY.validate("HTTPS://Example.com:443/a?b=1#frag") == (
        "https://example.com/a?b=1"
    )
    assert POLICY.validate("http://example.com:80") == "http://example.com/"
    assert POLICY.validate("https://8.8.8.8/x") == "https://8.8.8.8/x"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "http://localhost/x",
        "http://foo.internal/x",
        "http://127.0.0.1/x",
        "http://10.0.0.1/x",
        "http://169.254.169.254/latest/meta-data",
        "http://example.com:8080/x",
        "http://user:pass@example.com/x",
        "",
    ],
)
def test_url_policy_blocks_private_or_invalid_urls(url: str) -> None:
    with pytest.raises(UrlBlockedError):
        POLICY.validate(url)


def test_ensure_public_ip_rejects_non_global_addresses() -> None:
    with pytest.raises(UrlBlockedError, match="não público"):
        ensure_public_ip("host", "192.168.0.1", "http://host/")
    with pytest.raises(UrlBlockedError, match="IP inválido"):
        ensure_public_ip("host", "não-ip")


def test_default_rule_prompt_mentions_three_classes() -> None:
    for label in ("Altamente relevante", "Relevante", "Pouco relevante"):
        assert label in DEFAULT_RULE_PROMPT


def test_classification_prompt_contains_sections_and_correction() -> None:
    prompt = build_classification_user_prompt(
        rule_prompt="Regra X",
        content_markdown="Conteúdo",
        input_type="text",
        media_type=None,
        title="Título",
        source_uri=None,
        correction="Corrija o JSON",
    )
    assert "<regra_global>\nRegra X\n</regra_global>" in prompt
    assert "<material_nao_confiavel>\nConteúdo\n</material_nao_confiavel>" in prompt
    assert "<correcao_obrigatoria>\nCorrija o JSON\n</correcao_obrigatoria>" in prompt


def test_classification_schema_restricts_classes() -> None:
    schema = classification_json_schema()
    assert schema["properties"]["classification"]["enum"] == [
        "Altamente relevante",
        "Relevante",
        "Pouco relevante",
    ]
    assert schema["required"] == ["classification", "reason", "summary"]


def test_settings_default_to_heuristic_and_validate_prefix() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://x")
    assert settings.llm_provider == "heuristic"
    assert settings.api_v1_prefix == "/v1"
    assert settings.allowed_url_ports == [80, 443]


def test_settings_reject_openai_without_credentials() -> None:
    with pytest.raises(ValidationError, match="LLM_MODEL"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x",
            llm_provider="openai",
        )
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x",
            llm_provider="openai",
            llm_model="gpt",
        )


def test_settings_reject_empty_allowed_ports() -> None:
    with pytest.raises(ValidationError, match="allowed_url_ports"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x",
            allowed_url_ports=[],
        )
