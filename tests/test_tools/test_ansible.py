# Description: Tests for Ansible Automation Platform tool handlers.
# Description: Validates job management, inventory queries, and write permission enforcement.

import json

import httpx
import pytest
import respx

from lm_mcp.client.awx import AwxClient

BASE = "https://controller.example.com"
API = f"{BASE}/api/v2"


@pytest.fixture
def awx_client():
    """Create an AwxClient instance for testing."""
    return AwxClient(
        base_url=BASE,
        token="test-token",
    )


def _reload_config(monkeypatch, *, writes_enabled: bool = False):
    """Set LM env vars and reload config to pick up changes."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-12345")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", str(writes_enabled).lower())
    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


# -- Jinja2 validation --------------------------------------------------------


class TestValidateExtraVars:
    """Tests for Jinja2 injection validation."""

    def test_rejects_double_brace(self):
        from lm_mcp.tools.ansible import validate_extra_vars

        with pytest.raises(ValueError, match="Jinja2"):
            validate_extra_vars({"host": "{{ malicious }}"})

    def test_rejects_block_tag(self):
        from lm_mcp.tools.ansible import validate_extra_vars

        with pytest.raises(ValueError, match="Jinja2"):
            validate_extra_vars({"cmd": "{% if True %}rm -rf{% endif %}"})

    def test_rejects_comment_tag(self):
        from lm_mcp.tools.ansible import validate_extra_vars

        with pytest.raises(ValueError, match="Jinja2"):
            validate_extra_vars({"note": "{# hidden #}"})

    def test_allows_plain_values(self):
        from lm_mcp.tools.ansible import validate_extra_vars

        # Should not raise
        validate_extra_vars({"host": "server01", "port": "8080"})

    def test_allows_non_string_values(self):
        from lm_mcp.tools.ansible import validate_extra_vars

        # Non-string values are not checked
        validate_extra_vars({"count": 5, "enabled": True, "host": "ok"})


# -- Connection test -----------------------------------------------------------


class TestAwxConnection:
    """Tests for test_awx_connection tool."""

    @respx.mock
    async def test_returns_version_info(self, awx_client):
        from lm_mcp.tools.ansible import test_awx_connection

        respx.get(f"{BASE}/api/v2/ping/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ha": False,
                    "version": "4.5.0",
                    "active_node": "controller01",
                },
            )
        )

        result = await test_awx_connection(awx_client)
        data = json.loads(result[0].text)
        assert data["connected"] is True
        assert data["version"] == "4.5.0"

    @respx.mock
    async def test_handles_connection_failure(self, awx_client):
        from lm_mcp.tools.ansible import test_awx_connection

        respx.get(f"{BASE}/api/v2/ping/").mock(side_effect=httpx.ConnectError("Connection refused"))

        result = await test_awx_connection(awx_client)
        assert "Error" in result[0].text


# -- Job template tools --------------------------------------------------------


class TestGetJobTemplates:
    """Tests for get_job_templates tool."""

    @respx.mock
    async def test_returns_template_list(self, awx_client):
        from lm_mcp.tools.ansible import get_job_templates

        respx.get(f"{BASE}/api/v2/job_templates/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 2,
                    "results": [
                        {"id": 1, "name": "lm-remediate-disk-cleanup", "description": "Clean disk"},
                        {"id": 2, "name": "lm-remediate-service-restart"},
                    ],
                },
            )
        )

        result = await get_job_templates(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert len(data["templates"]) == 2
        assert data["templates"][0]["name"] == "lm-remediate-disk-cleanup"

    @respx.mock
    async def test_passes_name_filter(self, awx_client):
        from lm_mcp.tools.ansible import get_job_templates

        route = respx.get(f"{BASE}/api/v2/job_templates/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        await get_job_templates(awx_client, name_filter="disk")
        params = dict(route.calls[0].request.url.params)
        assert "search" in params
        assert params["search"] == "disk"

    @respx.mock
    async def test_passes_project_id(self, awx_client):
        from lm_mcp.tools.ansible import get_job_templates

        route = respx.get(f"{BASE}/api/v2/job_templates/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        await get_job_templates(awx_client, project_id=7)
        params = dict(route.calls[0].request.url.params)
        assert params["project"] == "7"


class TestGetJobTemplate:
    """Tests for get_job_template tool."""

    @respx.mock
    async def test_returns_template_details(self, awx_client):
        from lm_mcp.tools.ansible import get_job_template

        respx.get(f"{BASE}/api/v2/job_templates/42/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 42,
                    "name": "lm-remediate-disk-cleanup",
                    "description": "Clean up disk space",
                    "survey_enabled": True,
                    "ask_variables_on_launch": True,
                },
            )
        )

        result = await get_job_template(awx_client, template_id=42)
        data = json.loads(result[0].text)
        assert data["id"] == 42
        assert data["name"] == "lm-remediate-disk-cleanup"


# -- Job execution tools -------------------------------------------------------


class TestLaunchJob:
    """Tests for launch_job tool (write operation)."""

    async def test_blocked_without_write_permission(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=False)
        from lm_mcp.tools.ansible import launch_job

        result = await launch_job(awx_client, template_id=42)
        assert "Write operations are disabled" in result[0].text

    async def test_rejects_jinja2_in_extra_vars(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        result = await launch_job(
            awx_client,
            template_id=42,
            extra_vars={"target": "{{ malicious }}"},
        )
        assert "Jinja2" in result[0].text

    @respx.mock
    async def test_returns_job_id(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        respx.post(f"{BASE}/api/v2/job_templates/42/launch/").mock(
            return_value=httpx.Response(201, json={"job": 99, "status": "pending"})
        )

        result = await launch_job(awx_client, template_id=42)
        data = json.loads(result[0].text)
        assert data["job_id"] == 99
        assert data["status"] == "pending"

    @respx.mock
    async def test_sends_extra_vars(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        route = respx.post(f"{BASE}/api/v2/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json={"job": 50, "status": "pending"})
        )

        await launch_job(
            awx_client,
            template_id=10,
            extra_vars={"target_host": "server01", "threshold_pct": "90"},
        )

        body = json.loads(route.calls[0].request.content)
        assert body["extra_vars"]["target_host"] == "server01"

    @respx.mock
    async def test_check_mode(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        route = respx.post(f"{BASE}/api/v2/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json={"job": 51, "status": "pending"})
        )

        await launch_job(awx_client, template_id=10, check_mode=True)

        body = json.loads(route.calls[0].request.content)
        assert body["diff_mode"] is True
        assert body["job_type"] == "check"

    @respx.mock
    async def test_normal_mode_omits_check_fields(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        route = respx.post(f"{BASE}/api/v2/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json={"job": 52, "status": "pending"})
        )

        await launch_job(
            awx_client,
            template_id=10,
            extra_vars={"host": "server01"},
        )

        body = json.loads(route.calls[0].request.content)
        assert "diff_mode" not in body
        assert "job_type" not in body


def _launch_response(job_id: int, ignored_fields: dict | None, job_type: str = "run") -> dict:
    """A job template launch response, synthetic: the AWX controller was unreachable.

    Shape from the AWX source, JobTemplateLaunch.post in
    https://github.com/ansible/awx/blob/devel/awx/api/views/__init__.py: `job`, then
    `ignored_fields` (each prompt the template rejected, mapped to the value sent),
    then the JobSerializer fields. ignored_fields=None leaves the key out, as an
    older controller does.
    """
    data: dict = {"job": job_id}
    if ignored_fields is not None:
        data["ignored_fields"] = ignored_fields
    data.update({"id": job_id, "type": "job", "status": "pending", "job_type": job_type})
    return data


class TestLaunchJobIgnoredFields:
    """R5: a prompt the template ignores on launch is reported, never hidden."""

    @respx.mock
    async def test_ignored_check_mode_cancels_the_job_and_errors(self, awx_client, monkeypatch):
        """job_type ignored under check_mode: the job is cancelled; the error names the setting."""
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools import is_error_result
        from lm_mcp.tools.ansible import launch_job

        respx.post(f"{API}/job_templates/10/launch/").mock(
            return_value=httpx.Response(
                201, json=_launch_response(71, {"job_type": "check", "diff_mode": True})
            )
        )
        cancel = respx.post(f"{API}/jobs/71/cancel/").mock(return_value=httpx.Response(202))

        result = await launch_job(awx_client, template_id=10, check_mode=True)

        assert cancel.call_count == 1
        assert is_error_result(result)
        text = result[0].text
        assert "ask_job_type_on_launch" in text
        assert "71" in text
        assert "cancelled" in text

    @respx.mock
    async def test_ignored_check_mode_with_failed_cancel_says_the_job_may_run(
        self, awx_client, monkeypatch, caplog
    ):
        """A cancel that fails still errors, says the job may be running, and logs the failure."""
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools import is_error_result
        from lm_mcp.tools.ansible import launch_job

        respx.post(f"{API}/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json=_launch_response(72, {"job_type": "check"}))
        )
        respx.post(f"{API}/jobs/72/cancel/").mock(
            return_value=httpx.Response(405, json={"error": "not allowed"})
        )

        with caplog.at_level("WARNING", logger="lm_mcp.tools.ansible"):
            result = await launch_job(awx_client, template_id=10, check_mode=True)

        assert is_error_result(result)
        text = result[0].text
        assert "72" in text
        assert "could not be cancelled" in text
        records = [r for r in caplog.records if r.name == "lm_mcp.tools.ansible"]
        assert len(records) == 1
        assert records[0].levelname == "WARNING"
        assert "72" in records[0].getMessage()
        assert records[0].exc_info is not None

    @respx.mock
    async def test_empty_ignored_fields_returns_the_job(self, awx_client, monkeypatch):
        """ignored_fields {} under check_mode returns the job with no warnings and no cancel."""
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        respx.post(f"{API}/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json=_launch_response(73, {}, job_type="check"))
        )
        cancel = respx.post(f"{API}/jobs/73/cancel/").mock(return_value=httpx.Response(202))

        result = await launch_job(awx_client, template_id=10, check_mode=True)

        data = json.loads(result[0].text)
        assert data == {"job_id": 73, "status": "pending"}
        assert cancel.call_count == 0

    @pytest.mark.parametrize("field", ["limit", "extra_vars"])
    @respx.mock
    async def test_other_ignored_field_warns_and_returns_the_job(
        self, awx_client, monkeypatch, field
    ):
        """An ignored limit or extra_vars returns the job with a warning naming the field."""
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        sent = {"limit": "web01"} if field == "limit" else {"extra_vars": {"host": "web01"}}
        ignored = {"limit": "web01"} if field == "limit" else {"extra_vars": {"host": "web01"}}
        respx.post(f"{API}/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json=_launch_response(74, ignored))
        )
        cancel = respx.post(f"{API}/jobs/74/cancel/").mock(return_value=httpx.Response(202))

        result = await launch_job(awx_client, template_id=10, **sent)

        data = json.loads(result[0].text)
        assert data["job_id"] == 74
        assert len(data["warnings"]) == 1
        assert field in data["warnings"][0]
        assert cancel.call_count == 0

    @respx.mock
    async def test_missing_ignored_fields_key_is_not_ignored(self, awx_client, monkeypatch):
        """An older controller with no ignored_fields key: the job returns with no warnings."""
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_job

        respx.post(f"{API}/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json=_launch_response(75, None, job_type="check"))
        )
        cancel = respx.post(f"{API}/jobs/75/cancel/").mock(return_value=httpx.Response(202))

        result = await launch_job(awx_client, template_id=10, check_mode=True)

        data = json.loads(result[0].text)
        assert data == {"job_id": 75, "status": "pending"}
        assert cancel.call_count == 0


class TestGetJobStatus:
    """Tests for get_job_status tool."""

    @respx.mock
    async def test_returns_job_details(self, awx_client):
        from lm_mcp.tools.ansible import get_job_status

        respx.get(f"{BASE}/api/v2/jobs/99/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 99,
                    "status": "successful",
                    "started": "2026-02-18T10:00:00Z",
                    "finished": "2026-02-18T10:01:30Z",
                    "failed": False,
                    "elapsed": 90.5,
                },
            )
        )

        result = await get_job_status(awx_client, job_id=99)
        data = json.loads(result[0].text)
        assert data["id"] == 99
        assert data["status"] == "successful"


class TestGetJobOutput:
    """Tests for get_job_output tool."""

    @respx.mock
    async def test_returns_stdout_text(self, awx_client):
        from lm_mcp.tools.ansible import get_job_output

        respx.get(f"{BASE}/api/v2/jobs/99/stdout/").mock(
            return_value=httpx.Response(
                200,
                text="PLAY [all] ***\nTASK [cleanup] ***\nok: [server01]\n",
            )
        )

        result = await get_job_output(awx_client, job_id=99)
        assert "PLAY [all]" in result[0].text


class TestCancelJob:
    """Tests for cancel_job tool (write operation)."""

    async def test_blocked_without_write_permission(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=False)
        from lm_mcp.tools.ansible import cancel_job

        result = await cancel_job(awx_client, job_id=99)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_cancels_successfully(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import cancel_job

        respx.post(f"{BASE}/api/v2/jobs/99/cancel/").mock(return_value=httpx.Response(202, json={}))

        result = await cancel_job(awx_client, job_id=99)
        data = json.loads(result[0].text)
        assert data["cancelled"] is True
        assert data["job_id"] == 99


class TestRelaunchJob:
    """Tests for relaunch_job tool (write operation)."""

    async def test_blocked_without_write_permission(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=False)
        from lm_mcp.tools.ansible import relaunch_job

        result = await relaunch_job(awx_client, job_id=99)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_relaunches_successfully(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import relaunch_job

        respx.post(f"{BASE}/api/v2/jobs/99/relaunch/").mock(
            return_value=httpx.Response(201, json={"job": 100, "status": "pending"})
        )

        result = await relaunch_job(awx_client, job_id=99)
        data = json.loads(result[0].text)
        assert data["job_id"] == 100


# -- Inventory tools -----------------------------------------------------------


class TestGetInventories:
    """Tests for get_inventories tool."""

    @respx.mock
    async def test_returns_inventory_list(self, awx_client):
        from lm_mcp.tools.ansible import get_inventories

        respx.get(f"{BASE}/api/v2/inventories/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 5, "name": "Production", "total_hosts": 120}],
                },
            )
        )

        result = await get_inventories(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["inventories"][0]["name"] == "Production"

    @respx.mock
    async def test_passes_name_filter(self, awx_client):
        from lm_mcp.tools.ansible import get_inventories

        route = respx.get(f"{BASE}/api/v2/inventories/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        await get_inventories(awx_client, name_filter="prod")
        params = dict(route.calls[0].request.url.params)
        assert params["search"] == "prod"


class TestGetInventoryHosts:
    """Tests for get_inventory_hosts tool."""

    @respx.mock
    async def test_returns_host_list(self, awx_client):
        from lm_mcp.tools.ansible import get_inventory_hosts

        respx.get(f"{BASE}/api/v2/inventories/5/hosts/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 2,
                    "results": [
                        {"id": 10, "name": "server01", "enabled": True},
                        {"id": 11, "name": "server02", "enabled": True},
                    ],
                },
            )
        )

        result = await get_inventory_hosts(awx_client, inventory_id=5)
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert data["hosts"][0]["name"] == "server01"


# -- Workflow tools ------------------------------------------------------------


class TestLaunchWorkflow:
    """Tests for launch_workflow tool (write operation)."""

    async def test_blocked_without_write_permission(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=False)
        from lm_mcp.tools.ansible import launch_workflow

        result = await launch_workflow(awx_client, template_id=10)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_launches_workflow(self, awx_client, monkeypatch):
        _reload_config(monkeypatch, writes_enabled=True)
        from lm_mcp.tools.ansible import launch_workflow

        respx.post(f"{BASE}/api/v2/workflow_job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json={"workflow_job": 200, "status": "pending"})
        )

        result = await launch_workflow(awx_client, template_id=10)
        data = json.loads(result[0].text)
        assert data["workflow_job_id"] == 200


class TestGetWorkflowStatus:
    """Tests for get_workflow_status tool."""

    @respx.mock
    async def test_returns_workflow_details(self, awx_client):
        from lm_mcp.tools.ansible import get_workflow_status

        respx.get(f"{BASE}/api/v2/workflow_jobs/200/").mock(
            return_value=httpx.Response(
                200,
                json={"id": 200, "status": "successful", "elapsed": 120.0},
            )
        )

        result = await get_workflow_status(awx_client, job_id=200)
        data = json.loads(result[0].text)
        assert data["id"] == 200
        assert data["status"] == "successful"


class TestGetWorkflowTemplates:
    """Tests for get_workflow_templates tool."""

    @respx.mock
    async def test_returns_template_list(self, awx_client):
        from lm_mcp.tools.ansible import get_workflow_templates

        respx.get(f"{BASE}/api/v2/workflow_job_templates/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 30, "name": "full-remediation-workflow"}],
                },
            )
        )

        result = await get_workflow_templates(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["templates"][0]["name"] == "full-remediation-workflow"


# -- Admin tools ---------------------------------------------------------------


class TestGetProjects:
    """Tests for get_projects tool."""

    @respx.mock
    async def test_returns_project_list(self, awx_client):
        from lm_mcp.tools.ansible import get_projects

        respx.get(f"{BASE}/api/v2/projects/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 3, "name": "remediation-playbooks", "scm_type": "git"}],
                },
            )
        )

        result = await get_projects(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["projects"][0]["name"] == "remediation-playbooks"


class TestGetCredentials:
    """Tests for get_credentials tool."""

    @respx.mock
    async def test_returns_credential_list(self, awx_client):
        from lm_mcp.tools.ansible import get_credentials

        respx.get(f"{BASE}/api/v2/credentials/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 8, "name": "ssh-prod", "credential_type": 1}],
                },
            )
        )

        result = await get_credentials(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["credentials"][0]["name"] == "ssh-prod"

    @respx.mock
    async def test_passes_credential_type_filter(self, awx_client):
        from lm_mcp.tools.ansible import get_credentials

        route = respx.get(f"{BASE}/api/v2/credentials/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        await get_credentials(awx_client, credential_type=1)
        params = dict(route.calls[0].request.url.params)
        assert params["credential_type"] == "1"


class TestGetOrganizations:
    """Tests for get_organizations tool."""

    @respx.mock
    async def test_returns_org_list(self, awx_client):
        from lm_mcp.tools.ansible import get_organizations

        respx.get(f"{BASE}/api/v2/organizations/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 1, "name": "Default"}],
                },
            )
        )

        result = await get_organizations(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["organizations"][0]["name"] == "Default"


class TestGetJobEvents:
    """Tests for get_job_events tool."""

    @respx.mock
    async def test_returns_event_list(self, awx_client):
        from lm_mcp.tools.ansible import get_job_events

        respx.get(f"{BASE}/api/v2/jobs/99/job_events/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 2,
                    "results": [
                        {"id": 1, "event": "runner_on_ok", "task": "cleanup"},
                        {"id": 2, "event": "runner_on_ok", "task": "verify"},
                    ],
                },
            )
        )

        result = await get_job_events(awx_client, job_id=99)
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert data["events"][0]["event"] == "runner_on_ok"


class TestGetHosts:
    """Tests for get_hosts tool."""

    @respx.mock
    async def test_returns_host_list(self, awx_client):
        from lm_mcp.tools.ansible import get_hosts

        respx.get(f"{BASE}/api/v2/hosts/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 10, "name": "server01", "inventory": 5}],
                },
            )
        )

        result = await get_hosts(awx_client)
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["hosts"][0]["name"] == "server01"

    @respx.mock
    async def test_passes_inventory_filter(self, awx_client):
        from lm_mcp.tools.ansible import get_hosts

        route = respx.get(f"{BASE}/api/v2/hosts/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        await get_hosts(awx_client, inventory_id=5)
        params = dict(route.calls[0].request.url.params)
        assert params["inventory"] == "5"
