from uuid import UUID

from information_classifier_api.application.orchestrators.analysis_orchestrator import (
    AnalysisOrchestrator,
)
from information_classifier_api.domain.exceptions import ExtractionError
from information_classifier_api.infrastructure.config.settings import get_settings
from information_classifier_api.infrastructure.database.repositories import (
    SqlAlchemyAnalysisRepository,
)
from information_classifier_api.infrastructure.web.url_validator import DnsUrlValidator
from information_classifier_api.infrastructure.wiring import (
    build_object_storage,
    build_processing_limits,
)
from tests.unit.fakes import (
    FakeDocumentConverter,
    FakeRelevanceProvider,
    FakeWebPageFetcher,
)


async def _submit_text(client, text: str = "Notícia de tecnologia.") -> dict:
    response = await client.post("/v1/analyses", data={"text": text})
    assert response.status_code == 202
    return response.json()


async def test_submit_text_returns_accepted_and_dispatches(client, dispatcher) -> None:
    body = await _submit_text(client, "# Título\n\nNotícia de tecnologia.")
    analysis_id = UUID(body["analysis_id"])
    assert body["status"] == "queued"
    assert body["status_url"] == f"/v1/analyses/{analysis_id}"
    assert dispatcher.analyses == [analysis_id]

    detail = await client.get(body["status_url"])
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["input_type"] == "text"
    assert payload["status"] == "queued"
    assert payload["title"] == "Título"
    assert payload["classification"] is None


async def test_submit_file_returns_source_metadata(client) -> None:
    response = await client.post(
        "/v1/analyses",
        files={"file": ("nota.txt", b"conteudo de tecnologia", "text/plain")},
    )
    assert response.status_code == 202
    detail = await client.get(response.json()["status_url"])
    payload = detail.json()
    assert payload["input_type"] == "file"
    assert payload["source"] == {
        "url": None,
        "filename": "nota.txt",
        "media_type": "text/plain",
    }


async def test_submit_url_stores_canonical_url(client, monkeypatch) -> None:
    async def fake_validate(self: DnsUrlValidator, url: str) -> str:
        return "https://example.com/noticia"

    monkeypatch.setattr(DnsUrlValidator, "validate", fake_validate)
    response = await client.post(
        "/v1/analyses", data={"url": "HTTPS://EXAMPLE.COM/noticia#x"}
    )
    assert response.status_code == 202
    detail = await client.get(response.json()["status_url"])
    assert detail.json()["source"]["url"] == "https://example.com/noticia"


async def test_submit_requires_exactly_one_source(client) -> None:
    missing = await client.post("/v1/analyses")
    assert missing.status_code == 400
    assert "exatamente uma origem" in missing.json()["detail"]

    duplicated = await client.post(
        "/v1/analyses",
        data={"text": "texto", "url": "https://example.com/"},
    )
    assert duplicated.status_code == 400
    assert "exatamente uma origem" in duplicated.json()["detail"]


async def test_submit_rejects_unsupported_file(client) -> None:
    response = await client.post(
        "/v1/analyses",
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert ".exe" in response.json()["detail"]


async def test_get_unknown_analysis_returns_404(client) -> None:
    response = await client.get(f"/v1/analyses/{UUID(int=0)}")
    assert response.status_code == 404


async def test_rule_get_and_put_roundtrip(client) -> None:
    initial = await client.get("/v1/rule")
    assert initial.status_code == 200
    assert "Altamente relevante" in initial.json()["prompt"]
    assert initial.json()["updated_at"] is not None

    updated = await client.put("/v1/rule", json={"prompt": "  Nova regra  "})
    assert updated.status_code == 200
    assert updated.json()["prompt"] == "Nova regra"

    fetched = await client.get("/v1/rule")
    assert fetched.json()["prompt"] == "Nova regra"

    blank = await client.put("/v1/rule", json={"prompt": "   "})
    assert blank.status_code == 400
    empty = await client.put("/v1/rule", json={"prompt": ""})
    assert empty.status_code == 422


async def test_new_analysis_snapshots_current_rule(client, session) -> None:
    await client.put("/v1/rule", json={"prompt": "Regra vigente"})
    body = await _submit_text(client)
    stored = await SqlAlchemyAnalysisRepository(session).get_by_id(
        UUID(body["analysis_id"])
    )
    assert stored is not None
    assert stored.rule_prompt == "Regra vigente"


async def test_orchestrator_persists_completed_analysis(client, session) -> None:
    body = await _submit_text(client, "# Notícia\n\nTecnologia e inovação.")
    analysis_id = UUID(body["analysis_id"])
    settings = get_settings()
    orchestrator = AnalysisOrchestrator(
        analyses=SqlAlchemyAnalysisRepository(session),
        storage=build_object_storage(settings),
        converter=FakeDocumentConverter(),
        fetcher=FakeWebPageFetcher(),
        provider=FakeRelevanceProvider(),
        limits=build_processing_limits(settings),
    )
    completed = await orchestrator.process(analysis_id)
    await session.commit()
    assert completed.status == "completed"

    detail = await client.get(body["status_url"])
    payload = detail.json()
    assert payload["status"] == "completed"
    assert payload["classification"] == "Relevante"
    assert payload["reason"] == "A notícia trata de tecnologia."
    assert payload["summary"] == "Nova ferramenta de tecnologia."
    assert payload["model_name"] == "fake-model"
    assert payload["completed_at"] is not None


async def test_orchestrator_persists_permanent_failure(
    client, session, monkeypatch
) -> None:
    async def fake_validate(self: DnsUrlValidator, url: str) -> str:
        return "https://example.com/noticia"

    monkeypatch.setattr(DnsUrlValidator, "validate", fake_validate)
    response = await client.post(
        "/v1/analyses", data={"url": "https://example.com/noticia"}
    )
    analysis_id = UUID(response.json()["analysis_id"])
    settings = get_settings()
    orchestrator = AnalysisOrchestrator(
        analyses=SqlAlchemyAnalysisRepository(session),
        storage=build_object_storage(settings),
        converter=FakeDocumentConverter(),
        fetcher=FakeWebPageFetcher(error=ExtractionError("HTML inválido")),
        provider=FakeRelevanceProvider(),
        limits=build_processing_limits(settings),
    )
    await orchestrator.process(analysis_id)
    await session.commit()

    detail = await client.get(response.json()["status_url"])
    payload = detail.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "extraction_failed"
    assert "HTML inválido" in payload["error"]["message"]
