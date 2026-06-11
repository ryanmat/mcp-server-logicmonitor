# Description: Tests for OTLP Metrics query MCP tools.
# Description: Validates PromQL range queries, discovery endpoints, and feature-flag degrade paths.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient

BASE = "https://test.logicmonitor.com/santaba/rest"


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url=BASE,
        auth=auth,
        timeout=30,
        api_version=3,
    )


def _list_body(items: list[str] | None, message: str | None = None) -> dict:
    """Live-shaped list body for the three GET endpoints (X-Version: 3 form)."""
    meta: dict = {"accessible": True, "queryTimeMs": 42}
    if message:
        meta["message"] = message
    body: dict = {"meta": meta}
    if items is not None:
        body["data"] = items
    return body


def _matrix_body(series_count: int = 1, point_count: int = 2) -> dict:
    """Live-shaped query-range matrix body (dict-form values)."""
    series = []
    for s in range(series_count):
        series.append(
            {
                "metric": {
                    "__name__": "lmmcp_validation_requests",
                    "service_name": f"svc-{s}",
                    "source": "lm-mcp-v4.1.0-validation",
                },
                "values": [
                    {"value": str(9 + p), "timestamp": 1781200200 + 30 * p}
                    for p in range(point_count)
                ],
            }
        )
    return {
        "data": series,
        "meta": {"accessible": True, "queryTimeMs": 182, "resultType": "matrix"},
    }


_FEATURE_OFF_404 = httpx.Response(
    404, json={"errorMessage": "HTTP 404 Not Found", "errorCode": 1400, "errorDetail": None}
)
_FEATURE_OFF_400 = httpx.Response(
    400,
    json={
        "errorMessage": "OTLP Metrics feature is not enabled for this account",
        "errorCode": 1400,
    },
)
_ERRORS_IN_200 = httpx.Response(
    200,
    json={
        "meta": {"accessible": True},
        "errors": [
            {
                "type": "INTERNAL_ERROR",
                "message": "Unexpected error fetching labels",
                "operation": "READ",
                "status": "ERROR",
            }
        ],
    },
)


class TestGetOtlpMetricNames:
    """Tests for get_otlp_metric_names."""

    @respx.mock
    async def test_returns_metric_names(self, client):
        """Populated data list is surfaced with count and query time."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_names

        respx.get(f"{BASE}/metrics/metric-names").mock(
            return_value=httpx.Response(200, json=_list_body(["cpu_usage", "mem_usage"]))
        )

        result = await get_otlp_metric_names(client)
        data = json.loads(result[0].text)

        assert data["metric_names"] == ["cpu_usage", "mem_usage"]
        assert data["count"] == 2
        assert data["query_time_ms"] == 42

    @respx.mock
    async def test_params_passthrough(self, client):
        """Set params reach the wire; None params are omitted."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_names

        route = respx.get(f"{BASE}/metrics/metric-names").mock(
            return_value=httpx.Response(200, json=_list_body([]))
        )

        await get_otlp_metric_names(client, contains="lmmcp", start=1781200000, end=1781203600)

        params = route.calls[0].request.url.params
        assert params["contains"] == "lmmcp"
        assert params["start"] == "1781200000"
        assert params["end"] == "1781203600"
        assert params["limit"] == "50"

    @respx.mock
    async def test_none_params_omitted(self, client):
        """Only limit goes on the wire when no filters are set."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_names

        route = respx.get(f"{BASE}/metrics/metric-names").mock(
            return_value=httpx.Response(200, json=_list_body([]))
        )

        await get_otlp_metric_names(client)

        params = route.calls[0].request.url.params
        assert "contains" not in params
        assert "start" not in params
        assert "end" not in params

    @respx.mock
    async def test_absent_data_key_yields_empty_list(self, client):
        """The API omits the data key entirely when nothing matches."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_names

        respx.get(f"{BASE}/metrics/metric-names").mock(
            return_value=httpx.Response(
                200, json=_list_body(None, message="No matching labels-values found.")
            )
        )

        result = await get_otlp_metric_names(client)
        data = json.loads(result[0].text)

        assert data["metric_names"] == []
        assert data["count"] == 0
        assert data["note"] == "No matching labels-values found."


class TestGetOtlpMetricLabels:
    """Tests for get_otlp_metric_labels."""

    @respx.mock
    async def test_returns_labels(self, client):
        """Populated label list is surfaced."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_labels

        respx.get(f"{BASE}/metrics/labels").mock(
            return_value=httpx.Response(
                200, json=_list_body(["__name__", "service_name", "source"])
            )
        )

        result = await get_otlp_metric_labels(client)
        data = json.loads(result[0].text)

        assert data["labels"] == ["__name__", "service_name", "source"]
        assert data["count"] == 3

    @respx.mock
    async def test_label_name_maps_to_labelname_param(self, client):
        """label_name is sent as the API's labelName query param."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_labels

        route = respx.get(f"{BASE}/metrics/labels").mock(
            return_value=httpx.Response(200, json=_list_body([]))
        )

        await get_otlp_metric_labels(client, metric="cpu_usage", label_name="service")

        params = route.calls[0].request.url.params
        assert params["metric"] == "cpu_usage"
        assert params["labelName"] == "service"
        assert "label_name" not in params


