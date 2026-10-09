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

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock

import pytest

from cogs import general_news
from utils.news_fetcher import OptimizedNewsFetcher

# The cogs drop anything older than seven days, so a fixed date in a fixture
# silently expires: the fixture below carried "31 Aug 2026" and every test
# reading it started failing on 7 September. Always "yesterday", in RFC 2822.
PUBDATE = format_datetime(datetime.now(timezone.utc) - timedelta(days=1))


# ---------------------------------------------------------------------------
# Runner path: OptimizedNewsFetcher GUID dedupe must span all feeds
# ---------------------------------------------------------------------------

RSS_ONE_STORY = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>BBC UK</title>
  <item>
    <title>Same story, different feed</title>
    <link>https://www.bbc.co.uk/news/articles/abc123</link>
    <guid>https://www.bbc.co.uk/news/articles/abc123</guid>
    <description>One story syndicated into several BBC feeds.</description>
    <pubDate>{PUBDATE}</pubDate>
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

GENERAL_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>BBC UK</title>
  <item>
    <title>Shared headline</title>
    <link>https://www.bbc.co.uk/news/articles/abc123</link>
    <description>Story in both Top Stories and UK.</description>
    <pubDate>{PUBDATE}</pubDate>
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


# ---------------------------------------------------------------------------
# Canonical-key dedupe: tracking params, leading emoji, bounded store
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

from utils import news_dedupe  # noqa: E402
from utils.news_dedupe import (  # noqa: E402
    MAX_SEEN_PER_FEED, TITLE_KEY_TTL, is_duplicate, normalize_title, remember,
)

