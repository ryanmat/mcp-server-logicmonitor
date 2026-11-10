# Description: Tests for ask_edwin against a local websockets server replaying Edwin frames.
# Description: The frames are the 2026-11-07 capture of wss://lmryanmatuszewski.dexda.ai/ws/lm.

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from websockets.asyncio.server import serve

from lm_mcp.client.edwin import EdwinClient
from lm_mcp.tools import edwin as edwin_tools
from lm_mcp.tools.edwin import ask_edwin

# edwin-samples/edwin-ws-conversation.jsonl, copied verbatim: a header naming the probe
# and the message sent, then the 69 frames Edwin answered "which collectors are down" with
# (61 answer_thought, 7 answer_token, 1 response_end).
_LINES = (Path(__file__).parent.parent / "fixtures" / "edwin_ws_conversation.jsonl").read_text()
HEADER, *FRAMES = [line for line in _LINES.splitlines() if line.strip()]
QUESTION = json.loads(HEADER)["sent"]["message"]
PARSED = [json.loads(frame) for frame in FRAMES]
ANSWER = "".join(f["message"] for f in PARSED if f["type"] == "answer_token")
REASONING = "".join(f["message"] for f in PARSED if f["type"] == "answer_thought")
TRACE_ID = "87012a12ee47e22c858cd7537fc0aecf"

# POST /api/conversations with {} on lmryanmatuszewski.dexda.ai, 2026-11-10
# (docs/validation/probes-2026-11.md, Step 57).
CREATED = {
    "conversationId": "38d93fe7-6153-4caa-bf84-e5223f38e912",
    "orgId": "lmryanmatuszewski",
    "userId": "4454103f-2ae0-4851-a575-a4af1f498131",
    "status": "active",
    "createdAt": "2026-11-10T19:37:29.075655+00:00",
    "updatedAt": "2026-11-10T19:37:29.075655+00:00",
    "title": None,
}
JWT = "eyJhbGciOiJSUzI1NiJ9.ws-fixture-token.sig"

# Index of the frame after the third answer_token, where the partial replays stop.
_THIRD_TOKEN = [i for i, f in enumerate(PARSED) if f["type"] == "answer_token"][2] + 1


class EdwinServer:
    """A local Edwin websocket endpoint: records the handshake and replays frames.

    ``frames`` is what it sends after the client's message, then ``ending`` decides
    what follows: ``wait`` for the client to close, or ``close`` with ``close_code``.
    """

    def __init__(self) -> None:
        self.frames: list[str] = FRAMES
        self.ending = "wait"
        self.close_code = 1000
        self.headers: list = []
        self.received: list[dict] = []
        self.port = 0

    async def handler(self, ws) -> None:
        self.headers.append(ws.request.headers)
        self.received.append(json.loads(await ws.recv()))
        for frame in self.frames:
            await ws.send(frame)
        if self.ending == "close":
            await ws.close(self.close_code)
        else:
            await ws.wait_closed()


# The test server's own logger stops at INFO: at DEBUG it logs the handshake headers it
# receives, the token among them, which the client-side log test must not read as a leak.
_server_logger = logging.getLogger("tests.edwin_ws.server")
_server_logger.setLevel(logging.INFO)


@pytest.fixture
async def edwin_server():
    server = EdwinServer()
    async with serve(
        server.handler,
        "127.0.0.1",
        0,
        select_subprotocol=lambda conn, offered: offered[0] if offered else None,
        logger=_server_logger,
    ) as running:
        server.port = running.sockets[0].getsockname()[1]
        yield server


@pytest.fixture
def client(edwin_server):
    """An Edwin client on the local server; respx answers its two HTTP calls."""
    host = f"http://127.0.0.1:{edwin_server.port}"
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{host}/auth/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": JWT, "token_type": "Bearer", "expires_in": 1799}
            )
        )
        created = router.post(f"{host}/api/conversations").mock(
            return_value=httpx.Response(200, json=CREATED)
        )
        yield EdwinClient(host, "edwin-client-id-fixture", "edwin-secret-fix"), created


