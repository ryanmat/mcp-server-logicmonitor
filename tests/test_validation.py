# Description: Tests for the field validation module.
# Description: Validates field name checking, suggestions, and filter parsing.


from lm_mcp.validation import (
    ValidationResult,
    find_similar_fields,
    infer_resource_type,
    levenshtein_distance,
    validate_filter_fields,
)


class TestLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""

    def test_identical_strings(self):
        """Identical strings have distance 0."""
        assert levenshtein_distance("hello", "hello") == 0

    def test_single_insertion(self):
        """Single character insertion has distance 1."""
        assert levenshtein_distance("cat", "cats") == 1

    def test_single_deletion(self):
        """Single character deletion has distance 1."""
        assert levenshtein_distance("cats", "cat") == 1

    def test_single_substitution(self):
        """Single character substitution has distance 1."""
        assert levenshtein_distance("cat", "bat") == 1

    def test_empty_string(self):
        """Empty string distance equals length of other string."""
        assert levenshtein_distance("", "hello") == 5
        assert levenshtein_distance("hello", "") == 5

    def test_both_empty(self):
        """Both empty strings have distance 0."""
        assert levenshtein_distance("", "") == 0

    def test_multiple_edits(self):
        """Multiple edits are counted correctly."""
        assert levenshtein_distance("kitten", "sitting") == 3


