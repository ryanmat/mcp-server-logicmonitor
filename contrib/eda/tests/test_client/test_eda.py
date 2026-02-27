# Description: Tests for EDA Controller API client.
# Description: Uses respx to mock HTTP responses for testing.

import pytest
import respx
from httpx import Response

from lm_mcp.client.eda import EdaClient
from lm_mcp.exceptions import (
    AuthenticationError,
    LMConnectionError,
    LMError,
    LMPermissionError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

EDA_BASE = "https://eda.example.com"
EDA_API = f"{EDA_BASE}/api/eda/v1"


@pytest.fixture
def client():
    return EdaClient(
        base_url=EDA_BASE,
        token="test-eda-token",
        timeout=30,
        max_retries=3,
    )


class TestEdaClientInit:
    """Tests for EDA client initialization."""

    def test_stores_config(self):
        """Client stores base_url and token."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="my-token",
            timeout=60,
            max_retries=5,
        )
        assert client.base_url == EDA_API
        assert client.token == "my-token"
        assert client.max_retries == 5

    def test_strips_trailing_slash(self):
        """Client removes trailing slash from base_url."""
        client = EdaClient(
            base_url=f"{EDA_BASE}/",
            token="my-token",
        )
        assert client.base_url == EDA_API

    def test_default_values(self):
        """Client uses sensible defaults."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="my-token",
        )
        assert client.max_retries == 3
        assert client.verify_ssl is True


class TestEdaClientHeaders:
    """Tests for header generation."""

    def test_headers_include_auth(self, client):
        """Headers include Bearer token."""
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer test-eda-token"

    def test_headers_include_content_type(self, client):
        """Headers include Content-Type."""
        headers = client._get_headers()
        assert headers["Content-Type"] == "application/json"


class TestEdaClientGet:
    """Tests for GET requests."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_success(self, client):
        """Successful GET returns parsed JSON."""
        respx.get(f"{EDA_API}/activations/").mock(
            return_value=Response(200, json={"count": 1, "results": [{"id": 1}]})
        )
        result = await client.get("/activations/")
        assert result == {"count": 1, "results": [{"id": 1}]}

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_with_params(self, client):
        """GET passes query parameters."""
        route = respx.get(f"{EDA_API}/activations/").mock(
            return_value=Response(200, json={"count": 0, "results": []})
        )
        await client.get("/activations/", params={"page_size": 10})
        assert route.calls[0].request.url.params["page_size"] == "10"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_text_response(self, client):
        """GET with non-JSON content-type returns text wrapper."""
        respx.get(f"{EDA_API}/activation-instances/42/logs/").mock(
            return_value=Response(200, text="Activation started\nRule matched")
        )
        result = await client.get("/activation-instances/42/logs/")
        assert result == {"text": "Activation started\nRule matched"}


class TestEdaClientPost:
    """Tests for POST requests."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_success(self, client):
        """Successful POST returns parsed JSON."""
        respx.post(f"{EDA_API}/activations/").mock(
            return_value=Response(201, json={"id": 5, "name": "test-activation"})
        )
        result = await client.post(
            "/activations/", json_body={"name": "test-activation"}
        )
        assert result == {"id": 5, "name": "test-activation"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_empty_body(self, client):
        """POST with no body succeeds."""
        respx.post(f"{EDA_API}/activations/1/restart/").mock(
            return_value=Response(202, json={})
        )
        result = await client.post("/activations/1/restart/")
        assert result == {}


class TestEdaClientDelete:
    """Tests for DELETE requests."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_success(self, client):
        """Successful DELETE returns empty dict for 204."""
        respx.delete(f"{EDA_API}/activations/42/").mock(
            return_value=Response(204, text="")
        )
        result = await client.delete("/activations/42/")
        assert result == {}


class TestEdaClientErrorMapping:
    """Tests for HTTP error code mapping to exceptions."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_authentication_error(self, client):
        """401 response raises AuthenticationError."""
        respx.get(f"{EDA_API}/activations/").mock(
            return_value=Response(
                401, json={"detail": "Authentication credentials were not provided."}
            )
        )
        with pytest.raises(AuthenticationError):
            await client.get("/activations/")

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_raises_permission_error(self, client):
        """403 response raises LMPermissionError."""
        respx.get(f"{EDA_API}/projects/").mock(
            return_value=Response(
                403, json={"detail": "You do not have permission to perform this action."}
            )
        )
        with pytest.raises(LMPermissionError):
            await client.get("/projects/")

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_raises_not_found_error(self, client):
        """404 response raises NotFoundError."""
        respx.get(f"{EDA_API}/activations/999/").mock(
            return_value=Response(404, json={"detail": "Not found."})
        )
        with pytest.raises(NotFoundError):
            await client.get("/activations/999/")

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_raises_rate_limit_error_after_retries(self):
        """429 response raises RateLimitError after retries exhausted."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="test-token",
            max_retries=0,
        )
        respx.get(f"{EDA_API}/activations/").mock(
            return_value=Response(429, json={"detail": "Request was throttled."})
        )
        with pytest.raises(RateLimitError):
            await client.get("/activations/")

    @pytest.mark.asyncio
    @respx.mock
    async def test_500_raises_server_error_after_retries(self):
        """500 response raises ServerError after retries exhausted."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="test-token",
            max_retries=0,
        )
        respx.get(f"{EDA_API}/status/").mock(
            return_value=Response(500, json={"detail": "Internal server error"})
        )
        with pytest.raises(ServerError):
            await client.get("/status/")

    @pytest.mark.asyncio
    @respx.mock
    async def test_400_raises_lm_error(self, client):
        """400 response raises LMError with HTTP code."""
        respx.post(f"{EDA_API}/activations/").mock(
            return_value=Response(
                400, json={"name": ["This field may not be blank."]}
            )
        )
        with pytest.raises(LMError) as exc_info:
            await client.post(
                "/activations/", json_body={"name": ""}
            )
        assert exc_info.value.code == "HTTP_400"

    @pytest.mark.asyncio
    @respx.mock
    async def test_409_raises_lm_error(self, client):
        """409 response raises LMError with HTTP code."""
        respx.post(f"{EDA_API}/activations/42/restart/").mock(
            return_value=Response(409, json={"detail": "Activation already running."})
        )
        with pytest.raises(LMError) as exc_info:
            await client.post("/activations/42/restart/")
        assert exc_info.value.code == "HTTP_409"


