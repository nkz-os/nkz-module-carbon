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


@pytest.mark.parametrize("action", ["deactivate", "teardown"])
def test_deactivate_and_teardown_release(client, monkeypatch, action):
    rel = AsyncMock()
    run = AsyncMock()
    monkeypatch.setattr(internal, "release_continuous", rel)
    monkeypatch.setattr(internal, "run_campaign", run)
    r = _setup(client, action)
    assert r.status_code == 200 and r.json()["status"] == action
    rel.assert_awaited_once_with("acme", URN)
    run.assert_not_awaited()


def test_vegetation_down_does_not_change_setup_response(client, monkeypatch):
    monkeypatch.setattr(internal, "run_campaign", AsyncMock())
    monkeypatch.setenv("VEGETATION_INTERNAL_URL", "http://127.0.0.1:1")
    assert _setup(client, "activate").json()["scheduled"] is True
    assert _setup(client, "deactivate").json()["status"] == "deactivate"


def test_recalculate_open_requests_continuous_even_if_campaign_fails(client, monkeypatch):
    monkeypatch.setattr(api, "INTERNAL_SERVICE_SECRET", "s3")
    monkeypatch.setattr(api, "list_tenants_with_module", AsyncMock(return_value=["acme"]))
    monkeypatch.setattr(api, "list_parcel_ids", AsyncMock(return_value=["p1", "p2"]))
    monkeypatch.setattr(api, "run_campaign", AsyncMock(side_effect=RuntimeError("x")))
    req = AsyncMock()
    monkeypatch.setattr(api, "request_continuous", req)
    r = client.post("/api/carbon/internal/campaigns/recalculate-open", headers={"X-Internal-Service-Secret": "s3"})
    assert r.status_code == 200 and r.json()["failed"] == 2
    assert sorted(c.args for c in req.await_args_list) == [
        ("acme", canonical_parcel_urn("p1")), ("acme", canonical_parcel_urn("p2"))]


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
