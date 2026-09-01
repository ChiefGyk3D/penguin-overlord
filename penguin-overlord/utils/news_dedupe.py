# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared helpers for news deduplication and auto-post gating (issue #49).

Feeds from the same publisher syndicate one story into several feeds (BBC Top
Stories vs UK vs Politics), so dedupe state keyed per feed lets the same
article through once per feed. These helpers compare an item against the
union of every feed's seen-list, with light URL normalization so tracking
parameters and fragments don't defeat the comparison.
"""

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that vary between syndications of the same article.
_TRACKING_PREFIXES = ('utm_', 'at_', 'ns_', 'cmp', 'ocid', 'ref')


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


def seen_in_any(seen_lists, value: str) -> bool:
    """True if `value` matches an entry in ANY of the given seen-lists.

    `seen_lists` is an iterable of lists (e.g. dict.values() of a per-feed
    seen mapping). Comparison uses normalize_link on both sides.
    """
    if not value:
        return False
    target = normalize_link(value)
    for entries in seen_lists:
        for entry in entries:
            if normalize_link(entry) == target:
                return True
    return False


def autopost_enabled() -> bool:
    """Whether in-bot news auto-post loops should run (NEWS_AUTO_POST).

    Defaults to enabled so standalone deployments keep posting. Set
    NEWS_AUTO_POST=false where the systemd news timers own posting, so the
    same category is never posted by two schedulers with separate state.
    """
    return os.getenv('NEWS_AUTO_POST', 'true').strip().lower() not in (
        'false', '0', 'no', 'off',
    )
