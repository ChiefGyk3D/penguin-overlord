# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One HTTP identity for every outbound request the bot makes.

Without an explicit User-Agent, aiohttp announces `Python/x.y aiohttp/x.y`
— the default fingerprint of every unattended scraper on the internet, and
exactly what feed hosts rate-limit or block. The 2026-08-31 feed audit
found four "dead" feeds (Reddit's 429, all three EUR-Lex feeds serving
HTML) that were never dead at all: they were refusing the default UA and
worked immediately with an honest, descriptive one.

Feed etiquette, not spoofing: the UA names the bot and links the repo, so
an operator seeing us in their logs can find out what we are and open an
issue instead of a block rule.
"""

import aiohttp

USER_AGENT = ('PenguinOverlord/1.0 '
              '(+https://github.com/ChiefGyk3D/penguin-overlord; Discord bot)')

DEFAULT_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': ('application/rss+xml, application/atom+xml, '
               'application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5'),
}


def client_session(*, timeout: aiohttp.ClientTimeout = None,
                   **kwargs) -> aiohttp.ClientSession:
    """`aiohttp.ClientSession()` with the bot's identity attached.

    Every cog and runner should build its session here so a future header
    change (or per-host workaround) happens in one place. Extra kwargs and
    header overrides pass through untouched.
    """
    headers = dict(DEFAULT_HEADERS)
    headers.update(kwargs.pop('headers', None) or {})
    if timeout is not None:
        kwargs['timeout'] = timeout
    return aiohttp.ClientSession(headers=headers, **kwargs)
