import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import campaigns as api
from app.api import internal
from app.jobs import request_continuous_monitoring as job
from app.platform import vegetation_client as veg
from app.platform.crop_client import canonical_parcel_urn

URN = "urn:ngsi-ld:AgriParcel:p1"
BASE = "http://vegetation.test"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("VEGETATION_INTERNAL_URL", BASE)
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3")


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_request_posts_tenant_module_and_secret():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(204)

    assert await veg.request_continuous("acme", URN, client=_client(handler)) is True
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}/api/internal/vegetation/parcels/{URN}/continuous"
    assert req.headers["X-Internal-Service-Secret"] == "s3"
    assert json.loads(req.content) == {"tenant_id": "acme", "module_id": "carbon"}


@pytest.mark.asyncio
async def test_release_sends_delete_with_params():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(204)

    assert await veg.release_continuous("acme", URN, client=_client(handler)) is True
    req = seen[0]
    assert req.method == "DELETE"
    assert req.url.params["tenant_id"] == "acme" and req.url.params["module_id"] == "carbon"
    assert req.headers["X-Internal-Service-Secret"] == "s3"


@pytest.mark.asyncio
async def test_empty_url_makes_no_call(monkeypatch):
    monkeypatch.setenv("VEGETATION_INTERNAL_URL", "")
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(204)

    assert await veg.request_continuous("acme", URN, client=_client(handler)) is False
    assert await veg.release_continuous("acme", URN, client=_client(handler)) is False
    assert calls == []


@pytest.mark.asyncio
async def test_failures_never_raise_and_are_logged(caplog):
    def boom(req):
        raise httpx.ConnectError("down")

    with caplog.at_level(logging.WARNING):
        assert await veg.request_continuous("acme", URN, client=_client(boom)) is False
        assert await veg.release_continuous("acme", URN, client=_client(lambda r: httpx.Response(500))) is False
    assert "acme" in caplog.text and URN in caplog.text


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(internal.router)
    return TestClient(app)


def _setup(client, action):
    body = {"parcel_id": "urn:ngsi-ld:AgriParcel:p1", "tenant_id": "acme", "action": action}
    return client.post("/api/carbon/internal/setup-parcel", json=body, headers={"X-Internal-Service-Secret": "s3"})


def test_activate_requests_continuous_then_runs_campaign(client, monkeypatch):
    order = []
    req = AsyncMock(side_effect=lambda *a, **k: order.append("request"))
    run = AsyncMock(side_effect=lambda *a, **k: order.append("run"))
    monkeypatch.setattr(internal, "request_continuous", req)
    monkeypatch.setattr(internal, "run_campaign", run)
    r = _setup(client, "activate")
    assert r.status_code == 200 and r.json()["scheduled"] is True
    req.assert_awaited_once_with("acme", URN)
    assert order == ["request", "run"]


def test_teardown_releases_and_deactivate_does_not(client, monkeypatch):
    rel = AsyncMock()
    run = AsyncMock()
    monkeypatch.setattr(internal, "release_continuous", rel)
    monkeypatch.setattr(internal, "run_campaign", run)
    r = _setup(client, "deactivate")
    assert r.status_code == 200 and r.json()["status"] == "deactivate"
    rel.assert_not_awaited()
    r = _setup(client, "teardown")
    assert r.status_code == 200 and r.json()["status"] == "teardown"
    rel.assert_awaited_once_with("acme", URN)
    run.assert_not_awaited()


def test_campaign_runs_even_when_the_request_fails(client, monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr(internal, "request_continuous", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "run_campaign", run)
    assert _setup(client, "activate").json()["scheduled"] is True  # TestClient runs the background task
    run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 422])
async def test_rejections_are_false_and_warn(status, caplog):
    with caplog.at_level(logging.WARNING):
        assert await veg.request_continuous("acme", URN, client=_client(lambda r: httpx.Response(status))) is False
    assert "acme" in caplog.text


def test_vegetation_down_does_not_change_setup_response(client, monkeypatch):
    monkeypatch.setattr(internal, "run_campaign", AsyncMock())
    monkeypatch.setenv("VEGETATION_INTERNAL_URL", "http://127.0.0.1:1")
    assert _setup(client, "activate").json()["scheduled"] is True
    assert _setup(client, "deactivate").json()["status"] == "deactivate"


def test_recalculate_open_requests_continuity_after_the_sweep(client, monkeypatch):
    order = []
    monkeypatch.setattr(api, "INTERNAL_SERVICE_SECRET", "s3")
    monkeypatch.setattr(api, "list_tenants_with_module", AsyncMock(return_value=["acme"]))
    monkeypatch.setattr(api, "list_parcel_ids", AsyncMock(return_value=["p1", "p2"]))

    async def run(*a, **k):
        order.append("run")
        raise RuntimeError("x")

    async def batch(pairs, **k):
        order.append("batch")
        order.append(sorted(pairs))

    monkeypatch.setattr(api, "run_campaign", run)
    monkeypatch.setattr(api, "request_continuous_batch", batch)
    r = client.post("/api/carbon/internal/campaigns/recalculate-open", headers={"X-Internal-Service-Secret": "s3"})
    assert r.status_code == 200 and r.json()["failed"] == 2
    assert order == ["run", "run", "batch", [("acme", canonical_parcel_urn("p1")), ("acme", canonical_parcel_urn("p2"))]]


