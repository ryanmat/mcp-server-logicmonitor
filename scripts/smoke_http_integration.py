#!/usr/bin/env -S uv run --quiet python
# Description: Live smoke test for the Custom HTTP Delivery integration CRUD tools.
# Description: Creates a throwaway integration, reads it back, patches it, then deletes it.

"""One-shot smoke test for the v3.7.1 integration tools.

Run once post-merge against your portal to confirm end-to-end shape:

    $ LM_ENABLE_WRITE_OPERATIONS=true uv run python scripts/smoke_http_integration.py

The script creates an integration named ``mcp-smoke-<epoch>`` pointing at
``https://example.com/lm-mcp-smoke`` (the IANA-reserved example domain,
which resolves but ignores the POST), reads it back, patches the
description, then deletes it. LM does a DNS check on create and rejects
unroutable hosts like ``.invalid``, so this uses a resolvable but
harmless URL. Any failure prints the raw LM response and exits non-zero.

Requires LM_PORTAL and LM_BEARER_TOKEN in the environment (or .env).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Load .env when present so this works from the repo root without extra setup.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


async def main() -> int:
    portal = os.environ.get("LM_PORTAL")
    token = os.environ.get("LM_BEARER_TOKEN")
    if not portal or not token:
        print("LM_PORTAL and LM_BEARER_TOKEN must be set", file=sys.stderr)
        return 1
    if os.environ.get("LM_ENABLE_WRITE_OPERATIONS", "").lower() != "true":
        print(
            "LM_ENABLE_WRITE_OPERATIONS=true is required for this smoke test",
            file=sys.stderr,
        )
        return 1

    from lm_mcp.auth.bearer import BearerAuth
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.tools.integrations import (
        create_http_integration,
        delete_integration,
        get_integration,
        update_http_integration,
    )

    name = f"mcp-smoke-{int(time.time())}"
    client = LogicMonitorClient(
        base_url=f"https://{portal}/santaba/rest",
        auth=BearerAuth(token),
        timeout=30,
        api_version=3,
    )

    def _parse_tool_result(result, step):
        raw = result[0].text
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print(f"  {step} failed: {raw}", file=sys.stderr)
            raise SystemExit(1) from None

    try:
        print(f"create: {name}")
        result = await create_http_integration(
            client,
            name=name,
            url="https://example.com/lm-mcp-smoke",
            description="mcp-server-logicmonitor v3.7.1 smoke test - safe to delete",
            headers={"X-Test": "smoke"},
            alert_body='{"alertId":"##ALERTID##"}',
        )
        data = _parse_tool_result(result, "create")
        assert data.get("success"), data
        integration_id = data["integration_id"]
        print(f"  -> id={integration_id}")

        print("get:")
        got = json.loads((await get_integration(client, integration_id=integration_id))[0].text)
        assert got["name"] == name, got
        assert got["type"] == "http", got
        print(f"  -> name={got['name']} type={got['type']} url={got['url']}")

        print("patch description:")
        patched = json.loads(
            (
                await update_http_integration(
                    client,
                    integration_id=integration_id,
                    description="updated by smoke test",
                )
            )[0].text
        )
        assert patched.get("success"), patched
        print("  -> ok")

        print("delete:")
        deleted = json.loads(
            (await delete_integration(client, integration_id=integration_id))[0].text
        )
        assert deleted.get("success"), deleted
        print("  -> ok")
    finally:
        await client.close()

    print("smoke test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
