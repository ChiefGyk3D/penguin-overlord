# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared helpers for news deduplication and auto-post gating (issue #49).

Feeds from the same publisher syndicate one story into several feeds (BBC Top
Stories vs UK vs Politics), so dedupe state keyed per feed lets the same
article through once per feed. These helpers compare an item against the
union of every feed's seen-list, with light URL normalization so tracking
parameters and fragments don't defeat the comparison.

Each seen-list entry is a canonical link (or, when an item has no link, its
GUID), plus a time-stamped normalized-title entry ("title:<epoch>:<title>")
so the same headline posted with and without a leading emoji, or under a
different URL, is also caught. Title entries expire after TITLE_KEY_TTL so
recurring headlines ("Stable Channel Update for Desktop") still post, and
every per-feed list is capped at MAX_SEEN_PER_FEED entries.
"""

import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that vary between syndications of the same article.
_TRACKING_PREFIXES = ('utm_', 'at_', 'ns_', 'cmp', 'ocid', 'ref')

# Per-feed cap on stored entries (up to three per posted item: link, guid,
# title), so the persisted store cannot grow without bound.
MAX_SEEN_PER_FEED = 150
# How long a normalized-title key suppresses a repeat of the same headline.
TITLE_KEY_TTL = 48 * 3600
_TITLE_PREFIX = 'title:'


def normalize_link(value: str) -> str:
    """Normalize a URL-shaped GUID/link for duplicate comparison.

    Strips the fragment and tracking query parameters, lowercases the host,
    and drops a trailing slash. Non-URL strings are returned unchanged so
    opaque GUIDs still compare exactly.
    """
    if not value:
        return value
    value = value.strip()
    if not value.startswith(('http://', 'https://')):
        return value
    try:
        scheme, netloc, path, query, _fragment = urlsplit(value)
    except ValueError:
        return value
    kept = [
        (k, v) for k, v in parse_qsl(query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = path.rstrip('/') or ''
    return urlunsplit((scheme, netloc.lower(), path, urlencode(kept), ''))


def normalize_title(title) -> str:
    """Normalize a headline for duplicate comparison.

    Strips leading emoji, symbols, punctuation and whitespace, collapses
    internal whitespace and casefolds, so "📰 Big story" == "big story".
    """
    if not title:
        return ''
    start = 0
    while start < len(title) and not title[start].isalnum():
        start += 1
    return ' '.join(title[start:].split()).casefold()


def _title_entry(entry):
    """(timestamp, normalized title) for a stored title entry, else None."""
    if not isinstance(entry, str) or not entry.startswith(_TITLE_PREFIX):
        return None
    _prefix, stamp, title = (entry.split(':', 2) + ['', ''])[:3]
    try:
        return float(stamp), title
    except ValueError:
        return None


def _link_keys(link, guid) -> list:
    """Canonical link key, with the GUID as fallback / extra identity."""
    keys = []
    for value in (link, guid):
        key = normalize_link(value) if value else ''
        if key and key not in keys:
            keys.append(key)
    return keys


def is_duplicate(seen_lists, link=None, guid=None, title=None, now=None) -> bool:
    """True if the item matches an entry in ANY of the given seen-lists.

    Matches on the canonical link or GUID (tracking params and fragments
    stripped), or on the normalized title while its entry is younger than
    TITLE_KEY_TTL. Untagged legacy entries (raw links/GUIDs) still match.
    """
    now = time.time() if now is None else now
    links = set(_link_keys(link, guid))
    norm_title = normalize_title(title)
    for entries in seen_lists:
        for entry in entries:
            if not isinstance(entry, str):
                continue
            if entry.startswith(_TITLE_PREFIX):
                parsed = _title_entry(entry)
                if (parsed and norm_title and parsed[1] == norm_title
                        and now - parsed[0] < TITLE_KEY_TTL):
                    return True
            elif normalize_link(entry) in links:
                return True
    return False


def remember(store: dict, feed_key: str, link=None, guid=None, title=None,
             now=None, max_entries: int = MAX_SEEN_PER_FEED) -> None:
    """Record an item's dedupe keys under `feed_key` in the seen-store.

    Drops expired title entries and trims the list to `max_entries`, so the
    store stays bounded however long the bot runs.
    """
    now = time.time() if now is None else now
    entries = [
        e for e in store.get(feed_key, [])
        if (parsed := _title_entry(e)) is None or now - parsed[0] < TITLE_KEY_TTL
    ]
    for key in _link_keys(link, guid):
        if key in entries:
            entries.remove(key)  # re-append so a re-seen item isn't trimmed first
        entries.append(key)
    norm_title = normalize_title(title)
    if norm_title:
        entries.append(f'{_TITLE_PREFIX}{int(now)}:{norm_title}')
    store[feed_key] = entries[-max_entries:]


def autopost_enabled() -> bool:
    """Whether in-bot news auto-post loops should run (NEWS_AUTO_POST).

    Defaults to enabled so standalone deployments keep posting. Set
    NEWS_AUTO_POST=false where the systemd news timers own posting, so the
    same category is never posted by two schedulers with separate state.
    """
    from utils.config import load_news_config
    return load_news_config().auto_post
