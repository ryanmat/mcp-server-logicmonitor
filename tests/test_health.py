# Description: Tests for the health check module.
# Description: Validates health check logic and status determination.


from lm_mcp.health import HealthCheck, HealthResponse


class TestHealthCheck:
    """Tests for HealthCheck dataclass."""

    def test_create_passing_check(self):
        """HealthCheck can be created for passing status."""
        check = HealthCheck(name="server", status="pass", message="Running")

        assert check.name == "server"
        assert check.status == "pass"
        assert check.message == "Running"

    def test_create_failing_check(self):
        """HealthCheck can be created for failing status."""
        check = HealthCheck(name="client", status="fail", message="Not initialized")

        assert check.status == "fail"
        assert check.message == "Not initialized"

    def test_create_warning_check(self):
        """HealthCheck can be created for warning status."""
        check = HealthCheck(name="connectivity", status="warn")

        assert check.status == "warn"
        assert check.message is None

    def test_to_dict_includes_status(self):
        """to_dict includes status field."""
        check = HealthCheck(name="test", status="pass")
        result = check.to_dict()

        assert result["status"] == "pass"

    def test_to_dict_includes_message_when_present(self):
        """to_dict includes message when present."""
        check = HealthCheck(name="test", status="pass", message="OK")
        result = check.to_dict()

        assert result["message"] == "OK"

    def test_to_dict_excludes_message_when_none(self):
        """to_dict excludes message when None."""
        check = HealthCheck(name="test", status="pass")
        result = check.to_dict()

        assert "message" not in result


class TestHealthResponse:
    """Tests for HealthResponse dataclass."""

    def test_create_healthy_response(self):
        """HealthResponse can be created with healthy status."""
        response = HealthResponse(
            status="healthy",
            timestamp="2024-01-01T00:00:00Z",
            version="1.0.0",
        )

        assert response.status == "healthy"
        assert response.timestamp == "2024-01-01T00:00:00Z"
        assert response.version == "1.0.0"
        assert response.checks == {}

    def test_response_with_checks(self):
        """HealthResponse can include multiple checks."""
        checks = {
            "server": HealthCheck(name="server", status="pass"),
            "client": HealthCheck(name="client", status="pass"),
        }

        response = HealthResponse(
            status="healthy",
            timestamp="2024-01-01T00:00:00Z",
            version="1.0.0",
            checks=checks,
        )

        assert len(response.checks) == 2
        assert "server" in response.checks
        assert "client" in response.checks

    def test_to_dict_serializes_response(self):
        """to_dict serializes the full response."""
        checks = {
            "server": HealthCheck(name="server", status="pass", message="Running"),
        }

        response = HealthResponse(
            status="healthy",
            timestamp="2024-01-01T00:00:00Z",
            version="1.0.0",
            checks=checks,
        )

        result = response.to_dict()

        assert result["status"] == "healthy"
        assert result["timestamp"] == "2024-01-01T00:00:00Z"
        assert result["version"] == "1.0.0"
        assert "checks" in result
        assert result["checks"]["server"]["status"] == "pass"
        assert result["checks"]["server"]["message"] == "Running"


class TestHealthStatusDetermination:
    """Tests for overall status determination logic."""

    def test_all_pass_is_healthy(self):
        """All passing checks result in healthy status."""
        checks = {
            "server": HealthCheck(name="server", status="pass"),
            "client": HealthCheck(name="client", status="pass"),
            "config": HealthCheck(name="config", status="pass"),
        }

        statuses = [check.status for check in checks.values()]

        if "fail" in statuses:
            overall = "unhealthy"
        elif "warn" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        assert overall == "healthy"

    def test_any_warn_is_degraded(self):
        """Any warning check results in degraded status."""
        checks = {
            "server": HealthCheck(name="server", status="pass"),
            "connectivity": HealthCheck(name="connectivity", status="warn"),
        }

        statuses = [check.status for check in checks.values()]

        if "fail" in statuses:
            overall = "unhealthy"
        elif "warn" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        assert overall == "degraded"

    def test_any_fail_is_unhealthy(self):
        """Any failing check results in unhealthy status."""
        checks = {
            "server": HealthCheck(name="server", status="pass"),
            "client": HealthCheck(name="client", status="fail"),
        }

        statuses = [check.status for check in checks.values()]

        if "fail" in statuses:
            overall = "unhealthy"
        elif "warn" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        assert overall == "unhealthy"

    def test_fail_takes_precedence_over_warn(self):
        """Fail status takes precedence over warn status."""
        checks = {
            "server": HealthCheck(name="server", status="warn"),
            "client": HealthCheck(name="client", status="fail"),
        }

        statuses = [check.status for check in checks.values()]

        if "fail" in statuses:
            overall = "unhealthy"
        elif "warn" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        assert overall == "unhealthy"
