# Description: Tests for write operation audit trail logging.
# Description: Verifies that write operations emit audit events and reads do not.

import logging
from typing import ClassVar

import pytest


class TestWriteToolPrefixDetection:
    """Tests for identifying write tools by prefix."""

    WRITE_PREFIXES = (
        "create_",
        "update_",
        "delete_",
        "acknowledge_",
        "add_",
        "run_",
        "bulk_",
        "import_",
        "ingest_",
        "push_",
    )

    def test_write_tools_match_prefix(self):
        """Known write tools match at least one write prefix."""
        write_tools = [
            "create_device",
            "update_device",
            "delete_device",
            "acknowledge_alert",
            "add_alert_note",
            "run_netscan",
            "bulk_acknowledge_alerts",
            "import_datasource",
            "ingest_logs",
            "push_metrics",
        ]
        for tool in write_tools:
            assert any(tool.startswith(p) for p in self.WRITE_PREFIXES), (
                f"{tool} should match a write prefix"
            )

    def test_read_tools_dont_match_prefix(self):
        """Known read tools do not match any write prefix."""
        read_tools = [
            "get_devices",
            "get_alerts",
            "list_sdts",
            "get_audit_logs",
            "get_session_context",
            "export_datasource",
        ]
        for tool in read_tools:
            assert not any(tool.startswith(p) for p in self.WRITE_PREFIXES), (
                f"{tool} should not match a write prefix"
            )

    def test_recover_and_collect_are_write_tools(self):
        """recover_device and collect_device_config are detected as write tools.

        Both mutate the portal but lacked a write prefix, so they executed without an
        audit-log entry until recover_/collect_ were added to WRITE_TOOL_PREFIXES.
        """
        from lm_mcp.logging import is_write_tool

        assert is_write_tool("recover_device")
        assert is_write_tool("collect_device_config")

    def test_write_gated_terraform_tools_are_audited(self):
        """terraform_init and terraform_plan are write-gated, so they are audited too."""
        from lm_mcp.logging import is_write_tool

        assert is_write_tool("terraform_init")
        assert is_write_tool("terraform_plan")
        assert not is_write_tool("terraform_validate")


class TestAwxWriteToolPrefixes:
    """Tests for AWX write tool prefix detection."""

    AWX_WRITE_TOOLS: ClassVar[list[str]] = [
        "launch_job",
        "cancel_job",
        "relaunch_job",
        "launch_workflow",
    ]

    def test_awx_write_tools_match_prefix(self):
        """AWX write tools match write prefixes in WRITE_TOOL_PREFIXES."""
        from lm_mcp.logging import is_write_tool

        for tool in self.AWX_WRITE_TOOLS:
            assert is_write_tool(tool), f"{tool} should be detected as a write tool"


class TestWriteAuditLogging:
    """Tests for write audit trail integration in server.py."""

    def test_log_write_operation_emits_info(self, caplog):
        """log_write_operation emits INFO-level log."""
        from lm_mcp.logging import log_write_operation

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation("create_device", {"name": "test"}, success=True)

        assert "create_device" in caplog.text

    def test_log_write_operation_failure_emits_warning(self, caplog):
        """log_write_operation emits WARNING-level log on failure."""
        from lm_mcp.logging import log_write_operation

        with caplog.at_level(logging.WARNING, logger="lm_mcp.audit"):
            log_write_operation("delete_device", {"device_id": 1}, success=False)

        assert "delete_device" in caplog.text
        assert "failed" in caplog.text.lower()


class TestPortalAuditVisibility:
    """Portal switches are auditable and audit lines carry portal identity."""

    def test_use_portal_and_reload_portals_are_write_tools(self):
        from lm_mcp.logging import is_write_tool

        assert is_write_tool("use_portal")
        assert is_write_tool("reload_portals")
        assert not is_write_tool("list_portals")
        assert not is_write_tool("current_portal")

    def test_audit_line_includes_active_portal_in_multi_portal(
        self, monkeypatch, tmp_path, reset_portals, caplog
    ):
        import json

        from lm_mcp import portals
        from lm_mcp.logging import log_write_operation

        p = tmp_path / "portals.json"
        p.write_text(json.dumps({"acme": {"portal": "acme.example.com", "bearer_token": "t"}}))
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(p))
        monkeypatch.delenv("LM_PORTAL", raising=False)
        monkeypatch.delenv("LM_BEARER_TOKEN", raising=False)
        portals.activate("acme")

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation("create_device", {}, success=True)
        assert any("portal=acme" in r.getMessage() for r in caplog.records)

    def test_audit_line_has_no_portal_marker_in_single_portal(self, monkeypatch, caplog):
        from lm_mcp.logging import log_write_operation

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation("create_device", {}, success=True)
        assert not any("portal=" in r.getMessage() for r in caplog.records)


