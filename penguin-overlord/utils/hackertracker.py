# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Hacker Tracker as a Con Recon discovery source.

hackertracker.app (junctor) is the DEF CON schedule app that many BSides
chapters, Ekoparty, CCC and others now publish through. Organizers enter
their own dates, so it is the one source maintained by the con itself.
Its Firestore project answers an unauthenticated GET on the conferences
collection; this module turns that wire-format JSON into Conference
rows, keeps the last good response on disk, and maps a Conference onto
the events table. No discord here, no bot state: the cog drives it.

The read is undocumented and the data carries no reuse licence, so the
caller polls once a week, never pages beyond a few hundred rows, and
falls back to the cache when the read fails.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

FIRESTORE_URL = ('https://firestore.googleapis.com/v1/projects/junctor-hackertracker/'
                 'databases/(default)/documents/conferences')
APP_URL = 'https://hackertracker.app/{code}'
PAGE_SIZE = 300
MAX_PAGES = 3
CACHE_NAME = 'hackertracker_conferences.json'


def app_url(code: str) -> str:
    return APP_URL.format(code=code)


@dataclass(frozen=True)
class Conference:
    code: str
    name: str
    start_date: date
    end_date: date
    timezone: Optional[str]
    link: Optional[str]
    hidden: bool
    updated_at: Optional[str]


# -- wire format ---------------------------------------------------------------

def unwrap(value: dict):
    """One Firestore typed value ({'stringValue': 'x'}) to a Python value.
    Unknown wrappers become None rather than raising: a new field type on
    their side must not take the whole run down."""
    if not isinstance(value, dict):
        return None
    if 'stringValue' in value:
        return value['stringValue']
    if 'booleanValue' in value:
        return bool(value['booleanValue'])
    if 'integerValue' in value:
        try:
            return int(value['integerValue'])
        except (TypeError, ValueError):
            return None
    if 'doubleValue' in value:
        return value['doubleValue']
    if 'timestampValue' in value:
        return value['timestampValue']
    if 'arrayValue' in value:
        return [unwrap(v) for v in (value['arrayValue'] or {}).get('values', [])]
    if 'mapValue' in value:
        return {k: unwrap(v) for k, v in (value['mapValue'] or {}).get('fields', {}).items()}
    return None


def _fields(document: dict) -> dict:
    return {k: unwrap(v) for k, v in (document.get('fields') or {}).items()}


def parse_documents(payload: dict) -> list[Conference]:
    """Every well-formed conference in one list response. A document that
    lacks code, name or parseable dates is logged at DEBUG and dropped."""
    out = []
    for document in (payload or {}).get('documents') or []:
        f = _fields(document)
        code = (f.get('code') or '').strip()
        name = (f.get('name') or '').strip()
        try:
            start = date.fromisoformat(str(f.get('start_date') or '')[:10])
            end = date.fromisoformat(str(f.get('end_date') or '')[:10])
        except ValueError:
            start = end = None
        if not code or not name or start is None or end is None:
            logger.debug('Hacker Tracker: skipping malformed document %s', document.get('name'))
            continue
        if end < start:
            start, end = end, start
        out.append(Conference(
            code=code, name=name, start_date=start, end_date=end,
            timezone=(f.get('timezone') or '').strip() or None,
            link=(f.get('link') or '').strip() or None,
            hidden=bool(f.get('hidden')),
            updated_at=f.get('updated_at') or None,
        ))
    return out
