# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression tests for issue #49: duplicated news posts.

Two root causes:

1. Cross-feed duplication — dedupe state was keyed per feed URL (runner) or
   per source key (cogs), so the same BBC story syndicated into Top Stories
   AND the UK feed posted once per feed.

2. Cross-poster duplication — every news cog starts its own in-bot auto-post
   loop even when the systemd news timers run the same category externally,
   with separate state files, so each article could post twice with slightly
   different formatting. NEWS_AUTO_POST=false must keep the loops parked.
"""

from unittest.mock import MagicMock

import pytest

from cogs import general_news
from utils.news_fetcher import OptimizedNewsFetcher


# ---------------------------------------------------------------------------
# Runner path: OptimizedNewsFetcher GUID dedupe must span all feeds
# ---------------------------------------------------------------------------

RSS_ONE_STORY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>BBC UK</title>
  <item>
    <title>Same story, different feed</title>
    <link>https://www.bbc.co.uk/news/articles/abc123</link>
    <guid>https://www.bbc.co.uk/news/articles/abc123</guid>
    <description>One story syndicated into several BBC feeds.</description>
    <pubDate>Mon, 31 Aug 2026 12:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""


@pytest.fixture
def fetcher(tmp_data_dir):
    return OptimizedNewsFetcher(cache_file=str(tmp_data_dir / "feed_cache_test.json"))


def test_fetcher_skips_guid_seen_on_sibling_feed(fetcher):
    """A GUID recorded for one feed URL must suppress the item on every feed."""
    fetcher.feed_cache["last_guids"]["https://feeds.bbci.co.uk/news/rss.xml"] = [
        "https://www.bbc.co.uk/news/articles/abc123"
    ]

    result = fetcher._parse_feed_content(
        RSS_ONE_STORY, "https://feeds.bbci.co.uk/news/uk/rss.xml", "BBC UK"
    )

    assert result is None


def test_fetcher_treats_tracking_variants_as_same_guid(fetcher):
    """Fragment / tracking-parameter variants of a URL GUID are the same story."""
    fetcher.feed_cache["last_guids"]["https://feeds.bbci.co.uk/news/rss.xml"] = [
        "https://www.bbc.co.uk/news/articles/abc123?at_medium=RSS&at_campaign=rss#0"
    ]

    result = fetcher._parse_feed_content(
        RSS_ONE_STORY, "https://feeds.bbci.co.uk/news/uk/rss.xml", "BBC UK"
    )

    assert result is None


def test_fetcher_still_returns_genuinely_new_item(fetcher):
    """The global check must not suppress stories that were never posted."""
    fetcher.feed_cache["last_guids"]["https://feeds.bbci.co.uk/news/rss.xml"] = [
        "https://www.bbc.co.uk/news/articles/zzz999"
    ]

    result = fetcher._parse_feed_content(
        RSS_ONE_STORY, "https://feeds.bbci.co.uk/news/uk/rss.xml", "BBC UK"
    )

    assert result is not None
    assert result[0] == "Same story, different feed"


# ---------------------------------------------------------------------------
# Cog path: GeneralNews link dedupe must span all sources
# ---------------------------------------------------------------------------

GENERAL_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>BBC UK</title>
  <item>
    <title>Shared headline</title>
    <link>https://www.bbc.co.uk/news/articles/abc123</link>
    <description>Story in both Top Stories and UK.</description>
    <pubDate>Mon, 31 Aug 2026 12:00:00 GMT</pubDate>
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

    def get(self, url, **kwargs):
        return FakeResponse(self._text)


@pytest.fixture
def news_cog(tmp_data_dir):
    instance = general_news.GeneralNews.__new__(general_news.GeneralNews)
    instance.bot = MagicMock()
    instance.session = FakeSession(GENERAL_RSS)
    instance.state_file = str(tmp_data_dir / "general_news_state.json")
    instance.posted_items = {}
    return instance


async def test_cog_skips_link_posted_by_sibling_source(news_cog):
    """A link already posted from bbc_top must not post again from bbc_uk."""
    news_cog.posted_items["bbc_top"] = ["https://www.bbc.co.uk/news/articles/abc123"]

    result = await news_cog._fetch_rss_feed("bbc_uk")

    assert result is None


async def test_cog_skips_tracking_variant_of_posted_link(news_cog):
    """Tracking-parameter variants of an already-posted link are duplicates."""
    news_cog.posted_items["bbc_top"] = [
        "https://www.bbc.co.uk/news/articles/abc123?at_medium=RSS#0"
    ]

    result = await news_cog._fetch_rss_feed("bbc_uk")

    assert result is None


async def test_cog_returns_genuinely_new_item(news_cog):
    news_cog.posted_items["bbc_top"] = ["https://www.bbc.co.uk/news/articles/zzz999"]

    result = await news_cog._fetch_rss_feed("bbc_uk")

    assert result is not None
    assert result[0] == "Shared headline"


# ---------------------------------------------------------------------------
# Cross-poster: NEWS_AUTO_POST=false parks the in-bot auto-post loops
# ---------------------------------------------------------------------------

async def test_auto_post_gate_disables_loop(tmp_data_dir, monkeypatch):
    monkeypatch.setenv("NEWS_AUTO_POST", "false")
    cog = general_news.GeneralNews(MagicMock())
    try:
        assert not cog.news_auto_poster.is_running()
    finally:
        cog.news_auto_poster.cancel()


async def test_auto_post_defaults_to_enabled(tmp_data_dir, monkeypatch):
    monkeypatch.delenv("NEWS_AUTO_POST", raising=False)
    cog = general_news.GeneralNews(MagicMock())
    try:
        assert cog.news_auto_poster.is_running()
    finally:
        cog.news_auto_poster.cancel()


async def test_auto_post_gate_is_parsed_by_the_config_module(monkeypatch):
    # NEWS_AUTO_POST used to be a bare os.getenv here; it is a NewsConfig
    # field now, and the two must not drift.
    from utils.config import load_news_config
    from utils.news_dedupe import autopost_enabled
    for raw, expected in (("false", False), ("0", False), ("off", False),
                          ("true", True), ("on", True)):
        monkeypatch.setenv("NEWS_AUTO_POST", raw)
        assert autopost_enabled() is expected
        assert load_news_config().auto_post is expected
    monkeypatch.delenv("NEWS_AUTO_POST", raising=False)
    assert autopost_enabled() is True


async def test_auto_post_gate_honours_the_secrets_manager(monkeypatch):
    # NEWS_* is a secrets-manager platform, so an operator who keeps the
    # switch in Doppler gets it honoured here too, not only in news_manager.
    from utils.news_dedupe import autopost_enabled
    monkeypatch.delenv("NEWS_AUTO_POST", raising=False)
    monkeypatch.setattr(
        "utils.secrets.get_secret",
        lambda platform, key, **kw: "false"
        if (platform, key) == ("NEWS", "AUTO_POST") else None,
    )
    assert autopost_enabled() is False
