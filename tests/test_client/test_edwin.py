# Description: Tests for the Edwin AI client: settings, token exchange and cache, error mapping.
# Description: Shapes are copied from the 2026-11-10 probe of lmryanmatuszewski.dexda.ai.

import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from lm_mcp.client import edwin
from lm_mcp.client.edwin import EdwinClient, build_edwin_client, required_scope
from lm_mcp.edwin_config import load_edwin_config
from lm_mcp.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ScopeMissingError,
    ServerError,
    ValidationError,
)
from lm_mcp.tools import error_from_exception

HOST = "https://lmryanmatuszewski.dexda.ai"
CLIENT_ID = "edwin-client-id-fixture"
CLIENT_SECRET = "edwin-secret-fix"  # 16 characters, under the staged-secret scan
JWT_1 = "eyJhbGciOiJSUzI1NiJ9.first-fixture-token.sig"
JWT_2 = "eyJhbGciOiJSUzI1NiJ9.second-fixture-token.sig"


def token_response(jwt: str) -> httpx.Response:
    """The token exchange's 200 body.

    Keys and expires_in from the probe of POST /auth/token on
    lmryanmatuszewski.dexda.ai, 2026-11-10 (docs/validation/probes-2026-11.md,
    Step 53); the token, expires_at and now values are replaced.
    """
    return httpx.Response(
        200,
        json={
            "access_token": jwt,
            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "token_type": "Bearer",
            "expires_in": 1799,
            "expires_at": 1794340000000,
            "now": 1794338201000,
        },
    )


# Error bodies from the same probe, 2026-11-10.
BODY_401 = {
    "code": 401,
    "message": "HTTP 401 Unauthorized",
    "id": "f0a9336010487ef039bfe9011d49b609-aa9588f51f20466e",
}
BODY_403 = {
    "code": 403,
    "message": "User not authorized.",
    "id": "40d471e067f52571fc3b6968845efc09-27875ebf58a0f013",
}
BODY_404 = {
    "code": 404,
    "message": "Record not found",
    "id": "ea0ec09740098361e17d76db82e1b5d5-918b90c8c4cc5e34",
}
BODY_EXCHANGE_REFUSED = {"error": "access_denied"}