TOP_URL = "https://feeds.bbci.co.uk/news/rss.xml"
POLITICS_URL = "https://feeds.bbci.co.uk/news/politics/rss.xml"


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """No real credentials and no network: any attempt to open a real HTTP
    session (and so any chance of posting to Discord) fails the test."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    def _no_network(*args, **kwargs):
        raise AssertionError("tests must not open a network session")

    monkeypatch.setattr("utils.news_fetcher.client_session", _no_network)
    monkeypatch.setattr("cogs.general_news.client_session", _no_network)


def rss(*items):
    body = "".join(
        f"<item><title>{escape(title)}</title><link>{escape(link)}</link><guid>{escape(guid)}</guid>"
        f"<description>d</description><pubDate>{PUBDATE}</pubDate></item>"
        for title, link, guid in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


class FakeFeedResponse(FakeResponse):
    headers = {}


class FakeFeedSession:
    """Serves canned feed XML per URL; records every request."""

    def __init__(self, feeds):
        self.feeds = feeds
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        return FakeFeedResponse(self.feeds[url])

    async def close(self):
        pass


def make_fetcher(cache_file, feeds):
    f = OptimizedNewsFetcher(cache_file=str(cache_file))
    f.session = FakeFeedSession(feeds)
    f._request_semaphore = asyncio.Semaphore(5)
    return f


SOURCES = {
    "bbc_news": {"name": "BBC Top Stories", "url": TOP_URL},
    "bbc_politics": {"name": "BBC Politics", "url": POLITICS_URL},
}


def test_normalize_title_strips_leading_emoji_and_casefolds():
    assert normalize_title("📰  Minister RESIGNS   over report") == "minister resigns over report"
    assert normalize_title("🇬🇧️ Minister resigns over report") == "minister resigns over report"
    assert normalize_title("Minister resigns over report") == "minister resigns over report"
    assert normalize_title("") == ""
    assert normalize_title(None) == ""


async def test_runner_same_story_two_feeds_tracking_params_posts_once(tmp_data_dir):
    base = "https://www.bbc.co.uk/news/articles/c0abc123"
    feeds = {
        TOP_URL: rss(("Budget passes", f"{base}?at_medium=RSS&at_campaign=rss", f"{base}#0")),
        POLITICS_URL: rss(("Budget passes", f"{base}?at_medium=RSS&at_campaign=politics", f"{base}#1")),
    }
    cache = tmp_data_dir / "feed_cache_general_news.json"

    first = await make_fetcher(cache, feeds).fetch_multiple_feeds(SOURCES, list(SOURCES))
    assert len(first) == 1

    # Next run (fresh fetcher, persisted store) must not post it again.
    second = await make_fetcher(cache, feeds).fetch_multiple_feeds(SOURCES, list(SOURCES))
    assert second == []


async def test_runner_same_story_with_and_without_emoji_posts_once(tmp_data_dir):
    feeds = {
        TOP_URL: rss(("📰 Minister resigns over report",
                      "https://www.bbc.co.uk/news/articles/c0aaa111", "urn:bbc:1")),
        POLITICS_URL: rss(("Minister resigns over report",
                           "https://www.bbc.com/news/articles/c0aaa111", "urn:bbc:2")),
    }
    cache = tmp_data_dir / "feed_cache_general_news.json"

    items = await make_fetcher(cache, feeds).fetch_multiple_feeds(SOURCES, list(SOURCES))
    assert len(items) == 1

    # Same feed, next run, emoji dropped and a new GUID: still a duplicate.
    feeds[TOP_URL] = rss(("Minister resigns over report",
                          "https://www.bbc.co.uk/news/articles/c0aaa111?at_medium=RSS", "urn:bbc:3"))
    again = await make_fetcher(cache, feeds).fetch_multiple_feeds(SOURCES, list(SOURCES))
    assert again == []


async def test_runner_different_stories_with_similar_titles_both_post(tmp_data_dir):
    feeds = {
        TOP_URL: rss(("Minister resigns over report",
                      "https://www.bbc.co.uk/news/articles/c0aaa111", "urn:bbc:1")),
        POLITICS_URL: rss(("Minister resigns over new report",
                           "https://www.bbc.co.uk/news/articles/c0bbb222", "urn:bbc:2")),
    }
    items = await make_fetcher(tmp_data_dir / "c.json", feeds).fetch_multiple_feeds(SOURCES, list(SOURCES))
    assert sorted(i[0] for i in items) == ["Minister resigns over new report", "Minister resigns over report"]


def test_runner_store_stays_bounded(fetcher):
    for n in range(500):
        feed = rss((f"Story number {n}", f"https://www.bbc.co.uk/news/articles/c{n}", f"urn:{n}"))
        assert fetcher._parse_feed_content(feed, TOP_URL, "BBC") is not None
    assert len(fetcher.feed_cache["last_guids"][TOP_URL]) <= MAX_SEEN_PER_FEED


def test_remember_caps_entries_and_expires_title_keys():
    store = {}
    for n in range(1000):
        remember(store, "feed", link=f"https://example.org/a/{n}", title=f"Story {n}", now=1000.0)
    assert len(store["feed"]) == MAX_SEEN_PER_FEED

    # Title keys age out; link keys stay until trimmed by the cap.
    store = {}
    remember(store, "feed", link="https://example.org/a/1", title="Weekly update", now=0)
    later = TITLE_KEY_TTL + 1
    assert is_duplicate(store.values(), title="Weekly update", now=TITLE_KEY_TTL - 1)
    assert not is_duplicate(store.values(), title="Weekly update", now=later)
    remember(store, "feed", link="https://example.org/a/2", now=later)
    assert not any(e.startswith("title:") for e in store["feed"])
    assert is_duplicate(store.values(), link="https://example.org/a/1?utm_source=x#top", now=later)


def test_legacy_raw_entries_still_match():
    """Stores written before this change hold raw links/GUIDs; keep honouring them."""
    seen = [["https://www.bbc.co.uk/news/articles/abc123?at_medium=RSS#0"]]
    assert is_duplicate(seen, guid="https://www.bbc.co.uk/news/articles/abc123")
    assert not news_dedupe.is_duplicate(seen, link="https://www.bbc.co.uk/news/articles/xyz")


# Cog path: GeneralNews posts once across sources and emoji variants

async def _post_all(cog, feeds_by_source):
    channel = MagicMock()
    channel.send = AsyncMock()
    cog.bot.get_channel.return_value = channel
    for source_key, feed in feeds_by_source:
        cog.session = FakeSession(feed)
        await cog._post_news(1, source_key)
    return channel.send.await_count


async def test_cog_same_story_two_feeds_and_emoji_variant_posts_once(news_cog):
    base = "https://www.bbc.co.uk/news/articles/c0abc123"
    sent = await _post_all(news_cog, [
        ("bbc_news", rss(("Budget passes", f"{base}?at_medium=RSS&at_campaign=rss", f"{base}#0"))),
        ("bbc_politics", rss(("Budget passes", f"{base}?at_medium=RSS&at_campaign=politics", f"{base}#1"))),
        ("bbc_uk", rss(("📰 Budget passes", "https://www.bbc.com/news/articles/c0abc123", "urn:x"))),
    ])
    assert sent == 1


async def test_cog_similar_titles_both_post_and_store_bounded(news_cog):
    sent = await _post_all(news_cog, [
        ("bbc_news", rss(("Minister resigns over report", "https://www.bbc.co.uk/news/articles/a", "urn:a"))),
        ("bbc_politics", rss(("Minister resigns over new report", "https://www.bbc.co.uk/news/articles/b", "urn:b"))),
    ])
    assert sent == 2

    for n in range(300):
        await _post_all(news_cog, [
            ("bbc_news", rss((f"Story {n}", f"https://www.bbc.co.uk/news/articles/s{n}", f"urn:s{n}"))),
        ])
    assert len(news_cog.posted_items["bbc_news"]) <= MAX_SEEN_PER_FEED
