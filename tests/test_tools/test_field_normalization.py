# Description: Tests for LogicModule field name normalization utility.
# Description: Covers camelCase passthrough, snake_case, LM Exchange, recursion.

from lm_mcp.tools import normalize_definition_fields


class TestNormalizeDefinitionFields:
    def test_camelcase_passthrough(self):
        """Keys already in REST API camelCase pass through unchanged."""
        definition = {
            "name": "TestDS",
            "displayName": "Test DataSource",
            "collectMethod": "script",
            "dataPoints": [{"name": "dp1"}],
        }
        result = normalize_definition_fields(definition)
        assert result == definition

    def test_snake_case_to_camelcase(self):
        """snake_case keys from get_* output are normalized to camelCase."""
        definition = {
            "name": "TestDS",
            "display_name": "Test DataSource",
            "collect_method": "script",
            "applies_to": "isLinux()",
            "collect_interval": 300,
            "has_multi_instances": True,
        }
        result = normalize_definition_fields(definition)
        assert result["displayName"] == "Test DataSource"
        assert result["collectMethod"] == "script"
        assert result["appliesTo"] == "isLinux()"
        assert result["collectInterval"] == 300
        assert result["hasMultiInstances"] is True
        assert result["name"] == "TestDS"

    def test_lm_exchange_to_camelcase(self):
        """LM Exchange format keys are normalized to REST API camelCase."""
        definition = {
            "name": "TestDS",
            "displayedAs": "Test DataSource",
            "collectionMethod": "script",
            "collectionAttrs": {"timeout": 30},
            "datapoints": [{"name": "dp1"}],
        }
        result = normalize_definition_fields(definition)
        assert result["displayName"] == "Test DataSource"
        assert result["collectMethod"] == "script"
        assert result["collectorAttribute"] == {"timeout": 30}
        assert result["dataPoints"] == [{"name": "dp1"}]

    def test_mixed_formats(self):
        """Mix of camelCase, snake_case, and LM Exchange all normalize correctly."""
        definition = {
            "name": "TestDS",
            "displayedAs": "Test",
            "collect_interval": 300,
            "appliesTo": "isLinux()",
        }
        result = normalize_definition_fields(definition)
        assert result["displayName"] == "Test"
        assert result["collectInterval"] == 300
        assert result["appliesTo"] == "isLinux()"

    def test_canonical_key_wins_over_alias(self):
        """When both alias and canonical exist, canonical value wins."""
        definition = {
            "datapoints": [{"name": "old"}],
            "dataPoints": [{"name": "correct"}],
        }
        result = normalize_definition_fields(definition)
        assert result["dataPoints"] == [{"name": "correct"}]
        assert "datapoints" not in result

    def test_recursive_nested_dicts(self):
        """Nested dict values have their keys normalized too."""
        definition = {
            "collectionAttrs": {
                "display_name": "inner",
                "collect_method": "snmp",
            },
        }
        result = normalize_definition_fields(definition)
        inner = result["collectorAttribute"]
        assert inner["displayName"] == "inner"
        assert inner["collectMethod"] == "snmp"

    def test_recursive_lists_of_dicts(self):
        """Lists containing dicts have each element normalized."""
        definition = {
            "data_points": [
                {"alert_expr": "> 90", "post_processor_method": "expression"},
                {"alert_expr": "> 95", "post_processor_method": "regex"},
            ],
        }
        result = normalize_definition_fields(definition)
        assert len(result["dataPoints"]) == 2
        assert result["dataPoints"][0]["alertExpr"] == "> 90"
        assert result["dataPoints"][0]["postProcessorMethod"] == "expression"
        assert result["dataPoints"][1]["alertExpr"] == "> 95"

    def test_non_dict_list_elements_unchanged(self):
        """Non-dict list elements (strings, numbers) pass through."""
        definition = {
            "tags": ["linux", "server"],
            "collect_interval": 60,
        }
        result = normalize_definition_fields(definition)
        assert result["tags"] == ["linux", "server"]
        assert result["collectInterval"] == 60

    def test_unknown_keys_passthrough(self):
        """Keys not in the alias map pass through unchanged."""
        definition = {
            "name": "TestDS",
            "customField": "custom_value",
            "anotherThing": 42,
        }
        result = normalize_definition_fields(definition)
        assert result["customField"] == "custom_value"
        assert result["anotherThing"] == 42

    def test_empty_dict(self):
        """Empty dict returns empty dict."""
        assert normalize_definition_fields({}) == {}

    def test_does_not_mutate_input(self):
        """Original definition dict is not modified."""
        original = {
            "display_name": "Test",
            "collect_method": "script",
        }
        original_copy = dict(original)
        normalize_definition_fields(original)
        assert original == original_copy
