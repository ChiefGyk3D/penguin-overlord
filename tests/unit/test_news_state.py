# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression tests for the family-B news cogs' posted-state handling.

Historical bug: _fetch_rss_feed marked items as posted *before* the caller
sent them to Discord, so a failed send silently lost the item forever, and
the manual slash command consumed items out of the auto-poster's queue.
"""

import json
from unittest.mock import MagicMock

import pytest

from cogs import us_legislation


RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test Feed</title>
  <item>
    <title>Bill A</title>
    <link>https://example.gov/bill-a</link>
    <description>First bill</description>
  </item>
  <item>
    <title>Bill B</title>
    <link>https://example.gov/bill-b</link>
    <description>Second bill</description>
  </item>
</channel></rss>
"""


class FakeResponse:
    def __init__(self, text, status=200):
        self._text = text
        self.status = status

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, text):
        self._text = text
        self.closed = False

    def get(self, url):
        return FakeResponse(self._text)


@pytest.fixture
def cog(tmp_data_dir):
    """A USLegislation cog with the task loop stubbed out and a fake session."""
    instance = us_legislation.USLegislation.__new__(us_legislation.USLegislation)
    instance.bot = MagicMock()
    instance.session = FakeSession(RSS_SAMPLE)
    instance.state_file = str(tmp_data_dir / "us_legislation_state.json")
    instance.posted_items = {}
    return instance


async def test_fetch_does_not_mark_posted(cog):
    result = await cog._fetch_rss_feed("house_floor")
    assert result is not None
    title, link, description, source = result
    assert title == "Bill A"
    assert link == "https://example.gov/bill-a"
    # The fetcher must NOT record the item — only a successful send may.
    assert cog.posted_items.get("house_floor", []) == []


async def test_fetch_skips_posted_items(cog):
    cog.posted_items = {"house_floor": ["https://example.gov/bill-a"]}
    result = await cog._fetch_rss_feed("house_floor")
    assert result is not None
    assert result[1] == "https://example.gov/bill-b"


async def test_fetch_with_skip_posted_false_returns_latest(cog):
    """The manual command path must not consume the auto-poster's queue."""
    cog.posted_items = {"house_floor": ["https://example.gov/bill-a"]}
    result = await cog._fetch_rss_feed("house_floor", skip_posted=False)
    assert result is not None
    assert result[1] == "https://example.gov/bill-a"


async def test_mark_posted_persists_and_caps(cog):
    for i in range(60):
        cog._mark_posted("house_floor", f"https://example.gov/bill-{i}")
    assert len(cog.posted_items["house_floor"]) == 50
    assert cog.posted_items["house_floor"][-1] == "https://example.gov/bill-59"
    on_disk = json.loads(open(cog.state_file).read())
    assert on_disk["house_floor"][-1] == "https://example.gov/bill-59"
