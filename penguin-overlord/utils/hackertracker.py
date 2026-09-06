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

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from utils.events_logic import LOCATION_UNSET, fingerprint

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


# -- fetch ---------------------------------------------------------------------

class HackerTrackerError(RuntimeError):
    """The conferences read failed and no usable cache exists."""


async def fetch_conferences(session, *, url: str = FIRESTORE_URL, page_size: int = PAGE_SIZE,
                            max_pages: int = MAX_PAGES) -> list[dict]:
    """Raw conference documents from the Firestore list endpoint, following
    nextPageToken up to max_pages. Raises HackerTrackerError on any HTTP,
    transport or decode failure; the caller decides about the cache."""
    documents: list[dict] = []
    token = None
    for _ in range(max_pages):
        params = {'pageSize': page_size}
        if token:
            params['pageToken'] = token
        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise HackerTrackerError(f'HTTP {response.status} from {url}')
                payload = await response.json(content_type=None)
        except HackerTrackerError:
            raise
        except Exception as e:    # aiohttp.ClientError subclasses OSError; anything else is still a failed read
            raise HackerTrackerError(f'{type(e).__name__}: {e}') from e
        if not isinstance(payload, dict):
            raise HackerTrackerError('response was not a JSON object')
        documents.extend(payload.get('documents') or [])
        token = payload.get('nextPageToken')
        if not token:
            break
    return documents


# -- cache ---------------------------------------------------------------------

def cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / CACHE_NAME


def save_cache(path: Path, documents: list[dict], fetched_at: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps({'fetched_at': fetched_at, 'documents': documents}))
    tmp.replace(path)


def load_cache(path: Path) -> tuple[list[dict], Optional[str]]:
    path = Path(path)
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text())
        docs = data.get('documents') or []
        return (docs if isinstance(docs, list) else []), data.get('fetched_at')
    except (OSError, ValueError, AttributeError):
        logger.warning('Hacker Tracker: cache at %s is unreadable; ignoring it', path)
        return [], None


async def fetch_or_cache(session, cache: Path) -> tuple[list[Conference], str]:
    """Live read, cached on success; the last good response when the read
    fails (one WARNING). Raises HackerTrackerError when neither exists."""
    try:
        documents = await fetch_conferences(session)
    except HackerTrackerError as e:
        documents, fetched_at = load_cache(cache)
        if not documents:
            raise HackerTrackerError(f'{e}; no cached response to fall back on') from e
        logger.warning('Hacker Tracker: read failed (%s); using the cache from %s', e, fetched_at)
        return parse_documents({'documents': documents}), 'cache'
    save_cache(cache, documents, datetime.now(timezone.utc).isoformat())
    return parse_documents({'documents': documents}), 'live'


# -- mapping -------------------------------------------------------------------

def _valid_timezone(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    try:
        ZoneInfo(name)
    except Exception:
        return None
    return name


def conference_to_event(conf: Conference, *, guild_id: int) -> dict:
    """One Conference as an EventsStore.insert() row: pending, cyber,
    dates confirmed by the organizer, location left for a moderator, the
    con's own site as the link and the Hacker Tracker listing as the
    source. Section 7 of the spec."""
    return {
        'guild_id': guild_id,
        'title': conf.name,
        'fingerprint': fingerprint(conf.name, conf.start_date),
        'topic': 'cyber',
        'start_date': conf.start_date.isoformat(),
        'end_date': conf.end_date.isoformat(),
        'start_time': None,
        'timezone': _valid_timezone(conf.timezone),
        'date_status': 'confirmed',
        'city': LOCATION_UNSET,
        'region_code': None,
        'country_code': None,
        'scope': 'regional',
        'url': conf.link or app_url(conf.code),
        'notes': None,
        'recurrence': 'annual',
        'parent_event_id': None,
        'status': 'pending',
        'provenance': 'hackertracker',
        'submitted_by': None,
        'source_url': app_url(conf.code),
        'source_note': f'ht:{conf.code}',
    }
