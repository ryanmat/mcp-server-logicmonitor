# Description: Tests for LogicMonitor API client.
# Description: Uses respx to mock HTTP responses for testing.

import pytest
import respx
from httpx import Response


class TestLogicMonitorClientInit:
    """Tests for client initialization."""

    def test_client_stores_config(self):
        """Client stores base_url and auth provider."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        auth = BearerAuth("test_token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
            timeout=60,
            api_version=3,
        )

        assert client.base_url == "https://test.logicmonitor.com/santaba/rest"
        assert client.auth == auth
        assert client.api_version == 3

    def test_client_strips_trailing_slash(self):
        """Client removes trailing slash from base_url."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        auth = BearerAuth("test_token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest/",
            auth=auth,
        )

        assert client.base_url == "https://test.logicmonitor.com/santaba/rest"


class TestLogicMonitorClientHeaders:
    """Tests for header generation."""

    def test_get_headers_includes_content_type(self):
        """Headers include Content-Type."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        auth = BearerAuth("test_token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        )

        headers = client._get_headers("GET", "/alert/alerts")
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_includes_api_version(self):
        """Headers include X-Version."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        auth = BearerAuth("test_token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
            api_version=3,
        )

        headers = client._get_headers("GET", "/alert/alerts")
        assert headers["X-Version"] == "3"

    def test_get_headers_includes_auth(self):
        """Headers include Authorization from auth provider."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        auth = BearerAuth("my_token")
        client = LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        )

        headers = client._get_headers("GET", "/alert/alerts")
        assert headers["Authorization"] == "Bearer my_token"


class TestLogicMonitorClientRequests:
    """Tests for making HTTP requests."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_request_success(self):
        """Successful GET request returns parsed JSON."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=Response(200, json={"items": [{"id": 1}], "total": 1})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            result = await client.get("/alert/alerts")

        assert result == {"items": [{"id": 1}], "total": 1}

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_request_success(self):
        """Successful POST request with JSON body."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=Response(200, json={"id": 123, "type": "DeviceSDT"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            result = await client.post("/sdt/sdts", json_body={"type": "DeviceSDT"})

        assert result == {"id": 123, "type": "DeviceSDT"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_with_params(self):
        """GET request with query parameters."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        route = respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=Response(200, json={"items": [], "total": 0})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            await client.get("/alert/alerts", params={"size": 10, "offset": 0})

        assert route.called
        assert "size=10" in str(route.calls.last.request.url)


class TestLogicMonitorClientErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_authentication_error(self):
        """401 response raises AuthenticationError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import AuthenticationError

        respx.get("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(401, json={"errorMessage": "Auth failed"})
        )

        auth = BearerAuth("bad_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(AuthenticationError):
                await client.get("/test")

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_raises_permission_error(self):
        """403 response raises LMPermissionError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMPermissionError

        respx.get("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(403, json={"errorMessage": "Forbidden"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMPermissionError):
                await client.get("/test")

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_raises_not_found_error(self):
        """404 response raises NotFoundError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import NotFoundError

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/999").mock(
            return_value=Response(404, json={"errorMessage": "Not found"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(NotFoundError):
                await client.get("/device/devices/999")

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_raises_rate_limit_error(self):
        """429 response raises RateLimitError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import RateLimitError

        respx.get("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(
                429,
                json={"errorMessage": "Rate limited"},
                headers={"Retry-After": "60"},
            )
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(RateLimitError) as exc_info:
                await client.get("/test")

        assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    @respx.mock
    async def test_500_raises_server_error(self):
        """500 response raises ServerError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import ServerError

        respx.get("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(500, json={"errorMessage": "Internal error"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(ServerError):
                await client.get("/test")

    @pytest.mark.asyncio
    @respx.mock
    async def test_connection_error_raises_lm_connection_error(self):
        """Connection error raises LMConnectionError."""
        import httpx

        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMConnectionError

        respx.get("https://test.logicmonitor.com/santaba/rest/test").mock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMConnectionError):
                await client.get("/test")


class TestUnhandled4xx:
    """Tests for unhandled 4xx status codes (400, 405, 409, 415, etc.)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_400_raises_lm_error(self):
        """400 Bad Request raises LMError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMError

        respx.post("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(400, json={"errorMessage": "Invalid request body"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMError, match="Invalid request body") as exc_info:
                await client.post("/test", json_body={"bad": "data"})

        assert exc_info.value.code == "HTTP_400"

    @pytest.mark.asyncio
    @respx.mock
    async def test_409_raises_lm_error(self):
        """409 Conflict raises LMError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMError

        respx.post("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(409, json={"errorMessage": "Resource conflict"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMError, match="Resource conflict") as exc_info:
                await client.post("/test", json_body={"name": "duplicate"})

        assert exc_info.value.code == "HTTP_409"

    @pytest.mark.asyncio
    @respx.mock
    async def test_415_raises_lm_error(self):
        """415 Unsupported Media Type raises LMError."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMError

        respx.post("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(
                415, json={"errorMessage": "Unsupported media type"}
            )
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMError, match="Unsupported media type") as exc_info:
                await client.post("/test", json_body={"data": "test"})

        assert exc_info.value.code == "HTTP_415"

    @pytest.mark.asyncio
    @respx.mock
    async def test_4xx_error_includes_suggestion(self):
        """Unhandled 4xx errors include helpful suggestion text."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMError

        respx.post("https://test.logicmonitor.com/santaba/rest/test").mock(
            return_value=Response(405, json={"errorMessage": "Method not allowed"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMError) as exc_info:
                await client.post("/test", json_body={})

        assert "HTTP 405" in exc_info.value.suggestion


class TestLogicMonitorClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """Context manager closes the HTTP client."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        auth = BearerAuth("test_token")

        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            assert client._client is not None

        assert client._client.is_closed


class TestPostMultipart:
    """Tests for post_multipart method (multipart/form-data uploads)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_multipart_sends_file_upload(self):
        """post_multipart sends definition as multipart file upload."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/importjson"
        ).mock(
            return_value=Response(
                200,
                json={"id": 1001, "name": "TestDS"},
            )
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            result = await client.post_multipart(
                "/setting/datasources/importjson",
                definition={"name": "TestDS", "appliesTo": "isLinux()"},
            )

        assert result == {"id": 1001, "name": "TestDS"}
        assert route.called
        request = route.calls[0].request
        content_type = request.headers.get("content-type", "")
        assert "multipart/form-data" in content_type

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_multipart_does_not_send_json_content_type(self):
        """post_multipart does not set Content-Type to application/json."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/eventsources/importjson"
        ).mock(
            return_value=Response(200, json={"id": 2001, "name": "TestES"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            await client.post_multipart(
                "/setting/eventsources/importjson",
                definition={"name": "TestES"},
            )

        request = route.calls[0].request
        content_type = request.headers.get("content-type", "")
        assert "application/json" not in content_type

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_multipart_raises_on_error(self):
        """post_multipart raises appropriate exceptions on error status."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient
        from lm_mcp.exceptions import LMError

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/importjson"
        ).mock(
            return_value=Response(
                400, json={"errorMessage": "Invalid import format"}
            )
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            with pytest.raises(LMError, match="Invalid import format"):
                await client.post_multipart(
                    "/setting/datasources/importjson",
                    definition={"bad": "format"},
                )

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_multipart_includes_auth_header(self):
        """post_multipart includes Authorization header."""
        from lm_mcp.auth.bearer import BearerAuth
        from lm_mcp.client import LogicMonitorClient

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/importjson"
        ).mock(
            return_value=Response(200, json={"id": 1, "name": "DS"})
        )

        auth = BearerAuth("test_token")
        async with LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=auth,
        ) as client:
            await client.post_multipart(
                "/setting/datasources/importjson",
                definition={"name": "DS"},
            )

        request = route.calls[0].request
        assert "Bearer test_token" in request.headers.get("authorization", "")
