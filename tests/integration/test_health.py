from information_classifier_api.adapters.api.deps import get_readiness_checker


class FakeReadinessChecker:
    def __init__(self, failures: list[str] | None = None) -> None:
        self.failures = failures or []

    async def check(self, _session: object) -> list[str]:
        return self.failures


async def test_health_live_returns_ok(client) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready_returns_ready(app, client) -> None:
    app.dependency_overrides[get_readiness_checker] = lambda: FakeReadinessChecker()
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "failed": []}


async def test_health_ready_reports_failed_dependencies(app, client) -> None:
    app.dependency_overrides[get_readiness_checker] = lambda: FakeReadinessChecker(
        ["redis"]
    )
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "not_ready",
        "failed": ["redis"],
    }