def payload(result: list) -> dict:
    return json.loads(result[0].text)


async def test_a_full_conversation(edwin_server, client, caplog):
    edwin, created = client

    with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.edwin"):
        body = payload(await ask_edwin(edwin, question=QUESTION))

    assert [r for r in caplog.records if r.name == "lm_mcp.tools.edwin"] == []

    assert created.call_count == 1
    assert json.loads(created.calls.last.request.content) == {}
    (headers,) = edwin_server.headers
    assert headers["Sec-WebSocket-Protocol"] == JWT
    assert "Authorization" not in headers
    assert edwin_server.received == [
        {"conversationId": CREATED["conversationId"], "message": QUESTION}
    ]
    assert body == {
        "answer": ANSWER,
        "reasoning": REASONING,
        "conversation_id": CREATED["conversationId"],
        "langfuseTraceId": TRACE_ID,
        "truncated": False,
    }
    assert ANSWER.startswith("**Status:** Resolved")


async def test_a_conversation_id_continues_the_thread(edwin_server, client):
    edwin, created = client

    body = payload(
        await ask_edwin(edwin, question="and the collector groups?", conversation_id="c-1")
    )

    assert created.call_count == 0
    assert edwin_server.received == [
        {"conversationId": "c-1", "message": "and the collector groups?"}
    ]
    assert body["conversation_id"] == "c-1"
    assert body["truncated"] is False


async def test_an_early_close_returns_the_text_so_far(edwin_server, client, caplog):
    edwin, _ = client
    edwin_server.frames = FRAMES[:_THIRD_TOKEN]
    edwin_server.ending = "close"

    with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.edwin"):
        body = payload(await ask_edwin(edwin, question=QUESTION))

    tokens = [f["message"] for f in PARSED[:_THIRD_TOKEN] if f["type"] == "answer_token"]
    assert len(tokens) == 3
    assert body["answer"] == "".join(tokens)
    assert body["truncated"] is True
    (warning,) = [r for r in caplog.records if r.name == "lm_mcp.tools.edwin"]
    assert "before response_end" in warning.getMessage()
    assert "1000" in warning.getMessage()


async def test_the_budget_truncates(edwin_server, client, monkeypatch):
    edwin, _ = client
    monkeypatch.setattr(edwin_tools, "ASK_BUDGET_SECONDS", 0.2)
    edwin_server.frames = FRAMES[:_THIRD_TOKEN]

    body = payload(await asyncio.wait_for(ask_edwin(edwin, question=QUESTION), timeout=5))

    assert body["truncated"] is True
    assert body["answer"] == "".join(
        f["message"] for f in PARSED[:_THIRD_TOKEN] if f["type"] == "answer_token"
    )


async def test_a_1008_close_is_auth_failed(edwin_server, client):
    edwin, _ = client
    edwin_server.frames = []
    edwin_server.ending = "close"
    edwin_server.close_code = 1008

    body = payload(await ask_edwin(edwin, question=QUESTION))

    assert body["error"]["code"] == "AUTH_FAILED"
    assert "1008" in body["error"]["message"]


async def test_an_unreadable_frame_is_reported_and_logged(edwin_server, client, caplog):
    edwin, _ = client
    edwin_server.frames = ["not a json frame", *FRAMES]

    with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.edwin"):
        body = payload(await ask_edwin(edwin, question=QUESTION))

    assert body["unreadable"] == ["not a json frame"]
    assert body["answer"] == ANSWER
    assert body["truncated"] is False
    record = next(r for r in caplog.records if r.name == "lm_mcp.tools.edwin")
    assert record.exc_info is not None


async def test_the_token_never_reaches_the_log(edwin_server, client, caplog):
    edwin, _ = client

    with caplog.at_level(logging.DEBUG):
        await ask_edwin(edwin, question=QUESTION)

    assert JWT not in caplog.text