@pytest.mark.asyncio
async def test_batch_circuit_breaker_stops_after_first_transport_error(caplog):
    calls = []

    def down(req):
        calls.append(req)
        raise httpx.ConnectTimeout("slow")

    pairs = [("acme", f"urn:ngsi-ld:AgriParcel:p{i}") for i in range(30)]
    with caplog.at_level(logging.WARNING):
        done = await veg.request_continuous_batch(pairs, concurrency=5, client=_client(down))
    assert len(calls) <= 5 and done == 0
    assert caplog.text.count("circuit open") == 1 and "acme" in caplog.text


@pytest.mark.asyncio
async def test_batch_counts_successes_and_empty_url_skips(monkeypatch):
    pairs = [("acme", f"urn:ngsi-ld:AgriParcel:p{i}") for i in range(7)]
    assert await veg.request_continuous_batch(pairs, client=_client(lambda r: httpx.Response(204))) == 7
    monkeypatch.setenv("VEGETATION_INTERNAL_URL", "")
    assert await veg.request_continuous_batch(pairs, client=_client(lambda r: httpx.Response(204))) == 0


@pytest.mark.asyncio
async def test_list_carbon_parcels_reads_every_key_form(monkeypatch):
    def e(key, form, urn):
        return {"id": "x", "type": "CarbonAssessment", key: {"type": "Relationship", form: urn}}

    page1 = [e("hasAgriParcel", "object", "urn:ngsi-ld:AgriParcel:a")] * 50 + [
        e("refAgriParcel", "object", "urn:ngsi-ld:AgriParcel:b")] * 50
    page2 = [
        e("https://nkz-os.org/ns/hasAgriParcel", "value", "urn:ngsi-ld:AgriParcel:c"),
        e("https://uri.etsi.org/ngsi-ld/default-context/hasAgriParcel", "object", "urn:ngsi-ld:AgriParcel:a"),
        {"id": "y", "hasAgriParcel": "urn:ngsi-ld:AgriParcel:d"},
        {"id": "z"},
    ]
    orion = type("O", (), {})()
    orion.query_entities = AsyncMock(side_effect=[page1, page2])
    monkeypatch.setattr(job, "get_orion_client", lambda: orion)
    assert await job.list_carbon_parcels("acme") == [
        "urn:ngsi-ld:AgriParcel:a", "urn:ngsi-ld:AgriParcel:b",
        "urn:ngsi-ld:AgriParcel:c", "urn:ngsi-ld:AgriParcel:d"]


@pytest.mark.asyncio
async def test_cli_without_apply_lists_and_never_calls(monkeypatch, capsys):
    monkeypatch.setattr(job, "list_carbon_parcels", AsyncMock(return_value=[URN]))
    req = AsyncMock()
    monkeypatch.setattr(job, "request_continuous", req)
    monkeypatch.setattr(job, "list_tenants_with_module", AsyncMock(return_value=["acme"]))
    assert await job.run(["--tenant", "acme"]) == 0
    assert capsys.readouterr().out.split() == ["acme", URN]
    req.assert_not_awaited()


@pytest.mark.asyncio
async def test_cli_apply_calls_and_prints_result(monkeypatch, capsys):
    monkeypatch.setattr(job, "list_carbon_parcels", AsyncMock(return_value=[URN]))
    req = AsyncMock(return_value=True)
    monkeypatch.setattr(job, "request_continuous", req)
    assert await job.run(["--tenant", "acme", "--apply"]) == 0
    req.assert_awaited_once_with("acme", URN)
    assert capsys.readouterr().out.split() == ["acme", URN, "ok"]


@pytest.mark.asyncio
async def test_cli_main_initializes_and_closes_the_orion_client(monkeypatch):
    """Run outside the API, the one-off command must set up the Orion client itself."""
    from app.jobs import request_continuous_monitoring as cli

    calls = []
    monkeypatch.setattr(cli, "init_orion_client", lambda: calls.append("init"))

    async def fake_close_orion():
        calls.append("close_orion")

    async def fake_close_pool():
        calls.append("close_pool")

    async def fake_run(argv=None):
        assert calls == ["init"]
        return 0

    monkeypatch.setattr(cli, "close_orion_client", fake_close_orion)
    monkeypatch.setattr(cli, "close_pool", fake_close_pool)
    monkeypatch.setattr(cli, "run", fake_run)
    assert await cli._main() == 0
    assert calls == ["init", "close_orion", "close_pool"]