class TestGetOtlpLabelValues:
    """Tests for get_otlp_label_values."""

    @respx.mock
    async def test_returns_values_and_echoes_key(self, client):
        """Values list is surfaced and the queried key is echoed."""
        from lm_mcp.tools.otlp_metrics import get_otlp_label_values

        route = respx.get(f"{BASE}/metrics/label-values").mock(
            return_value=httpx.Response(200, json=_list_body(["lm-mcp-v4.1.0-validation"]))
        )

        result = await get_otlp_label_values(client, key="source")
        data = json.loads(result[0].text)

        assert route.calls[0].request.url.params["key"] == "source"
        assert data["key"] == "source"
        assert data["values"] == ["lm-mcp-v4.1.0-validation"]
        assert data["count"] == 1

    @respx.mock
    async def test_empty_key_is_validation_error(self, client):
        """Empty key fails before any API call."""
        from lm_mcp.tools.otlp_metrics import get_otlp_label_values

        route = respx.get(f"{BASE}/metrics/label-values").mock(
            return_value=httpx.Response(200, json=_list_body([]))
        )

        result = await get_otlp_label_values(client, key="")

        assert result[0].text.startswith("Error:")
        assert "key is required" in result[0].text
        assert not route.called


class TestQueryOtlpMetrics:
    """Tests for query_otlp_metrics."""

    @respx.mock
    async def test_returns_series_matrix(self, client):
        """Matrix series normalize to name/labels/points with float values."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        respx.post(f"{BASE}/metrics/query-range").mock(
            return_value=httpx.Response(200, json=_matrix_body())
        )

        result = await query_otlp_metrics(
            client, query="lmmcp_validation_requests", start=1781200000, end=1781203600
        )
        data = json.loads(result[0].text)

        assert data["result_type"] == "matrix"
        assert data["series_count_total"] == 1
        assert data["series_count_returned"] == 1
        series = data["series"][0]
        assert series["name"] == "lmmcp_validation_requests"
        assert series["labels"]["service_name"] == "svc-0"
        assert "__name__" not in series["labels"]
        assert series["points"] == [[1781200200, 9.0], [1781200230, 10.0]]
        assert series["point_count"] == 2
        assert data["query_time_ms"] == 182
        assert "truncated" not in data

    @respx.mock
    async def test_request_body_includes_step(self, client):
        """The POST body carries query/start/end/step verbatim."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        route = respx.post(f"{BASE}/metrics/query-range").mock(
            return_value=httpx.Response(200, json=_matrix_body())
        )

        await query_otlp_metrics(
            client, query="nginx_up", start=1781200000, end=1781203600, step="30s"
        )

        body = json.loads(route.calls[0].request.content)
        assert body == {"query": "nginx_up", "start": 1781200000, "end": 1781203600, "step": "30s"}

    @respx.mock
    async def test_request_body_omits_step_when_none(self, client):
        """step stays off the body when not provided."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        route = respx.post(f"{BASE}/metrics/query-range").mock(
            return_value=httpx.Response(200, json=_matrix_body())
        )

        await query_otlp_metrics(client, query="nginx_up", start=1781200000, end=1781203600)

        body = json.loads(route.calls[0].request.content)
        assert "step" not in body

    @respx.mock
    async def test_empty_query_is_validation_error(self, client):
        """Empty query fails before any API call."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        route = respx.post(f"{BASE}/metrics/query-range").mock(
            return_value=httpx.Response(200, json=_matrix_body())
        )

        result = await query_otlp_metrics(client, query="", start=1, end=2)

        assert result[0].text.startswith("Error:")
        assert "query is required" in result[0].text
        assert not route.called

    @respx.mock
    async def test_start_after_end_is_validation_error(self, client):
        """start >= end fails before any API call."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        route = respx.post(f"{BASE}/metrics/query-range").mock(
            return_value=httpx.Response(200, json=_matrix_body())
        )

        result = await query_otlp_metrics(client, query="nginx_up", start=200, end=100)

        assert result[0].text.startswith("Error:")
        assert "start must be before end" in result[0].text
        assert not route.called

    @respx.mock
    async def test_truncates_series_and_points(self, client):
        """Series above the cap are dropped; long series are stride-downsampled."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        body = _matrix_body(series_count=21, point_count=1)
        body["data"][0]["values"] = [
            {"value": str(p), "timestamp": 1781200200 + 30 * p} for p in range(501)
        ]
        respx.post(f"{BASE}/metrics/query-range").mock(return_value=httpx.Response(200, json=body))

        result = await query_otlp_metrics(
            client, query="lmmcp_validation_requests", start=1781200000, end=1781203600
        )
        data = json.loads(result[0].text)

        assert data["truncated"] is True
        assert data["series_count_total"] == 21
        assert data["series_count_returned"] == 20
        assert data["series"][0]["point_count"] <= 500
        assert "capped" in data["note"]

    @respx.mock
    async def test_tolerates_pair_form_values(self, client):
        """Prometheus-native [ts, "val"] pairs normalize like the dict form."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        body = _matrix_body()
        body["data"][0]["values"] = [[1781200200, "1.5"], [1781200230, "NaN-ish"]]
        respx.post(f"{BASE}/metrics/query-range").mock(return_value=httpx.Response(200, json=body))

        result = await query_otlp_metrics(
            client, query="lmmcp_validation_requests", start=1781200000, end=1781203600
        )
        data = json.loads(result[0].text)

        assert data["series"][0]["points"][0] == [1781200200, 1.5]
        # Unparseable values stay as the raw string rather than crashing.
        assert data["series"][0]["points"][1] == [1781200230, "NaN-ish"]


_DEGRADE_CASES = [
    ("get_otlp_metric_names", "GET", "/metrics/metric-names", {}),
    ("get_otlp_metric_labels", "GET", "/metrics/labels", {}),
    ("get_otlp_label_values", "GET", "/metrics/label-values", {"key": "source"}),
    ("query_otlp_metrics", "POST", "/metrics/query-range", {"query": "up", "start": 1, "end": 2}),
]


class TestGracefulDegrade:
    """Feature-unavailable portals produce a friendly notice, not a raw error."""

    @pytest.mark.parametrize(("tool_name", "method", "path", "kwargs"), _DEGRADE_CASES)
    @respx.mock
    async def test_flag_disabled_404_is_friendly(self, client, tool_name, method, path, kwargs):
        """Flag-disabled portals 404 (routes absent) -> friendly availability notice."""
        from lm_mcp.tools import otlp_metrics

        respx.request(method, f"{BASE}{path}").mock(return_value=_FEATURE_OFF_404)

        result = await getattr(otlp_metrics, tool_name)(client, **kwargs)
        data = json.loads(result[0].text)

        assert data["available"] is False
        assert "not available on this portal" in data["message"]

    @pytest.mark.parametrize(("tool_name", "method", "path", "kwargs"), _DEGRADE_CASES)
    @respx.mock
    async def test_feature_disabled_400_is_friendly(self, client, tool_name, method, path, kwargs):
        """Flag-deployed-but-off portals 400 with the feature message -> same notice."""
        from lm_mcp.tools import otlp_metrics

        respx.request(method, f"{BASE}{path}").mock(return_value=_FEATURE_OFF_400)

        result = await getattr(otlp_metrics, tool_name)(client, **kwargs)
        data = json.loads(result[0].text)

        assert data["available"] is False
        assert "not available on this portal" in data["message"]

    @respx.mock
    async def test_storage_failure_400_is_normal_error(self, client):
        """Non-feature 400s keep the standard error envelope (no over-matching)."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        respx.post(f"{BASE}/metrics/query-range").mock(
            return_value=httpx.Response(
                400, json={"errorMessage": "query execution failed in storage", "errorCode": 1400}
            )
        )

        result = await query_otlp_metrics(client, query="up", start=1, end=2)

        assert result[0].text.startswith("Error:")
        assert "query execution failed in storage" in result[0].text


class TestErrorsArrayIn200:
    """The metrics backend reports failures as 200 + errors[]; tools must catch it."""

    @respx.mock
    async def test_get_tool_surfaces_errors_array(self, client):
        """A 200 body with errors[] becomes an error envelope on GET tools."""
        from lm_mcp.tools.otlp_metrics import get_otlp_metric_labels

        respx.get(f"{BASE}/metrics/labels").mock(return_value=_ERRORS_IN_200)

        result = await get_otlp_metric_labels(client)

        assert result[0].text.startswith("Error:")
        assert "Unexpected error fetching labels" in result[0].text

    @respx.mock
    async def test_query_range_surfaces_errors_array(self, client):
        """A 200 body with errors[] becomes an error envelope on query-range."""
        from lm_mcp.tools.otlp_metrics import query_otlp_metrics

        respx.post(f"{BASE}/metrics/query-range").mock(return_value=_ERRORS_IN_200)

        result = await query_otlp_metrics(client, query="up", start=1, end=2)

        assert result[0].text.startswith("Error:")
        assert "Unexpected error fetching labels" in result[0].text
