# Description: Creates the sandbox state the skill scenarios under evals/skills assume.
# Description: Idempotent, and it refuses every portal but the lmryanmatuszewski sandbox.

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

SANDBOX = "lmryanmatuszewski.logicmonitor.com"

# The device the lm-health and lm-remediate scenarios name. Its address sits in
# TEST-NET-1 (RFC 5737) and answers nothing, so the device never reports a metric.
# Collector 82 is rm-collector, the sandbox's own.
DEVICE_NAME = "lm-mcp-eval-host"
DEVICE_ADDRESS = "192.0.2.10"
COLLECTOR_ID = 82


async def ensure_state(client: LogicMonitorClient) -> str:
    """Find the eval device, or create it; return one line saying which."""
    found = await client.get(
        "/device/devices",
        params={"filter": f'displayName:"{DEVICE_NAME}"', "fields": "id,displayName"},
    )
    if found["items"]:
        return f"found {DEVICE_NAME} (id {found['items'][0]['id']})"
    created = await client.post(
        "/device/devices",
        json_body={
            "name": DEVICE_ADDRESS,
            "displayName": DEVICE_NAME,
            "preferredCollectorId": COLLECTOR_ID,
            "hostGroupIds": "1",
            "description": "Skill eval fixture, created by evals/skills/setup.py.",
        },
    )
    return f"created {DEVICE_NAME} (id {created['id']})"


async def main() -> int:
    """Read LM_PORTAL and the credentials from the environment or .env: 0 done, 2 refused."""
    from dotenv import load_dotenv

    from lm_mcp.client import build_client
    from lm_mcp.config import get_config

    load_dotenv(ROOT / ".env")
    config = get_config()
    if config.portal != SANDBOX:
        print(f"refusing to run against {config.portal}: sandbox only", file=sys.stderr)
        return 2
    client = build_client(
        config.portal,
        bearer_token=config.bearer_token,
        access_id=config.access_id,
        access_key=config.access_key,
    )
    async with client:
        print(await ensure_state(client))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
