# Description: LogicMonitor API client for making authenticated requests.
# Description: Handles HTTP communication, error mapping, and response parsing.

import asyncio
import json
import random

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

    Handles authentication, request building, error mapping, and retry logic.
    Use as async context manager for proper resource cleanup.
    """

    def __init__(
        self,
        base_url: str,
        auth: AuthProvider,
        timeout: int = 30,
        api_version: int = 3,
        max_retries: int = 3,
        ingest_url: str | None = None,
    ):
        """Initialize the client.

        Args:
            base_url: LogicMonitor API base URL (e.g., https://company.logicmonitor.com/santaba/rest)
            auth: Authentication provider for generating auth headers.
            timeout: Request timeout in seconds.
            api_version: LogicMonitor API version.
            max_retries: Maximum retry attempts for rate-limited requests.
            ingest_url: Base URL for ingestion APIs (e.g., https://company.logicmonitor.com).
        """
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.api_version = api_version
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(timeout=timeout)
        self.ingest_url = ingest_url.rstrip("/") if ingest_url else None

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

    def _parse_error_response(self, response: httpx.Response) -> tuple[str, int | None]:
        """Parse error message and retry-after from response.

        Args:
            response: The HTTP response to parse.

        Returns:
            Tuple of (error message, retry_after value or None).
        """
        try:
            error_data = response.json()
            message = error_data.get("errorMessage", response.text)
        except (json.JSONDecodeError, ValueError):
            message = response.text

        retry_after = None
        if "Retry-After" in response.headers:
            try:
                retry_after = int(response.headers["Retry-After"])
            except ValueError:
                pass

        return message, retry_after

    def _raise_for_status(
        self, response: httpx.Response, message: str, retry_after: int | None
    ) -> None:
        """Raise appropriate exception for error responses.

        Args:
            response: The HTTP response to check.
            message: Parsed error message.
            retry_after: Retry-After header value if present.

        Raises:
            AuthenticationError: For 401 responses.
            LMPermissionError: For 403 responses.
            NotFoundError: For 404 responses.
            RateLimitError: For 429 responses.
            ServerError: For 5xx responses.
        """
        status = response.status_code

        if status == 401:
            raise AuthenticationError(message)
        elif status == 403:
            raise LMPermissionError(message)
        elif status == 404:
            raise NotFoundError(message)
        elif status == 429:
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
        """Make an authenticated request to the LogicMonitor API with retry.

        Implements exponential backoff for rate-limited (429) responses.

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
            RateLimitError: For 429 responses after retries exhausted.
            ServerError: For 5xx responses.
        """
        url = f"{self.base_url}{path}"
        body_str = json.dumps(json_body) if json_body else ""
        headers = self._get_headers(method, path, body_str)

        last_retry_after: int | None = None
        last_message = "Rate limited"

        for attempt in range(self.max_retries + 1):
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

            # Retry on rate limit (429) or server errors (5xx)
            if response.status_code == 429 or response.status_code >= 500:
                message, retry_after = self._parse_error_response(response)
                last_message = message
                last_retry_after = retry_after

                if attempt < self.max_retries:
                    # Exponential backoff with jitter to prevent thundering herd
                    base_backoff = 2**attempt
                    jitter = random.uniform(0, 0.5 * base_backoff)
                    wait_time = base_backoff + jitter
                    if retry_after is not None:
                        wait_time = min(retry_after, wait_time)
                    await asyncio.sleep(wait_time)
                    continue

            if response.status_code >= 400:
                message, retry_after = self._parse_error_response(response)
                self._raise_for_status(response, message, retry_after)

            return response.json()

        raise RateLimitError(last_message, retry_after=last_retry_after)

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

    async def ingest_post(
        self,
        path: str,
        json_body: list | dict | None = None,
    ) -> dict:
        """Make a POST request to ingestion API.

        Uses the ingest_url base instead of the standard base_url.
        Ingestion APIs use paths like /rest/log/ingest.

        Args:
            path: Ingestion API path (e.g., /rest/log/ingest).
            json_body: JSON body (list of log entries or metric payload).

        Returns:
            Parsed JSON response.

        Raises:
            ConfigurationError: If ingest_url is not configured.
        """
        from lm_mcp.exceptions import ConfigurationError

        if not self.ingest_url:
            raise ConfigurationError(
                "Ingestion URL not configured. Set ingest_url when creating client."
            )

        url = f"{self.ingest_url}{path}"
        body_str = json.dumps(json_body) if json_body else ""

        # Build headers with auth for the ingest path
        headers = {
            "Content-Type": "application/json",
        }
        headers.update(self.auth.get_auth_headers("POST", path, body_str))

        last_retry_after: int | None = None
        last_message = "Rate limited"

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method="POST",
                    url=url,
                    json=json_body,
                    headers=headers,
                )
            except httpx.ConnectError as e:
                raise LMConnectionError(f"Failed to connect to {self.ingest_url}: {e}")

            # Retry on rate limit (429) or server errors (5xx)
            if response.status_code == 429 or response.status_code >= 500:
                message, retry_after = self._parse_error_response(response)
                last_message = message
                last_retry_after = retry_after

                if attempt < self.max_retries:
                    base_backoff = 2**attempt
                    jitter = random.uniform(0, 0.5 * base_backoff)
                    wait_time = base_backoff + jitter
                    if retry_after is not None:
                        wait_time = min(retry_after, wait_time)
                    await asyncio.sleep(wait_time)
                    continue

            # Handle 202 Accepted (success for ingestion)
            if response.status_code == 202:
                try:
                    return response.json()
                except (json.JSONDecodeError, ValueError):
                    return {"success": True, "message": "Accepted"}

            if response.status_code >= 400:
                message, retry_after = self._parse_error_response(response)
                self._raise_for_status(response, message, retry_after)

            return response.json()

        raise RateLimitError(last_message, retry_after=last_retry_after)
