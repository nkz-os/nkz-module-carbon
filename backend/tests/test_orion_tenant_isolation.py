"""Orion writes must never land in another tenant's namespace.

The wrapper held one process-wide SDK client and rebound its tenant_id on every
call. Between two awaits the event loop can run another request, so the client's
tenant no longer matches the caller that set it. upsert_entity's 409 branch is the
concrete case: it awaits create_entity, and on conflict awaits update_entity_attrs
with whatever tenant_id was rebound in the meantime.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.common import orion as orion_mod


@pytest.fixture(autouse=True)
def _reset():
    asyncio.get_event_loop_policy()
    orion_mod._clients.clear()
    orion_mod._initialized = False
    yield
    orion_mod._clients.clear()
    orion_mod._initialized = False


def _conflict():
    resp = MagicMock()
    resp.status_code = 409
    return httpx.HTTPStatusError("conflict", request=MagicMock(), response=resp)


class TestPerTenantClients:
    def test_each_tenant_gets_its_own_client(self):
        orion_mod.init_orion_client()
        with patch.object(orion_mod, "SDKOrionClient", side_effect=lambda **kw: MagicMock(**kw)):
            a = orion_mod._client_for("tenant-a")
            b = orion_mod._client_for("tenant-b")
        assert a is not b

    def test_same_tenant_reuses_its_client(self):
        orion_mod.init_orion_client()
        with patch.object(orion_mod, "SDKOrionClient", side_effect=lambda **kw: MagicMock(**kw)):
            assert orion_mod._client_for("tenant-a") is orion_mod._client_for("tenant-a")

    def test_client_tenant_is_never_rebound(self):
        orion_mod.init_orion_client()
        with patch.object(orion_mod, "SDKOrionClient", side_effect=lambda **kw: MagicMock(**kw)):
            c = orion_mod._client_for("tenant-a")
            before = c.tenant_id
            orion_mod._client_for("tenant-b")
        assert c.tenant_id == before == "tenant-a"

    def test_requires_initialization(self):
        with pytest.raises(RuntimeError):
            orion_mod.get_orion_client()


class TestUpsertConflictPath:
    @pytest.mark.asyncio
    async def test_conflict_updates_on_the_same_tenant(self):
        """The 409 retry must target the tenant that issued the write."""
        orion_mod.init_orion_client()
        made = {}

        def _factory(**kw):
            c = MagicMock()
            c.tenant_id = kw["tenant_id"]
            c.create_entity = AsyncMock(side_effect=_conflict())
            c.update_entity_attrs = AsyncMock()
            made[kw["tenant_id"]] = c
            return c

        with patch.object(orion_mod, "SDKOrionClient", side_effect=_factory):
            w = orion_mod.get_orion_client()
            await w.upsert_entity({"id": "urn:ngsi-ld:X:1", "type": "X"}, "tenant-a")

        made["tenant-a"].update_entity_attrs.assert_awaited_once()
        assert "tenant-b" not in made

    @pytest.mark.asyncio
    async def test_interleaved_tenants_do_not_cross(self):
        """Two concurrent upserts, both hitting 409, must stay in their namespace."""
        orion_mod.init_orion_client()
        made = {}
        updates = []

        def _factory(**kw):
            tid = kw["tenant_id"]
            c = MagicMock()
            c.tenant_id = tid

            async def _create(_entity):
                await asyncio.sleep(0)  # hand the loop to the other request
                raise _conflict()

            async def _update(entity_id, _attrs):
                await asyncio.sleep(0)
                updates.append((c.tenant_id, entity_id))

            c.create_entity = _create
            c.update_entity_attrs = _update
            made[tid] = c
            return c

        with patch.object(orion_mod, "SDKOrionClient", side_effect=_factory):
            w = orion_mod.get_orion_client()
            await asyncio.gather(
                w.upsert_entity({"id": "urn:ngsi-ld:X:a", "type": "X"}, "tenant-a"),
                w.upsert_entity({"id": "urn:ngsi-ld:X:b", "type": "X"}, "tenant-b"),
            )

        assert sorted(updates) == [("tenant-a", "urn:ngsi-ld:X:a"), ("tenant-b", "urn:ngsi-ld:X:b")]

    @pytest.mark.asyncio
    async def test_non_conflict_errors_propagate(self):
        orion_mod.init_orion_client()

        def _factory(**kw):
            c = MagicMock()
            c.tenant_id = kw["tenant_id"]
            c.create_entity = AsyncMock(side_effect=RuntimeError("orion down"))
            return c

        with (
            patch.object(orion_mod, "SDKOrionClient", side_effect=_factory),
            pytest.raises(RuntimeError),
        ):
            await orion_mod.get_orion_client().upsert_entity({"id": "x", "type": "X"}, "t")


class TestGetEntityFailSafe:
    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        orion_mod.init_orion_client()
        resp = MagicMock()
        resp.status_code = 404
        err = httpx.HTTPStatusError("nf", request=MagicMock(), response=resp)

        def _factory(**kw):
            c = MagicMock()
            c.get_entity = AsyncMock(side_effect=err)
            return c

        with patch.object(orion_mod, "SDKOrionClient", side_effect=_factory):
            assert await orion_mod.get_orion_client().get_entity("urn:x", "t") is None

    @pytest.mark.asyncio
    async def test_other_errors_are_not_swallowed(self):
        """Reporting 'entity absent' when Orion is unreachable is a false zero."""
        orion_mod.init_orion_client()

        def _factory(**kw):
            c = MagicMock()
            c.get_entity = AsyncMock(side_effect=httpx.ConnectError("refused"))
            return c

        with (
            patch.object(orion_mod, "SDKOrionClient", side_effect=_factory),
            pytest.raises(httpx.ConnectError),
        ):
            await orion_mod.get_orion_client().get_entity("urn:x", "t")


class TestShutdown:
    @pytest.mark.asyncio
    async def test_close_closes_every_tenant_client(self):
        orion_mod.init_orion_client()
        closed = []

        def _factory(**kw):
            c = MagicMock()
            c.close = AsyncMock(side_effect=lambda: closed.append(kw["tenant_id"]))
            return c

        with patch.object(orion_mod, "SDKOrionClient", side_effect=_factory):
            orion_mod._client_for("tenant-a")
            orion_mod._client_for("tenant-b")
            await orion_mod.close_orion_client()

        assert sorted(closed) == ["tenant-a", "tenant-b"]
        assert orion_mod._clients == {}
