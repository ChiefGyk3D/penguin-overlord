#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Audit every feed the bot is configured to fetch.

Feeds rot quietly: a domain expires and starts serving a parking page, a
site redesign moves the RSS path, a CDN starts blocking non-browser user
agents — and the bot logs one warning per cycle that nobody reads. The
2026-08-31 audit found 26 of 242 configured feeds in that state, some for
months.

Run this periodically (or before touching feed lists):

    python scripts/feed_audit.py             # everything
    python scripts/feed_audit.py --cog tech_news
    python scripts/feed_audit.py --failures-only

It fetches every URL with the bot's real User-Agent (utils/http.py — the
same identity the bot uses, so results match production), follows
redirects, and classifies each feed:

    OK          parseable RSS/Atom/JSON with entries
    EMPTY       parseable but zero entries (valid; worth an eyebrow)
    REDIRECTED  works, but from a different final URL — update the config
    HTML        the URL serves a web page now, not a feed
    PARSE       fetched but not parseable
    FAIL        HTTP error / DNS / TLS / timeout

Exit code is the number of HTML+PARSE+FAIL feeds, so CI or cron can alert.
"""

import argparse
import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOT_DIR = REPO_ROOT / 'penguin-overlord'
sys.path.insert(0, str(BOT_DIR))

import aiohttp  # noqa: E402

from utils.http import DEFAULT_HEADERS  # noqa: E402


def harvest() -> dict:
    """{(cog, source_name): url} for every feed defined in the cogs."""
    feeds = {}
    for path in sorted((BOT_DIR / 'cogs').glob('*.py')):
        text = path.read_text(encoding='utf-8')
        # entries look like:  'name': 'X', ... 'url': 'Y'
        for m in re.finditer(
                r"'name':\s*'([^']+)'[^{}]*?'url':\s*'([^']+)'", text, re.DOTALL):
            feeds[(path.stem, m.group(1))] = m.group(2)
    return feeds


def classify(url: str, final_url: str, body: bytes) -> str:
    # Remote XML is untrusted. ENTITY declarations are the actual weapon
    # (billion-laughs, XXE) — refuse those outright. A bare DOCTYPE with no
    # entities (GitHub's feeds carry one) is harmless to ElementTree, which
    # neither fetches external DTDs nor expands undeclared entities.
    if b'<!ENTITY' in body[:8000]:
        return 'PARSE (ENTITY refused)'
    head = body[:800].lower()
    if b'<html' in head and b'<rss' not in head and b'<feed' not in head:
        # JSON endpoints (KEV, NVD, Zscaler) are legitimate non-XML feeds
        try:
            json.loads(body)
            return 'OK'
        except ValueError:
            return 'HTML'
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        try:
            json.loads(body)
            return 'OK'
        except ValueError:
            return 'PARSE'
    entries = sum(1 for e in root.iter() if e.tag.endswith(('item', 'entry')))
    if entries == 0:
        return 'EMPTY'
    if final_url.rstrip('/') != url.rstrip('/'):
        return 'REDIRECTED'
    return 'OK'


async def probe(session, key, url, results):
    try:
        async with session.get(url) as response:
            if response.status != 200:
                results[key] = (f'FAIL HTTP {response.status}', url)
                return
            body = await response.read()
            results[key] = (classify(url, str(response.url), body), url)
    except Exception as e:
        results[key] = (f'FAIL {type(e).__name__}', url)


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cog', help='audit a single cog (e.g. tech_news)')
    ap.add_argument('--failures-only', action='store_true')
    ap.add_argument('--concurrency', type=int, default=16)
    args = ap.parse_args()

    feeds = harvest()
    if args.cog:
        feeds = {k: v for k, v in feeds.items() if k[0] == args.cog}
    print(f'Auditing {len(feeds)} feed(s)…\n')

    results = {}
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=args.concurrency)
    async with aiohttp.ClientSession(
            timeout=timeout, connector=connector,
            headers=DEFAULT_HEADERS) as session:
        await asyncio.gather(*(
            probe(session, key, url, results) for key, url in feeds.items()))

    order = {'FAIL': 0, 'HTML': 1, 'PARSE': 2, 'REDIRECTED': 3, 'EMPTY': 4, 'OK': 5}
    broken = 0
    for (cog, name), (status, url) in sorted(
            results.items(), key=lambda kv: (order.get(kv[1][0].split()[0], 0), kv[0])):
        kind = status.split()[0]
        if kind in ('FAIL', 'HTML', 'PARSE'):
            broken += 1
        elif args.failures_only:
            continue
        print(f'{status:22} {cog:22} {name[:34]:34} {url}')

    ok = len(results) - broken
    print(f'\n{ok}/{len(results)} healthy; {broken} broken')
    return min(broken, 125)


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
