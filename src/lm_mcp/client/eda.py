# Description: EDA Controller API client for event-driven automation workflows.
# Description: Handles HTTP communication, error mapping, and retry logic for EDA REST API.

from __future__ import annotations

import asyncio
import json
import random
import time

import httpx

from lm_mcp.exceptions import (
    AuthenticationError,
    LMConnectionError,
    LMError,
    LMPermissionError,
    NotFoundError,
    RateLimitError,
    ServerError,
)
from lm_mcp.logging import log_api_request, log_api_response


class EdaClient:
    """Async HTTP client for EDA Controller REST API v1.

    Handles Bearer token authentication, request building, error mapping,
    and retry logic with exponential backoff. Mirrors the AwxClient
    pattern for consistency.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 30,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ):
        """Initialize the EDA client.

        Args:
            base_url: EDA Controller base URL (e.g., https://eda.example.com).
            token: OAuth2 Bearer token for authentication.
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts for transient errors.
            verify_ssl: Whether to verify SSL certificates.
        """
        self.base_url = base_url.rstrip("/") + "/api/eda/v1"
        self.token = token
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        self._client = httpx.AsyncClient(timeout=timeout, verify=verify_ssl)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> EdaClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context manager and close client."""
        await self.close()

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with Bearer auth.

        Returns:
            Dict of headers for EDA API requests.
        """
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _parse_error_response(self, response: httpx.Response) -> str:
        """Parse error message from EDA response.

        EDA uses 'detail' for most errors, but some endpoints return
        field-level errors as dicts.

        Args:
            response: The HTTP response to parse.

        Returns:
            Error message string.
        """
        try:
            error_data = response.json()
            if isinstance(error_data, dict):
                if "detail" in error_data:
                    return str(error_data["detail"])
                return json.dumps(error_data)
            return str(error_data)
        except (json.JSONDecodeError, ValueError):
            return response.text

    def _raise_for_status(self, response: httpx.Response, message: str) -> None:
        """Raise appropriate exception for error responses.

        Args:
            response: The HTTP response to check.
            message: Parsed error message.

        Raises:
            AuthenticationError: For 401 responses.
            LMPermissionError: For 403 responses.
            NotFoundError: For 404 responses.
            RateLimitError: For 429 responses.
            ServerError: For 5xx responses.
            LMError: For other 4xx responses.
        """
        status = response.status_code

        if status == 401:
            raise AuthenticationError(
                message,
                suggestion="Check your EDA_TOKEN. Generate a new token in EDA "
                "Controller under User > Tokens.",
            )
        elif status == 403:
            raise LMPermissionError(
                message,
                suggestion="Your EDA token lacks required permissions. "
                "Check the token's scope and user role in EDA Controller.",
            )
        elif status == 404:
            raise NotFoundError(
                message,
                suggestion="The EDA resource does not exist. Verify the ID is correct.",
            )
        elif status == 429:
            raise RateLimitError(message)
        elif status >= 500:
            raise ServerError(
                message,
                suggestion="EDA Controller returned a server error. Check EDA service health.",
            )
        elif 400 <= status < 500:
            raise LMError(
                message=message,
                code=f"HTTP_{status}",
                suggestion=f"EDA API returned HTTP {status}. "
                "Check the request parameters.",
            )

    async def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        """Make an authenticated request to the EDA API with retry.

        Implements exponential backoff for rate-limited (429) and server
        error (5xx) responses.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: API resource path (e.g., /activations/).
            params: Query parameters.
            json_body: JSON body for POST requests.

        Returns:
            Parsed JSON response as dict.

        Raises:
            LMConnectionError: If connection fails.
            AuthenticationError: For 401 responses.
            LMPermissionError: For 403 responses.
            NotFoundError: For 404 responses.
            RateLimitError: For 429 responses after retries exhausted.
            ServerError: For 5xx responses after retries exhausted.
        """
        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        log_api_request(method, path, params)

        last_message = "Rate limited"

        for attempt in range(self.max_retries + 1):
            request_start = time.monotonic()
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
            except httpx.ConnectError as e:
                raise LMConnectionError(
                    f"Failed to connect to EDA Controller at {self.base_url}: {e}"
                )

            # Retry on rate limit (429) or server errors (5xx)
            if response.status_code == 429 or response.status_code >= 500:
                last_message = self._parse_error_response(response)
                if attempt < self.max_retries:
                    base_backoff = 2**attempt
                    jitter = random.uniform(0, 0.5 * base_backoff)
                    wait_time = base_backoff + jitter
                    await asyncio.sleep(wait_time)
                    continue

            # Handle error responses
            if response.status_code >= 400:
                message = self._parse_error_response(response)
                self._raise_for_status(response, message)

            elapsed = time.monotonic() - request_start
            log_api_response(response.status_code, elapsed, path)

            # Handle 204 No Content (DELETE responses)
            if response.status_code == 204:
                return {}

            # Handle non-JSON responses (e.g., log output)
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return {"text": response.text}

            return response.json()

        # All retries exhausted on 429/5xx
        if last_message:
            raise RateLimitError(last_message)
        raise RateLimitError("Request failed after retries")

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

    async def delete(self, path: str, params: dict | None = None) -> dict:
        """Make a DELETE request.

        Args:
            path: API resource path.
            params: Query parameters.

        Returns:
            Parsed JSON response (empty dict for 204).
        """
        return await self.request("DELETE", path, params=params)
