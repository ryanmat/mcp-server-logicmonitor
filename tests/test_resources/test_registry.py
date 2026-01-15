# Description: Tests for MCP resource registry.
# Description: Verifies resource listing and content retrieval functions.

from __future__ import annotations

import json

import pytest

from lm_mcp.resources import RESOURCES, get_resource_content
from lm_mcp.resources.registry import get_resource_by_uri, list_resource_uris


class TestResourcesRegistry:
    """Tests for the RESOURCES list and registry functions."""

    def test_resources_list_not_empty(self):
        """RESOURCES list contains resource definitions."""
        assert len(RESOURCES) > 0

    def test_resources_have_required_fields(self):
        """Each resource has uri, name, and description."""
        for resource in RESOURCES:
            assert resource.uri is not None
            assert resource.name is not None
            assert resource.description is not None

    def test_resources_uris_are_unique(self):
        """All resource URIs are unique."""
        uris = [str(r.uri) for r in RESOURCES]
        assert len(uris) == len(set(uris))

    def test_resources_uris_follow_scheme(self):
        """All resource URIs use the lm:// scheme."""
        for resource in RESOURCES:
            assert str(resource.uri).startswith("lm://")

    def test_list_resource_uris_returns_all(self):
        """list_resource_uris returns all registered URIs."""
        uris = list_resource_uris()
        assert len(uris) == len(RESOURCES)
        for resource in RESOURCES:
            assert str(resource.uri) in uris

    def test_get_resource_by_uri_found(self):
        """get_resource_by_uri returns resource for valid URI."""
        resource = get_resource_by_uri("lm://schema/alerts")
        assert resource is not None
        assert str(resource.uri) == "lm://schema/alerts"
        assert resource.name == "Alert Schema"

    def test_get_resource_by_uri_not_found(self):
        """get_resource_by_uri returns None for invalid URI."""
        resource = get_resource_by_uri("lm://invalid/resource")
        assert resource is None


class TestGetResourceContent:
    """Tests for get_resource_content function."""

    def test_get_schema_alerts(self):
        """get_resource_content returns alert schema JSON."""
        content = get_resource_content("lm://schema/alerts")
        data = json.loads(content)
        assert data["name"] == "alerts"
        assert "fields" in data
        assert "severity" in data["fields"]
        assert "cleared" in data["fields"]

    def test_get_schema_devices(self):
        """get_resource_content returns device schema JSON."""
        content = get_resource_content("lm://schema/devices")
        data = json.loads(content)
        assert data["name"] == "devices"
        assert "fields" in data
        assert "displayName" in data["fields"]
        assert "hostStatus" in data["fields"]

    def test_get_schema_sdts(self):
        """get_resource_content returns SDT schema JSON."""
        content = get_resource_content("lm://schema/sdts")
        data = json.loads(content)
        assert data["name"] == "sdts"
        assert "fields" in data
        assert "type" in data["fields"]
        assert "startDateTime" in data["fields"]

    def test_get_enum_severity(self):
        """get_resource_content returns severity enum JSON."""
        content = get_resource_content("lm://enums/severity")
        data = json.loads(content)
        assert data["name"] == "severity"
        assert "values" in data
        assert "critical" in data["values"]
        assert data["values"]["critical"]["api_value"] == 4

    def test_get_enum_device_status(self):
        """get_resource_content returns device-status enum JSON."""
        content = get_resource_content("lm://enums/device-status")
        data = json.loads(content)
        assert data["name"] == "device-status"
        assert "values" in data
        assert "normal" in data["values"]
        assert data["values"]["normal"]["api_value"] == 0

    def test_get_enum_sdt_type(self):
        """get_resource_content returns sdt-type enum JSON."""
        content = get_resource_content("lm://enums/sdt-type")
        data = json.loads(content)
        assert data["name"] == "sdt-type"
        assert "values" in data
        assert "DeviceSDT" in data["values"]
        assert "DeviceGroupSDT" in data["values"]

    def test_get_filters_alerts(self):
        """get_resource_content returns alert filters JSON."""
        content = get_resource_content("lm://filters/alerts")
        data = json.loads(content)
        assert data["name"] == "alerts"
        assert "fields" in data
        assert "severity" in data["fields"]
        assert "common_queries" in data

    def test_get_filters_devices(self):
        """get_resource_content returns device filters JSON."""
        content = get_resource_content("lm://filters/devices")
        data = json.loads(content)
        assert data["name"] == "devices"
        assert "fields" in data
        assert "displayName" in data["fields"]

    def test_get_syntax_operators(self):
        """get_resource_content returns filter operators JSON."""
        content = get_resource_content("lm://syntax/operators")
        data = json.loads(content)
        assert "operators" in data
        assert ":" in data["operators"]
        assert "~" in data["operators"]
        assert ">:" in data["operators"]

    def test_invalid_uri_scheme(self):
        """get_resource_content raises ValueError for invalid scheme."""
        with pytest.raises(ValueError, match="Invalid resource URI"):
            get_resource_content("https://invalid/uri")

    def test_invalid_uri_path(self):
        """get_resource_content raises ValueError for invalid path."""
        with pytest.raises(ValueError, match="Invalid resource path"):
            get_resource_content("lm://invalid")

    def test_unknown_resource(self):
        """get_resource_content raises ValueError for unknown resource."""
        with pytest.raises(ValueError, match="Resource not found"):
            get_resource_content("lm://schema/unknown")


class TestResourceContentStructure:
    """Tests verifying resource content structure and completeness."""

    def test_all_schema_resources_loadable(self):
        """All schema resources return valid JSON."""
        schema_uris = [str(r.uri) for r in RESOURCES if "/schema/" in str(r.uri)]
        for uri in schema_uris:
            content = get_resource_content(uri)
            data = json.loads(content)
            assert "name" in data
            assert "fields" in data

    def test_all_enum_resources_loadable(self):
        """All enum resources return valid JSON."""
        enum_uris = [str(r.uri) for r in RESOURCES if "/enums/" in str(r.uri)]
        for uri in enum_uris:
            content = get_resource_content(uri)
            data = json.loads(content)
            assert "name" in data
            assert "values" in data

    def test_all_filter_resources_loadable(self):
        """All filter resources return valid JSON."""
        filter_uris = [str(r.uri) for r in RESOURCES if "/filters/" in str(r.uri)]
        for uri in filter_uris:
            content = get_resource_content(uri)
            data = json.loads(content)
            assert "name" in data
            assert "fields" in data

    def test_schema_fields_have_types(self):
        """Schema field definitions include type information."""
        content = get_resource_content("lm://schema/alerts")
        data = json.loads(content)
        for field_name, field_def in data["fields"].items():
            assert "type" in field_def, f"Field {field_name} missing type"
            assert "description" in field_def, f"Field {field_name} missing description"

    def test_filter_fields_have_operators(self):
        """Filter field definitions include supported operators."""
        content = get_resource_content("lm://filters/alerts")
        data = json.loads(content)
        for field_name, field_def in data["fields"].items():
            assert "operators" in field_def, f"Field {field_name} missing operators"
            assert len(field_def["operators"]) > 0