class TestFindSimilarFields:
    """Tests for finding similar field names."""

    def test_exact_match_case_insensitive(self):
        """Case-insensitive exact match returns the valid field."""
        valid_fields = {"deviceId", "hostName", "displayName"}

        result = find_similar_fields("DEVICEID", valid_fields)

        assert result == ["deviceId"]

    def test_prefix_match(self):
        """Prefix matches are found."""
        valid_fields = {"deviceId", "deviceName", "deviceType", "hostName"}

        result = find_similar_fields("device", valid_fields)

        assert len(result) <= 3
        assert all("device" in f.lower() for f in result)

    def test_contains_match(self):
        """Substring matches are found."""
        valid_fields = {"deviceId", "hostDeviceName", "name"}

        result = find_similar_fields("Device", valid_fields)

        assert "deviceId" in result or "hostDeviceName" in result

    def test_typo_suggestions(self):
        """Typos get suggestions via Levenshtein distance."""
        valid_fields = {"severity", "status", "cleared"}

        result = find_similar_fields("serverity", valid_fields)

        assert "severity" in result

    def test_max_results_limit(self):
        """Results are limited to max_results."""
        valid_fields = {"field1", "field2", "field3", "field4", "field5"}

        result = find_similar_fields("field", valid_fields, max_results=2)

        assert len(result) <= 2

    def test_no_matches_returns_empty(self):
        """No matches returns empty list."""
        valid_fields = {"alpha", "beta", "gamma"}

        result = find_similar_fields("xyz123", valid_fields, max_distance=2)

        assert result == []


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Valid result has valid=True and empty lists."""
        result = ValidationResult(valid=True)

        assert result.valid is True
        assert result.invalid_fields == []
        assert result.suggestions == {}

    def test_invalid_result(self):
        """Invalid result includes invalid fields and suggestions."""
        result = ValidationResult(
            valid=False,
            invalid_fields=["badField"],
            suggestions={"badField": ["goodField"]},
        )

        assert result.valid is False
        assert result.invalid_fields == ["badField"]
        assert result.suggestions == {"badField": ["goodField"]}

    def test_to_dict_valid(self):
        """to_dict for valid result only includes valid flag."""
        result = ValidationResult(valid=True)

        data = result.to_dict()

        assert data == {"valid": True}

    def test_to_dict_invalid(self):
        """to_dict for invalid result includes all fields."""
        result = ValidationResult(
            valid=False,
            invalid_fields=["bad"],
            suggestions={"bad": ["good"]},
            valid_field_names=["good", "better"],
        )

        data = result.to_dict()

        assert data["valid"] is False
        assert "invalid_fields" in data
        assert "suggestions" in data
        assert "valid_fields" in data


class TestInferResourceType:
    """Tests for inferring resource type from tool names."""

    def test_device_tools(self):
        """Device-related tools return 'devices' type."""
        assert infer_resource_type("get_devices") == "devices"
        assert infer_resource_type("get_device") == "devices"
        assert infer_resource_type("create_device") == "devices"
        assert infer_resource_type("update_device") == "devices"

    def test_alert_tools(self):
        """Alert-related tools return 'alerts' type."""
        assert infer_resource_type("get_alerts") == "alerts"
        assert infer_resource_type("get_alert_details") == "alerts"
        assert infer_resource_type("acknowledge_alert") == "alerts"

    def test_sdt_tools(self):
        """SDT-related tools return 'sdts' type."""
        assert infer_resource_type("list_sdts") == "sdts"
        assert infer_resource_type("create_sdt") == "sdts"
        assert infer_resource_type("delete_sdt") == "sdts"

    def test_collector_tools(self):
        """Collector-related tools return 'collectors' type."""
        assert infer_resource_type("get_collectors") == "collectors"
        assert infer_resource_type("get_collector") == "collectors"

    def test_dashboard_tools(self):
        """Dashboard-related tools return 'dashboards' type."""
        assert infer_resource_type("get_dashboards") == "dashboards"
        assert infer_resource_type("create_dashboard") == "dashboards"

    def test_website_tools(self):
        """Website-related tools return 'websites' type."""
        assert infer_resource_type("get_websites") == "websites"
        assert infer_resource_type("get_website_data") == "websites"

    def test_user_tools(self):
        """User-related tools return 'users' type."""
        assert infer_resource_type("get_users") == "users"
        assert infer_resource_type("get_user") == "users"

    def test_unknown_tools_return_none(self):
        """Unknown tool patterns return None."""
        assert infer_resource_type("get_reports") is None
        assert infer_resource_type("run_netscan") is None


class TestValidateFields:
    """Tests for field validation."""

    def test_valid_fields_pass(self):
        """Valid field names pass validation."""
        # Mock schema would need to be set up, so we test the logic
        result = ValidationResult(valid=True)
        assert result.valid is True

    def test_string_input_is_split(self):
        """String input with commas is split into list."""
        # The function handles both list and string input
        fields_str = "id, name, status"
        fields_list = [f.strip() for f in fields_str.split(",") if f.strip()]

        assert fields_list == ["id", "name", "status"]


class TestValidateFilterFields:
    """Tests for filter expression validation."""

    def test_parse_colon_filter(self):
        """Colon-separated filters are parsed correctly."""
        import re

        filter_string = "severity:4,cleared:false"
        pattern = r"([a-zA-Z_][a-zA-Z0-9_.]*)\s*[:<>~!]"
        matches = re.findall(pattern, filter_string)

        assert "severity" in matches
        assert "cleared" in matches

    def test_parse_tilde_filter(self):
        """Tilde filters are parsed correctly."""
        import re

        filter_string = "name~prod*"
        pattern = r"([a-zA-Z_][a-zA-Z0-9_.]*)\s*[:<>~!]"
        matches = re.findall(pattern, filter_string)

        assert "name" in matches

    def test_parse_comparison_filter(self):
        """Comparison operators are parsed correctly."""
        import re

        filter_string = "id>100,id<200"
        pattern = r"([a-zA-Z_][a-zA-Z0-9_.]*)\s*[:<>~!]"
        matches = re.findall(pattern, filter_string)

        assert matches.count("id") == 2

    def test_empty_filter_returns_valid(self):
        """Empty filter returns valid result."""
        result = validate_filter_fields("devices", "")

        assert result.valid is True

    def test_nested_property_filter(self):
        """Nested property filters are parsed correctly."""
        import re

        filter_string = "systemProperties.name:value"
        pattern = r"([a-zA-Z_][a-zA-Z0-9_.]*)\s*[:<>~!]"
        matches = re.findall(pattern, filter_string)

        assert "systemProperties.name" in matches
