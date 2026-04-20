# Description: Tests for LM Integration CRUD (Custom HTTP Delivery).
# Description: Validates /setting/integrations endpoints with mocked responses.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


def _enable_writes(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


def _disable_writes(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestGetIntegrations:
    @respx.mock
    async def test_list_returns_summaries(self, client):
        from lm_mcp.tools.integrations import get_integrations

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [
                        {
                            "id": 1,
                            "name": "LM Slack",
                            "type": "slack-2",
                            "description": "Slack alert channel",
                        },
                        {
                            "id": 3,
                            "name": "Azure Sentinel Pipeline (POC)",
                            "type": "http",
                            "description": "Event Hub",
                        },
                    ],
                },
            )
        )

        result = await get_integrations(client)
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["integrations"]) == 2
        assert data["integrations"][1]["type"] == "http"

    @respx.mock
    async def test_name_and_type_filter_combined(self, client):
        from lm_mcp.tools.integrations import get_integrations

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        await get_integrations(client, name_filter="sentinel", type_filter="http")

        params = route.calls[0].request.url.params
        filter_str = params["filter"]
        assert 'name~"sentinel"' in filter_str
        assert 'type:"http"' in filter_str


class TestGetIntegration:
    @respx.mock
    async def test_returns_full_passthrough(self, client):
        from lm_mcp.tools.integrations import get_integration

        http_shape = {
            "id": 3,
            "name": "Azure Sentinel Pipeline (POC)",
            "type": "http",
            "url": "https://example/ingest",
            "method": "post",
            "enabledStatus": ["active", "ack", "clear", "update"],
            "payload": "{}",
            "payloadFormat": "json",
            "headers": [{"Authorization": "***"}],
        }
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/integrations/3").mock(
            return_value=httpx.Response(200, json=http_shape)
        )

        result = await get_integration(client, integration_id=3)
        data = json.loads(result[0].text)
        # Passthrough: no snake-casing, no field stripping.
        assert data == http_shape

    @respx.mock
    async def test_not_found(self, client):
        from lm_mcp.tools.integrations import get_integration

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/integrations/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Integration not found"})
        )

        result = await get_integration(client, integration_id=999)
        assert "Error:" in result[0].text


