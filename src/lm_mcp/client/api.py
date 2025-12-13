# Description: LogicMonitor API client for making authenticated requests.
# Description: Handles HTTP communication, error mapping, and response parsing.

import json

import httpx

from lm_mcp.auth import AuthProvider
from lm_mcp.exceptions import (
    AuthenticationError,
    LMConnectionError,
    LMPermissionError,
    NotFoundError,
    RateLimitError,
    ServerError,
)


class LogicMonitorClient:
    """Async HTTP client for LogicMonitor REST API.

    Handles authentication, request building, and error mapping.
    Use as async context manager for proper resource cleanup.
    """

    def __init__(
        self,
        base_url: str,
        auth: AuthProvider,
        timeout: int = 30,
        api_version: int = 3,
    ):
        """Initialize the client.

        Args:
            base_url: LogicMonitor API base URL (e.g., https://company.logicmonitor.com/santaba/rest)
            auth: Authentication provider for generating auth headers.
            timeout: Request timeout in seconds.
            api_version: LogicMonitor API version.
        """
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.api_version = api_version
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "LogicMonitorClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context manager and close client."""
        await self.close()

    def _get_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Build request headers including auth.

        Args:
            method: HTTP method.
            path: API resource path.
            body: Request body string for signature calculation.

        Returns:
            Dict of headers for the request.
        """
        headers = {
            "Content-Type": "application/json",
            "X-Version": str(self.api_version),
        }
        headers.update(self.auth.get_auth_headers(method, path, body))
        return headers

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Raise appropriate exception for error responses.

        Args:
            response: The HTTP response to check.

        Raises:
            AuthenticationError: For 401 responses.
            LMPermissionError: For 403 responses.
            NotFoundError: For 404 responses.
            RateLimitError: For 429 responses.
            ServerError: For 5xx responses.
        """
        status = response.status_code

        try:
            error_data = response.json()
            message = error_data.get("errorMessage", response.text)
        except (json.JSONDecodeError, ValueError):
            message = response.text

        if status == 401:
            raise AuthenticationError(message)
        elif status == 403:
            raise LMPermissionError(message)
        elif status == 404:
            raise NotFoundError(message)
        elif status == 429:
            retry_after = None
            if "Retry-After" in response.headers:
                try:
                    retry_after = int(response.headers["Retry-After"])
                except ValueError:
                    pass
            raise RateLimitError(message, retry_after=retry_after)
        elif status >= 500:
            raise ServerError(message)

    async def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        """Make an authenticated request to the LogicMonitor API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API resource path (e.g., /alert/alerts).
            params: Query parameters.
            json_body: JSON body for POST/PUT/PATCH requests.

        Returns:
            Parsed JSON response as dict.

        Raises:
            LMConnectionError: If connection fails.
            AuthenticationError: For 401 responses.
            LMPermissionError: For 403 responses.
            NotFoundError: For 404 responses.
            RateLimitError: For 429 responses.
            ServerError: For 5xx responses.
        """
        url = f"{self.base_url}{path}"
        body_str = json.dumps(json_body) if json_body else ""
        headers = self._get_headers(method, path, body_str)

        try:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.ConnectError as e:
            raise LMConnectionError(f"Failed to connect to {self.base_url}: {e}")

        if response.status_code >= 400:
            self._handle_error_response(response)

        return response.json()

    async def get(self, path: str, params: dict | None = None) -> dict:
        """Make a GET request.

        Args:
            path: API resource path.
            params: Query parameters.

        Returns:
            Parsed JSON response.
        """
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json_body: dict | None = None) -> dict:
        """Make a POST request.

        Args:
            path: API resource path.
            json_body: JSON body.

        Returns:
            Parsed JSON response.
        """
        return await self.request("POST", path, json_body=json_body)

    async def put(self, path: str, json_body: dict | None = None) -> dict:
        """Make a PUT request.

        Args:
            path: API resource path.
            json_body: JSON body.

        Returns:
            Parsed JSON response.
        """
        return await self.request("PUT", path, json_body=json_body)

    async def patch(self, path: str, json_body: dict | None = None) -> dict:
        """Make a PATCH request.

        Args:
            path: API resource path.
            json_body: JSON body.

        Returns:
            Parsed JSON response.
        """
        return await self.request("PATCH", path, json_body=json_body)

    async def delete(self, path: str, params: dict | None = None) -> dict:
        """Make a DELETE request.

        Args:
            path: API resource path.
            params: Query parameters.

        Returns:
            Parsed JSON response.
        """
        return await self.request("DELETE", path, params=params)
