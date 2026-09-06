# Con Recon phase 2a: Hacker Tracker discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Once a week, read the public Hacker Tracker conference list, insert every unknown upcoming conference as a pending Con Recon row that links back to its Hacker Tracker listing, and tell moderators when Hacker Tracker disagrees with an approved event's dates.

**Architecture:** A pure module `utils/hackertracker.py` (Firestore wire-format parsing, one paged HTTP read through the bot's `client_session`, a last-known-good JSON cache in `DATA_DIR`) feeds a new `Events.run_discovery()` in the cog, which runs inside the existing Monday sweep and behind a new `EVENTS_DISCOVERY_ENABLED` flag (default off), and is also reachable as the moderator command `/events discover`. Rows land through the existing `EventsStore.insert()` with `provenance = 'hackertracker'`, `source_url = https://hackertracker.app/<code>`, `source_note = 'ht:<code>'`, and a placeholder city that approval refuses until a moderator sets the real location. No model, no Gemini, no schema change: the phase 1 schema already has `source_url`, `source_note` and `provenance`.

**Tech Stack:** Python 3.10+, discord.py 2.7.1 (`app_commands`, `tasks`), aiohttp 3.14 via `utils.http.client_session`, aiosqlite through `utils.events_store.EventsStore`, pytest with the existing `tmp_data_dir` fixture and the fakes in `tests/unit/test_events_cog.py`.

**Spec:** `docs/superpowers/specs/2026-09-03-conference-database-design.md`, section 7, layer 2 "Hacker Tracker" (revision 3). Section 5 (schema, `provenance` values), section 6 (cards), section 14 (decisions) also bind.

## Global Constraints

- Provenance values are `member`, `calendar`, `ai`, `hackertracker`, `rollover` (spec section 5). This plan adds `hackertracker` to `PROVENANCES` in `utils/events_logic.py`; nothing else in the enum changes.
- Hacker Tracker rows insert as `pending`, `provenance = hackertracker`, `url = link` (falling back to the Hacker Tracker page when `link` is empty), `source_url = https://hackertracker.app/<code>`, `date_status = confirmed` (spec section 7).
- `hidden` rows and anything already ended are skipped (spec section 7).
- Match existing rows first by the code stored in `source_note` (`ht:<code>`), then by fingerprint (spec section 7).
- Every card and public embed for a `hackertracker` row carries a second link, "On Hacker Tracker", to `source_url` (spec section 7). Deep links are never fetched, only linked.
- One list call per week; cache the last good response in `DATA_DIR`; log one WARNING per run when the read fails (spec section 7).
- Discovery is off by default: `EVENTS_DISCOVERY_ENABLED=false`. Nothing contacts Hacker Tracker until the operator flips it (and, per spec, says hello in junctor's Discord first).
- Public posts never mention individual users: `cards.allowed_mentions(roles)` only (spec section 6, unchanged).
- No em dashes in any user-facing string, LLM prompt, doc, or commit message (code comments exempt). Use a comma, colon, or a new sentence.
- Never write a hostname, serial, employer name, token, or the work gh handle into anything.
- Hermetic tests: never execute `bot.py`, any `*_runner.py`, or `scripts/*.py` outside a hermetic environment (stub `dotenv.load_dotenv`, clear every `DISCORD_*`, `NEWS_*`, `DOPPLER_*` variable). Unit tests only. `load_dotenv` walks up to the real `.env`. Tests never touch the network: every HTTP call goes through an injected fake session.
- Never open, cat, grep, or Read `.env` or `.env.example`. The only permitted operation on `.env.example` is a standalone `cat >> .env.example <<'EOF' ... EOF` append (Task 5).
- The pytest summary line is suppressed by repo config: use the exit code (`python -m pytest tests/unit -q >/dev/null; echo $?`). Run pytest in the foreground only. `ruff check penguin-overlord tests scripts` must pass before each commit.
- Commits: `git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit ...`, message ends with a blank line and `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do not push; do not open or merge PRs.
- Python source files start with the MPL-2.0 header block already used by every file in `penguin-overlord/utils/`.
- Working directory for `python -m pytest` is the repo root; imports resolve as `from utils import ...` and `from cogs.events import ...` (see `tests/unit/test_events_cog.py`).

## Rulings recorded while writing this plan

- **Location placeholder.** The conference document carries no city or country. A row with no city and no codes already means "Online" to `location_field()`, so an unset location needs a distinct value: `LOCATION_UNSET = 'Location TBD'` in `utils/events_logic.py`, stored in `city`. The review card shows it under Where, the edit modal prefills `Location TBD, Online` for the moderator to overwrite, and `decide()` refuses to approve a row whose `city == LOCATION_UNSET`. Cost if wrong: one extra edit per Hacker Tracker row before approval, which is the moderator step the spec already describes.
- **Locations subcollection deferred.** The spec says to try `/conferences/<code>/locations` for a venue string. Those documents are rooms and tracks, not cities, and it is one extra call per new conference. Phase 2a does not fetch it; Task 7 amends the spec sentence to say so. Cost if wrong: moderators type a city that a venue string would have hinted at.
- **Date mismatch on an approved matched row.** The verify job that would carry a proposal card does not exist yet. Phase 2a posts a plain notice embed to the review channel (no buttons) naming the row, both date pairs, and the `/events edit` command, deduped by an `event_audit` row with action `hackertracker_mismatch` whose `after_json` holds the Hacker Tracker dates. Pending, rejected, cancelled, and retired matched rows get no notice. Cost if wrong: a moderator edits by hand instead of clicking Apply.
- **Reused conference codes.** If the row found by `source_note` is retired, cancelled, or rejected and its `start_date` year differs from the fetched conference's year, the conference is treated as new (next year's edition under the same code); same year means skip. `find_source_note` returns the row with the latest `start_date`.
- **Topic.** Every Hacker Tracker conference inserts with `topic = 'cyber'`. Moderators change it on Edit if a con is not.
- **Guild.** Rows belong to the guild that owns the events channel (`_target_guild_id()`), the same scoping phase 1 uses for posting. No target guild means the run logs a warning and does nothing.
- **Fingerprint match links, never duplicates.** When no `source_note` matches but `find_fingerprint` does (a member or CSV row for the same con), the existing row gets `source_url` and `source_note` written (audit action `hackertracker_link`) so its card and embeds carry the link, and it counts as `linked`, not `new`.
- **Schedule.** Discovery runs inside `run_sweep()` on Mondays (`today.weekday() == 0`) when enabled, wrapped so a Hacker Tracker failure never aborts the rest of the sweep. `/events discover` runs the same code on demand for moderators.

## File structure

- Create `penguin-overlord/utils/hackertracker.py`: `Conference` dataclass, Firestore wire-format `unwrap`/`parse_documents`, `fetch_conferences(session, ...)`, `HackerTrackerError`, cache `save_cache`/`load_cache`, `fetch_or_cache(session, cache_path)`, `conference_to_event(conf, guild_id)`, `app_url(code)`. Pure: no discord import, no bot state.
- Modify `penguin-overlord/utils/events_logic.py`: `PROVENANCES` gains `'hackertracker'`; new `LOCATION_UNSET`.
- Modify `penguin-overlord/utils/events_store.py`: `find_source_note`, `update(..., action='edit')`, `last_audit(event_id, action)`.
- Modify `penguin-overlord/utils/events_cards.py`: `source_link(event)` helper; `review_card` and `reminder_embed` carry it; new `mismatch_embed`.
- Modify `penguin-overlord/utils/config.py`: `EventsConfig.discovery_enabled`, `_load_events` reads `EVENTS_DISCOVERY_ENABLED`; `describe`/summary line if one lists events flags.
- Modify `penguin-overlord/utils/metrics.py`: `EVENTS_DISCOVERY` counter.
- Modify `penguin-overlord/cogs/events.py`: `PROVENANCE_LINES['hackertracker']`, `run_discovery`, Monday hook in `run_sweep`, `/events discover`, approve gate in `decide`, a discovery line in `/events status`.
- Modify docs: `docs/features/CON_RECON.md`, `docs/reference/COMMANDS.md`, `docs/reference/CONFIGURATION.md`, `docs/ROADMAP.md`, the spec (one sentence), `.env.example` (append only).
- Tests: create `tests/unit/test_hackertracker.py`; extend `tests/unit/test_events_logic.py`, `tests/unit/test_events_store.py`, `tests/unit/test_events_cards.py`, `tests/unit/test_events_cog.py`, `tests/unit/test_config.py`.

---

### Task 1: Firestore wire-format parsing

**Files:**
- Create: `penguin-overlord/utils/hackertracker.py`
- Test: `tests/unit/test_hackertracker.py`

**Interfaces:**
- Consumes: nothing from this plan.
- Produces: `Conference(code: str, name: str, start_date: date, end_date: date, timezone: str | None, link: str | None, hidden: bool, updated_at: str | None)` (frozen dataclass); `unwrap(value: dict) -> object`; `parse_documents(payload: dict) -> list[Conference]`; `app_url(code: str) -> str`; constants `FIRESTORE_URL`, `APP_URL`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_hackertracker.py`:

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Hacker Tracker: Firestore wire format in, Conference rows out. No
network anywhere in this file; the fetch tests use a fake session."""

from datetime import date

import pytest

from utils import hackertracker as ht


def doc(code, name, start, end, *, hidden=False, link='', tz='America/Los_Angeles', extra=None):
    fields = {
        'code': {'stringValue': code},
        'name': {'stringValue': name},
        'start_date': {'stringValue': start},
        'end_date': {'stringValue': end},
        'timezone': {'stringValue': tz},
        'link': {'stringValue': link},
        'hidden': {'booleanValue': hidden},
        'updated_at': {'timestampValue': '2026-08-01T12:00:00Z'},
        'id': {'integerValue': '42'},
        'maps': {'arrayValue': {'values': []}},
        'description': {'nullValue': None},
    }
    fields.update(extra or {})
    return {
        'name': f'projects/junctor-hackertracker/databases/(default)/documents/conferences/{code}',
        'fields': fields,
        'createTime': '2026-01-01T00:00:00Z',
        'updateTime': '2026-08-01T12:00:00Z',
    }


DEFCON = doc('DEFCON34', 'DEF CON 34', '2026-08-06', '2026-08-09', link='https://defcon.org')
HIDDEN = doc('TESTCON', 'Test Con', '2026-10-01', '2026-10-02', hidden=True)
BSIDES = doc('BSIDESDET2026', 'BSides Detroit 2026', '2026-09-26', '2026-09-27', tz='America/Detroit')


def test_unwrap_each_firestore_value_type():
    assert ht.unwrap({'stringValue': 'x'}) == 'x'
    assert ht.unwrap({'booleanValue': True}) is True
    assert ht.unwrap({'integerValue': '42'}) == 42
    assert ht.unwrap({'timestampValue': '2026-08-01T12:00:00Z'}) == '2026-08-01T12:00:00Z'
    assert ht.unwrap({'nullValue': None}) is None
    assert ht.unwrap({'arrayValue': {'values': [{'stringValue': 'a'}, {'integerValue': '1'}]}}) == ['a', 1]
    assert ht.unwrap({'mapValue': {'fields': {'k': {'stringValue': 'v'}}}}) == {'k': 'v'}
    assert ht.unwrap({'somethingNew': 1}) is None


def test_parse_documents_returns_one_conference_per_document():
    confs = ht.parse_documents({'documents': [DEFCON, BSIDES]})
    assert [c.code for c in confs] == ['DEFCON34', 'BSIDESDET2026']
    dc = confs[0]
    assert dc.name == 'DEF CON 34'
    assert dc.start_date == date(2026, 8, 6)
    assert dc.end_date == date(2026, 8, 9)
    assert dc.timezone == 'America/Los_Angeles'
    assert dc.link == 'https://defcon.org'
    assert dc.hidden is False
    assert dc.updated_at == '2026-08-01T12:00:00Z'


def test_parse_documents_keeps_hidden_flag_and_blank_link_as_none():
    (conf,) = ht.parse_documents({'documents': [HIDDEN]})
    assert conf.hidden is True
    assert conf.link is None


def test_parse_documents_skips_documents_missing_required_fields(caplog):
    broken = doc('BROKEN', 'Broken', '2026-13-40', '2026-10-02')
    nameless = doc('NONAME', '', '2026-10-01', '2026-10-02')
    confs = ht.parse_documents({'documents': [broken, nameless, DEFCON, {'name': 'x', 'fields': {}}]})
    assert [c.code for c in confs] == ['DEFCON34']


def test_parse_documents_tolerates_empty_payload():
    assert ht.parse_documents({}) == []
    assert ht.parse_documents({'documents': []}) == []


def test_parse_documents_swaps_reversed_dates():
    (conf,) = ht.parse_documents({'documents': [doc('REV', 'Reversed', '2026-10-05', '2026-10-01')]})
    assert (conf.start_date, conf.end_date) == (date(2026, 10, 1), date(2026, 10, 5))


def test_app_url_is_the_public_listing():
    assert ht.app_url('DEFCON34') == 'https://hackertracker.app/DEFCON34'
    assert ht.FIRESTORE_URL.endswith('/documents/conferences')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_hackertracker.py -q; echo exit=$?`
Expected: exit 1 or 2, `ModuleNotFoundError: No module named 'utils.hackertracker'`.

- [ ] **Step 3: Write the module**

Create `penguin-overlord/utils/hackertracker.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_hackertracker.py -q; echo exit=$?`
Expected: exit 0.

- [ ] **Step 5: Ruff and commit**

```bash
ruff check penguin-overlord tests scripts
git add penguin-overlord/utils/hackertracker.py tests/unit/test_hackertracker.py
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "feat(events): parse Hacker Tracker conference documents

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Fetch, cache, and the row mapping

**Files:**
- Modify: `penguin-overlord/utils/hackertracker.py`
- Modify: `penguin-overlord/utils/events_logic.py` (`PROVENANCES`, `LOCATION_UNSET`)
- Test: `tests/unit/test_hackertracker.py`, `tests/unit/test_events_logic.py`

**Interfaces:**
- Consumes: `Conference`, `parse_documents`, `app_url` from Task 1; `fingerprint(title, start_date)` from `utils.events_logic`; `utils.http.client_session` is the session factory the cog will pass in (the module itself only receives a session).
- Produces: `class HackerTrackerError(RuntimeError)`; `async fetch_conferences(session, *, url=FIRESTORE_URL, page_size=PAGE_SIZE, max_pages=MAX_PAGES) -> list[dict]` (raw documents); `save_cache(path: Path, documents: list[dict], fetched_at: str) -> None`; `load_cache(path: Path) -> tuple[list[dict], str | None]`; `async fetch_or_cache(session, cache_path: Path) -> tuple[list[Conference], str]` where the second item is `'live'` or `'cache'` (raises `HackerTrackerError` when both fail); `conference_to_event(conf: Conference, *, guild_id: int) -> dict`; `LOCATION_UNSET = 'Location TBD'` and `'hackertracker'` in `PROVENANCES` (events_logic).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_hackertracker.py`:

```python
class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Records every GET; answers from a queue of (status, payload)."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def get(self, url, *, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if not self.answers:
            raise AssertionError('unexpected extra GET')
        status, payload = self.answers.pop(0)
        if isinstance(payload, Exception) and status is None:
            raise payload
        return FakeResponse(status, payload)


async def test_fetch_conferences_follows_next_page_token_and_stops():
    session = FakeSession([
        (200, {'documents': [DEFCON], 'nextPageToken': 'p2'}),
        (200, {'documents': [BSIDES]}),
    ])
    docs = await ht.fetch_conferences(session)
    assert [d['fields']['code']['stringValue'] for d in docs] == ['DEFCON34', 'BSIDESDET2026']
    assert session.calls[0] == (ht.FIRESTORE_URL, {'pageSize': ht.PAGE_SIZE})
    assert session.calls[1][1] == {'pageSize': ht.PAGE_SIZE, 'pageToken': 'p2'}


async def test_fetch_conferences_caps_the_page_count():
    session = FakeSession([(200, {'documents': [DEFCON], 'nextPageToken': 'again'})] * 5)
    docs = await ht.fetch_conferences(session, max_pages=2)
    assert len(docs) == 2
    assert len(session.calls) == 2


async def test_fetch_conferences_raises_on_http_error():
    with pytest.raises(ht.HackerTrackerError) as err:
        await ht.fetch_conferences(FakeSession([(503, {})]))
    assert '503' in str(err.value)


async def test_fetch_conferences_raises_on_bad_json_and_transport_errors():
    with pytest.raises(ht.HackerTrackerError):
        await ht.fetch_conferences(FakeSession([(200, ValueError('not json'))]))
    with pytest.raises(ht.HackerTrackerError):
        await ht.fetch_conferences(FakeSession([(None, OSError('connection reset'))]))


def test_cache_round_trip(tmp_path):
    path = tmp_path / 'ht.json'
    assert ht.load_cache(path) == ([], None)
    ht.save_cache(path, [DEFCON], '2026-09-07T07:00:00+00:00')
    docs, fetched_at = ht.load_cache(path)
    assert docs == [DEFCON]
    assert fetched_at == '2026-09-07T07:00:00+00:00'


def test_load_cache_survives_a_corrupt_file(tmp_path):
    path = tmp_path / 'ht.json'
    path.write_text('{not json')
    assert ht.load_cache(path) == ([], None)


async def test_fetch_or_cache_prefers_live_and_writes_the_cache(tmp_path):
    path = tmp_path / 'ht.json'
    confs, source = await ht.fetch_or_cache(FakeSession([(200, {'documents': [DEFCON]})]), path)
    assert source == 'live'
    assert [c.code for c in confs] == ['DEFCON34']
    assert ht.load_cache(path)[0] == [DEFCON]


async def test_fetch_or_cache_falls_back_to_cache_and_warns(tmp_path, caplog):
    path = tmp_path / 'ht.json'
    ht.save_cache(path, [BSIDES], '2026-08-31T07:00:00+00:00')
    with caplog.at_level('WARNING'):
        confs, source = await ht.fetch_or_cache(FakeSession([(500, {})]), path)
    assert source == 'cache'
    assert [c.code for c in confs] == ['BSIDESDET2026']
    assert sum('Hacker Tracker' in r.message for r in caplog.records if r.levelname == 'WARNING') == 1


async def test_fetch_or_cache_raises_when_nothing_is_available(tmp_path):
    with pytest.raises(ht.HackerTrackerError):
        await ht.fetch_or_cache(FakeSession([(500, {})]), tmp_path / 'missing.json')


def test_conference_to_event_maps_the_spec_columns():
    (conf,) = ht.parse_documents({'documents': [DEFCON]})
    row = ht.conference_to_event(conf, guild_id=7)
    assert row['guild_id'] == 7
    assert row['title'] == 'DEF CON 34'
    assert row['fingerprint'] == 'def con:2026'
    assert row['topic'] == 'cyber'
    assert (row['start_date'], row['end_date']) == ('2026-08-06', '2026-08-09')
    assert row['timezone'] == 'America/Los_Angeles'
    assert row['date_status'] == 'confirmed'
    assert row['city'] == 'Location TBD'
    assert row['region_code'] is None and row['country_code'] is None
    assert row['scope'] == 'regional'
    assert row['url'] == 'https://defcon.org'
    assert row['status'] == 'pending'
    assert row['provenance'] == 'hackertracker'
    assert row['submitted_by'] is None
    assert row['source_url'] == 'https://hackertracker.app/DEFCON34'
    assert row['source_note'] == 'ht:DEFCON34'
    assert row['recurrence'] == 'annual'


def test_conference_to_event_uses_the_listing_when_the_con_has_no_site():
    (conf,) = ht.parse_documents({'documents': [HIDDEN]})
    row = ht.conference_to_event(conf, guild_id=7)
    assert row['url'] == 'https://hackertracker.app/TESTCON'


def test_conference_to_event_drops_a_timezone_the_bot_cannot_load():
    (conf,) = ht.parse_documents({'documents': [doc('TZ', 'Bad TZ Con', '2026-10-01', '2026-10-02', tz='Mars/Olympus')]})
    assert ht.conference_to_event(conf, guild_id=7)['timezone'] is None
```

Append to `tests/unit/test_events_logic.py`:

```python
def test_provenances_include_hackertracker_and_unset_location_constant():
    from utils.events_logic import LOCATION_UNSET, PROVENANCES
    assert 'hackertracker' in PROVENANCES
    assert LOCATION_UNSET == 'Location TBD'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_hackertracker.py tests/unit/test_events_logic.py -q; echo exit=$?`
Expected: exit 1, `AttributeError: module 'utils.hackertracker' has no attribute 'fetch_conferences'` and an ImportError for `LOCATION_UNSET`.

- [ ] **Step 3: Implement**

In `penguin-overlord/utils/events_logic.py` change the two constants:

```python
PROVENANCES = ('member', 'calendar', 'ai', 'hackertracker', 'rollover')
LOCATION_UNSET = 'Location TBD'    # city placeholder for discovered rows; approval refuses it
```

Append to `penguin-overlord/utils/hackertracker.py` (add `import asyncio` and `from zoneinfo import ZoneInfo` at the top, and `from utils.events_logic import LOCATION_UNSET, fingerprint`):

```python
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
        except (OSError, ValueError, asyncio.TimeoutError) as e:
            raise HackerTrackerError(f'{type(e).__name__}: {e}') from e
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_hackertracker.py tests/unit/test_events_logic.py -q; echo exit=$?`
Expected: exit 0.

- [ ] **Step 5: Ruff and commit**

```bash
ruff check penguin-overlord tests scripts
git add penguin-overlord/utils/hackertracker.py penguin-overlord/utils/events_logic.py tests/unit/test_hackertracker.py tests/unit/test_events_logic.py
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "feat(events): fetch Hacker Tracker conferences with a last-known-good cache

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Store lookups the discovery run needs

**Files:**
- Modify: `penguin-overlord/utils/events_store.py`
- Test: `tests/unit/test_events_store.py`

**Interfaces:**
- Consumes: existing `EventsStore.insert`, `update`, `audit_rows`, `_audit_unlocked`.
- Produces: `async find_source_note(guild_id: int, note: str) -> dict | None` (latest `start_date` wins); `async update(event_id, changes, *, actor_id, action='edit')` (new keyword, default keeps today's audit action); `async last_audit(event_id: int, action: str) -> dict | None` (the newest `event_audit` row with that action, `after_json` decoded into key `after`).

- [ ] **Step 1: Write the failing tests**

Look at the top of `tests/unit/test_events_store.py` for its store fixture and row helper (they exist from phase 1; reuse their names). Append:

```python
async def test_find_source_note_returns_the_latest_edition(store):
    old = await store.insert(event(title='DEF CON 33', fingerprint='def con:2025', start_date='2025-08-07',
                                   end_date='2025-08-10', status='retired', source_note='ht:DEFCON'),
                             actor_id=0, action='import')
    new = await store.insert(event(title='DEF CON 34', fingerprint='def con:2026', start_date='2026-08-06',
                                   end_date='2026-08-09', source_note='ht:DEFCON'),
                             actor_id=0, action='import')
    found = await store.find_source_note(1, 'ht:DEFCON')
    assert found['id'] == new and found['id'] != old
    assert await store.find_source_note(1, 'ht:NOPE') is None
    assert await store.find_source_note(2, 'ht:DEFCON') is None


async def test_update_records_the_caller_action_in_the_audit_trail(store):
    event_id = await store.insert(event(), actor_id=0, action='import')
    await store.update(event_id, {'source_url': 'https://hackertracker.app/X', 'source_note': 'ht:X'},
                       actor_id=0, action='hackertracker_link')
    actions = [r['action'] for r in await store.audit_rows(event_id)]
    assert actions[-1] == 'hackertracker_link'
    await store.update(event_id, {'notes': 'n'}, actor_id=0)
    assert (await store.audit_rows(event_id))[-1]['action'] == 'edit'


async def test_last_audit_returns_the_newest_row_for_one_action(store):
    event_id = await store.insert(event(), actor_id=0, action='import')
    assert await store.last_audit(event_id, 'hackertracker_mismatch') is None
    await store.audit(event_id, 0, 'hackertracker_mismatch', None, {'start_date': '2026-10-01', 'end_date': '2026-10-02'})
    await store.audit(event_id, 0, 'hackertracker_mismatch', None, {'start_date': '2026-10-03', 'end_date': '2026-10-04'})
    last = await store.last_audit(event_id, 'hackertracker_mismatch')
    assert last['after'] == {'start_date': '2026-10-03', 'end_date': '2026-10-04'}
```

The file's fixture is `store` and its row helper is `event(**over)` (guild 1, BSides Detroit); if `audit_rows` returns the newest row first rather than last, index accordingly.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_events_store.py -q; echo exit=$?`
Expected: exit 1, `AttributeError: 'EventsStore' object has no attribute 'find_source_note'` (and a TypeError on the `action` keyword).

- [ ] **Step 3: Implement**

In `penguin-overlord/utils/events_store.py`, after `find_fingerprint`:

```python
    async def find_source_note(self, guild_id: int, note: str) -> dict | None:
        """The row a discovery source already produced for this guild
        (`ht:<code>` for Hacker Tracker). Several editions can share a
        note when a source reuses its code year to year; the latest start
        date is the one the caller compares against."""
        cursor = await self._conn.execute(
            'SELECT * FROM events WHERE guild_id = ? AND source_note = ? ORDER BY start_date DESC, id DESC LIMIT 1',
            (guild_id, note))
        row = await cursor.fetchone()
        return dict(row) if row else None
```

Change the `update` signature and its audit call:

```python
    async def update(self, event_id: int, changes: dict, *, actor_id: int, action: str = 'edit') -> dict | None:
```

and inside, `await self._audit_unlocked(event_id, actor_id, action, before, after)`.

After `audit_rows`:

```python
    async def last_audit(self, event_id: int, action: str) -> dict | None:
        """Newest trail row with this action, `after_json` decoded under
        'after'. Discovery uses it to avoid repeating a notice."""
        cursor = await self._conn.execute(
            'SELECT * FROM event_audit WHERE event_id = ? AND action = ? ORDER BY id DESC LIMIT 1',
            (event_id, action))
        row = await cursor.fetchone()
        if not row:
            return None
        out = dict(row)
        out['after'] = json.loads(out['after_json']) if out.get('after_json') else None
        return out
```

Check how `audit_rows` decodes json (it may already expose a decoded shape); match its key names if it does, and keep `after` as the decoded dict either way.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_events_store.py -q; echo exit=$?`
Expected: exit 0.

- [ ] **Step 5: Ruff and commit**

```bash
ruff check penguin-overlord tests scripts
git add penguin-overlord/utils/events_store.py tests/unit/test_events_store.py
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "feat(events): store lookups by source note and last audit action

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: The "On Hacker Tracker" link on cards and embeds, plus the mismatch notice

**Files:**
- Modify: `penguin-overlord/utils/events_cards.py`
- Test: `tests/unit/test_events_cards.py`

**Interfaces:**
- Consumes: `review_card(event, regions, *, provenance_line, decided=None)`, `reminder_embed(event, regions, days, *, changed=False)`, `format_dates(event)`, `COLOUR`.
- Produces: `source_link(event: dict) -> str | None` (`'On Hacker Tracker: <url>'` for `provenance == 'hackertracker'` with a `source_url`, else None); `review_card` Link field carries it on a second line; `reminder_embed` description ends with `[On Hacker Tracker](<url>)`; `mismatch_embed(event: dict, *, ht_start: str, ht_end: str, source_url: str) -> discord.Embed`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_events_cards.py` (the file already has `regions` and `event(**over)` helpers; reuse them):

```python
def ht_event(**over):
    return event(provenance='hackertracker', source_url='https://hackertracker.app/DEFCON34',
                 source_note='ht:DEFCON34', url='https://defcon.org', **over)


def test_source_link_only_for_hackertracker_rows():
    assert cards.source_link(ht_event()) == 'On Hacker Tracker: https://hackertracker.app/DEFCON34'
    assert cards.source_link(event(source_url='https://example.com')) is None
    assert cards.source_link(ht_event(source_url=None)) is None


def test_review_card_link_field_carries_both_links(regions):
    embed = cards.review_card(ht_event(), regions, provenance_line='Found on Hacker Tracker')
    link = next(f for f in embed.fields if f.name == 'Link')
    assert link.value == 'https://defcon.org\nOn Hacker Tracker: https://hackertracker.app/DEFCON34'
    plain = cards.review_card(event(), regions, provenance_line='x')
    assert 'Hacker Tracker' not in next(f for f in plain.fields if f.name == 'Link').value


def test_reminder_embed_ends_with_the_listing_link(regions):
    embed = cards.reminder_embed(ht_event(), regions, 7)
    assert embed.description.splitlines()[-1] == '[On Hacker Tracker](https://hackertracker.app/DEFCON34)'
    assert embed.url == 'https://defcon.org'
    assert 'Hacker Tracker' not in cards.reminder_embed(event(), regions, 7).description


def test_mismatch_embed_names_both_date_pairs_and_the_edit_command():
    embed = cards.mismatch_embed(ht_event(id=12), ht_start='2026-08-05', ht_end='2026-08-09',
                                 source_url='https://hackertracker.app/DEFCON34')
    assert embed.title == 'Hacker Tracker disagrees on #12: GrrCON'
    assert '2026-08-24 to 2026-08-25' in embed.description or 'Aug 24' in embed.description
    assert '2026-08-05' in embed.description and '2026-08-09' in embed.description
    assert '/events edit 12' in embed.description
    assert 'https://hackertracker.app/DEFCON34' in embed.description
    assert embed.author.name == 'Con Recon'
```

Adjust the `format_dates` expectation in the last test to whatever `format_dates` renders for the fixture's dates (check `test_format_dates` parameters in the same file) so the assertion is exact rather than an `or`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_events_cards.py -q; echo exit=$?`
Expected: exit 1, `AttributeError: module 'utils.events_cards' has no attribute 'source_link'`.

- [ ] **Step 3: Implement**

In `penguin-overlord/utils/events_cards.py`:

```python
def source_link(event: dict) -> str | None:
    """The second link a discovered row carries: the listing it came from.
    Only Hacker Tracker rows have one today; the text names the source so
    a member knows what they are clicking."""
    if event.get('provenance') == 'hackertracker' and event.get('source_url'):
        return f"On Hacker Tracker: {event['source_url']}"
    return None
```

In `review_card`, replace the Link field line with:

```python
    link_value = event['url'] or 'none given'
    extra = source_link(event)
    if extra:
        link_value = f'{link_value}\n{extra}'
    embed.add_field(name='Link', value=link_value, inline=False)
```

In `reminder_embed`, after the notes block and before building the embed:

```python
    if source_link(event):
        lines.append(f"[On Hacker Tracker]({event['source_url']})")
```

Add:

```python
def mismatch_embed(event: dict, *, ht_start: str, ht_end: str, source_url: str) -> discord.Embed:
    """Review-channel notice, no buttons: the organizer's dates on Hacker
    Tracker differ from an approved row. Phase 2b's verify job replaces
    this with a proposal card that applies the change in one click."""
    ours = format_dates(event)
    theirs = ht_start if ht_start == ht_end else f'{ht_start} to {ht_end}'
    body = (f'Calendar: {ours}\nHacker Tracker: {theirs}\n'
            f'Check {source_url} and use `/events edit {event["id"]}` if the organizer is right.')
    embed = discord.Embed(title=f"Hacker Tracker disagrees on #{event['id']}: {event['title']}",
                          description=body, colour=COLOUR['pending'])
    embed.set_author(name='Con Recon')
    return embed
```

Use `COLOUR['pending']` only if that key exists in `COLOUR`; otherwise pick the key the review card uses for pending rows.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_events_cards.py -q; echo exit=$?`
Expected: exit 0.

- [ ] **Step 5: Ruff and commit**

```bash
ruff check penguin-overlord tests scripts
git add penguin-overlord/utils/events_cards.py tests/unit/test_events_cards.py
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "feat(events): Hacker Tracker link on cards and embeds, mismatch notice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Config flag and metric

**Files:**
- Modify: `penguin-overlord/utils/config.py` (`EventsConfig`, `_load_events`, and the effective-config summary line near `f'events={flag(config.events.enabled)}'`)
- Modify: `penguin-overlord/utils/metrics.py`
- Modify: `.env.example` (append only), `docs/reference/CONFIGURATION.md`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `_Reader.bool`, `EventsConfig`.
- Produces: `EventsConfig.discovery_enabled: bool = False` read from `EVENTS_DISCOVERY_ENABLED`; `EVENTS_DISCOVERY = Counter('penguin_events_discovery_total', 'Discovery runs by source and outcome', ['source', 'outcome'])` with the `_NoopMetric` fallback like the other events metrics.

- [ ] **Step 1: Write the failing tests**

Find the existing events config tests in `tests/unit/test_config.py` (search for `EVENTS_ENABLED`) and add next to them, using the same helper that file uses to build an env and call `load_config`/`load_events_config`:

```python
def test_events_discovery_flag_defaults_off_and_parses():
    from utils.config import load_events_config
    assert load_events_config({}).discovery_enabled is False
    assert load_events_config({'EVENTS_DISCOVERY_ENABLED': 'true'}).discovery_enabled is True


def test_events_discovery_metric_exists():
    from utils import metrics
    assert hasattr(metrics, 'EVENTS_DISCOVERY')
    metrics.EVENTS_DISCOVERY.labels(source='hackertracker', outcome='live').inc()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_config.py -q -k discovery; echo exit=$?`
Expected: exit 1, `AttributeError: 'EventsConfig' object has no attribute 'discovery_enabled'`.

- [ ] **Step 3: Implement**

`utils/config.py`, in `EventsConfig` after `pending_expire_days`:

```python
    discovery_enabled: bool = False
```

In `_load_events`, inside the `EventsConfig(...)` call:

```python
        discovery_enabled=r.bool('EVENTS_DISCOVERY_ENABLED', False),
```

In the effective-config summary (the line that renders `events=...`), extend it to `f'events={flag(config.events.enabled)}/discovery={flag(config.events.discovery_enabled)}'` only if the surrounding lines use the same `a/b` form for other features; otherwise leave the summary alone.

`utils/metrics.py`, next to the other `EVENTS_*` definitions inside the `try` block:

```python
    EVENTS_DISCOVERY = Counter('penguin_events_discovery_total', 'Discovery runs by source and outcome',
                               ['source', 'outcome'])
```

and in the fallback block add `EVENTS_DISCOVERY = _NoopMetric()` (or extend the existing chained assignment).

`.env.example`: the events block exists from phase 1. Append (standalone command, this is the only permitted operation on that file):

```bash
cat >> .env.example <<'EOF'

# Con Recon discovery: read the public Hacker Tracker conference list every Monday
# and queue unknown cons for review. Off until you have said hello in junctor's Discord.
EVENTS_DISCOVERY_ENABLED=false
EOF
```

`docs/reference/CONFIGURATION.md`: add a row to the events table:

`| `EVENTS_DISCOVERY_ENABLED` | bool | `false` | Monday Hacker Tracker read; new cons land in the review queue with a "Location TBD" city for a moderator to fill in. |`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_config.py -q; echo exit=$?`
Expected: exit 0.

- [ ] **Step 5: Ruff and commit**

```bash
ruff check penguin-overlord tests scripts
git add penguin-overlord/utils/config.py penguin-overlord/utils/metrics.py .env.example docs/reference/CONFIGURATION.md tests/unit/test_config.py
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "feat(events): EVENTS_DISCOVERY_ENABLED flag and discovery metric

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `run_discovery`, the Monday hook, `/events discover`, and the approval gate

**Files:**
- Modify: `penguin-overlord/cogs/events.py`
- Test: `tests/unit/test_events_cog.py`

**Interfaces:**
- Consumes: `hackertracker.fetch_or_cache(session, cache_path)`, `hackertracker.cache_path(data_dir)`, `hackertracker.conference_to_event(conf, guild_id=...)`, `hackertracker.HackerTrackerError`, `hackertracker.app_url`; `EventsStore.find_source_note`, `find_fingerprint`, `insert`, `update(..., action=)`, `last_audit`, `audit`; `cards.mismatch_embed`, `cards.allowed_mentions`; `LOCATION_UNSET`; `EVENTS_DISCOVERY`, `EVENTS_SUBMISSIONS`, `EVENTS_PENDING`; `utils.http.client_session`; `self.cfg.discovery_enabled`; `self._target_guild_id()`; `self.post_review_card`; `self._channel`.
- Produces: `async Events.run_discovery(today: date | None = None, *, session=None) -> dict` returning `{'source': 'live'|'cache'|'failed', 'fetched': int, 'new': int, 'linked': int, 'mismatches': int, 'skipped': int}`; `Events.discovery_cache_path() -> Path`; `PROVENANCE_LINES['hackertracker']`; `/events discover` (moderator, ephemeral); `decide()` refuses approval while `city == LOCATION_UNSET`; `run_sweep` result gains a `'discovery'` key on Mondays when enabled; `/events status` gains a `discovery: on|off` fragment.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_events_cog.py`. The file's `cog` fixture builds the cog from env vars, and its `wire`, `interaction`, `event`, `FakeChannel` helpers are reused here. Discovery is enabled per test by replacing `cog.cfg` the same way the fixture replaces channel ids.

```python
# -- discovery (Hacker Tracker) -------------------------------------------------

from datetime import date as _date

from utils import hackertracker as ht


def enable_discovery(cog):
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'discovery_enabled': True})


def conf(code, name, start, end, *, hidden=False, link='https://example.org'):
    return ht.Conference(code=code, name=name, start_date=_date.fromisoformat(start),
                         end_date=_date.fromisoformat(end), timezone='America/Detroit',
                         link=link, hidden=hidden, updated_at=None)


def fake_fetch(confs, source='live'):
    async def _fetch(session, cache):
        return list(confs), source
    return _fetch


async def test_discovery_inserts_new_upcoming_cons_as_pending_with_a_card(cog, monkeypatch):
    enable_discovery(cog)
    guild, channels = wire(cog)
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([
        conf('BSIDESDET2026', 'BSides Detroit 2026', '2026-09-26', '2026-09-27'),
        conf('HIDDEN', 'Secret Con', '2026-10-01', '2026-10-02', hidden=True),
        conf('OLD', 'Last Year Con', '2026-01-10', '2026-01-11'),
    ]))
    result = await cog.run_discovery()
    assert result == {'source': 'live', 'fetched': 3, 'new': 1, 'linked': 0, 'mismatches': 0, 'skipped': 2}
    pending = await cog.store.list_pending(GUILD)
    assert [p['title'] for p in pending] == ['BSides Detroit 2026']
    row = pending[0]
    assert row['provenance'] == 'hackertracker'
    assert row['source_url'] == 'https://hackertracker.app/BSIDESDET2026'
    assert row['source_note'] == 'ht:BSIDESDET2026'
    assert row['city'] == 'Location TBD'
    assert row['review_message_id'] is not None
    card = channels[6000].sent[-1].embed
    assert 'Hacker Tracker' in card.description
    assert 'On Hacker Tracker: https://hackertracker.app/BSIDESDET2026' in \
        next(f for f in card.fields if f.name == 'Link').value


async def test_discovery_is_idempotent_across_runs(cog, monkeypatch):
    enable_discovery(cog)
    wire(cog)
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('X', 'X Con', '2026-11-01', '2026-11-02')]))
    first = await cog.run_discovery()
    second = await cog.run_discovery()
    assert first['new'] == 1 and second['new'] == 0 and second['skipped'] == 1
    assert len(await cog.store.list_pending(GUILD)) == 1


async def test_discovery_links_an_existing_row_that_matches_by_fingerprint(cog, monkeypatch):
    enable_discovery(cog)
    wire(cog)
    existing = await cog.store.insert(event(title='GrrCON', start_date='2026-09-24', end_date='2026-09-25',
                                            fingerprint='grrcon:2026'), actor_id=0, action='import')
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('GRRCON2026', 'GrrCON', '2026-09-24', '2026-09-25')]))
    result = await cog.run_discovery()
    assert result['linked'] == 1 and result['new'] == 0
    row = await cog.store.get(existing)
    assert row['source_url'] == 'https://hackertracker.app/GRRCON2026'
    assert row['source_note'] == 'ht:GRRCON2026'
    assert row['provenance'] == 'calendar'        # linking does not rewrite who added it
    assert (await cog.store.audit_rows(existing))[-1]['action'] == 'hackertracker_link'


async def test_discovery_posts_one_mismatch_notice_per_date_pair(cog, monkeypatch):
    enable_discovery(cog)
    guild, channels = wire(cog)
    existing = await cog.store.insert(event(title='GrrCON', fingerprint='grrcon:2026', source_note='ht:GRRCON2026',
                                            source_url='https://hackertracker.app/GRRCON2026'),
                                      actor_id=0, action='import')
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('GRRCON2026', 'GrrCON', '2026-09-25', '2026-09-26')]))
    assert (await cog.run_discovery())['mismatches'] == 1
    notice = channels[6000].sent[-1]
    assert notice.embed.title == f'Hacker Tracker disagrees on #{existing}: GrrCON'
    assert notice.view is None
    assert (await cog.run_discovery())['mismatches'] == 0          # same dates again: silent
    assert len(channels[6000].sent) == 1
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('GRRCON2026', 'GrrCON', '2026-09-27', '2026-09-28')]))
    assert (await cog.run_discovery())['mismatches'] == 1          # new dates: one more notice


async def test_discovery_ignores_mismatches_on_rows_that_are_not_approved(cog, monkeypatch):
    enable_discovery(cog)
    guild, channels = wire(cog)
    await cog.store.insert(event(title='Pend', fingerprint='pend:2026', status='pending', source_note='ht:PEND'),
                           actor_id=0, action='import')
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('PEND', 'Pend', '2026-09-25', '2026-09-26')]))
    result = await cog.run_discovery()
    assert result == {'source': 'live', 'fetched': 1, 'new': 0, 'linked': 0, 'mismatches': 0, 'skipped': 1}
    assert channels[6000].sent == []


async def test_discovery_treats_a_reused_code_next_year_as_a_new_edition(cog, monkeypatch):
    enable_discovery(cog)
    wire(cog)
    await cog.store.insert(event(title='DEF CON 33', fingerprint='def con:2025', start_date='2025-08-07',
                                 end_date='2025-08-10', status='retired', source_note='ht:DEFCON'),
                           actor_id=0, action='import')
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('DEFCON', 'DEF CON 34', '2026-08-06', '2026-08-09')]))
    cog.today = lambda: _date(2026, 6, 1)
    assert (await cog.run_discovery())['new'] == 1


async def test_discovery_reports_failure_without_raising(cog, monkeypatch, caplog):
    enable_discovery(cog)
    wire(cog)

    async def boom(session, cache):
        raise ht.HackerTrackerError('HTTP 500')
    monkeypatch.setattr(ht, 'fetch_or_cache', boom)
    with caplog.at_level('WARNING'):
        result = await cog.run_discovery()
    assert result['source'] == 'failed' and result['new'] == 0
    assert any('Hacker Tracker' in r.message for r in caplog.records)


async def test_discovery_does_nothing_without_a_target_guild(cog, monkeypatch):
    enable_discovery(cog)
    wire(cog, channels={})
    called = []

    async def spy(session, cache):
        called.append(1)
        return [], 'live'
    monkeypatch.setattr(ht, 'fetch_or_cache', spy)
    result = await cog.run_discovery()
    assert called == [] and result['source'] == 'failed'


async def test_sweep_runs_discovery_on_mondays_only_when_enabled(cog, monkeypatch):
    wire(cog)
    runs = []

    async def fake_run(today=None, **kw):
        runs.append(today)
        return {'source': 'live', 'fetched': 0, 'new': 0, 'linked': 0, 'mismatches': 0, 'skipped': 0}
    monkeypatch.setattr(cog, 'run_discovery', fake_run)
    monday, tuesday = _date(2026, 9, 7), _date(2026, 9, 8)
    assert 'discovery' not in await cog.run_sweep(today=monday)          # flag off
    enable_discovery(cog)
    assert 'discovery' not in await cog.run_sweep(today=tuesday)
    result = await cog.run_sweep(today=monday)
    assert result['discovery']['source'] == 'live' and runs == [monday]


async def test_sweep_survives_a_discovery_crash(cog, monkeypatch):
    wire(cog)
    enable_discovery(cog)

    async def crash(today=None, **kw):
        raise RuntimeError('boom')
    monkeypatch.setattr(cog, 'run_discovery', crash)
    result = await cog.run_sweep(today=_date(2026, 9, 7))
    assert result['discovery'] == {'source': 'failed', 'fetched': 0, 'new': 0, 'linked': 0, 'mismatches': 0, 'skipped': 0}
    assert 'retired' in result


async def test_discover_command_is_mod_only_and_reports_counts(cog, monkeypatch):
    enable_discovery(cog)
    wire(cog)
    monkeypatch.setattr(ht, 'fetch_or_cache', fake_fetch([conf('X', 'X Con', '2026-11-01', '2026-11-02')]))
    member = interaction()
    await cog.events_discover.callback(cog, member)
    assert member.response.sent[-1].content == MOD_ONLY_TEXT
    mod = interaction(mod=True)
    await cog.events_discover.callback(cog, mod)
    text = mod.followup.sent[-1].content
    assert 'new: 1' in text and 'live' in text


async def test_discover_command_refuses_when_discovery_is_off(cog):
    wire(cog)
    mod = interaction(mod=True)
    await cog.events_discover.callback(cog, mod)
    assert 'EVENTS_DISCOVERY_ENABLED' in mod.response.sent[-1].content


async def test_approve_refuses_a_row_with_the_location_placeholder(cog):
    guild, channels = wire(cog)
    event_id = await cog.store.insert(event(title='TBD Con', fingerprint='tbd con:2026', status='pending',
                                            city='Location TBD', region_code=None, country_code=None,
                                            provenance='hackertracker'), actor_id=0, action='discover')
    mod = interaction(mod=True)
    await cog.decide(mod, event_id, 'approved')
    assert (await cog.store.get(event_id))['status'] == 'pending'
    assert 'location' in mod.response.sent[-1].content.lower()     # refused before the defer
    await cog.store.update(event_id, {'city': 'Detroit', 'region_code': 'US-MI', 'country_code': 'US'}, actor_id=1)
    await cog.decide(interaction(mod=True), event_id, 'approved')
    assert (await cog.store.get(event_id))['status'] == 'approved'


async def test_status_mentions_discovery(cog):
    wire(cog)
    mod = interaction(mod=True)
    await cog.events_status.callback(cog, mod)
    assert 'discovery: off' in mod.followup.sent[-1].content
```

Replies sent before a defer land in `interaction.response.sent`; replies after `defer()` land in `interaction.followup.sent` (see `FakeResponse`/`FakeFollowup` at the top of the file). Import `MOD_ONLY_TEXT` from `cogs.events` next to `DISABLED_TEXT`. The `interaction()` helper's `mod=` flag drives `_is_mod`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_events_cog.py -q -k "discover or mismatch or placeholder or status_mentions or sweep_runs or sweep_survives"; echo exit=$?`
Expected: exit 1, `AttributeError: 'Events' object has no attribute 'run_discovery'` and friends.

- [ ] **Step 3: Implement**

In `penguin-overlord/cogs/events.py`:

Imports: add `from pathlib import Path`, `from utils import hackertracker`, `from utils.http import client_session`, extend the `utils.events_logic` import with `LOCATION_UNSET`, extend the `utils.metrics` import with `EVENTS_DISCOVERY`. Add `import aiohttp` if a timeout object is built here.

`PROVENANCE_LINES` gains:

```python
    'hackertracker': 'Found on Hacker Tracker; the organizer set the dates. Set the location (Edit) before approving.',
```

Approval gate, in `decide()` right after the moderator check and before the defer:

```python
        if status == 'approved':
            current = await self.store.get(event_id)
            if current and current.get('city') == LOCATION_UNSET:
                await self._reply(interaction,
                                  f'#{event_id} has no location yet. Use Edit (or /events edit {event_id}) '
                                  f'to set the city and place, then approve.')
                return
```

`_reply` must work before a defer: read `_reply` (line ~408) and confirm it sends an ephemeral `response.send_message` when the interaction is not yet done; the existing tests for `MOD_ONLY_TEXT` prove that path.

Discovery, placed after `run_sweep`:

```python
    # -- discovery -------------------------------------------------------------

    EMPTY_DISCOVERY = {'source': 'failed', 'fetched': 0, 'new': 0, 'linked': 0, 'mismatches': 0, 'skipped': 0}

    def discovery_cache_path(self) -> Path:
        config = getattr(self.bot, 'config', None)
        data_dir = config.paths.data_dir if config is not None else resolve_data_dir()
        return hackertracker.cache_path(Path(data_dir))

    async def run_discovery(self, today: Optional[date] = None, *, session=None) -> dict:
        """Read Hacker Tracker once, queue unknown upcoming cons for review,
        link rows we already had, and tell moderators when the organizer's
        dates differ from an approved row. Never raises: the sweep and the
        command both read the returned counts."""
        today = today or self.today()
        result = dict(self.EMPTY_DISCOVERY)
        guild_id = await self._target_guild_id()
        if guild_id is None:
            logger.warning('Hacker Tracker: no events channel guild resolved; discovery skipped')
            return result
        own_session = session is None
        if own_session:
            session = client_session(timeout=aiohttp.ClientTimeout(total=20),
                                     headers={'Accept': 'application/json'})
        try:
            confs, source = await hackertracker.fetch_or_cache(session, self.discovery_cache_path())
        except hackertracker.HackerTrackerError as e:
            logger.warning('Hacker Tracker: discovery failed: %s', e)
            EVENTS_DISCOVERY.labels(source='hackertracker', outcome='failed').inc()
            return result
        finally:
            if own_session:
                await session.close()
        result['source'] = source
        result['fetched'] = len(confs)
        EVENTS_DISCOVERY.labels(source='hackertracker', outcome=source).inc()
        for conf in confs:
            if conf.hidden or conf.end_date < today:
                result['skipped'] += 1
                continue
            outcome = await self._reconcile_conference(conf, guild_id)
            result[outcome] += 1
        EVENTS_PENDING.set(await self.store.pending_count(guild_id))
        logger.info('Hacker Tracker discovery for %s: %s', today, result)
        return result

    async def _reconcile_conference(self, conf, guild_id: int) -> str:
        """One conference against the table. Returns the counter to bump:
        'new', 'linked', 'mismatches' or 'skipped'."""
        row = hackertracker.conference_to_event(conf, guild_id=guild_id)
        known = await self.store.find_source_note(guild_id, row['source_note'])
        if known is not None:
            same_year = known['start_date'][:4] == row['start_date'][:4]
            if known['status'] in ('retired', 'cancelled', 'rejected') and not same_year:
                known = None                     # next year's edition under a reused code
        if known is None:
            twin = await self.store.find_fingerprint(guild_id, row['fingerprint'])
            if twin is not None:
                if not twin.get('source_note'):
                    await self.store.update(twin['id'], {'source_url': row['source_url'],
                                                         'source_note': row['source_note']},
                                            actor_id=0, action='hackertracker_link')
                    logger.info('Hacker Tracker: linked #%d %s to %s', twin['id'], twin['title'], row['source_url'])
                    return 'linked'
                return 'skipped'
            try:
                event_id = await self.store.insert(row, actor_id=0, action='discover')
            except database.aiosqlite.IntegrityError:
                return 'skipped'
            EVENTS_SUBMISSIONS.labels(provenance='hackertracker').inc()
            event = await self.store.get(event_id)
            message_id = await self.post_review_card(event)
            if message_id:
                await self.store.set_review_message(event_id, message_id)
            return 'new'
        if known['status'] != 'approved':
            return 'skipped'
        if (known['start_date'], known['end_date']) == (row['start_date'], row['end_date']):
            return 'skipped'
        last = await self.store.last_audit(known['id'], 'hackertracker_mismatch')
        theirs = {'start_date': row['start_date'], 'end_date': row['end_date']}
        if last and last.get('after') == theirs:
            return 'skipped'
        channel = await self._channel(self.cfg.review_channel_id)
        if channel is None:
            return 'skipped'
        try:
            await channel.send(embed=cards.mismatch_embed(known, ht_start=row['start_date'], ht_end=row['end_date'],
                                                          source_url=row['source_url']),
                               allowed_mentions=cards.allowed_mentions([]))
        except discord.HTTPException as e:
            logger.warning('Hacker Tracker: mismatch notice for #%d failed: %s', known['id'], e)
            return 'skipped'
        await self.store.audit(known['id'], 0, 'hackertracker_mismatch', None, theirs)
        return 'mismatches'
```

Import `resolve_data_dir` from `utils.state`.

Monday hook, in `run_sweep` after `purged = ...` and before the `EVENTS_PENDING` loop:

```python
        if self.cfg.discovery_enabled and today.weekday() == 0:
            try:
                discovery = await self.run_discovery(today)
            except Exception:
                logger.exception('Hacker Tracker discovery crashed; the rest of the sweep continues')
                discovery = dict(self.EMPTY_DISCOVERY)
```

and add `'discovery': discovery` to `result` only when the block ran (initialise `discovery = None` above and include the key when it is not None).

Moderator command, next to `events_status`:

```python
    @events.command(name='discover', description='Read Hacker Tracker now and queue new cons for review')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_discover(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        if not self._is_mod(interaction):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        if not self.cfg.discovery_enabled:
            await self._reply(interaction, 'Discovery is off. Set EVENTS_DISCOVERY_ENABLED=true and restart the bot.')
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.run_discovery()
        await self._reply(interaction,
                          f"Hacker Tracker ({result['source']}): fetched {result['fetched']}, new: {result['new']}, "
                          f"linked: {result['linked']}, date mismatches: {result['mismatches']}, "
                          f"skipped: {result['skipped']}.")
```

Status line: in `events_status`, extend the digest fragment: `f"digest {'on' if self.cfg.digest_enabled else 'off'}; discovery: {'on' if self.cfg.discovery_enabled else 'off'}"`.

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest tests/unit -q >/dev/null; echo exit=$?`
Expected: exit 0.

- [ ] **Step 5: Ruff and commit**

```bash
ruff check penguin-overlord tests scripts
git add penguin-overlord/cogs/events.py tests/unit/test_events_cog.py
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "feat(events): Monday Hacker Tracker discovery, /events discover, location gate on approve

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Docs

**Files:**
- Modify: `docs/features/CON_RECON.md`, `docs/reference/COMMANDS.md`, `docs/ROADMAP.md`, `docs/superpowers/specs/2026-09-03-conference-database-design.md`

**Interfaces:** none; text only. No em dashes.

- [ ] **Step 1: CON_RECON.md**

Replace the "What comes next" section (added 2026-09-05) with a "Discovery: Hacker Tracker" section that says: what the source is and why it is trusted (organizers enter their own dates); the flag `EVENTS_DISCOVERY_ENABLED` (default off) and the Monday timing inside the nightly sweep; `/events discover` for an immediate run; what a discovered row looks like on the review card (provenance line, "Location TBD", the two links) and that Approve refuses until the location is set via Edit; the mismatch notice for approved rows and that it repeats only when the organizer's dates change again; the cache file `hackertracker_conferences.json` in `DATA_DIR`; the etiquette paragraph (one read per week, undocumented endpoint, no data licence, say hello in junctor's Discord, linked from github.com/junctor/hackertracker-about, before turning it on). Add `EVENTS_DISCOVERY_ENABLED` to the settings table and `penguin_events_discovery_total{source,outcome}` to the Metrics paragraph. Add a Rollout step 4: "When you are ready for discovery: say hello in junctor's Discord, set `EVENTS_DISCOVERY_ENABLED=true`, run `/events discover` once, and work the review queue; every discovered row needs its location set before Approve accepts it."

- [ ] **Step 2: COMMANDS.md**

Add `/events discover` to the moderator events commands with one line: "Reads Hacker Tracker now and queues unknown cons for review; reports fetched, new, linked, mismatches, skipped."

- [ ] **Step 3: ROADMAP.md**

In the Con Recon table row, change "Phase 2 adds the Gemini key pool, verify and discovery, with Hacker Tracker (hackertracker.app) as the first discovery source; rows from it link back to their Hacker Tracker listing." to "Phase 2a (Hacker Tracker discovery, no model) shipped; phase 2b adds the Gemini key pool, verify with proposal cards, and the aggregator fetchers." Change the numbered item "Con Recon phase 2 (Gemini verify and discovery; phase 1 shipped)" to "Con Recon phase 2b (Gemini verify and aggregator discovery; phases 1 and 2a shipped)".

- [ ] **Step 4: Spec**

In section 7, Hacker Tracker bullet 2, replace "the `locations` subcollection is tried first for a venue string when it is not empty" with "phase 2a leaves the location to the moderator (Approve refuses a row until it is set); the `locations` subcollection holds rooms and tracks, not cities, so a venue hint from it is a phase 2b experiment". Also change "a date change on a matched approved row becomes a proposal card exactly like the verify job's" to "a date change on a matched approved row posts a notice to the review channel in phase 2a (one per distinct date pair), and becomes a proposal card once the verify job exists".

- [ ] **Step 5: Check and commit**

```bash
grep -c $'\xe2\x80\x94' docs/features/CON_RECON.md docs/reference/COMMANDS.md docs/ROADMAP.md docs/superpowers/specs/2026-09-03-conference-database-design.md
git add docs/features/CON_RECON.md docs/reference/COMMANDS.md docs/ROADMAP.md docs/superpowers/specs/2026-09-03-conference-database-design.md
git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com -c user.name=ChiefGyk3D commit -m "docs(events): Hacker Tracker discovery, /events discover, spec phase 2a notes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Every count from the grep must be 0.

---

## Self-review

- **Spec coverage (section 7, Hacker Tracker bullets):** poll Monday before page fetches (Task 6 sweep hook; there are no page fetches yet); skip hidden and ended (Task 6 `run_discovery`); match by `source_note` then fingerprint (Task 6 `_reconcile_conference`, Task 3 lookups); date change on approved row (Task 6 notice, Task 4 embed, spec amended in Task 7); insert columns (Task 2 `conference_to_event`); location left to the moderator (Task 2 placeholder, Task 6 gate, Task 7 spec amendment); second link on card and public embed (Task 4); never fetch deep links (nothing fetches them); cache last good, one WARNING, one list call per week (Task 2 `fetch_or_cache`, Task 6 Monday-only); say hello before going live (Task 7 docs, flag default off in Task 5); only onboarded cons (documented in Task 7).
- **Placeholders:** none; every step carries its code or exact text.
- **Type consistency:** `fetch_or_cache(session, cache_path) -> (list[Conference], str)` is what Task 6 monkeypatches and calls; `conference_to_event(conf, guild_id=)` keyword-only in Tasks 2 and 6; `update(..., action=)` in Tasks 3 and 6; `last_audit` returns a dict with `after` in Tasks 3 and 6; `mismatch_embed(event, *, ht_start, ht_end, source_url)` in Tasks 4 and 6; `EVENTS_DISCOVERY.labels(source=, outcome=)` in Tasks 5 and 6; `LOCATION_UNSET` in Tasks 2 and 6; `EMPTY_DISCOVERY` keys equal the dict the tests compare against.
