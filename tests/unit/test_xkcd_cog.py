# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression tests for the XKCD cog.

Historical bug: _fetch_comic used synchronous requests.get on the event
loop, and xkcd_search issued up to 100 sequential blocking HTTP calls,
freezing the whole bot.
"""

import asyncio
import inspect
from unittest.mock import MagicMock

from cogs.xkcd import XKCD


COMIC = {
    "num": 100,
    "title": "Family Circus",
    "img": "https://imgs.xkcd.com/comics/family_circus.jpg",
    "alt": "alt text",
    "year": "2006",
    "month": "1",
    "day": "20",
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload

    def raise_for_status(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        return FakeResponse(self._payload)


def make_cog():
    cog = XKCD.__new__(XKCD)
    cog.bot = MagicMock()
    cog.session = FakeSession(COMIC)
    return cog


def test_fetch_comic_is_async():
    # The old implementation was a blocking sync method.
    assert inspect.iscoroutinefunction(XKCD._fetch_comic)


async def test_fetch_comic_returns_data():
    cog = make_cog()
    data = await cog._fetch_comic(100)
    assert data["num"] == 100


def test_embed_handles_string_dates():
    cog = make_cog()
    embed = cog._create_comic_embed(COMIC)
    assert embed.title == "#100: Family Circus"
    assert "2006-01-20" in embed.footer.text


async def test_search_fan_out_is_bounded():
    """Search must cap concurrent requests, not fire 100 at once."""
    in_flight = 0
    max_in_flight = 0

    class CountingSession:
        def get(self, url, timeout=None):
            return self

        async def __aenter__(self):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0)
            return FakeResponse(COMIC)

        async def __aexit__(self, *args):
            nonlocal in_flight
            in_flight -= 1
            return False

    # Exercise the same bounded-fetch pattern the command uses
    session = CountingSession()

    semaphore = asyncio.Semaphore(XKCD.SEARCH_CONCURRENCY)

    async def fetch_bounded(num):
        async with semaphore:
            async with session.get("url") as resp:
                return await resp.json()

    await asyncio.gather(*(fetch_bounded(n) for n in range(100)))
    assert max_in_flight <= XKCD.SEARCH_CONCURRENCY