class TestEdaClientRetry:
    """Tests for retry logic on transient errors."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_429(self):
        """Client retries on 429 and succeeds."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="test-token",
            max_retries=2,
        )
        route = respx.get(f"{EDA_API}/activations/").mock(
            side_effect=[
                Response(429, json={"detail": "Throttled"}),
                Response(200, json={"count": 1, "results": []}),
            ]
        )
        result = await client.get("/activations/")
        assert result == {"count": 1, "results": []}
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_500(self):
        """Client retries on 500 and succeeds."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="test-token",
            max_retries=2,
        )
        route = respx.get(f"{EDA_API}/status/").mock(
            side_effect=[
                Response(500, json={"detail": "Server error"}),
                Response(200, json={"status": "ready"}),
            ]
        )
        result = await client.get("/status/")
        assert result["status"] == "ready"
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_exhausted_retries_raises(self):
        """Client raises after all retries exhausted."""
        client = EdaClient(
            base_url=EDA_BASE,
            token="test-token",
            max_retries=1,
        )
        respx.get(f"{EDA_API}/activations/").mock(
            side_effect=[
                Response(429, json={"detail": "Throttled"}),
                Response(429, json={"detail": "Throttled"}),
            ]
        )
        with pytest.raises(RateLimitError):
            await client.get("/activations/")


class TestEdaClientConnectionError:
    """Tests for connection failure handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_connection_error_raises(self, client):
        """Connection failure raises LMConnectionError."""
        import httpx

        respx.get(f"{EDA_API}/status/").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(LMConnectionError):
            await client.get("/status/")


class TestEdaClientClose:
    """Tests for client cleanup."""

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Client close does not raise."""
        await client.close()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Client works as async context manager."""
        async with EdaClient(
            base_url=EDA_BASE,
            token="test-token",
        ) as client:
            assert client.token == "test-token"