class TestAuditRedaction:
    """Write audit lines redact argument values under credential-shaped keys (R3.7)."""

    def test_password_is_redacted_and_other_values_kept(self, caplog):
        """The audit line keeps the username and shows *** in place of the password."""
        from lm_mcp.logging import log_write_operation

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation("create_user", {"password": "hunter2", "username": "a"}, True)

        assert "username" in caplog.text
        assert "'a'" in caplog.text
        assert "***" in caplog.text
        assert "hunter2" not in caplog.text

    def test_failed_write_line_is_redacted_too(self, caplog):
        """The WARNING line for a failed write goes through the same redaction."""
        from lm_mcp.logging import log_write_operation

        with caplog.at_level(logging.WARNING, logger="lm_mcp.audit"):
            log_write_operation("create_user", {"password": "hunter2", "username": "a"}, False)

        assert "hunter2" not in caplog.text
        assert "***" in caplog.text

    def test_nested_keys_are_redacted(self):
        """A credential key inside a nested object is redacted; its siblings are kept."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments({"vars": {"token": "x", "host": "h"}, "name": "n"})

        assert redacted == {"vars": {"token": "***", "host": "h"}, "name": "n"}

    def test_extra_vars_is_redacted_whole(self):
        """extra_vars carries playbook input of any shape, so the whole value is hidden."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments({"extra_vars": {"token": "x", "plain": "p"}, "limit": "web"})

        assert redacted == {"extra_vars": "***", "limit": "web"}

    def test_lists_of_objects_are_walked(self):
        """Objects inside lists are redacted like top-level objects."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments({"users": [{"password": "p", "name": "n"}, "plain"]})

        assert redacted == {"users": [{"password": "***", "name": "n"}, "plain"]}

    def test_arguments_are_not_mutated(self):
        """Redaction returns a new structure; the tool still receives its arguments."""
        from lm_mcp.logging import redact_arguments

        arguments = {"password": "hunter2", "nested": {"api_key": "k"}}
        redact_arguments(arguments)

        assert arguments == {"password": "hunter2", "nested": {"api_key": "k"}}

    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "PASSWORD",
            "passwd",
            "token",
            "bearer_token",
            "LM_BEARER_TOKEN",
            "secret",
            "client_secret",
            "clientSecret",
            "key",
            "api_key",
            "apiKey",
            "APIKey",
            "private-key",
            "credential",
            "credentials",
            "extra_vars",
            "extraVars",
            "ssh.pass",
            "wmi.pass",
            "esx.pass",
            "snmp.community",
            "snmp.auth",
            "snmp.priv",
            "passphrase",
            "apikey",
            "aws.secretkey",
            "aws.accesskey",
            "azure.clientsecret",
            "privatekey",
        ],
    )
    def test_credential_shaped_keys_are_redacted(self, key):
        """Keys match a whole credential word, case-insensitive, across snake and camel case."""
        from lm_mcp.logging import redact_arguments

        assert redact_arguments({key: "value"}) == {key: "***"}

    @pytest.mark.parametrize(
        "key",
        [
            "keyword",
            "monkey",
            "tokenizer",
            "secretary",
            "name",
            "token_id",
            "api_key_id",
            "device_ids",
            "ssh.user",
            "snmp.version",
            "passport",
            "author",
            "privacy",
        ],
    )
    def test_other_keys_are_kept(self, key):
        """A credential word inside another word, and an identifier, are not redacted."""
        from lm_mcp.logging import redact_arguments

        assert redact_arguments({key: "value"}) == {key: "value"}


class TestPairedNameValueRedaction:
    """A value is redacted when the name it is paired with is a credential property (R3.7)."""

    def test_property_value_is_redacted_when_property_name_is_sensitive(self):
        """update_device_property with ssh.pass hides the value and keeps the name."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments(
            {"device_id": 7, "property_name": "ssh.pass", "property_value": "hunter2"}
        )

        assert redacted == {"device_id": 7, "property_name": "ssh.pass", "property_value": "***"}

    def test_property_value_is_kept_when_property_name_is_plain(self):
        """A plain property keeps its value."""
        from lm_mcp.logging import redact_arguments

        arguments = {"device_id": 7, "property_name": "location", "property_value": "nyc"}

        assert redact_arguments(arguments) == arguments

    def test_name_value_items_in_a_list_are_paired(self):
        """{name, value} items, as LM property lists are shaped, are paired item by item."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments(
            {
                "properties": [
                    {"name": "snmp.community", "value": "public"},
                    {"name": "location", "value": "nyc"},
                ]
            }
        )

        assert redacted == {
            "properties": [
                {"name": "snmp.community", "value": "***"},
                {"name": "location", "value": "nyc"},
            ]
        }

    def test_custom_properties_object_keys_are_redacted(self):
        """create_device custom_properties carrying LM credential properties are hidden."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments(
            {"name": "web-01", "custom_properties": {"ssh.pass": "s", "ssh.user": "root"}}
        )

        assert redacted == {
            "name": "web-01",
            "custom_properties": {"ssh.pass": "***", "ssh.user": "root"},
        }

    def test_failed_property_write_audit_line_carries_no_plaintext(self, caplog):
        """The WARNING for a failed update_device_property never shows the property value."""
        from lm_mcp.logging import log_write_operation

        with caplog.at_level(logging.WARNING, logger="lm_mcp.audit"):
            log_write_operation(
                "update_device_property",
                {"device_id": 7, "property_name": "wmi.pass", "property_value": "hunter2"},
                False,
            )

        assert "wmi.pass" in caplog.text
        assert "hunter2" not in caplog.text


