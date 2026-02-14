# Description: Tests for the analysis store and workflow dispatch.
# Description: Validates AnalysisRequest lifecycle and workflow routing.

from __future__ import annotations

import time

import pytest


class TestAnalysisRequest:
    """Tests for AnalysisRequest dataclass."""

    def test_request_has_required_fields(self):
        """AnalysisRequest has id, workflow, arguments, status, timestamps."""
        from lm_mcp.analysis import AnalysisRequest

        req = AnalysisRequest(
            id="test-123",
            workflow="health_check",
            arguments={},
        )
        assert req.id == "test-123"
        assert req.workflow == "health_check"
        assert req.status == "pending"
        assert req.result is None
        assert req.error is None

    def test_request_default_status_is_pending(self):
        """New requests default to pending status."""
        from lm_mcp.analysis import AnalysisRequest

        req = AnalysisRequest(id="a", workflow="w", arguments={})
        assert req.status == "pending"

    def test_request_to_dict(self):
        """AnalysisRequest serializes to dict."""
        from lm_mcp.analysis import AnalysisRequest

        req = AnalysisRequest(
            id="test-1", workflow="rca", arguments={"device_id": 42}
        )
        d = req.to_dict()
        assert d["id"] == "test-1"
        assert d["workflow"] == "rca"
        assert d["status"] == "pending"
        assert "created_at" in d


class TestAnalysisStore:
    """Tests for AnalysisStore in-memory storage."""

    def test_create_returns_request(self):
        """create() returns an AnalysisRequest with generated ID."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        req = store.create("health_check", {})
        assert req.id is not None
        assert req.workflow == "health_check"
        assert req.status == "pending"

    def test_get_returns_stored_request(self):
        """get() retrieves a previously created request."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        created = store.create("rca", {"device_id": 1})
        fetched = store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.workflow == "rca"

    def test_get_returns_none_for_unknown(self):
        """get() returns None for unknown analysis ID."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        assert store.get("nonexistent") is None

    def test_update_changes_status(self):
        """update() modifies request status and result."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        req = store.create("test", {})
        store.update(req.id, status="running")
        assert store.get(req.id).status == "running"

    def test_update_sets_result(self):
        """update() stores analysis result."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        req = store.create("test", {})
        store.update(req.id, status="completed", result={"data": "ok"})
        fetched = store.get(req.id)
        assert fetched.status == "completed"
        assert fetched.result == {"data": "ok"}

    def test_update_sets_error(self):
        """update() stores error message on failure."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        req = store.create("test", {})
        store.update(req.id, status="failed", error="Something broke")
        fetched = store.get(req.id)
        assert fetched.status == "failed"
        assert fetched.error == "Something broke"

    def test_cleanup_expired_removes_old_entries(self):
        """cleanup_expired() removes entries past TTL."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore(ttl_minutes=0)
        req = store.create("test", {})
        # Force created_at to the past
        req.created_at = time.time() - 120
        store.cleanup_expired()
        assert store.get(req.id) is None

    def test_cleanup_keeps_recent_entries(self):
        """cleanup_expired() keeps entries within TTL."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore(ttl_minutes=60)
        req = store.create("test", {})
        store.cleanup_expired()
        assert store.get(req.id) is not None

    def test_list_recent(self):
        """list_recent() returns entries ordered by creation time."""
        from lm_mcp.analysis import AnalysisStore

        store = AnalysisStore()
        store.create("first", {})
        r2 = store.create("second", {})
        recent = store.list_recent(limit=10)
        assert len(recent) == 2
        assert recent[0].id == r2.id  # Most recent first


class TestWorkflowDispatch:
    """Tests for workflow routing."""

    def test_valid_workflows_list(self):
        """VALID_WORKFLOWS contains expected workflow names."""
        from lm_mcp.analysis import VALID_WORKFLOWS

        assert "alert_correlation" in VALID_WORKFLOWS
        assert "rca_workflow" in VALID_WORKFLOWS
        assert "top_talkers" in VALID_WORKFLOWS
        assert "health_check" in VALID_WORKFLOWS

    def test_invalid_workflow_raises(self):
        """Unknown workflow raises ValueError."""
        from lm_mcp.analysis import validate_workflow

        with pytest.raises(ValueError, match="Unknown workflow"):
            validate_workflow("nonexistent_workflow")

    def test_valid_workflow_passes(self):
        """Known workflow passes validation."""
        from lm_mcp.analysis import validate_workflow

        validate_workflow("health_check")
