# Description: Paged device instance data responses in the live endpoint's shape, for the readers.
# Description: Rows newest first, times in milliseconds, each page naming the next one.

from __future__ import annotations

import time

import httpx

from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES


def _page(times_ms: list[int], next_page: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "dataSourceName": "CPU",
            "dataPoints": ["CPUBusyPercent"],
            "values": [[float(i % 100)] for i in range(len(times_ms))],
            "time": times_ms,
            "nextPageParams": next_page,
        },
    )


def day_of_minutes() -> list[httpx.Response]:
    """A 24-hour window of 1,440 one-minute samples, newest first, served as two pages."""
    now = int(time.time())
    times = [(now - 60 * i) * 1000 for i in range(1440)]
    newer, older = times[:720], times[720:]
    return [
        _page(newer, f"start={now - 86400}&end={newer[-1] // 1000 - 1}"),
        _page(older, ""),
    ]


def capped_read() -> list[httpx.Response]:
    """MAX_SERIES_PAGES pages of two samples, every one naming another: the cap binds."""
    now = int(time.time())
    pages = []
    for page in range(MAX_SERIES_PAGES):
        newest = now - page * 120
        pages.append(
            _page(
                [newest * 1000, (newest - 60) * 1000],
                f"start={now - 86400}&end={newest - 61}",
            )
        )
    return pages