class TestRedactCredentialsInsideStrings:
    """R5: a credential inside a string argument is masked like a credential key."""

    def test_url_credentials_are_masked_beside_a_credential_key(self):
        """Both secrets in the url are masked, as the password key's value is."""
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments(
            {"url": "https://admin:s3cret@10.0.0.5/?password=s3cret2", "password": "p"}
        )

        assert redacted == {"url": "https://***@10.0.0.5/?password=***", "password": "***"}

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://admin:s3cret@host/?password=x", "https://***@host/?password=***"),
            ("https://admin@host/path", "https://***@host/path"),
            ("ssh://git:tok@host:22/repo", "ssh://***@host:22/repo"),
            ("https://a:b@c@host/", "https://***@host/"),
            ("https://host/?a=1&token=t&b=2", "https://host/?a=1&token=***&b=2"),
            ("https://host/?api_key=k", "https://host/?api_key=***"),
            ("https://host/?apiKey=k", "https://host/?apiKey=***"),
            ("https://host/?password=a;b&c=1", "https://host/?password=***&c=1"),
            ("https://host/#access_token=t&state=s", "https://host/#access_token=***&state=s"),
            ("https://host/?a=1#token=t", "https://host/?a=1#token=***"),
            ("host.example.com/?password=x", "host.example.com/?password=***"),
            (
                "see https://u:p@h/ and https://k:v@g/x?secret=s now",
                "see https://***@h/ and https://***@g/x?secret=*** now",
            ),
            ('curl "https://u:p@h/?token=t" -o out', 'curl "https://***@h/?token=***" -o out'),
        ],
    )
    def test_credentials_are_masked(self, value, expected):
        from lm_mcp.logging import redact_arguments

        assert redact_arguments(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "web-01",
            "a=b",
            "ops@example.com",
            "mailto:ops@example.com",
            "https://host/path",
            "https://host/users/ops@example.com",
            "https://host/?email=ops@example.com",
            "https://host/?token_id=5",
            "https://host/?keyword=foo&name=bar",
            'displayName~"prod",hostStatus:"normal"',
        ],
    )
    def test_strings_without_credentials_are_unchanged(self, value):
        from lm_mcp.logging import redact_arguments

        assert redact_arguments(value) == value

    def test_nested_strings_are_masked(self):
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments(
            {
                "hooks": [{"endpoint": "https://u:p@h/"}, "https://x:y@z/"],
                "config": {"ack_url": "https://h/?api_key=k&x=1"},
            }
        )

        assert redacted == {
            "hooks": [{"endpoint": "https://***@h/"}, "https://***@z/"],
            "config": {"ack_url": "https://h/?api_key=***&x=1"},
        }

    def test_paired_value_is_masked_inside_or_whole_by_its_name(self):
        from lm_mcp.logging import redact_arguments

        redacted = redact_arguments(
            [
                {"name": "site", "value": "https://u:p@h/"},
                {"name": "ssh.pass", "value": "https://h/"},
            ]
        )

        assert redacted == [
            {"name": "site", "value": "https://***@h/"},
            {"name": "ssh.pass", "value": "***"},
        ]

    def test_values_that_are_not_strings_pass_through(self):
        from lm_mcp.logging import redact_arguments

        arguments = {"port": 443, "enabled": True, "nothing": None, "ratio": 0.5}

        assert redact_arguments(arguments) == arguments

    def test_input_is_not_modified(self):
        from lm_mcp.logging import redact_arguments

        arguments = {"url": "https://u:p@h/", "hooks": ["https://x:y@z/"]}

        redact_arguments(arguments)

        assert arguments == {"url": "https://u:p@h/", "hooks": ["https://x:y@z/"]}

    @pytest.mark.parametrize(("success", "level"), [(True, logging.INFO), (False, logging.WARNING)])
    def test_audit_line_carries_no_plaintext(self, caplog, success, level):
        from lm_mcp.logging import log_write_operation

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            log_write_operation(
                "create_http_integration",
                {"url": "https://admin:s3cret@host/?password=s3cret2"},
                success,
            )

        assert [record.levelno for record in caplog.records] == [level]
        assert "s3cret" not in caplog.text
        assert "https://***@host/?password=***" in caplog.text