def envelope(error: Exception) -> dict:
    """The R2.7 error envelope a tool would return for this exception."""
    return json.loads(error_from_exception(error)[0].text)["error"]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip retry backoff waits."""

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr("lm_mcp.client._retry.asyncio.sleep", fake_sleep)


@pytest.fixture
def clock(monkeypatch):
    """A monotonic clock the test advances by hand."""
    now = {"t": 1000.0}
    monkeypatch.setattr(edwin, "monotonic", lambda: now["t"])
    return now


@pytest.fixture
def client():
    return EdwinClient(HOST, CLIENT_ID, CLIENT_SECRET, timeout=30, max_retries=1)


@pytest.fixture
def edwin_env(monkeypatch):
    """A single-portal LM env with no Edwin variables, whatever the shell carries."""
    monkeypatch.setenv("LM_PORTAL", "lmryanmatuszewski.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "lm-bearer-token-fixture")
    for name in ("EDWIN_CLIENT_ID", "EDWIN_CLIENT_TOKEN", "EDWIN_HOST"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestTokenExchange:
    @respx.mock
    async def test_exchange_posts_form_encoded_client_credentials(self, client):
        token = respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        data = respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json={}))

        assert await client.get("/metadata") == {}

        sent = token.calls.last.request
        assert sent.headers["content-type"] == "application/x-www-form-urlencoded"
        assert parse_qs(sent.content.decode()) == {
            "grant_type": ["client_credentials"],
            "client_id": [CLIENT_ID],
            "client_secret": [CLIENT_SECRET],
        }
        assert "authorization" not in sent.headers
        assert data.calls.last.request.headers["authorization"] == f"Bearer {JWT_1}"

    @respx.mock
    async def test_second_call_within_window_makes_no_exchange(self, client, clock):
        token = respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        data = respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json={}))

        await client.get("/metadata")
        clock["t"] += 1799 - 61
        await client.get("/metadata")

        assert token.call_count == 1
        assert data.calls.last.request.headers["authorization"] == f"Bearer {JWT_1}"

    @respx.mock
    async def test_call_60s_before_expiry_refreshes(self, client, clock):
        token = respx.post(f"{HOST}/auth/token")
        token.side_effect = [token_response(JWT_1), token_response(JWT_2)]
        data = respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json={}))

        await client.get("/metadata")
        clock["t"] += 1799 - 60
        await client.get("/metadata")

        assert token.call_count == 2
        assert data.calls.last.request.headers["authorization"] == f"Bearer {JWT_2}"

    @respx.mock
    async def test_refused_exchange_is_auth_failed(self, client):
        respx.post(f"{HOST}/auth/token").mock(
            return_value=httpx.Response(401, json=BODY_EXCHANGE_REFUSED)
        )
        data = respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json={}))

        with pytest.raises(AuthenticationError) as caught:
            await client.get("/metadata")

        assert data.call_count == 0
        body = envelope(caught.value)
        assert body["code"] == "AUTH_FAILED"
        assert "access_denied" in body["message"]
        assert "EDWIN_CLIENT_ID" in body["message"]

    @respx.mock
    async def test_401_mid_call_refreshes_once_and_retries(self, client):
        token = respx.post(f"{HOST}/auth/token")
        token.side_effect = [token_response(JWT_1), token_response(JWT_2)]
        data = respx.get(f"{HOST}/metadata")
        data.side_effect = [
            httpx.Response(401, json=BODY_401),
            httpx.Response(200, json={"types": []}),
        ]

        assert await client.get("/metadata") == {"types": []}

        assert token.call_count == 2
        assert data.calls[0].request.headers["authorization"] == f"Bearer {JWT_1}"
        assert data.calls[1].request.headers["authorization"] == f"Bearer {JWT_2}"

    @respx.mock
    async def test_second_401_is_auth_failed(self, client):
        token = respx.post(f"{HOST}/auth/token")
        token.side_effect = [token_response(JWT_1), token_response(JWT_2)]
        data = respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(401, json=BODY_401))

        with pytest.raises(AuthenticationError) as caught:
            await client.get("/metadata")

        assert token.call_count == 2
        assert data.call_count == 2
        body = envelope(caught.value)
        assert body["code"] == "AUTH_FAILED"
        assert body["errorCategory"] == "permission"
        assert body["details"]["lm_message"] == "HTTP 401 Unauthorized"

    @respx.mock
    async def test_neither_credential_nor_token_reaches_the_log(self, client, caplog):
        respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(200, json={}))

        with caplog.at_level(logging.DEBUG):
            await client.get("/metadata")

        assert "/metadata" in caplog.text
        for secret in (CLIENT_SECRET, JWT_1):
            assert secret not in caplog.text


class TestScopeTable:
    @pytest.mark.parametrize(
        ("path", "scope"),
        [
            ("/ui/query/metrics", "query_aggregate"),
            ("/ui/query/records", "query_records"),
            ("/ui/query/record/insights/68f0c2e1a7", "query_record"),
            ("/metadata", None),
        ],
    )
    def test_required_scope(self, path, scope):
        assert required_scope(path) == scope

    @respx.mock
    async def test_403_is_scope_missing_naming_the_table_scope(self, client):
        respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        respx.post(f"{HOST}/ui/query/metrics").mock(return_value=httpx.Response(403, json=BODY_403))

        with pytest.raises(ScopeMissingError) as caught:
            await client.post("/ui/query/metrics", json_body={"source": "alerts"})

        assert caught.value.scope == "query_aggregate"
        body = envelope(caught.value)
        assert body["code"] == "SCOPE_MISSING"
        assert body["errorCategory"] == "permission"
        assert body["isRetryable"] is False
        assert "query_aggregate" in body["message"]
        assert "POST /ui/query/metrics" in body["message"]
        assert body["details"]["lm_message"] == "User not authorized."

    @respx.mock
    async def test_403_outside_the_table_is_scope_missing_without_a_scope(self, client):
        respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        respx.get(f"{HOST}/metadata").mock(return_value=httpx.Response(403, json=BODY_403))

        with pytest.raises(ScopeMissingError) as caught:
            await client.get("/metadata")

        assert caught.value.scope is None
        body = envelope(caught.value)
        assert body["code"] == "SCOPE_MISSING"
        assert "GET /metadata" in body["message"]


class TestErrorMapping:
    @respx.mock
    async def test_404_is_not_found(self, client):
        respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        respx.get(f"{HOST}/ui/query/record/insights/does-not-exist").mock(
            return_value=httpx.Response(404, json=BODY_404)
        )

        with pytest.raises(NotFoundError) as caught:
            await client.get("/ui/query/record/insights/does-not-exist")

        assert envelope(caught.value)["code"] == "NOT_FOUND"
        assert "Record not found" in caught.value.message

    @respx.mock
    async def test_429_is_rate_limited_after_the_retry(self, client):
        respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        data = respx.get(f"{HOST}/metadata").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "7"})
        )

        with pytest.raises(RateLimitError) as caught:
            await client.get("/metadata")

        assert data.call_count == 2
        assert caught.value.retry_after == 7
        assert envelope(caught.value)["code"] == "RATE_LIMITED"

    @respx.mock
    async def test_post_5xx_is_upstream_error_and_not_resent(self, client):
        respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))
        data = respx.post(f"{HOST}/ui/query/records").mock(return_value=httpx.Response(502))

        with pytest.raises(ServerError) as caught:
            await client.post("/ui/query/records", json_body={"source": "insights"})

        assert data.call_count == 1
        assert envelope(caught.value)["code"] == "UPSTREAM_ERROR"

    @respx.mock
    async def test_path_escape_is_refused_before_any_request(self, client):
        token = respx.post(f"{HOST}/auth/token").mock(return_value=token_response(JWT_1))

        with pytest.raises(ValidationError):
            await client.get("/ui/query/record/insights/../../metadata")

        assert token.call_count == 0


class TestConfig:
    def test_both_credentials_unset_means_no_client(self, edwin_env):
        assert load_edwin_config() is None
        assert build_edwin_client("lmryanmatuszewski.logicmonitor.com") is None

    @pytest.mark.parametrize(
        ("present", "missing"),
        [("EDWIN_CLIENT_ID", "EDWIN_CLIENT_TOKEN"), ("EDWIN_CLIENT_TOKEN", "EDWIN_CLIENT_ID")],
    )
    def test_one_credential_set_logs_the_missing_one(self, edwin_env, caplog, present, missing):
        edwin_env.setenv(present, "half-set-credential-value")

        with caplog.at_level(logging.WARNING):
            assert build_edwin_client("lmryanmatuszewski.logicmonitor.com") is None

        assert missing in caplog.text
        assert "half-set-credential-value" not in caplog.text

    def test_host_is_derived_from_the_portal_name(self, edwin_env):
        edwin_env.setenv("EDWIN_CLIENT_ID", CLIENT_ID)
        edwin_env.setenv("EDWIN_CLIENT_TOKEN", CLIENT_SECRET)

        client = build_edwin_client("lmryanmatuszewski.logicmonitor.com")

        assert client is not None
        assert client.host == HOST

    @respx.mock
    async def test_edwin_host_overrides_the_derived_host(self, edwin_env):
        edwin_env.setenv("EDWIN_CLIENT_ID", CLIENT_ID)
        edwin_env.setenv("EDWIN_CLIENT_TOKEN", CLIENT_SECRET)
        edwin_env.setenv("EDWIN_HOST", "https://edwin.example.test/")
        token = respx.post("https://edwin.example.test/auth/token").mock(
            return_value=token_response(JWT_1)
        )
        data = respx.get("https://edwin.example.test/metadata").mock(
            return_value=httpx.Response(200, json={})
        )

        client = build_edwin_client("lmryanmatuszewski.logicmonitor.com")
        assert client is not None
        await client.get("/metadata")

        assert client.host == "https://edwin.example.test"
        assert token.call_count == 1
        assert data.call_count == 1

    def test_plain_http_edwin_host_is_refused(self, edwin_env, caplog):
        edwin_env.setenv("EDWIN_CLIENT_ID", CLIENT_ID)
        edwin_env.setenv("EDWIN_CLIENT_TOKEN", CLIENT_SECRET)
        edwin_env.setenv("EDWIN_HOST", "http://edwin.example.test")

        with caplog.at_level(logging.WARNING):
            assert build_edwin_client("lmryanmatuszewski.logicmonitor.com") is None

        assert "EDWIN_HOST" in caplog.text
        (record,) = [r for r in caplog.records if r.name == "lm_mcp.edwin_config"]
        assert record.exc_info is not None
        assert CLIENT_SECRET not in caplog.text
        assert "http://edwin.example.test" not in caplog.text

    def test_settings_come_from_the_lm_config(self, edwin_env):
        edwin_env.setenv("EDWIN_CLIENT_ID", CLIENT_ID)
        edwin_env.setenv("EDWIN_CLIENT_TOKEN", CLIENT_SECRET)
        edwin_env.setenv("LM_MAX_RETRIES", "5")

        client = build_edwin_client("lmryanmatuszewski.logicmonitor.com")

        assert client is not None
        assert client.max_retries == 5