class TestCreateHttpIntegration:
    @respx.mock
    async def test_blocked_when_writes_disabled(self, client, monkeypatch):
        _disable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        result = await create_http_integration(
            client,
            name="Test",
            url="https://example/ingest",
        )
        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_posts_minimal_body(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(
                200,
                json={"id": 42, "name": "mcp-test", "type": "http"},
            )
        )

        result = await create_http_integration(
            client,
            name="mcp-test",
            url="https://example/ingest",
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["integration_id"] == 42

        body = json.loads(route.calls[0].request.content)
        assert body["type"] == "http"
        assert body["name"] == "mcp-test"
        assert body["url"] == "https://example/ingest"
        assert body["method"] == "post"
        assert body["payloadFormat"] == "json"
        assert body["enabledStatus"] == ["active", "ack", "clear", "update"]

    @respx.mock
    async def test_headers_dict_form_is_flattened(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"id": 10})
        )

        await create_http_integration(
            client,
            name="h",
            url="https://example/ingest",
            headers={"Authorization": "Bearer X", "Content-Type": "application/json"},
        )

        body = json.loads(route.calls[0].request.content)
        assert body["headers"] == [
            {"Authorization": "Bearer X"},
            {"Content-Type": "application/json"},
        ]

    @respx.mock
    async def test_headers_friendly_list_form_is_converted(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"id": 11})
        )

        await create_http_integration(
            client,
            name="h",
            url="https://example/ingest",
            headers=[
                {"name": "Authorization", "value": "Bearer X"},
                {"name": "Content-Type", "value": "application/json"},
            ],
        )

        body = json.loads(route.calls[0].request.content)
        assert body["headers"] == [
            {"Authorization": "Bearer X"},
            {"Content-Type": "application/json"},
        ]

    @respx.mock
    async def test_default_enabled_lifecycles_inherit_active_url_and_method(
        self, client, monkeypatch
    ):
        """LM rejects a create with any enabled lifecycle missing url+method.

        The LM UI silently copies the active-lifecycle values into each
        enabled lifecycle. Mirror that so callers do not have to repeat
        themselves for the common "same URL for all lifecycles" case.
        """
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"id": 77})
        )

        await create_http_integration(
            client,
            name="inherit",
            url="https://example.com/hook",
            http_method="post",
            alert_body='{"x":1}',
            headers={"X-Test": "inherit"},
        )

        body = json.loads(route.calls[0].request.content)
        for lifecycle in ("ack", "clear", "update"):
            assert body[f"{lifecycle}Url"] == "https://example.com/hook"
            assert body[f"{lifecycle}Method"] == "post"
            assert body[f"{lifecycle}Payload"] == '{"x":1}'
            assert body[f"{lifecycle}PayloadFormat"] == "json"
            assert body[f"{lifecycle}Headers"] == [{"X-Test": "inherit"}]

    @respx.mock
    async def test_explicit_lifecycle_override_is_not_clobbered_by_inherit(
        self, client, monkeypatch
    ):
        """An explicit ack_url takes precedence over the active-default copy."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"id": 78})
        )

        await create_http_integration(
            client,
            name="override-keeps-its-value",
            url="https://example.com/active",
            ack_url="https://example.com/ack-only",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["url"] == "https://example.com/active"
        assert body["ackUrl"] == "https://example.com/ack-only"
        # clear and update inherit from active.
        assert body["clearUrl"] == "https://example.com/active"
        assert body["updateUrl"] == "https://example.com/active"

    @respx.mock
    async def test_disabled_lifecycle_does_not_get_inherited_fields(self, client, monkeypatch):
        """Lifecycles not listed in enabled_lifecycles are left untouched."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"id": 79})
        )

        await create_http_integration(
            client,
            name="active-only",
            url="https://example.com/hook",
            enabled_lifecycles=["active"],
        )

        body = json.loads(route.calls[0].request.content)
        assert body["enabledStatus"] == ["active"]
        for lifecycle in ("ack", "clear", "update"):
            assert f"{lifecycle}Url" not in body
            assert f"{lifecycle}Method" not in body

    @respx.mock
    async def test_lifecycle_overrides_and_extra_fields(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import create_http_integration

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/integrations").mock(
            return_value=httpx.Response(200, json={"id": 55})
        )

        await create_http_integration(
            client,
            name="lifecycle",
            url="https://example/active",
            ack_url="https://example/ack",
            clear_method="put",
            update_body='{"x":"##ALERTID##"}',
            enabled_lifecycles=["active", "ack", "clear", "update", "actionNotes"],
            extra_fields={
                "actionNotesUrl": "https://example/notes",
                "oAuthClientId": "abc",
                "extra": '{"includeIDInHttpResponse":false}',
            },
        )

        body = json.loads(route.calls[0].request.content)
        assert body["ackUrl"] == "https://example/ack"
        assert body["clearMethod"] == "put"
        assert body["updatePayload"] == '{"x":"##ALERTID##"}'
        assert body["enabledStatus"][-1] == "actionNotes"
        # extra_fields merges last
        assert body["actionNotesUrl"] == "https://example/notes"
        assert body["oAuthClientId"] == "abc"
        assert body["extra"] == '{"includeIDInHttpResponse":false}'


class TestUpdateHttpIntegration:
    @respx.mock
    async def test_blocked_when_writes_disabled(self, client, monkeypatch):
        _disable_writes(monkeypatch)
        from lm_mcp.tools.integrations import update_http_integration

        result = await update_http_integration(client, integration_id=3, description="x")
        assert "Error:" in result[0].text

    @respx.mock
    async def test_empty_body_rejected(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import update_http_integration

        result = await update_http_integration(client, integration_id=3)
        assert "Error:" in result[0].text
        assert "No fields provided to update" in result[0].text

    @respx.mock
    async def test_patch_sends_only_provided_fields(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import update_http_integration

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/integrations/3"
        ).mock(return_value=httpx.Response(200, json={"id": 3}))

        await update_http_integration(
            client,
            integration_id=3,
            description="new description",
            ack_url="https://example/ack-new",
        )

        body = json.loads(route.calls[0].request.content)
        assert body == {
            "description": "new description",
            "ackUrl": "https://example/ack-new",
        }


class TestDeleteIntegration:
    @respx.mock
    async def test_blocked_when_writes_disabled(self, client, monkeypatch):
        _disable_writes(monkeypatch)
        from lm_mcp.tools.integrations import delete_integration

        result = await delete_integration(client, integration_id=3)
        assert "Error:" in result[0].text

    @respx.mock
    async def test_deletes_by_id(self, client, monkeypatch):
        _enable_writes(monkeypatch)
        from lm_mcp.tools.integrations import delete_integration

        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/integrations/3").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_integration(client, integration_id=3)
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestIntegrationToolRegistration:
    def test_tools_are_registered(self):
        from lm_mcp.registry import TOOLS

        names = {t.name for t in TOOLS}
        assert {
            "get_integrations",
            "get_integration",
            "create_http_integration",
            "update_http_integration",
            "delete_integration",
        } <= names

    def test_handlers_are_wired(self):
        from lm_mcp.registry import get_tool_handler

        for name in [
            "get_integrations",
            "get_integration",
            "create_http_integration",
            "update_http_integration",
            "delete_integration",
        ]:
            assert get_tool_handler(name) is not None
