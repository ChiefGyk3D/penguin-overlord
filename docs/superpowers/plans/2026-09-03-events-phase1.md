# Events Database Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CSV event pinger with a SQLite-backed events system: member submissions, a mod approval queue with restart-safe cards, `/events` slash commands, 30/7/1 reminders that mention topic and region roles, a Monday digest, a nightly sweep, and a one-shot CSV import.

**Architecture:** Schema v3 adds the events tables to the existing `ModerationDatabase` migration authority; `utils/events_store.py` owns every query on the shared connection; `utils/events_logic.py` holds the pure decisions (fingerprints, windows, rollover dates, role resolution, CSV mapping); `utils/events_cards.py` renders embeds; `cogs/events.py` is the thin Discord layer (one `app_commands.Group`, `DynamicItem` buttons, two clock-aligned `tasks.loop`s). No AI, no Gemini, no discovery in this phase.

**Tech Stack:** Python 3.10+, discord.py 2.7.1, aiosqlite, zoneinfo, pytest (asyncio_mode=auto), ruff.

**Spec:** `docs/superpowers/specs/2026-09-03-conference-database-design.md` (approved, revision 2). Sections 3 to 6, 8 to 13 are phase 1; section 7 (AI jobs) and the Gemini parts of 9 and 12 are phase 2.

## Global Constraints

- **No em dashes** in anything user-facing: bot reply strings, embed text, log lines, docs, the `.env.example` block, commit messages. Use commas, colons, parentheses. Code comments and docstrings are exempt but avoid them there too.
- **Hermetic tests only.** Never run `bot.py`, any `*_runner.py`, or `scripts/import-events-csv.py` against real data, even from a worktree, even with `env -i`. The unit suite plus the fake bot in tests is the whole verification surface. A subagent that thinks it needs to "try the bot" stops and reports instead.
- **Never read `.env` or `.env.example` with Read/cat** (permission-blocked); append to `.env.example` with a `cat >>` heredoc as Task 11 shows.
- **TDD:** every task writes the failing test, runs it, then the code. Test command: `python3 -m pytest tests/unit -q -p no:cacheprovider`. Lint: `.venv/bin/ruff check .` (line length 120, bare `except` allowed only in cogs/utils).
- **Commit** each task on branch `feat/events-phase1` (branched from `main`, tip `1720c53` or later). Messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Commit author email `19499446+ChiefGyk3D@users.noreply.github.com`. Never write the work gh handle or the employer name anywhere.
- **No hostnames, serials or asset tags** in any file.
- Cog directory rule: `bot.py` and `tests/unit/test_cog_imports.py` load **every** `cogs/*.py` as an extension, so helper modules go in `utils/`, never in `cogs/`.
- Mentions: every member-facing send uses `AllowedMentions(everyone=False, users=False, roles=[...])`. `users=False` is non-negotiable.
- Nothing here creates Discord roles. `/roles post` does that.
- Timezone default `America/New_York`; "today" is the date in `EVENTS_TIMEZONE`.
- Topics: `cyber`, `ham`, `foss`, `other`. Statuses: `pending`, `approved`, `rejected`, `cancelled`, `retired`. Provenance: `member`, `calendar`, `ai`, `rollover`.

**Deliberate departures from spec section 4** (the plan wins; do not "fix" these back):
- `/events list` takes `topic`, `where`, `page` over a fixed 365-day horizon instead of `days` + separate `region` and `country`. One `where` autocomplete covers states, provinces, countries and Online, which is what the spec's own "select wherever they want" decision asks for; paging replaces the days knob.
- `/events next` has no `topic` filter; it is the 30-day slice of `list`.
- `/events search` matches title and city (region names are already in `list`'s filter).
- `/events status` omits "last five discovery runs" and "key pool summary" (phase 2). It does include the mention permission check.
- `/events discover` is phase 2.
- Spec section 8.2 deletes `events/`; this plan keeps the CSV (the import test reads it, the image ships it for the one-time import) and drops only the bind mount and the cog. Delete the directory in a follow-up after the import has run on the box.

---

## File structure

| path | responsibility |
| --- | --- |
| `penguin-overlord/utils/database.py` (modify) | `SCHEMA_VERSION = 3`, six new tables in `_SCHEMA`, public `conn`/`lock` properties |
| `penguin-overlord/utils/events_logic.py` (create) | pure functions: fingerprint, date math, windows, rollover, validation, region loading and role resolution, CSV row mapping, autocomplete choices |
| `penguin-overlord/utils/events_store.py` (create) | `EventsStore`: every SQL statement for events, reminders, audit, sweep |
| `penguin-overlord/utils/events_cards.py` (create) | embeds and mention plumbing: review card, reminder, list page, digest, `allowed_mentions()` |
| `penguin-overlord/utils/config.py` (modify) | `EventsConfig`, `_load_events`, `load_events_config`, `describe_config` line |
| `penguin-overlord/utils/metrics.py` (modify) | six `penguin_events_*` metrics |
| `penguin-overlord/assets/events/regions.json` (create) | region and country code to picker role name |
| `penguin-overlord/assets/role_panels/event_topics.json` (create) | the topic opt-in panel |
| `penguin-overlord/cogs/events.py` (create) | the cog: group, member and mod commands, buttons, modals, loops |
| `scripts/import-events-csv.py` (create) | one-shot CSV importer |
| `tests/unit/test_events_logic.py`, `test_events_store.py`, `test_events_cards.py`, `test_events_cog.py`, `test_events_import.py` (create) | one test module per unit |
| deletions | `penguin-overlord/cogs/eventpinger.py` (Task 7). `events/*.csv` stays: the import script and its test read it, and the image ships it for the one-time import on the box. |
| docs and build | `docs/features/EVENTS.md` (create), `README.md`, `docs/reference/COMMANDS.md`, `QUICK_REFERENCE.md`, `docs/ROADMAP.md`, `docs/features/ROLE_PICKER.md`, `cogs/help_categorized.py`, `cogs/admin.py`, `Dockerfile`, `docker-compose.yml`, `.env.example` |

The event row is a plain `dict` keyed by column name everywhere (store returns `dict(row)`, logic and cards take `Mapping`). Dates are ISO `YYYY-MM-DD` strings in the dict; logic functions convert with `date.fromisoformat` at the edge.

---

### Task 1: Schema v3 and the store skeleton

**Files:**
- Modify: `penguin-overlord/utils/database.py`
- Create: `penguin-overlord/utils/events_store.py`
- Test: `tests/unit/test_events_store.py`

**Interfaces:**
- Consumes: `utils.database.ModerationDatabase`, `get_database()`, `reset_database()`.
- Produces: `ModerationDatabase.conn` and `.lock` properties; `EventsStore(db)` with `insert(event, *, actor_id, action) -> int`, `get(event_id) -> dict | None`, `find_fingerprint(guild_id, fingerprint) -> dict | None`, `audit(event_id, actor_id, action, before=None, after=None)`, `audit_rows(event_id) -> list[dict]`; module constant `EVENT_COLUMNS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_events_store.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""EventsStore against a real aiosqlite file in a temp dir. Every write
that changes state must leave an audit row; fingerprints are unique per
guild."""

import json

import pytest

from utils import database
from utils.events_store import EventsStore


@pytest.fixture
async def store(tmp_data_dir):
    database.reset_database()
    db = await database.get_database()
    yield EventsStore(db)
    await db.close()
    database.reset_database()


def event(**over):
    base = dict(
        guild_id=1, title='BSides Detroit', fingerprint='bsides detroit:2026',
        topic='cyber', start_date='2026-05-30', end_date='2026-05-30',
        start_time=None, timezone=None, date_status='confirmed',
        city='Detroit', region_code='US-MI', country_code='US', scope='regional',
        url='https://bsidesdetroit.com', notes=None, recurrence='annual',
        parent_event_id=None, status='pending', provenance='member',
        submitted_by=42, source_url=None, source_note=None,
    )
    base.update(over)
    return base


async def test_schema_is_v3_with_events_tables(store):
    cursor = await store.db.conn.execute('SELECT version FROM schema_version')
    assert (await cursor.fetchone())['version'] == 3
    cursor = await store.db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    names = {row['name'] for row in await cursor.fetchall()}
    assert {'events', 'event_reminders', 'event_proposals', 'event_audit',
            'event_discovery_runs', 'ai_key_usage'} <= names


async def test_insert_returns_id_and_writes_audit(store):
    eid = await store.insert(event(), actor_id=42, action='submit')
    row = await store.get(eid)
    assert row['title'] == 'BSides Detroit' and row['status'] == 'pending'
    assert row['created_at'] and row['updated_at']
    audit = await store.audit_rows(eid)
    assert [a['action'] for a in audit] == ['submit']
    assert audit[0]['actor_id'] == 42
    assert json.loads(audit[0]['after_json'])['title'] == 'BSides Detroit'


async def test_fingerprint_is_unique_per_guild(store):
    await store.insert(event(), actor_id=42, action='submit')
    with pytest.raises(database.aiosqlite.IntegrityError):
        await store.insert(event(title='BSides Detroit 2026'), actor_id=42, action='submit')
    # Another guild may hold the same fingerprint.
    assert await store.insert(event(guild_id=2), actor_id=42, action='submit')


async def test_find_fingerprint(store):
    eid = await store.insert(event(), actor_id=42, action='submit')
    found = await store.find_fingerprint(1, 'bsides detroit:2026')
    assert found['id'] == eid
    assert await store.find_fingerprint(1, 'nothing:2026') is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_store.py -q -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'utils.events_store'`

- [ ] **Step 3: Bump the schema**

In `penguin-overlord/utils/database.py`:

1. Change `SCHEMA_VERSION = 2` to `SCHEMA_VERSION = 3`.
2. Update the module docstring's "Stores:" list to add `- events and its side tables: the conference database (utils/events_store.py owns the queries).`
3. Append to `_SCHEMA` (inside the triple-quoted string, after `mod_review_votes`):

```sql
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    fingerprint TEXT NOT NULL,      -- normalized title + start year, see events_logic.fingerprint
    topic TEXT NOT NULL,            -- cyber | ham | foss | other
    start_date TEXT NOT NULL,       -- ISO date
    end_date TEXT NOT NULL,
    start_time TEXT,                -- HH:MM or NULL for all-day
    timezone TEXT,                  -- IANA name, NULL means EVENTS_TIMEZONE
    date_status TEXT NOT NULL,      -- confirmed | estimated
    city TEXT,
    region_code TEXT,               -- ISO 3166-2, NULL for online
    country_code TEXT,              -- ISO 3166-1 alpha-2, NULL for online
    scope TEXT NOT NULL DEFAULT 'regional',  -- regional | national
    url TEXT,
    notes TEXT,
    recurrence TEXT NOT NULL DEFAULT 'none', -- none | annual
    parent_event_id INTEGER,
    status TEXT NOT NULL,           -- pending | approved | rejected | cancelled | retired
    provenance TEXT NOT NULL,       -- member | calendar | ai | rollover
    submitted_by INTEGER,
    source_url TEXT,
    source_note TEXT,
    ai_relevance TEXT,
    review_message_id INTEGER,
    decided_by INTEGER,
    decided_at TEXT,
    reject_reason TEXT,
    last_verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_guild_status_start
    ON events (guild_id, status, start_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_fingerprint
    ON events (guild_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_events_review_message
    ON events (review_message_id);
CREATE INDEX IF NOT EXISTS idx_events_status_created
    ON events (status, created_at);

CREATE TABLE IF NOT EXISTS event_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    window TEXT NOT NULL,           -- '30' | '7' | '1' | 'changed' | 'cancelled'
    channel_id INTEGER,
    message_id INTEGER,
    roles_mentioned TEXT,
    posted_at TEXT,
    UNIQUE (event_id, window)
);

CREATE TABLE IF NOT EXISTS event_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    proposed_json TEXT NOT NULL,
    review_message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',  -- open | applied | ignored
    decided_by INTEGER,
    decided_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,      -- user id, 0 for the bot
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_audit_event
    ON event_audit (event_id, id);

CREATE TABLE IF NOT EXISTS event_discovery_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    key_id TEXT,
    fetched_bytes INTEGER NOT NULL DEFAULT 0,
    candidates INTEGER NOT NULL DEFAULT 0,
    queued INTEGER NOT NULL DEFAULT 0,
    dup_skipped INTEGER NOT NULL DEFAULT 0,
    offtopic_skipped INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS ai_key_usage (
    key_id TEXT NOT NULL,
    day TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    cooldown_until TEXT,
    disabled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, day)
);
```

4. `_migrate` needs no ALTER for v3 (all new tables are `CREATE IF NOT EXISTS`); add a comment inside `_migrate` after the `from_version < 2` block: `# v3: events tables; CREATE IF NOT EXISTS in _SCHEMA is the whole migration.`
5. Add two properties on `ModerationDatabase` right after `__init__`:

```python
    @property
    def conn(self):
        """The shared aiosqlite connection (EventsStore borrows it)."""
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        """Guards read-modify-write sequences across every store on this connection."""
        return self._lock
```

- [ ] **Step 4: Write the store skeleton**

```python
# penguin-overlord/utils/events_store.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Queries for the events database (schema v3 tables in utils/database.py).

Borrows the connection from ModerationDatabase so there is one SQLite
file, one WAL, one lock. Rows come back as plain dicts keyed by column
name; callers never see aiosqlite.Row. Every state change writes an
event_audit row in the same call, so the trail cannot drift from the data.
"""

import json
import logging
from datetime import datetime, timezone

from utils.database import ModerationDatabase

logger = logging.getLogger(__name__)

# Columns a caller may supply on insert; everything else is set here.
EVENT_COLUMNS = (
    'guild_id', 'title', 'fingerprint', 'topic', 'start_date', 'end_date',
    'start_time', 'timezone', 'date_status', 'city', 'region_code',
    'country_code', 'scope', 'url', 'notes', 'recurrence', 'parent_event_id',
    'status', 'provenance', 'submitted_by', 'source_url', 'source_note',
    'ai_relevance', 'review_message_id', 'decided_by', 'decided_at',
    'reject_reason', 'last_verified_at',
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(row) -> str | None:
    return None if row is None else json.dumps(dict(row), default=str, sort_keys=True)


class EventsStore:
    def __init__(self, db: ModerationDatabase):
        self.db = db

    @property
    def _conn(self):
        return self.db.conn

    # -- audit --------------------------------------------------------------

    async def audit(self, event_id: int, actor_id: int, action: str,
                    before=None, after=None) -> None:
        """Append one trail row. Callers that hold db.lock call _audit_unlocked."""
        async with self.db.lock:
            await self._audit_unlocked(event_id, actor_id, action, before, after)
            await self._conn.commit()

    async def _audit_unlocked(self, event_id, actor_id, action, before=None, after=None):
        await self._conn.execute(
            """INSERT INTO event_audit (event_id, actor_id, action, before_json, after_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, actor_id, action, _dump(before), _dump(after), _utcnow()),
        )

    async def audit_rows(self, event_id: int) -> list[dict]:
        cursor = await self._conn.execute(
            'SELECT * FROM event_audit WHERE event_id = ? ORDER BY id', (event_id,))
        return [dict(r) for r in await cursor.fetchall()]

    # -- rows ---------------------------------------------------------------

    async def insert(self, event: dict, *, actor_id: int, action: str) -> int:
        """Insert one row plus its audit entry. Raises aiosqlite.IntegrityError
        when the (guild_id, fingerprint) pair already exists; callers check
        find_fingerprint() first for the friendly message and treat the
        error as the race-loser path."""
        now = _utcnow()
        values = {col: event.get(col) for col in EVENT_COLUMNS}
        # An explicit NULL bypasses the column DEFAULT, so apply the two
        # defaults here for callers that leave them out.
        values['scope'] = values['scope'] or 'regional'
        values['recurrence'] = values['recurrence'] or 'none'
        values['created_at'] = now
        values['updated_at'] = now
        columns = ', '.join(values)
        marks = ', '.join('?' for _ in values)
        async with self.db.lock:
            cursor = await self._conn.execute(
                f'INSERT INTO events ({columns}) VALUES ({marks})', tuple(values.values()))
            event_id = cursor.lastrowid
            values['id'] = event_id
            await self._audit_unlocked(event_id, actor_id, action, None, values)
            await self._conn.commit()
        return event_id

    async def get(self, event_id: int) -> dict | None:
        cursor = await self._conn.execute('SELECT * FROM events WHERE id = ?', (event_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def find_fingerprint(self, guild_id: int, fingerprint: str) -> dict | None:
        cursor = await self._conn.execute(
            'SELECT * FROM events WHERE guild_id = ? AND fingerprint = ?', (guild_id, fingerprint))
        row = await cursor.fetchone()
        return dict(row) if row else None
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_store.py tests/unit/test_moderation.py -q -p no:cacheprovider`
Expected: all pass (the moderation DB tests prove v2 data still opens: `_migrate` stamps v3).

- [ ] **Step 6: Commit**

```bash
git checkout -b feat/events-phase1 main
git add penguin-overlord/utils/database.py penguin-overlord/utils/events_store.py tests/unit/test_events_store.py
git commit -m "feat(events): schema v3 and the events store skeleton

Six new tables under the existing migration authority, CREATE IF NOT
EXISTS so v2 databases move to v3 with no ALTER. EventsStore borrows the
moderation connection and writes an audit row with every insert.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2: Pure logic: fingerprint, dates, windows, rollover, validation

**Files:**
- Create: `penguin-overlord/utils/events_logic.py`
- Test: `tests/unit/test_events_logic.py`

**Interfaces:**
- Produces (all pure, no Discord, no DB):
  - `TOPICS = ('cyber', 'ham', 'foss', 'other')`, `TOPIC_LABELS: dict`, `TOPIC_ROLES: dict` (`cyber` -> `Cybersecurity Events`, `ham` -> `Ham Radio Events`, `foss` -> `FOSS Events`; `other` absent), `STATUSES`, `DATE_STATUSES = ('confirmed', 'estimated')`
  - `normalize_title(title: str) -> str`
  - `fingerprint(title: str, start_date: date) -> str`
  - `parse_date(text: str) -> date` (raises `ValueError` with a readable message)
  - `local_today(tz_name: str, now: datetime | None = None) -> date`
  - `days_until(start_date: str | date, today: date) -> int`
  - `due_window(days: int, windows: Sequence[int]) -> str | None`
  - `next_annual_dates(start: date, end: date) -> tuple[date, date]`
  - `validate_submission(*, title, topic, start, end, city, url, notes, today) -> tuple[dict | None, str | None]`
  - `parse_dates_field(text: str) -> tuple[date, date]`, `parse_location_field(text: str, regions) -> tuple[str, str | None, str | None, str]` (city, region_code, country_code, scope); both raise `ValueError`
- Task 3 adds the region functions to this same module.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_events_logic.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The pure decisions behind the events system. No Discord, no database:
a fixed `today` goes in, a decision comes out."""

from datetime import date, datetime, timezone

import pytest

from utils import events_logic as el


# -- fingerprint --------------------------------------------------------------

@pytest.mark.parametrize('title, expected', [
    ('BSides Detroit', 'bsides detroit'),
    ('BSides Detroit 2026', 'bsides detroit'),
    ('DEF CON 34', 'def con'),
    ('  GrrCON!!  ', 'grrcon'),
    ('BSides312 (Chicago)', 'bsides312 chicago'),
    ('Dayton Hamvention 2026', 'dayton hamvention'),
    ('Café Con', 'cafe con'),
])
def test_normalize_title_strips_case_punctuation_years_and_editions(title, expected):
    assert el.normalize_title(title) == expected


def test_fingerprint_carries_the_start_year():
    assert el.fingerprint('BSides Detroit 2026', date(2026, 5, 30)) == 'bsides detroit:2026'
    assert el.fingerprint('BSides Detroit', date(2027, 5, 29)) == 'bsides detroit:2027'


# -- dates ---------------------------------------------------------------------

def test_parse_date_accepts_iso_only():
    assert el.parse_date('2026-09-24') == date(2026, 9, 24)
    with pytest.raises(ValueError):
        el.parse_date('09/24/2026')
    with pytest.raises(ValueError):
        el.parse_date('2026-13-01')


def test_local_today_uses_the_configured_zone():
    # 03:30 UTC on the 5th is still the 4th in New York.
    now = datetime(2026, 9, 5, 3, 30, tzinfo=timezone.utc)
    assert el.local_today('America/New_York', now) == date(2026, 9, 4)
    assert el.local_today('UTC', now) == date(2026, 9, 5)


def test_days_until_accepts_iso_strings():
    assert el.days_until('2026-09-24', date(2026, 9, 17)) == 7
    assert el.days_until(date(2026, 9, 24), date(2026, 9, 24)) == 0
    assert el.days_until('2026-09-24', date(2026, 9, 25)) == -1


def test_due_window_matches_exact_days_only():
    assert el.due_window(30, (30, 7, 1)) == '30'
    assert el.due_window(7, (30, 7, 1)) == '7'
    assert el.due_window(8, (30, 7, 1)) is None
    assert el.due_window(0, (30, 7, 1)) is None


# -- rollover ------------------------------------------------------------------

def test_rollover_keeps_the_ordinal_weekday():
    # Sat 2026-05-30 is the 5th Saturday of May; May 2027 also has five.
    start, end = el.next_annual_dates(date(2026, 5, 30), date(2026, 5, 30))
    assert start == date(2027, 5, 29) and start.weekday() == 5
    assert end == start


def test_rollover_fifth_occurrence_falls_back_to_the_last():
    # Sat 2026-08-29 is the 5th Saturday of August; August 2027 has only four.
    start, _ = el.next_annual_dates(date(2026, 8, 29), date(2026, 8, 29))
    assert start == date(2027, 8, 28) and start.weekday() == 5


def test_rollover_third_saturday_stays_third_saturday():
    # 2026-04-18 is the third Saturday of April.
    start, end = el.next_annual_dates(date(2026, 4, 18), date(2026, 4, 19))
    assert start == date(2027, 4, 17) and end == date(2027, 4, 18)


def test_rollover_keeps_duration():
    start, end = el.next_annual_dates(date(2026, 8, 6), date(2026, 8, 9))
    assert (end - start).days == 3 and start.weekday() == 3


# -- validation ----------------------------------------------------------------

def _submit(**over):
    kwargs = dict(title='GrrCON', topic='cyber', start='2026-09-24', end='2026-09-25',
                  city='Grand Rapids', url='https://grrcon.com', notes=None,
                  today=date(2026, 9, 3))
    kwargs.update(over)
    return el.validate_submission(**kwargs)


def test_valid_submission_returns_clean_fields():
    clean, problem = _submit()
    assert problem is None
    assert clean['start_date'] == '2026-09-24' and clean['end_date'] == '2026-09-25'
    assert clean['fingerprint'] == 'grrcon:2026'
    assert clean['title'] == 'GrrCON'


def test_missing_end_copies_start():
    clean, _ = _submit(end=None)
    assert clean['end_date'] == '2026-09-24'


@pytest.mark.parametrize('over, fragment', [
    (dict(start='next week'), 'YYYY-MM-DD'),
    (dict(end='2026-09-20'), 'before'),
    (dict(start='2029-01-01', end='2029-01-01'), 'two years'),
    (dict(start='2026-01-01', end='2026-01-01'), 'past'),
    (dict(url='grrcon.com'), 'http'),
    (dict(topic='crypto'), 'topic'),
    (dict(title='   '), 'title'),
    (dict(city=''), 'city'),
    (dict(notes='x' * 501), '500'),
])
def test_invalid_submissions_name_the_problem(over, fragment):
    clean, problem = _submit(**over)
    assert clean is None and fragment in problem


def test_parse_dates_field_single_and_range():
    assert el.parse_dates_field('2026-09-24') == (date(2026, 9, 24), date(2026, 9, 24))
    assert el.parse_dates_field('2026-09-24 to 2026-09-25') == (date(2026, 9, 24), date(2026, 9, 25))
    with pytest.raises(ValueError):
        el.parse_dates_field('2026-09-25 to 2026-09-24')
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_logic.py -q -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'utils.events_logic'`

- [ ] **Step 3: Write the module**

```python
# penguin-overlord/utils/events_logic.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pure decisions for the events system: no Discord, no database.

Everything time-related takes an explicit `today` so tests pin the clock.
"Today" for reminder math is the calendar date in EVENTS_TIMEZONE, not the
event's own zone: a Saturday con gets its reminder on the same Eastern
morning wherever it is.
"""

import calendar
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

TOPICS = ('cyber', 'ham', 'foss', 'other')
TOPIC_LABELS = {'cyber': 'Cybersecurity', 'ham': 'Ham Radio', 'foss': 'FOSS', 'other': 'Other'}
TOPIC_ROLES = {'cyber': 'Cybersecurity Events', 'ham': 'Ham Radio Events', 'foss': 'FOSS Events'}
STATUSES = ('pending', 'approved', 'rejected', 'cancelled', 'retired')
DATE_STATUSES = ('confirmed', 'estimated')
PROVENANCES = ('member', 'calendar', 'ai', 'rollover')

MAX_NOTES = 500
MAX_TITLE = 120
MAX_YEARS_AHEAD = 2

_ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'events'
_PUNCT = re.compile(r'[^a-z0-9 ]+')
_NUMBER_WORD = re.compile(r'\b\d+\b')          # a year or an edition number on its own
_SPACES = re.compile(r'\s+')


# -- fingerprint ---------------------------------------------------------------

def normalize_title(title: str) -> str:
    """Lowercase ASCII, punctuation gone, standalone numbers gone (years and
    edition numbers), whitespace collapsed. 'DEF CON 34' and 'DEF CON 35'
    collide on purpose; the start year in fingerprint() separates them."""
    text = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    text = _PUNCT.sub(' ', text.lower())
    text = _NUMBER_WORD.sub(' ', text)
    return _SPACES.sub(' ', text).strip()


def fingerprint(title: str, start_date: date) -> str:
    return f'{normalize_title(title)}:{start_date.year}'


# -- dates ---------------------------------------------------------------------

def parse_date(text: str) -> date:
    text = (text or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        raise ValueError(f'{text!r} is not a date in YYYY-MM-DD form')
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f'{text!r} is not a real calendar date') from None


def local_today(tz_name: str, now: Optional[datetime] = None) -> date:
    now = now or datetime.now(ZoneInfo('UTC'))
    return now.astimezone(ZoneInfo(tz_name)).date()


def days_until(start_date, today: date) -> int:
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    return (start_date - today).days


def due_window(days: int, windows: Sequence[int]) -> Optional[str]:
    """The reminder window a countdown lands on, as the string key used in
    event_reminders.window, or None."""
    return str(days) if days in windows else None


def next_annual_dates(start: date, end: date) -> tuple[date, date]:
    """Same ordinal weekday next year (third Saturday stays third Saturday);
    a fifth occurrence that does not exist becomes the last one. Duration
    is preserved."""
    ordinal = (start.day - 1) // 7 + 1
    year = start.year + 1
    first_weekday, days_in_month = calendar.monthrange(year, start.month)
    first_match = 1 + (start.weekday() - first_weekday) % 7
    day = first_match + 7 * (ordinal - 1)
    while day > days_in_month:
        day -= 7
    new_start = date(year, start.month, day)
    return new_start, new_start + (end - start)


# -- submissions ---------------------------------------------------------------

def validate_submission(*, title: str, topic: str, start: str, end: Optional[str],
                        city: str, url: Optional[str], notes: Optional[str],
                        today: date) -> tuple[Optional[dict], Optional[str]]:
    """Returns (clean_fields, None) or (None, reason). The reason is member-
    facing, so it says exactly which field and why."""
    title = (title or '').strip()
    if not title:
        return None, 'A title is required.'
    if len(title) > MAX_TITLE:
        return None, f'The title is over {MAX_TITLE} characters.'
    if topic not in TOPICS:
        return None, f'Unknown topic; pick one of {", ".join(TOPICS)}.'
    try:
        start_date = parse_date(start)
        end_date = parse_date(end) if end and end.strip() else start_date
    except ValueError as e:
        return None, f'{e}. Dates are YYYY-MM-DD.'
    if end_date < start_date:
        return None, 'The end date is before the start date.'
    if start_date < today:
        return None, 'That start date is in the past.'
    if start_date > today.replace(year=today.year + MAX_YEARS_AHEAD):
        return None, f'That start is more than {MAX_YEARS_AHEAD} years out.'
    city = (city or '').strip()
    if not city:
        return None, 'A city is required (use Online for virtual events).'
    url = (url or '').strip() or None
    if url and not url.lower().startswith(('http://', 'https://')):
        return None, 'The url must start with http:// or https://.'
    notes = (notes or '').strip() or None
    if notes and len(notes) > MAX_NOTES:
        return None, f'Notes are limited to {MAX_NOTES} characters.'
    return {
        'title': title, 'fingerprint': fingerprint(title, start_date), 'topic': topic,
        'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(),
        'city': city, 'url': url, 'notes': notes,
    }, None


def parse_dates_field(text: str) -> tuple[date, date]:
    """'2026-09-24' or '2026-09-24 to 2026-09-25' (the edit modal's field)."""
    parts = [p.strip() for p in re.split(r'\s+(?:to|-)\s+|\s*/\s*', (text or '').strip()) if p.strip()]
    if not 1 <= len(parts) <= 2:
        raise ValueError('Dates are YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD.')
    start = parse_date(parts[0])
    end = parse_date(parts[1]) if len(parts) == 2 else start
    if end < start:
        raise ValueError('The end date is before the start date.')
    return start, end
```

The `_ASSETS`, `json`, `dataclass` and `Mapping` imports are used by Task 3; leave them in (ruff will flag unused imports until then, so Task 3 must land before lint is run on this file, or add them in Task 3 instead: pick the latter if a lint gate runs between tasks).

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_logic.py -q -p no:cacheprovider`
Expected: all pass. If `test_rollover_keeps_the_ordinal_weekday` fails, check the arithmetic against `calendar.monthcalendar(2027, 5)` by hand before touching the code.

- [ ] **Step 5: Commit**

```bash
git add penguin-overlord/utils/events_logic.py tests/unit/test_events_logic.py
git commit -m "feat(events): pure logic for fingerprints, windows, rollover and validation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 3: Regions file, topic panel, role resolution, CSV mapping

**Files:**
- Create: `penguin-overlord/assets/events/regions.json`
- Create: `penguin-overlord/assets/role_panels/event_topics.json`
- Modify: `penguin-overlord/utils/events_logic.py` (append)
- Test: `tests/unit/test_events_logic.py` (append), `tests/unit/test_role_picker.py` (append)

**Interfaces:**
- Produces: `Regions` dataclass (`regions: dict[str, str]`, `countries: dict[str, str]`, `.name(code) -> str | None`, `.country_of(region_code) -> str`), `load_regions(path=None) -> Regions`, `role_names_for(event: Mapping, regions: Regions) -> list[str]`, `region_choices(regions, current: str, limit=25) -> list[tuple[str, str]]`, `parse_location_field(text, regions) -> tuple[str, str | None, str | None, str]`, `csv_row_to_event(row: Mapping[str, str], guild_id: int) -> dict`, `CSV_TOPICS`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_events_logic.py`)

```python
# -- regions and roles -----------------------------------------------------------

def test_regions_file_covers_states_provinces_and_countries():
    regions = el.load_regions()
    assert regions.regions['US-MI'] == 'Michigan'
    assert regions.regions['US-DC'] == 'District of Columbia'
    assert regions.regions['CA-ON'] == 'Ontario'
    assert regions.countries['US'] == 'United States'
    assert regions.countries['CA'] == 'Canada'
    assert regions.countries['DE'] == 'Germany'
    assert len(regions.regions) == 51 + 13
    assert regions.name('US-OH') == 'Ohio' and regions.name('nope') is None
    assert regions.country_of('CA-ON') == 'CA'


def _ev(**over):
    base = dict(topic='cyber', scope='regional', region_code='US-MI', country_code='US')
    base.update(over)
    return base


def test_regional_event_mentions_topic_and_region_only():
    assert el.role_names_for(_ev(), el.load_regions()) == ['Cybersecurity Events', 'Michigan']


def test_national_event_mentions_country_instead_of_region():
    ev = _ev(scope='national', region_code='US-NV')
    assert el.role_names_for(ev, el.load_regions()) == ['Cybersecurity Events', 'United States']


def test_online_event_mentions_topic_only():
    ev = _ev(region_code=None, country_code=None)
    assert el.role_names_for(ev, el.load_regions()) == ['Cybersecurity Events']


def test_other_topic_has_no_topic_role():
    assert el.role_names_for(_ev(topic='other'), el.load_regions()) == ['Michigan']


def test_region_choices_match_name_or_code_and_include_online():
    regions = el.load_regions()
    assert ('Online', 'online') in el.region_choices(regions, '')
    names = el.region_choices(regions, 'mich')
    assert names == [('Michigan (US-MI)', 'US-MI')]
    assert ('Ontario (CA-ON)', 'CA-ON') in el.region_choices(regions, 'ca-o')
    assert ('Canada (CA)', 'CA') in el.region_choices(regions, 'can')
    assert len(el.region_choices(regions, '')) == 25


def test_parse_location_field_variants():
    regions = el.load_regions()
    assert el.parse_location_field('Grand Rapids, US-MI', regions) == ('Grand Rapids', 'US-MI', 'US', 'regional')
    assert el.parse_location_field('Las Vegas, US-NV, national', regions) == ('Las Vegas', 'US-NV', 'US', 'national')
    assert el.parse_location_field('Online', regions) == ('Online', None, None, 'regional')
    assert el.parse_location_field('Berlin, DE', regions) == ('Berlin', None, 'DE', 'national')
    with pytest.raises(ValueError):
        el.parse_location_field('Grand Rapids, US-ZZ', regions)
    with pytest.raises(ValueError):
        el.parse_location_field('', regions)


# -- CSV mapping ------------------------------------------------------------------

def test_csv_row_maps_to_an_approved_annual_calendar_row():
    row = {'Event': 'GrrCON', 'Start Date': '2026-09-24', 'End Date': '2026-09-25',
           'City': 'Grand Rapids', 'State': 'MI', 'URL': 'https://grrcon.com',
           'Source': 'official site', 'Type': 'Cybersecurity', 'Date Status': 'Confirmed'}
    ev = el.csv_row_to_event(row, guild_id=1)
    assert ev['status'] == 'approved' and ev['provenance'] == 'calendar'
    assert ev['recurrence'] == 'annual' and ev['scope'] == 'regional'
    assert ev['topic'] == 'cyber' and ev['date_status'] == 'confirmed'
    assert ev['region_code'] == 'US-MI' and ev['country_code'] == 'US'
    assert ev['fingerprint'] == 'grrcon:2026' and ev['decided_by'] == 0
    assert ev['source_note'] == 'official site' and ev['guild_id'] == 1


def test_csv_row_ontario_is_canada_and_missing_end_copies_start():
    row = {'Event': 'Ontario Hamfest 2026 (Burlington)', 'Start Date': '2026-09-12', 'End Date': '',
           'City': 'Burlington', 'State': 'ON', 'URL': '', 'Source': 'x', 'Type': 'Ham Radio',
           'Date Status': 'Estimated'}
    ev = el.csv_row_to_event(row, guild_id=1)
    assert ev['region_code'] == 'CA-ON' and ev['country_code'] == 'CA'
    assert ev['end_date'] == '2026-09-12' and ev['topic'] == 'ham'
    assert ev['date_status'] == 'estimated' and ev['url'] is None


def test_csv_def_con_is_national():
    row = {'Event': 'DEF CON 34', 'Start Date': '2026-08-06', 'End Date': '2026-08-09',
           'City': 'Las Vegas', 'State': 'NV', 'URL': 'https://defcon.org', 'Source': 'x',
           'Type': 'Cybersecurity', 'Date Status': 'Confirmed'}
    assert el.csv_row_to_event(row, guild_id=1)['scope'] == 'national'
```

Append to `tests/unit/test_role_picker.py`:

```python
# -- the events system depends on these role names --------------------------------

def test_every_region_role_name_exists_in_exactly_one_panel():
    from utils.events_logic import TOPIC_ROLES, load_regions
    panels = rp.load_panels()
    owners = {}
    for key, panel in panels.items():
        for name in panel.role_names():
            owners.setdefault(name, []).append(key)
    regions = load_regions()
    wanted = list(regions.regions.values()) + list(regions.countries.values()) + list(TOPIC_ROLES.values())
    problems = {name: owners.get(name, []) for name in wanted if len(owners.get(name, [])) != 1}
    assert not problems, f'role names not owned by exactly one panel: {problems}'


def test_event_topics_panel_is_non_exclusive_opt_in():
    panel = rp.load_panels()['event_topics']
    assert panel.exclusive is False
    assert panel.role_names() == ['Cybersecurity Events', 'Ham Radio Events', 'FOSS Events']
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_logic.py tests/unit/test_role_picker.py -q -p no:cacheprovider`
Expected: failures on `load_regions` (AttributeError) and `KeyError: 'event_topics'`.

- [ ] **Step 3: Write the assets**

`penguin-overlord/assets/role_panels/event_topics.json`:

```json
{
  "key": "event_topics",
  "title": "Event pings: which topics?",
  "description": "Tick the kinds of events you want reminders for. Regional events also mention the state, province or country roles you picked in the other panels, so pick those too. Submitting the menu sets your whole list, and the bot reads it back to you.",
  "exclusive": false,
  "groups": [
    {
      "placeholder": "Pick your event topics",
      "options": [
        {"label": "Cybersecurity events", "role": "Cybersecurity Events", "emoji": "🔐"},
        {"label": "Ham radio events", "role": "Ham Radio Events", "emoji": "📻"},
        {"label": "FOSS events", "role": "FOSS Events", "emoji": "🐧"}
      ]
    }
  ]
}
```

(Check `Panel.from_dict` in `cogs/role_picker.py` for the emoji key name before saving; the country panel uses the same key.)

`penguin-overlord/assets/events/regions.json`: generate it rather than typing 90 lines by hand, then commit the output:

```bash
cd penguin-overlord && ../.venv/bin/python - <<'EOF'
import json
US = {'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado',
 'CT':'Connecticut','DE':'Delaware','DC':'District of Columbia','FL':'Florida','GA':'Georgia','HI':'Hawaii',
 'ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana',
 'ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi',
 'MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey',
 'NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma',
 'OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota',
 'TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington',
 'WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'}
CA = {'AB':'Alberta','BC':'British Columbia','MB':'Manitoba','NB':'New Brunswick',
 'NL':'Newfoundland and Labrador','NT':'Northwest Territories','NS':'Nova Scotia','NU':'Nunavut',
 'ON':'Ontario','PE':'Prince Edward Island','QC':'Quebec','SK':'Saskatchewan','YT':'Yukon'}
COUNTRIES = {'US':'United States','CA':'Canada','MX':'Mexico','GB':'United Kingdom','IE':'Ireland',
 'DE':'Germany','FR':'France','NL':'Netherlands','ES':'Spain','IT':'Italy','PL':'Poland','SE':'Sweden',
 'NO':'Norway','DK':'Denmark','FI':'Finland','AU':'Australia','NZ':'New Zealand','IN':'India','JP':'Japan',
 'BR':'Brazil','AR':'Argentina','IL':'Israel','ZA':'South Africa','NG':'Nigeria'}
regions = {f'US-{k}': v for k, v in US.items()} | {f'CA-{k}': v for k, v in CA.items()}
out = {'_comment': 'Region and country codes to picker role names. Every name here must exist in exactly one panel under assets/role_panels (test_role_picker checks). The events cog never creates roles.',
       'regions': regions, 'countries': COUNTRIES}
open('assets/events/regions.json', 'w').write(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
EOF
```

`International` (in the country panel) is deliberately absent: it is a picker role for members, not a place an event can be in.

- [ ] **Step 4: Append to `utils/events_logic.py`**

```python
# -- regions and roles ---------------------------------------------------------

@dataclass(frozen=True)
class Regions:
    regions: Mapping[str, str]      # 'US-MI' -> 'Michigan'
    countries: Mapping[str, str]    # 'US' -> 'United States'

    def name(self, code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        return self.regions.get(code) or self.countries.get(code)

    @staticmethod
    def country_of(region_code: str) -> str:
        return region_code.split('-', 1)[0]


def load_regions(path: Optional[Path] = None) -> Regions:
    data = json.loads((path or _ASSETS / 'regions.json').read_text(encoding='utf-8'))
    return Regions(regions=dict(data['regions']), countries=dict(data['countries']))


def role_names_for(event: Mapping, regions: Regions) -> list[str]:
    """Role names a reminder mentions: the topic role (none for 'other'),
    then the region role for regional events or the country role for
    national ones. Online events (no codes) get the topic role only."""
    names = []
    topic_role = TOPIC_ROLES.get(event.get('topic'))
    if topic_role:
        names.append(topic_role)
    if event.get('scope') == 'national':
        geo = regions.countries.get(event.get('country_code') or '')
    else:
        geo = regions.regions.get(event.get('region_code') or '')
        if geo is None and not event.get('region_code'):
            geo = regions.countries.get(event.get('country_code') or '')
    if geo:
        names.append(geo)
    return names


def region_choices(regions: Regions, current: str, limit: int = 25) -> list[tuple[str, str]]:
    """Autocomplete rows: (label, value). Regions first, then countries,
    then Online; a prefix on the name or a substring of the code matches."""
    needle = (current or '').strip().lower()
    rows = [(f'{name} ({code})', code) for code, name in regions.regions.items()]
    rows += [(f'{name} ({code})', code) for code, name in regions.countries.items()]
    rows.append(('Online', 'online'))
    if needle:
        rows = [(label, value) for label, value in rows
                if label.lower().startswith(needle) or needle in value.lower()
                or any(word.startswith(needle) for word in label.lower().split())]
    return rows[:limit]


def parse_location_field(text: str, regions: Regions) -> tuple[str, Optional[str], Optional[str], str]:
    """The edit modal's location line: 'City, US-MI[, national]', 'City, DE'
    (country only, national), or 'Online'. Returns (city, region_code,
    country_code, scope)."""
    parts = [p.strip() for p in (text or '').split(',') if p.strip()]
    if not parts:
        raise ValueError('Location is City, CODE (for example Grand Rapids, US-MI) or Online.')
    city = parts[0]
    if len(parts) == 1:
        if city.lower() == 'online':
            return 'Online', None, None, 'regional'
        raise ValueError('Add the region or country code after the city, for example Grand Rapids, US-MI.')
    code = parts[1].upper()
    scope = parts[2].lower() if len(parts) > 2 else None
    if scope not in (None, 'regional', 'national'):
        raise ValueError('The third part, if given, is regional or national.')
    if code in regions.regions:
        return city, code, Regions.country_of(code), scope or 'regional'
    if code in regions.countries:
        return city, None, code, scope or 'national'
    raise ValueError(f'Unknown region or country code {code}.')


# -- CSV import -----------------------------------------------------------------

CSV_TOPICS = {'cybersecurity': 'cyber', 'ham radio': 'ham', 'foss': 'foss'}
_CA_CODES = frozenset(('AB', 'BC', 'MB', 'NB', 'NL', 'NT', 'NS', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'))


def csv_row_to_event(row: Mapping[str, str], guild_id: int) -> dict:
    """One events/*.csv row (Event, Start Date, End Date, City, State, URL,
    Source, Type, Date Status) to an approved, annual, calendar-provenance
    row ready for EventsStore.insert(). Raises ValueError on a bad date."""
    title = row['Event'].strip()
    start = parse_date(row['Start Date'])
    end = parse_date(row['End Date']) if row.get('End Date', '').strip() else start
    code = row['State'].strip().upper()
    country = 'CA' if code in _CA_CODES else 'US'
    url = row.get('URL', '').strip() or None
    return {
        'guild_id': guild_id, 'title': title, 'fingerprint': fingerprint(title, start),
        'topic': CSV_TOPICS.get(row['Type'].strip().lower(), 'other'),
        'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'start_time': None, 'timezone': None,
        'date_status': row['Date Status'].strip().lower() or 'estimated',
        'city': row['City'].strip(), 'region_code': f'{country}-{code}', 'country_code': country,
        'scope': 'national' if normalize_title(title).startswith('def con') else 'regional',
        'url': url, 'notes': None, 'recurrence': 'annual', 'parent_event_id': None,
        'status': 'approved', 'provenance': 'calendar', 'submitted_by': None,
        'source_url': None, 'source_note': row.get('Source', '').strip() or None,
        'decided_by': 0, 'decided_at': None, 'reject_reason': None,
    }
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_logic.py tests/unit/test_role_picker.py -q -p no:cacheprovider`
Expected: all pass. `test_region_choices_match_name_or_code_and_include_online` asserts `'mich'` yields exactly Michigan; if `Mississippi`/`Missouri` sneak in the prefix logic is wrong (they start with `mis`).

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check penguin-overlord/utils/events_logic.py
git add penguin-overlord/assets/events/regions.json penguin-overlord/assets/role_panels/event_topics.json \
        penguin-overlord/utils/events_logic.py tests/unit/test_events_logic.py tests/unit/test_role_picker.py
git commit -m "feat(events): regions map, topic opt-in panel, role resolution, CSV mapping

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 4: EventsConfig and metrics

**Files:**
- Modify: `penguin-overlord/utils/config.py`
- Modify: `penguin-overlord/utils/metrics.py`
- Test: `tests/unit/test_config.py` (append)

**Interfaces:**
- Produces: `EventsConfig` frozen dataclass (fields below), `Config.events`, `load_events_config(env=None) -> EventsConfig` (lenient, like `load_metrics_config`), `describe_config` gains `events=on/off`. Metrics: `EVENTS_SUBMISSIONS{provenance}`, `EVENTS_DECISIONS{decision}`, `EVENTS_REMINDERS{window}`, `EVENTS_POST_ERRORS`, `EVENTS_ROLE_MISSING{role}`, `EVENTS_PENDING` (gauge).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_config.py`; `_load` and `_problems` helpers already exist there, `SNOWFLAKE` too)

```python
# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_events_defaults_are_off_and_dry():
    events = _load().events
    assert events.enabled is False and events.dry_run is True
    assert events.channel_id is None and events.review_channel_id is None
    assert events.timezone == 'America/New_York' and events.post_at == (9, 0)
    assert events.reminder_days == (30, 7, 1) and events.digest_enabled is True
    assert events.max_pending_per_member == 3 and events.pending_expire_days == 30


def test_events_enabled_requires_a_channel():
    text = _problems(EVENTS_ENABLED='true')
    assert 'EVENTS_CHANNEL_ID' in text


def test_events_review_channel_falls_back_to_mod_alert_channel():
    events = _load(EVENTS_ENABLED='true', EVENTS_CHANNEL_ID=SNOWFLAKE,
                   MOD_ALERT_CHANNEL_ID=OTHER_SNOWFLAKE).events
    assert events.review_channel_id == int(OTHER_SNOWFLAKE)


def test_events_reminder_days_parse_and_sort_descending():
    events = _load(EVENTS_REMINDER_DAYS='1, 14,7').events
    assert events.reminder_days == (14, 7, 1)
    assert 'EVENTS_REMINDER_DAYS' in _problems(EVENTS_REMINDER_DAYS='soon')
    assert 'EVENTS_REMINDER_DAYS' in _problems(EVENTS_REMINDER_DAYS='0,7')


def test_events_post_at_and_timezone_validate():
    events = _load(EVENTS_POST_AT='18:30', EVENTS_TIMEZONE='Europe/Berlin').events
    assert events.post_at == (18, 30) and events.timezone == 'Europe/Berlin'
    assert 'EVENTS_POST_AT' in _problems(EVENTS_POST_AT='6pm')
    assert 'EVENTS_TIMEZONE' in _problems(EVENTS_TIMEZONE='Mars/Olympus')


def test_describe_config_mentions_events():
    from utils.config import describe_config
    assert 'events=off' in describe_config(_load())
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_config.py -q -p no:cacheprovider -k events`
Expected: `AttributeError: 'Config' object has no attribute 'events'`

- [ ] **Step 3: Add the section to `utils/config.py`**

After `class BanterConfig` add:

```python
@dataclass(frozen=True)
class EventsConfig:
    enabled: bool = False
    dry_run: bool = True
    channel_id: Optional[int] = None
    review_channel_id: Optional[int] = None
    timezone: str = 'America/New_York'
    post_at: tuple[int, int] = (9, 0)
    reminder_days: tuple[int, ...] = (30, 7, 1)
    digest_enabled: bool = True
    max_pending_per_member: int = 3
    pending_expire_days: int = 30
```

Add `events: EventsConfig = field(default_factory=EventsConfig)` as the last field of `Config`.

After `_load_banter` add:

```python
def _load_events(r: _Reader) -> EventsConfig:
    enabled = r.bool('EVENTS_ENABLED', False)
    channel_id = r.snowflake('EVENTS_CHANNEL_ID')
    if enabled and channel_id is None:
        r.fail('EVENTS_CHANNEL_ID', 'required when EVENTS_ENABLED=true')
    raw_days = r.str('EVENTS_REMINDER_DAYS', '30,7,1')
    days: tuple[int, ...] = (30, 7, 1)
    try:
        parsed = sorted({int(part) for part in _split(raw_days, lower=False)}, reverse=True)
        if not parsed or any(day < 1 for day in parsed):
            raise ValueError
        days = tuple(parsed)
    except ValueError:
        r.fail('EVENTS_REMINDER_DAYS', 'expected comma-separated positive day counts such as 30,7,1', raw_days)
    return EventsConfig(
        enabled=enabled,
        dry_run=r.bool('EVENTS_DRY_RUN', True),
        channel_id=channel_id,
        review_channel_id=r.snowflake('EVENTS_REVIEW_CHANNEL_ID') or r.snowflake('MOD_ALERT_CHANNEL_ID'),
        timezone=r.timezone('EVENTS_TIMEZONE', 'America/New_York'),
        post_at=r.time('EVENTS_POST_AT') or (9, 0),
        reminder_days=days,
        digest_enabled=r.bool('EVENTS_DIGEST_ENABLED', True),
        max_pending_per_member=r.int('EVENTS_MAX_PENDING_PER_MEMBER', 3, minimum=1),
        pending_expire_days=r.int('EVENTS_PENDING_EXPIRE_DAYS', 30, minimum=1),
    )
```

In `load_config` add `events=_load_events(r),` after `banter=`. After `load_paths_config` add:

```python
def load_events_config(env: Optional[Mapping[str, str]] = None) -> EventsConfig:
    """EVENTS_* only, lenient; for the cog when the bot carries no Config
    (tests, tooling). bot.py's load_config() has already refused to start
    on anything malformed here."""
    return _load_events(_reader(env, None, use_secrets=False))
```

In `describe_config` append `f'events={flag(config.events.enabled)}',` to `parts`.

`_split` exists at line ~368 (`_split(raw, lower)`); check its signature before calling.

- [ ] **Step 4: Add the metrics**

In `utils/metrics.py`, inside the `if METRICS_ENABLED and PROMETHEUS_AVAILABLE:` block after `HELPER_REPLIES`:

```python
    EVENTS_SUBMISSIONS = Counter('penguin_events_submissions_total', 'Event rows created', ['provenance'])
    EVENTS_DECISIONS = Counter('penguin_events_decisions_total', 'Moderator and sweep decisions on events', ['decision'])
    EVENTS_REMINDERS = Counter('penguin_events_reminders_total', 'Event reminders posted', ['window'])
    EVENTS_POST_ERRORS = Counter('penguin_events_post_errors_total', 'Event posts that failed to send')
    EVENTS_ROLE_MISSING = Counter('penguin_events_role_missing_total', 'Reminders sent with a role the guild lacks', ['role'])
    EVENTS_PENDING = Gauge('penguin_events_pending', 'Event submissions awaiting a moderator')
```

and in the `else:` branch:

```python
    EVENTS_SUBMISSIONS = EVENTS_DECISIONS = EVENTS_REMINDERS = _NoopMetric()
    EVENTS_POST_ERRORS = EVENTS_ROLE_MISSING = EVENTS_PENDING = _NoopMetric()
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/unit/test_config.py -q -p no:cacheprovider`
Expected: all pass, including the pre-existing `test_config_is_frozen` and the round-trip test (which may enumerate `Config` fields; if it asserts a field count, update it).

- [ ] **Step 6: Commit**

```bash
git add penguin-overlord/utils/config.py penguin-overlord/utils/metrics.py tests/unit/test_config.py
git commit -m "feat(events): EVENTS_* config section and Prometheus counters

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 5: Store queries: listing, decisions, edits, reminders, sweep

**Files:**
- Modify: `penguin-overlord/utils/events_store.py`
- Test: `tests/unit/test_events_store.py` (append)

**Interfaces:**
- Produces on `EventsStore`:
  - `count_open_submissions(guild_id, user_id) -> int`
  - `list_upcoming(guild_id, *, today: str, days: int, topic=None, region_code=None, country_code=None) -> list[dict]` (approved and cancelled, `start_date` in `[today, today+days]`, ordered by start)
  - `search(guild_id, query, *, today: str, limit=10) -> list[dict]`
  - `mine(guild_id, user_id, limit=10) -> list[dict]`
  - `list_pending(guild_id, limit=15) -> list[dict]`
  - `pending_count(guild_id) -> int`, `counts(guild_id) -> dict[str, int]`
  - `set_review_message(event_id, message_id)`
  - `decide(event_id, *, status, moderator_id, reason=None) -> bool` (pending only)
  - `cancel(event_id, *, moderator_id, reason) -> bool` (approved only)
  - `update(event_id, changes: dict, *, actor_id) -> dict | None`
  - `claim_reminder(event_id, window, channel_id) -> int | None`, `mark_reminder_sent(reminder_id, message_id, roles_mentioned)`, `release_reminder(reminder_id)`, `dated_reminder_sent(event_id) -> bool`
  - `approved_between(start: str, end: str) -> list[dict]` (all guilds)
  - `retire_ended(today: str) -> list[dict]`, `has_rollover(parent_id) -> bool`
  - `expire_pending(cutoff_iso: str) -> list[int]`, `purge_rejected(cutoff_iso: str) -> int`

- [ ] **Step 1: Write the failing tests** (append)

```python
# -- listing -----------------------------------------------------------------------

async def _seed(store):
    ids = {}
    ids['grr'] = await store.insert(event(title='GrrCON', fingerprint='grrcon:2026',
                                          start_date='2026-09-24', end_date='2026-09-25',
                                          status='approved', submitted_by=None), actor_id=0, action='import')
    ids['ham'] = await store.insert(event(title='Ontario Hamfest', fingerprint='ontario hamfest:2026',
                                          topic='ham', start_date='2026-09-12', end_date='2026-09-12',
                                          region_code='CA-ON', country_code='CA', status='approved'),
                                    actor_id=0, action='import')
    ids['pend'] = await store.insert(event(title='Queen City Con', fingerprint='queen city con:2026',
                                           start_date='2026-10-10', end_date='2026-10-11',
                                           region_code='US-OH'), actor_id=42, action='submit')
    ids['old'] = await store.insert(event(title='BSides SF', fingerprint='bsides sf:2026',
                                          start_date='2026-03-21', end_date='2026-03-22',
                                          region_code='US-CA', status='approved'), actor_id=0, action='import')
    return ids


async def test_list_upcoming_filters_by_window_topic_and_place(store):
    await _seed(store)
    rows = await store.list_upcoming(1, today='2026-09-03', days=30)
    assert [r['title'] for r in rows] == ['Ontario Hamfest', 'GrrCON']       # pending and past excluded
    assert [r['title'] for r in await store.list_upcoming(1, today='2026-09-03', days=30, topic='ham')] == ['Ontario Hamfest']
    assert [r['title'] for r in await store.list_upcoming(1, today='2026-09-03', days=365, region_code='US-MI')] == ['GrrCON']
    assert [r['title'] for r in await store.list_upcoming(1, today='2026-09-03', days=365, country_code='CA')] == ['Ontario Hamfest']
    assert await store.list_upcoming(1, today='2026-09-03', days=5) == []


async def test_search_matches_title_or_city_case_insensitively(store):
    await _seed(store)
    assert [r['title'] for r in await store.search(1, 'grr', today='2026-09-03')] == ['GrrCON']
    assert [r['title'] for r in await store.search(1, 'detroit', today='2026-09-03')] == []
    # past events are not searchable; pending ones are not either
    assert await store.search(1, 'bsides', today='2026-09-03') == []
    assert await store.search(1, 'queen', today='2026-09-03') == []


async def test_mine_and_open_submission_count(store):
    ids = await _seed(store)
    assert await store.count_open_submissions(1, 42) == 1
    mine = await store.mine(1, 42)
    assert [m['id'] for m in mine] == [ids['pend']]
    assert await store.decide(ids['pend'], status='rejected', moderator_id=7, reason='dupe')
    assert await store.count_open_submissions(1, 42) == 0
    assert (await store.mine(1, 42))[0]['reject_reason'] == 'dupe'


# -- decisions ---------------------------------------------------------------------

async def test_decide_is_first_click_wins(store):
    ids = await _seed(store)
    assert await store.decide(ids['pend'], status='approved', moderator_id=7) is True
    assert await store.decide(ids['pend'], status='rejected', moderator_id=8, reason='no') is False
    row = await store.get(ids['pend'])
    assert row['status'] == 'approved' and row['decided_by'] == 7 and row['decided_at']
    assert [a['action'] for a in await store.audit_rows(ids['pend'])] == ['submit', 'approve']


async def test_pending_listing_and_counts(store):
    ids = await _seed(store)
    pending = await store.list_pending(1)
    assert [p['id'] for p in pending] == [ids['pend']]
    assert await store.pending_count(1) == 1
    assert await store.counts(1) == {'approved': 3, 'pending': 1}
    await store.set_review_message(ids['pend'], 555)
    assert (await store.get(ids['pend']))['review_message_id'] == 555


async def test_cancel_only_from_approved(store):
    ids = await _seed(store)
    assert await store.cancel(ids['pend'], moderator_id=7, reason='x') is False
    assert await store.cancel(ids['grr'], moderator_id=7, reason='venue lost') is True
    row = await store.get(ids['grr'])
    assert row['status'] == 'cancelled' and row['reject_reason'] == 'venue lost'
    assert (await store.audit_rows(ids['grr']))[-1]['action'] == 'cancel'


async def test_update_records_before_and_after(store):
    ids = await _seed(store)
    row = await store.update(ids['grr'], {'city': 'Grand Rapids', 'end_date': '2026-09-26'}, actor_id=7)
    assert row['city'] == 'Grand Rapids' and row['end_date'] == '2026-09-26'
    last = (await store.audit_rows(ids['grr']))[-1]
    assert last['action'] == 'edit'
    assert json.loads(last['before_json'])['end_date'] == '2026-09-25'
    assert json.loads(last['after_json'])['end_date'] == '2026-09-26'
    assert await store.update(9999, {'city': 'x'}, actor_id=7) is None


# -- reminders ---------------------------------------------------------------------

async def test_reminder_window_posts_once_ever(store):
    ids = await _seed(store)
    rid = await store.claim_reminder(ids['grr'], '30', channel_id=99)
    assert rid
    assert await store.claim_reminder(ids['grr'], '30', channel_id=99) is None
    await store.mark_reminder_sent(rid, message_id=123, roles_mentioned='Cybersecurity Events, Michigan')
    assert await store.dated_reminder_sent(ids['grr']) is True
    assert await store.claim_reminder(ids['grr'], '7', channel_id=99)


async def test_released_reminder_can_be_claimed_again(store):
    ids = await _seed(store)
    rid = await store.claim_reminder(ids['grr'], '7', channel_id=99)
    await store.release_reminder(rid)
    assert await store.dated_reminder_sent(ids['grr']) is False
    assert await store.claim_reminder(ids['grr'], '7', channel_id=99)


async def test_changed_window_does_not_count_as_dated(store):
    ids = await _seed(store)
    rid = await store.claim_reminder(ids['grr'], 'changed', channel_id=99)
    await store.mark_reminder_sent(rid, message_id=1, roles_mentioned='')
    assert await store.dated_reminder_sent(ids['grr']) is False


async def test_approved_between_spans_guilds(store):
    await _seed(store)
    await store.insert(event(guild_id=2, title='Other', fingerprint='other:2026',
                             start_date='2026-09-20', end_date='2026-09-20', status='approved'),
                       actor_id=0, action='import')
    rows = await store.approved_between('2026-09-03', '2026-10-03')
    assert [r['title'] for r in rows] == ['Ontario Hamfest', 'Other', 'GrrCON']


# -- sweep -------------------------------------------------------------------------

async def test_retire_ended_and_rollover_flag(store):
    ids = await _seed(store)
    retired = await store.retire_ended('2026-09-03')
    assert [r['id'] for r in retired] == [ids['old']]
    assert (await store.get(ids['old']))['status'] == 'retired'
    assert (await store.audit_rows(ids['old']))[-1]['action'] == 'retire'
    assert await store.has_rollover(ids['old']) is False
    await store.insert(event(title='BSides SF', fingerprint='bsides sf:2027', start_date='2027-03-20',
                             end_date='2027-03-21', parent_event_id=ids['old'], provenance='rollover',
                             date_status='estimated'), actor_id=0, action='rollover')
    assert await store.has_rollover(ids['old']) is True
    assert await store.retire_ended('2026-09-03') == []


async def test_expire_pending_and_purge_rejected(store):
    ids = await _seed(store)
    assert await store.expire_pending('2020-01-01T00:00:00+00:00') == []
    expired = await store.expire_pending('2999-01-01T00:00:00+00:00')
    assert expired == [ids['pend']]
    row = await store.get(ids['pend'])
    assert row['status'] == 'rejected' and row['reject_reason'] == 'expired' and row['decided_by'] == 0
    assert await store.purge_rejected('2020-01-01T00:00:00+00:00') == 0
    assert await store.purge_rejected('2999-01-01T00:00:00+00:00') == 1
    assert await store.get(ids['pend']) is None
    assert len(await store.audit_rows(ids['pend'])) == 2      # the trail outlives the row
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_store.py -q -p no:cacheprovider`
Expected: `AttributeError: 'EventsStore' object has no attribute 'list_upcoming'` and friends.

- [ ] **Step 3: Append the methods to `EventsStore`**

```python
    # -- member views -------------------------------------------------------

    async def count_open_submissions(self, guild_id: int, user_id: int) -> int:
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE guild_id = ? AND submitted_by = ? AND status = 'pending'",
            (guild_id, user_id))
        return (await cursor.fetchone())[0]

    async def list_upcoming(self, guild_id: int, *, today: str, days: int, topic=None,
                            region_code=None, country_code=None) -> list[dict]:
        """Approved (and cancelled, shown struck through) events starting
        within `days` of `today`, soonest first."""
        until = (datetime.fromisoformat(today) + timedelta(days=days)).date().isoformat()
        sql = """SELECT * FROM events
                 WHERE guild_id = ? AND status IN ('approved', 'cancelled')
                   AND start_date >= ? AND start_date <= ?"""
        params: list = [guild_id, today, until]
        if topic:
            sql += ' AND topic = ?'
            params.append(topic)
        if region_code:
            sql += ' AND region_code = ?'
            params.append(region_code)
        if country_code:
            sql += ' AND country_code = ?'
            params.append(country_code)
        sql += ' ORDER BY start_date, id'
        cursor = await self._conn.execute(sql, params)
        return [dict(r) for r in await cursor.fetchall()]

    async def search(self, guild_id: int, query: str, *, today: str, limit: int = 10) -> list[dict]:
        like = f'%{query.strip().lower()}%'
        cursor = await self._conn.execute(
            """SELECT * FROM events
               WHERE guild_id = ? AND status IN ('approved', 'cancelled') AND start_date >= ?
                 AND (lower(title) LIKE ? OR lower(coalesce(city, '')) LIKE ?)
               ORDER BY start_date, id LIMIT ?""",
            (guild_id, today, like, like, limit))
        return [dict(r) for r in await cursor.fetchall()]

    async def mine(self, guild_id: int, user_id: int, limit: int = 10) -> list[dict]:
        cursor = await self._conn.execute(
            """SELECT * FROM events WHERE guild_id = ? AND submitted_by = ?
               ORDER BY id DESC LIMIT ?""", (guild_id, user_id, limit))
        return [dict(r) for r in await cursor.fetchall()]

    # -- moderation ---------------------------------------------------------

    async def list_pending(self, guild_id: int, limit: int = 15) -> list[dict]:
        cursor = await self._conn.execute(
            """SELECT * FROM events WHERE guild_id = ? AND status = 'pending'
               ORDER BY id ASC LIMIT ?""", (guild_id, limit))
        return [dict(r) for r in await cursor.fetchall()]

    async def pending_count(self, guild_id: int) -> int:
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE guild_id = ? AND status = 'pending'", (guild_id,))
        return (await cursor.fetchone())[0]

    async def counts(self, guild_id: int) -> dict:
        cursor = await self._conn.execute(
            'SELECT status, COUNT(*) AS n FROM events WHERE guild_id = ? GROUP BY status', (guild_id,))
        return {r['status']: r['n'] for r in await cursor.fetchall()}

    async def set_review_message(self, event_id: int, message_id: int) -> None:
        async with self.db.lock:
            await self._conn.execute(
                'UPDATE events SET review_message_id = ? WHERE id = ?', (message_id, event_id))
            await self._conn.commit()

    async def decide(self, event_id: int, *, status: str, moderator_id: int,
                     reason: str = None) -> bool:
        """pending -> approved | rejected. First decision wins; False when
        the row was already decided (or does not exist)."""
        async with self.db.lock:
            before = await self._get_unlocked(event_id)
            cursor = await self._conn.execute(
                """UPDATE events SET status = ?, decided_by = ?, decided_at = ?, reject_reason = ?,
                          updated_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (status, moderator_id, _utcnow(), reason, _utcnow(), event_id))
            decided = cursor.rowcount > 0
            if decided:
                after = await self._get_unlocked(event_id)
                action = 'approve' if status == 'approved' else 'reject'
                await self._audit_unlocked(event_id, moderator_id, action, before, after)
            await self._conn.commit()
        return decided

    async def cancel(self, event_id: int, *, moderator_id: int, reason: str) -> bool:
        async with self.db.lock:
            before = await self._get_unlocked(event_id)
            cursor = await self._conn.execute(
                """UPDATE events SET status = 'cancelled', decided_by = ?, decided_at = ?,
                          reject_reason = ?, updated_at = ?
                   WHERE id = ? AND status = 'approved'""",
                (moderator_id, _utcnow(), reason, _utcnow(), event_id))
            done = cursor.rowcount > 0
            if done:
                after = await self._get_unlocked(event_id)
                await self._audit_unlocked(event_id, moderator_id, 'cancel', before, after)
            await self._conn.commit()
        return done

    async def update(self, event_id: int, changes: dict, *, actor_id: int) -> dict | None:
        """Apply a moderator edit to any status. Only EVENT_COLUMNS keys are
        written. Returns the updated row, or None when the id is unknown."""
        allowed = {k: v for k, v in changes.items() if k in EVENT_COLUMNS}
        if not allowed:
            return await self.get(event_id)
        async with self.db.lock:
            before = await self._get_unlocked(event_id)
            if before is None:
                return None
            allowed['updated_at'] = _utcnow()
            assignments = ', '.join(f'{col} = ?' for col in allowed)
            await self._conn.execute(
                f'UPDATE events SET {assignments} WHERE id = ?', (*allowed.values(), event_id))
            after = await self._get_unlocked(event_id)
            await self._audit_unlocked(event_id, actor_id, 'edit', before, after)
            await self._conn.commit()
        return after

    async def _get_unlocked(self, event_id: int) -> dict | None:
        cursor = await self._conn.execute('SELECT * FROM events WHERE id = ?', (event_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    # -- reminders ----------------------------------------------------------

    async def claim_reminder(self, event_id: int, window: str, channel_id: int) -> int | None:
        """Reserve (event_id, window). None when it was already claimed: the
        UNIQUE index is the dedupe across restarts and date edits."""
        async with self.db.lock:
            cursor = await self._conn.execute(
                """INSERT OR IGNORE INTO event_reminders (event_id, window, channel_id)
                   VALUES (?, ?, ?)""", (event_id, window, channel_id))
            await self._conn.commit()
            return cursor.lastrowid if cursor.rowcount > 0 else None

    async def mark_reminder_sent(self, reminder_id: int, message_id: int, roles_mentioned: str) -> None:
        async with self.db.lock:
            await self._conn.execute(
                'UPDATE event_reminders SET message_id = ?, roles_mentioned = ?, posted_at = ? WHERE id = ?',
                (message_id, roles_mentioned, _utcnow(), reminder_id))
            await self._conn.commit()

    async def release_reminder(self, reminder_id: int) -> None:
        """The send failed: drop the claim so the next run retries."""
        async with self.db.lock:
            await self._conn.execute('DELETE FROM event_reminders WHERE id = ?', (reminder_id,))
            await self._conn.commit()

    async def dated_reminder_sent(self, event_id: int) -> bool:
        """Has a 30/7/1-style window actually gone out? Decides whether a
        change or cancellation is worth a notice: nobody saw an event that
        was never announced."""
        cursor = await self._conn.execute(
            """SELECT 1 FROM event_reminders
               WHERE event_id = ? AND posted_at IS NOT NULL AND window NOT IN ('changed', 'cancelled')
               LIMIT 1""", (event_id,))
        return await cursor.fetchone() is not None

    async def approved_between(self, start: str, end: str) -> list[dict]:
        """Approved events in every guild with start_date in [start, end]."""
        cursor = await self._conn.execute(
            """SELECT * FROM events WHERE status = 'approved' AND start_date >= ? AND start_date <= ?
               ORDER BY start_date, id""", (start, end))
        return [dict(r) for r in await cursor.fetchall()]

    # -- nightly sweep ------------------------------------------------------

    async def retire_ended(self, today: str) -> list[dict]:
        """approved or cancelled rows whose end_date is before today become
        retired. Returns the rows as they were, for rollover decisions."""
        async with self.db.lock:
            cursor = await self._conn.execute(
                """SELECT * FROM events WHERE status IN ('approved', 'cancelled') AND end_date < ?
                   ORDER BY id""", (today,))
            rows = [dict(r) for r in await cursor.fetchall()]
            for row in rows:
                await self._conn.execute(
                    "UPDATE events SET status = 'retired', updated_at = ? WHERE id = ?",
                    (_utcnow(), row['id']))
                await self._audit_unlocked(row['id'], 0, 'retire', row, {**row, 'status': 'retired'})
            await self._conn.commit()
        return rows

    async def has_rollover(self, parent_id: int) -> bool:
        cursor = await self._conn.execute(
            'SELECT 1 FROM events WHERE parent_event_id = ? LIMIT 1', (parent_id,))
        return await cursor.fetchone() is not None

    async def expire_pending(self, cutoff_iso: str) -> list[int]:
        """pending rows created before the cutoff become rejected/expired."""
        async with self.db.lock:
            cursor = await self._conn.execute(
                "SELECT * FROM events WHERE status = 'pending' AND created_at < ? ORDER BY id",
                (cutoff_iso,))
            rows = [dict(r) for r in await cursor.fetchall()]
            for row in rows:
                await self._conn.execute(
                    """UPDATE events SET status = 'rejected', reject_reason = 'expired', decided_by = 0,
                              decided_at = ?, updated_at = ? WHERE id = ?""",
                    (_utcnow(), _utcnow(), row['id']))
                await self._audit_unlocked(row['id'], 0, 'expire', row,
                                           {**row, 'status': 'rejected', 'reject_reason': 'expired'})
            await self._conn.commit()
        return [row['id'] for row in rows]

    async def purge_rejected(self, cutoff_iso: str) -> int:
        """Delete rejected rows decided before the cutoff (180 days in the
        sweep). Audit rows stay."""
        async with self.db.lock:
            cursor = await self._conn.execute(
                "DELETE FROM events WHERE status = 'rejected' AND decided_at < ?", (cutoff_iso,))
            await self._conn.commit()
            return cursor.rowcount
```

Add `timedelta` to the `datetime` import at the top of the module.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_store.py -q -p no:cacheprovider`
Expected: all pass. `test_approved_between_spans_guilds` expects order by `start_date` then id: Hamfest (09-12), Other (09-20), GrrCON (09-24).

- [ ] **Step 5: Commit**

```bash
git add penguin-overlord/utils/events_store.py tests/unit/test_events_store.py
git commit -m "feat(events): store queries for listing, decisions, reminders and the sweep

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 6: Embeds and mention policy (`utils/events_cards.py`)

**Files:**
- Create: `penguin-overlord/utils/events_cards.py`
- Test: `tests/unit/test_events_cards.py`

**Interfaces:**
- Consumes: `Regions` (Task 3, `regions.name(code)`), `TOPIC_LABELS`, `days_until` (Task 2), event dict rows.
- Produces:
  - `allowed_mentions(roles: list[discord.Role]) -> discord.AllowedMentions` (everyone False, users False, roles exactly the list)
  - `format_dates(event) -> str` (`Sep 24 to 25, 2026`, `Sep 12, 2026`, `Aug 6 to 9, 2026 (estimated)`)
  - `location(event, regions) -> str` (`Grand Rapids, Michigan`, `Online`, `Berlin, Germany`, `Las Vegas, Nevada (national)`)
  - `countdown(days: int) -> str` (`in 30 days`, `tomorrow`, `today`)
  - `review_card(event, regions, *, provenance_line: str, decided: str | None = None) -> discord.Embed`
  - `reminder_embed(event, regions, days: int) -> discord.Embed`
  - `reminder_text(event, role_mentions: list[str], missing: list[str]) -> str` (the message content above the embed)
  - `list_embed(events, regions, *, today: str, page: int, pages: int, heading: str) -> discord.Embed`
  - `digest_embed(events, regions, *, today: str) -> discord.Embed`
  - `mine_lines(events) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Events embeds: what members and moderators see, and the one mention
policy every post goes through."""

import types

import discord
import pytest

from utils import events_cards as cards
from utils.events_logic import load_regions


@pytest.fixture(scope='module')
def regions():
    return load_regions()


def event(**over):
    base = dict(id=12, guild_id=1, title='GrrCON', topic='cyber', start_date='2026-09-24',
                end_date='2026-09-25', date_status='confirmed', city='Grand Rapids',
                region_code='US-MI', country_code='US', scope='regional',
                url='https://grrcon.com', notes=None, status='approved', provenance='member',
                submitted_by=42, decided_by=None, decided_at=None, reject_reason=None,
                created_at='2026-09-01T12:00:00+00:00')
    base.update(over)
    return base


# -- mention policy -----------------------------------------------------------

def test_allowed_mentions_never_pings_users_or_everyone():
    role = types.SimpleNamespace(id=5, name='Michigan')
    am = cards.allowed_mentions([role])
    assert am.everyone is False and am.users is False
    assert am.roles == [role]


def test_allowed_mentions_with_no_roles_pings_nothing():
    am = cards.allowed_mentions([])
    assert am.roles == [] and am.users is False and am.everyone is False


# -- text pieces --------------------------------------------------------------

@pytest.mark.parametrize('start, end, status, expected', [
    ('2026-09-24', '2026-09-25', 'confirmed', 'Sep 24 to 25, 2026'),
    ('2026-09-12', '2026-09-12', 'confirmed', 'Sep 12, 2026'),
    ('2026-08-06', '2026-08-09', 'estimated', 'Aug 6 to 9, 2026 (estimated)'),
    ('2026-12-30', '2027-01-02', 'confirmed', 'Dec 30, 2026 to Jan 2, 2027'),
])
def test_format_dates(start, end, status, expected):
    assert cards.format_dates(event(start_date=start, end_date=end, date_status=status)) == expected


def test_location_variants(regions):
    assert cards.location(event(), regions) == 'Grand Rapids, Michigan'
    assert cards.location(event(city='Online', region_code=None, country_code=None), regions) == 'Online'
    assert cards.location(event(city='Berlin', region_code=None, country_code='DE', scope='national'),
                          regions) == 'Berlin, Germany (national)'
    assert cards.location(event(city='Las Vegas', region_code='US-NV', scope='national'),
                          regions) == 'Las Vegas, Nevada (national)'


@pytest.mark.parametrize('days, expected', [(30, 'in 30 days'), (7, 'in 7 days'), (1, 'tomorrow'), (0, 'today')])
def test_countdown(days, expected):
    assert cards.countdown(days) == expected


# -- review card --------------------------------------------------------------

def test_review_card_shows_everything_a_mod_needs(regions):
    embed = cards.review_card(event(notes='Bring a badge'), regions,
                              provenance_line='Submitted by <@42>')
    assert embed.title == 'Event #12: GrrCON'
    names = {f.name: f.value for f in embed.fields}
    assert names['When'] == 'Sep 24 to 25, 2026'
    assert names['Where'] == 'Grand Rapids, Michigan'
    assert names['Topic'] == 'Cybersecurity'
    assert names['Link'] == 'https://grrcon.com'
    assert names['Notes'] == 'Bring a badge'
    assert names['Reminder tags'] == 'Cybersecurity Events, Michigan'
    assert 'Submitted by <@42>' in embed.description
    assert embed.footer.text == 'Pending review'


def test_review_card_decided_footer(regions):
    embed = cards.review_card(event(status='rejected', reject_reason='dupe'), regions,
                              provenance_line='Submitted by <@42>',
                              decided='Rejected by <@7> at 2026-09-02 10:00 ET: dupe')
    assert embed.footer.text == 'Rejected by <@7> at 2026-09-02 10:00 ET: dupe'


def test_review_card_has_no_em_dash(regions):
    embed = cards.review_card(event(), regions, provenance_line='Imported from the calendar')
    blob = (embed.title or '') + (embed.description or '') + ''.join(f.value for f in embed.fields)
    assert '—' not in blob


# -- reminders ----------------------------------------------------------------

def test_reminder_embed_and_text(regions):
    embed = cards.reminder_embed(event(), regions, 7)
    assert embed.title == 'GrrCON in 7 days'
    assert embed.url == 'https://grrcon.com'
    assert 'Sep 24 to 25, 2026' in embed.description
    assert 'Grand Rapids, Michigan' in embed.description
    text = cards.reminder_text(event(), ['<@&1>', '<@&2>'], missing=['Michigan'])
    assert text.startswith('<@&1> <@&2>')
    assert 'Michigan' in text            # missing role named in plain text


def test_reminder_text_with_nothing_to_mention_is_plain(regions):
    assert cards.reminder_text(event(), [], missing=[]) == 'Upcoming event'


def test_cancelled_reminder_says_so(regions):
    embed = cards.reminder_embed(event(status='cancelled', reject_reason='venue lost'), regions, 0)
    assert embed.title.startswith('Cancelled: GrrCON')
    assert 'venue lost' in embed.description


def test_changed_reminder_is_marked_updated(regions):
    embed = cards.reminder_embed(event(), regions, 12, changed=True)
    assert embed.title == 'Updated: GrrCON in 12 days'


# -- lists and digest ---------------------------------------------------------

def test_list_embed_pages_and_strikes_cancelled(regions):
    rows = [event(), event(id=13, title='Ontario Hamfest', topic='ham', start_date='2026-09-12',
                           end_date='2026-09-12', city='Milton', region_code='CA-ON',
                           country_code='CA', status='cancelled')]
    embed = cards.list_embed(rows, regions, today='2026-09-03', page=1, pages=3, heading='Next 90 days')
    assert embed.title == 'Next 90 days'
    assert embed.footer.text == 'Page 1 of 3'
    assert '~~Ontario Hamfest~~' in embed.description
    assert '**GrrCON**' in embed.description and 'in 21 days' in embed.description
    assert '—' not in embed.description


def test_list_embed_empty(regions):
    embed = cards.list_embed([], regions, today='2026-09-03', page=1, pages=1, heading='Next 90 days')
    assert 'Nothing' in embed.description


def test_digest_embed_groups_by_week(regions):
    rows = [event(start_date='2026-09-08', end_date='2026-09-08'),
            event(id=14, title='Later', start_date='2026-09-30', end_date='2026-09-30')]
    embed = cards.digest_embed(rows, regions, today='2026-09-07')
    assert embed.title == 'This month in events'
    assert 'GrrCON' in embed.description and 'Later' in embed.description
    assert embed.description.index('GrrCON') < embed.description.index('Later')


def test_mine_lines(regions):
    text = cards.mine_lines([event(status='pending'), event(id=9, status='rejected', reject_reason='dupe')])
    assert '#12' in text and 'pending' in text
    assert '#9' in text and 'rejected (dupe)' in text
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_cards.py -q -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'utils.events_cards'`.

- [ ] **Step 3: Write the module**

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Everything the events cog shows in Discord.

One rule lives here that every poster path must honour: member-facing
posts mention roles and nothing else. `allowed_mentions` is the only way
to build the AllowedMentions for an events post, and it pins users and
everyone to False.
"""

from datetime import date

import discord

from utils.events_logic import TOPIC_LABELS, days_until, role_names_for

COLOUR = {
    'pending': 0xF1C40F,
    'approved': 0x2ECC71,
    'rejected': 0x95A5A6,
    'cancelled': 0xE74C3C,
    'retired': 0x7F8C8D,
}


def allowed_mentions(roles) -> discord.AllowedMentions:
    """Roles only. Never users, never everyone."""
    return discord.AllowedMentions(everyone=False, users=False, roles=list(roles), replied_user=False)


def format_dates(event: dict) -> str:
    start = date.fromisoformat(event['start_date'])
    end = date.fromisoformat(event['end_date'])
    if start == end:
        text = f'{start:%b} {start.day}, {start.year}'
    elif start.year == end.year and start.month == end.month:
        text = f'{start:%b} {start.day} to {end.day}, {start.year}'
    elif start.year == end.year:
        text = f'{start:%b} {start.day} to {end:%b} {end.day}, {start.year}'
    else:
        text = f'{start:%b} {start.day}, {start.year} to {end:%b} {end.day}, {end.year}'
    if event.get('date_status') == 'estimated':
        text += ' (estimated)'
    return text


def location(event: dict, regions) -> str:
    parts = [event['city']]
    if event.get('region_code'):
        parts.append(regions.name(event['region_code']))
    elif event.get('country_code'):
        parts.append(regions.name(event['country_code']))
    text = ', '.join(p for p in parts if p)
    if event.get('scope') == 'national' and (event.get('region_code') or event.get('country_code')):
        text += ' (national)'
    return text


def countdown(days: int) -> str:
    if days <= 0:
        return 'today'
    if days == 1:
        return 'tomorrow'
    return f'in {days} days'


def review_card(event: dict, regions, *, provenance_line: str, decided: str = None) -> discord.Embed:
    embed = discord.Embed(title=f"Event #{event['id']}: {event['title']}",
                          description=provenance_line,
                          colour=COLOUR.get(event['status'], 0x95A5A6))
    embed.add_field(name='When', value=format_dates(event), inline=True)
    embed.add_field(name='Where', value=location(event, regions), inline=True)
    embed.add_field(name='Topic', value=TOPIC_LABELS[event['topic']], inline=True)
    embed.add_field(name='Link', value=event['url'] or 'none given', inline=False)
    if event.get('notes'):
        embed.add_field(name='Notes', value=event['notes'][:1024], inline=False)
    # Plain names, not mentions: the review channel must never ping.
    embed.add_field(name='Reminder tags', value=', '.join(role_names_for(event, regions)) or 'none',
                    inline=False)
    embed.set_footer(text=decided or 'Pending review')
    return embed


def reminder_embed(event: dict, regions, days: int, *, changed: bool = False) -> discord.Embed:
    cancelled = event['status'] == 'cancelled'
    if cancelled:
        title = f"Cancelled: {event['title']}"
    elif changed:
        title = f"Updated: {event['title']} {countdown(days)}"
    else:
        title = f"{event['title']} {countdown(days)}"
    lines = [format_dates(event), location(event, regions), TOPIC_LABELS[event['topic']]]
    if cancelled and event.get('reject_reason'):
        lines.append(f"Reason: {event['reject_reason']}")
    if event.get('notes'):
        lines.append('')
        lines.append(event['notes'])
    embed = discord.Embed(title=title, url=event['url'], description='\n'.join(lines),
                          colour=COLOUR['cancelled' if cancelled else 'approved'])
    embed.set_footer(text=f"Event #{event['id']}")
    return embed


def reminder_text(event: dict, role_mentions: list, missing: list) -> str:
    """Message content above the embed: the role pings, plus the plain
    names of roles the guild is missing so the post still says who it
    was for."""
    parts = list(role_mentions) + list(missing)
    return ' '.join(parts) if parts else 'Upcoming event'


def _line(event: dict, regions, today: date) -> str:
    name = f"~~{event['title']}~~" if event['status'] == 'cancelled' else f"**{event['title']}**"
    when = format_dates(event)
    link = f" <{event['url']}>" if event.get('url') else ''
    return (f"{name}: {when}, {location(event, regions)} "
            f"({countdown(days_until(event['start_date'], today))}){link}")


def list_embed(events: list, regions, *, today: str, page: int, pages: int, heading: str) -> discord.Embed:
    day = date.fromisoformat(today)
    body = '\n'.join(_line(e, regions, day) for e in events) or 'Nothing scheduled in this window.'
    embed = discord.Embed(title=heading, description=body[:4000], colour=COLOUR['approved'])
    embed.set_footer(text=f'Page {page} of {pages}')
    return embed


def digest_embed(events: list, regions, *, today: str) -> discord.Embed:
    day = date.fromisoformat(today)
    body = '\n'.join(_line(e, regions, day) for e in events) or 'Nothing scheduled in the next 30 days.'
    return discord.Embed(title='This month in events', description=body[:4000], colour=COLOUR['approved'])


def mine_lines(events: list) -> str:
    lines = []
    for e in events:
        state = e['status']
        if state == 'rejected' and e.get('reject_reason'):
            state = f"rejected ({e['reject_reason']})"
        lines.append(f"#{e['id']} {e['title']} ({e['start_date']}): {state}")
    return '\n'.join(lines) or 'You have not submitted any events.'
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_cards.py -q -p no:cacheprovider`
Expected: all pass. If `test_list_embed_pages_and_strikes_cancelled` fails on `in 21 days`, check `days_until('2026-09-24', '2026-09-03')` returns 21 (it should; the Task 2 tests cover it).

- [ ] **Step 5: Commit**

```bash
git add penguin-overlord/utils/events_cards.py tests/unit/test_events_cards.py
git commit -m "feat(events): embeds and the roles-only mention policy

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 7: The cog: member commands (`/events list|next|search|submit|mine`)

**Files:**
- Modify: `penguin-overlord/utils/events_logic.py` (add `resolve_place`)
- Create: `penguin-overlord/cogs/events.py`
- Test: `tests/unit/test_events_logic.py` (append), `tests/unit/test_events_cog.py`

**Interfaces:**
- Consumes: `EventsConfig`/`load_events_config` (Task 4), `EventsStore` (Tasks 1, 5), `load_regions`, `region_choices`, `validate_submission`, `local_today`, `TOPIC_LABELS` (Tasks 2, 3), `events_cards` (Task 6), `EVENTS_SUBMISSIONS`, `EVENTS_PENDING` (Task 4).
- Produces:
  - `events_logic.resolve_place(where: str, national: bool, regions) -> tuple[str | None, str | None, str]` = `(region_code, country_code, scope)`; raises `ValueError` with a member-facing message.
  - `cogs.events.Events(bot)` with attributes `cfg: EventsConfig`, `store: EventsStore | None`, `regions: Regions`, `today() -> date`, `async attach()` (opens the store; `cog_load` calls it, tests call it directly), `async post_review_card(event) -> int | None` (Task 8 replaces the stub), the group `events = app_commands.Group(name='events', ...)`, commands `events_list`, `events_next`, `events_search`, `events_submit`, `events_mine`, and `_where_autocomplete`.
  - Constants: `PAGE_SIZE = 5`, `LIST_DAYS = 365`, `NEXT_DAYS = 30`, `DISABLED_TEXT = 'Events are not enabled on this server.'`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_events_logic.py`:

```python
# -- submit: resolving the "where" autocomplete value -------------------------

@pytest.mark.parametrize('where, national, expected', [
    ('US-MI', False, ('US-MI', 'US', 'regional')),
    ('US-NV', True, ('US-NV', 'US', 'national')),
    ('DE', False, (None, 'DE', 'national')),
    ('online', False, (None, None, 'regional')),
    ('Online', True, (None, None, 'regional')),
])
def test_resolve_place(where, national, expected):
    assert logic.resolve_place(where, national, logic.load_regions()) == expected


def test_resolve_place_rejects_free_text():
    with pytest.raises(ValueError, match='Pick'):
        logic.resolve_place('Michigan', False, logic.load_regions())
```

(`logic` is the module alias the file already uses; check the import line at the top of the file and match it.)

Create `tests/unit/test_events_cog.py`:

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The events cog against a real store and a fake Discord.

Hermetic: no gateway, no .env. The bot object is a SimpleNamespace; the
interaction fakes record what was sent. Nothing here may call a bot
entrypoint or load dotenv.
"""

import types

import discord
import pytest

from cogs.events import DISABLED_TEXT, PAGE_SIZE, Events
from utils import database

GUILD = 1


@pytest.fixture
async def cog(tmp_data_dir, monkeypatch):
    monkeypatch.setenv('EVENTS_ENABLED', 'true')
    monkeypatch.setenv('EVENTS_DRY_RUN', 'false')
    monkeypatch.setenv('EVENTS_CHANNEL_ID', '5000')
    monkeypatch.setenv('EVENTS_REVIEW_CHANNEL_ID', '6000')
    monkeypatch.setenv('EVENTS_TIMEZONE', 'America/New_York')
    database.reset_database()
    bot = types.SimpleNamespace(added=[], config=None,
                                add_dynamic_items=lambda *items: bot.added.extend(items))
    c = Events(bot)
    await c.attach()
    c.today = lambda: __import__('datetime').date(2026, 9, 3)      # frozen clock
    yield c
    await c.store.db.close()
    database.reset_database()


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, *, embed=None, embeds=None, ephemeral=False,
                           allowed_mentions=None, view=None):
        self.sent.append(types.SimpleNamespace(content=content, embed=embed, embeds=embeds,
                                               ephemeral=ephemeral, allowed_mentions=allowed_mentions,
                                               view=view))

    async def defer(self, *, ephemeral=False, thinking=False):
        self.sent.append(types.SimpleNamespace(content=None, embed=None, deferred=True, ephemeral=ephemeral))


def interaction(user_id=42, *, roles=(), guild_id=GUILD, mod=False):
    guild = types.SimpleNamespace(id=guild_id, roles=[types.SimpleNamespace(name=n, id=i, mention=f'<@&{i}>')
                                                     for i, n in enumerate(roles, start=100)],
                                  me=types.SimpleNamespace(id=1), get_channel=lambda cid: None)
    user = types.SimpleNamespace(id=user_id, mention=f'<@{user_id}>', display_name=f'user{user_id}',
                                 guild_permissions=discord.Permissions(moderate_members=mod))
    return types.SimpleNamespace(guild=guild, guild_id=guild_id, user=user, response=FakeResponse(),
                                 followup=None, client=None, channel=None, message=None)


def event(**over):
    base = dict(guild_id=GUILD, title='GrrCON', fingerprint='grrcon:2026', topic='cyber',
                start_date='2026-09-24', end_date='2026-09-25', start_time=None, timezone=None,
                date_status='confirmed', city='Grand Rapids', region_code='US-MI', country_code='US',
                scope='regional', url='https://grrcon.com', notes=None, recurrence='annual',
                parent_event_id=None, status='approved', provenance='calendar', submitted_by=None,
                source_url=None, source_note=None, decided_by=0)
    base.update(over)
    return base


async def seed(cog, n=7):
    ids = []
    for i in range(n):
        ids.append(await cog.store.insert(
            event(title=f'Con {i}', fingerprint=f'con {i}:2026', start_date=f'2026-10-{10 + i:02d}',
                  end_date=f'2026-10-{10 + i:02d}'), actor_id=0, action='import'))
    return ids


# -- disabled -----------------------------------------------------------------

async def test_disabled_cog_answers_every_command_with_one_line(tmp_data_dir, monkeypatch):
    monkeypatch.delenv('EVENTS_ENABLED', raising=False)
    c = Events(types.SimpleNamespace(config=None))
    await c.cog_load()                      # no store, no loops
    assert c.store is None
    i = interaction()
    await c.events_list.callback(c, i)
    assert i.response.sent[0].content == DISABLED_TEXT and i.response.sent[0].ephemeral


# -- list / next / search -----------------------------------------------------

async def test_list_pages_five_at_a_time(cog):
    await seed(cog)
    i = interaction()
    await cog.events_list.callback(cog, i)
    sent = i.response.sent[0]
    assert sent.ephemeral is False
    assert sent.embed.footer.text == 'Page 1 of 2'
    assert sent.embed.description.count('**Con') == PAGE_SIZE
    i = interaction()
    await cog.events_list.callback(cog, i, page=2)
    assert i.response.sent[0].embed.description.count('**Con') == 2


async def test_list_filters_by_topic_and_place(cog):
    await seed(cog, 2)
    await cog.store.insert(event(title='Hamfest', fingerprint='hamfest:2026', topic='ham',
                                 start_date='2026-10-01', end_date='2026-10-01',
                                 region_code='CA-ON', country_code='CA'), actor_id=0, action='import')
    i = interaction()
    await cog.events_list.callback(cog, i, topic='ham')
    assert 'Hamfest' in i.response.sent[0].embed.description
    assert 'Con 0' not in i.response.sent[0].embed.description
    i = interaction()
    await cog.events_list.callback(cog, i, where='CA')
    assert 'Hamfest' in i.response.sent[0].embed.description
    i = interaction()
    await cog.events_list.callback(cog, i, where='US-MI')
    assert 'Hamfest' not in i.response.sent[0].embed.description
    i = interaction()
    await cog.events_list.callback(cog, i, where='Narnia')
    assert 'Pick' in i.response.sent[0].content and i.response.sent[0].ephemeral


async def test_next_is_the_thirty_day_window(cog):
    await seed(cog, 2)                                     # Oct 10 and 11: beyond 30 days from Sep 3
    await cog.store.insert(event(title='Soon', fingerprint='soon:2026', start_date='2026-09-20',
                                 end_date='2026-09-20'), actor_id=0, action='import')
    i = interaction()
    await cog.events_next.callback(cog, i)
    text = i.response.sent[0].embed.description
    assert 'Soon' in text and 'Con 0' not in text


async def test_search_is_ephemeral_and_case_insensitive(cog):
    await seed(cog, 2)
    i = interaction()
    await cog.events_search.callback(cog, i, query='con 1')
    sent = i.response.sent[0]
    assert sent.ephemeral and 'Con 1' in sent.embed.description and 'Con 0' not in sent.embed.description


async def test_where_autocomplete_returns_choices(cog):
    choices = await cog._where_autocomplete(interaction(), 'mich')
    assert [(c.name, c.value) for c in choices] == [('Michigan (US-MI)', 'US-MI')]


# -- submit -------------------------------------------------------------------

async def test_submit_creates_pending_row_and_posts_a_card(cog):
    posted = []

    async def post_review_card(ev):
        posted.append(ev)
        return 777
    cog.post_review_card = post_review_card
    i = interaction(user_id=42)
    await cog.events_submit.callback(cog, i, title='Queen City Con', topic='cyber', start='2026-10-10',
                                     end='2026-10-11', city='Cincinnati', where='US-OH',
                                     url='https://queencitycon.org')
    sent = i.response.sent[0]
    assert sent.ephemeral and '#1' in sent.content and 'review' in sent.content.lower()
    row = await cog.store.get(1)
    assert row['status'] == 'pending' and row['submitted_by'] == 42 and row['provenance'] == 'member'
    assert row['region_code'] == 'US-OH' and row['country_code'] == 'US' and row['scope'] == 'regional'
    assert row['review_message_id'] == 777
    assert posted[0]['id'] == 1


async def test_submit_rejects_bad_input_with_the_reason(cog):
    i = interaction()
    await cog.events_submit.callback(cog, i, title='X', topic='cyber', start='next friday', city='Detroit',
                                     where='US-MI')
    sent = i.response.sent[0]
    assert sent.ephemeral and 'YYYY-MM-DD' in sent.content
    assert await cog.store.get(1) is None


async def test_submit_duplicate_names_the_existing_event(cog):
    await seed(cog, 1)                                     # Con 0 on 2026-10-10
    i = interaction()
    await cog.events_submit.callback(cog, i, title='Con 0', topic='cyber', start='2026-10-12',
                                     city='Detroit', where='US-MI')
    sent = i.response.sent[0]
    assert 'matches #1' in sent.content and 'Con 0' in sent.content and 'approved' in sent.content
    assert await cog.store.count_open_submissions(GUILD, 42) == 0


async def test_submit_caps_open_submissions(cog):
    cog.post_review_card = lambda ev: _async(None)
    for n in range(3):
        i = interaction()
        await cog.events_submit.callback(cog, i, title=f'Pending {n}', topic='cyber',
                                         start=f'2026-11-{10 + n}', city='Detroit', where='US-MI')
    i = interaction()
    await cog.events_submit.callback(cog, i, title='One more', topic='cyber', start='2026-11-20',
                                     city='Detroit', where='US-MI')
    assert 'already have 3' in i.response.sent[0].content
    assert await cog.store.count_open_submissions(GUILD, 42) == 3


async def test_submit_online_event_has_no_place(cog):
    cog.post_review_card = lambda ev: _async(None)
    i = interaction()
    await cog.events_submit.callback(cog, i, title='Virtual Con', topic='foss', start='2026-11-01',
                                     city='Online', where='online')
    row = await cog.store.get(1)
    assert row['region_code'] is None and row['country_code'] is None and row['city'] == 'Online'


async def test_mine_lists_the_callers_rows_only(cog):
    cog.post_review_card = lambda ev: _async(None)
    i = interaction(user_id=42)
    await cog.events_submit.callback(cog, i, title='Mine', topic='cyber', start='2026-11-01',
                                     city='Detroit', where='US-MI')
    i = interaction(user_id=43)
    await cog.events_submit.callback(cog, i, title='Theirs', topic='cyber', start='2026-11-02',
                                     city='Detroit', where='US-MI')
    i = interaction(user_id=42)
    await cog.events_mine.callback(cog, i)
    sent = i.response.sent[0]
    assert sent.ephemeral and 'Mine' in sent.content and 'Theirs' not in sent.content


def _async(value):
    async def coro():
        return value
    return coro()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_logic.py tests/unit/test_events_cog.py -q -p no:cacheprovider`
Expected: `AttributeError: module 'utils.events_logic' has no attribute 'resolve_place'` and `ModuleNotFoundError: No module named 'cogs.events'`.

- [ ] **Step 3: Add `resolve_place` to `utils/events_logic.py`** (after `parse_location_field`)

```python
def resolve_place(where: str, national: bool, regions: Regions) -> tuple[Optional[str], Optional[str], str]:
    """The /events submit `where` value (an autocomplete code, or 'online')
    to (region_code, country_code, scope). A country code alone is a
    national event; `national` promotes a regional code to the country
    role."""
    code = (where or '').strip()
    if code.lower() == 'online':
        return None, None, 'regional'
    code = code.upper()
    if code in regions.regions:
        return code, Regions.country_of(code), 'national' if national else 'regional'
    if code in regions.countries:
        return None, code, 'national'
    raise ValueError('Pick a place from the list (start typing a state, province or country), or Online.')
```

- [ ] **Step 4: Write the cog**

`penguin-overlord/cogs/events.py`:

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Community events: member submissions, moderator review, dated reminders.

Thin Discord layer. Decisions live in utils.events_logic, SQL in
utils.events_store, embeds in utils.events_cards. Spec:
docs/superpowers/specs/2026-09-03-conference-database-design.md.
"""

import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import events_cards as cards
from utils.config import load_events_config
from utils.database import get_database
from utils.events_logic import (TOPIC_LABELS, load_regions, local_today, region_choices,
                                resolve_place, validate_submission)
from utils.events_store import EventsStore
from utils.metrics import EVENTS_PENDING, EVENTS_SUBMISSIONS

logger = logging.getLogger('penguin.events')

PAGE_SIZE = 5
LIST_DAYS = 365
NEXT_DAYS = 30
DISABLED_TEXT = 'Events are not enabled on this server.'
TOPIC_CHOICES = [app_commands.Choice(name=label, value=key) for key, label in TOPIC_LABELS.items()]


class Events(commands.Cog):
    """Conference and meetup calendar with role-targeted reminders."""

    def __init__(self, bot):
        self.bot = bot
        config = getattr(bot, 'config', None)
        self.cfg = config.events if config is not None else load_events_config()
        self.store: Optional[EventsStore] = None
        self.regions = load_regions()

    # -- lifecycle ------------------------------------------------------------

    async def cog_load(self):
        if not self.cfg.enabled:
            logger.info('Events disabled (EVENTS_ENABLED=false)')
            return
        await self.attach()
        logger.info('Events active: channel=%s review=%s dry_run=%s post_at=%02d:%02d %s reminders=%s',
                    self.cfg.channel_id, self.cfg.review_channel_id, self.cfg.dry_run,
                    *self.cfg.post_at, self.cfg.timezone, self.cfg.reminder_days)

    async def attach(self):
        """Open the store. Separate from cog_load so tests can attach
        without starting the clock loops."""
        self.store = EventsStore(await get_database())

    def today(self) -> datetime.date:
        return local_today(self.cfg.timezone)

    async def _refuse_if_off(self, interaction: discord.Interaction) -> bool:
        if self.store is None:
            await interaction.response.send_message(DISABLED_TEXT, ephemeral=True)
            return True
        return False

    async def post_review_card(self, event: dict) -> Optional[int]:
        """Post the moderator card for a new submission; returns the message
        id. Filled in by the moderation task; until then nothing is posted."""
        return None

    # -- autocomplete ---------------------------------------------------------

    async def _where_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=label, value=value)
                for label, value in region_choices(self.regions, current)]

    # -- member commands ------------------------------------------------------

    events = app_commands.Group(name='events', description='Community events calendar')

    @events.command(name='list', description='Upcoming events, soonest first')
    @app_commands.describe(topic='Only this topic', where='Only this state, province or country',
                           page='Page number')
    @app_commands.choices(topic=TOPIC_CHOICES)
    @app_commands.autocomplete(where=_where_autocomplete)
    async def events_list(self, interaction: discord.Interaction, topic: Optional[str] = None,
                          where: Optional[str] = None, page: app_commands.Range[int, 1, 50] = 1):
        if await self._refuse_if_off(interaction):
            return
        region_code = country_code = None
        if where:
            try:
                region_code, country_code, _ = resolve_place(where, False, self.regions)
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return
            if region_code:
                country_code = None                      # filter on the region alone
        today = self.today().isoformat()
        rows = await self.store.list_upcoming(interaction.guild_id, today=today, days=LIST_DAYS,
                                              topic=topic, region_code=region_code, country_code=country_code)
        pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        chunk = rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
        heading = 'Upcoming events'
        if topic:
            heading += f': {TOPIC_LABELS[topic]}'
        if where:
            heading += f' in {self.regions.name(region_code or country_code) or "Online"}'
        embed = cards.list_embed(chunk, self.regions, today=today, page=page, pages=pages, heading=heading)
        await interaction.response.send_message(embed=embed, allowed_mentions=cards.allowed_mentions([]))

    @events.command(name='next', description=f'Everything in the next {NEXT_DAYS} days')
    async def events_next(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        today = self.today().isoformat()
        rows = await self.store.list_upcoming(interaction.guild_id, today=today, days=NEXT_DAYS)
        embed = cards.list_embed(rows[:10], self.regions, today=today, page=1, pages=1,
                                 heading=f'Next {NEXT_DAYS} days')
        await interaction.response.send_message(embed=embed, allowed_mentions=cards.allowed_mentions([]))

    @events.command(name='search', description='Find an event by name or city')
    @app_commands.describe(query='Part of the name or city')
    async def events_search(self, interaction: discord.Interaction, query: app_commands.Range[str, 2, 80]):
        if await self._refuse_if_off(interaction):
            return
        today = self.today().isoformat()
        rows = await self.store.search(interaction.guild_id, query, today=today)
        embed = cards.list_embed(rows, self.regions, today=today, page=1, pages=1,
                                 heading=f'Events matching "{query}"')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @events.command(name='submit', description='Suggest an event for the calendar')
    @app_commands.describe(title='Event name', topic='What kind of event', start='Start date, YYYY-MM-DD',
                           end='End date, YYYY-MM-DD (blank for one day)',
                           city='City, or Online', where='State, province or country (start typing)',
                           url='Event website', notes='Anything else, up to 500 characters',
                           national='Notify the whole country, not just the state or province')
    @app_commands.choices(topic=TOPIC_CHOICES)
    @app_commands.autocomplete(where=_where_autocomplete)
    async def events_submit(self, interaction: discord.Interaction, title: str, topic: str, start: str,
                            city: str, where: str, end: Optional[str] = None, url: Optional[str] = None,
                            notes: Optional[str] = None, national: bool = False):
        if await self._refuse_if_off(interaction):
            return
        guild_id, user = interaction.guild_id, interaction.user
        clean, problem = validate_submission(title=title, topic=topic, start=start, end=end, city=city,
                                             url=url, notes=notes, today=self.today())
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        try:
            region_code, country_code, scope = resolve_place(where, national, self.regions)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        existing = await self.store.find_fingerprint(guild_id, clean['fingerprint'])
        if existing:
            await interaction.response.send_message(
                f"That matches #{existing['id']}, {existing['title']} ({existing['status']}). "
                'If the details changed, ask a moderator to edit it.', ephemeral=True)
            return
        open_count = await self.store.count_open_submissions(guild_id, user.id)
        if open_count >= self.cfg.max_pending_per_member:
            await interaction.response.send_message(
                f'You already have {open_count} submissions waiting for review. '
                'Once a moderator handles those you can add more.', ephemeral=True)
            return
        row = {
            **clean, 'guild_id': guild_id, 'start_time': None, 'timezone': None,
            'date_status': 'confirmed', 'region_code': region_code, 'country_code': country_code,
            'scope': scope, 'recurrence': 'none', 'parent_event_id': None, 'status': 'pending',
            'provenance': 'member', 'submitted_by': user.id, 'source_url': None, 'source_note': None,
        }
        event_id = await self.store.insert(row, actor_id=user.id, action='submit')
        EVENTS_SUBMISSIONS.labels(provenance='member').inc()
        EVENTS_PENDING.set(await self.store.pending_count(guild_id))
        event = await self.store.get(event_id)
        message_id = await self.post_review_card(event)
        if message_id:
            await self.store.set_review_message(event_id, message_id)
        logger.info('Event #%d submitted by %s: %s (%s)', event_id, user.id, clean['title'], clean['start_date'])
        await interaction.response.send_message(
            f"Thanks. #{event_id} {clean['title']} is in the review queue; a moderator will look at it. "
            'You can check on it with /events mine.', ephemeral=True)

    @events.command(name='mine', description='Your submissions and what happened to them')
    async def events_mine(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        rows = await self.store.mine(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(cards.mine_lines(rows), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Events(bot))
```

`recurrence` is `'none'` for member submissions and `'annual'` for the calendar import, matching the Task 1 column comment.

- [ ] **Step 5: Retire the old cog's commands now, not in Task 11**

`cogs/eventpinger.py` registers a hybrid command named `events`; with the new group loaded alongside it `test_cog_loading` fails on the duplicate name. Delete it in this task (the `events/` CSV directory, Dockerfile line and docs go in Task 11; the import script in Task 10 still needs the CSV on disk):

```bash
git rm penguin-overlord/cogs/eventpinger.py
```

Then replace the two help texts that named its commands. `test_help_pages` checks every `` `/name`` and `` `!name`` mention against registered command and group names, so the new text may only reference `/events`.

In `penguin-overlord/cogs/help_categorized.py`, replace the whole `elif category == "events":` branch (the block from that line to just before `elif category == "utilities":`) with:

```python
    elif category == "events":
        embed = discord.Embed(
            title="📅 Events - Community Calendar",
            description="Cybersecurity, ham radio and FOSS events, with reminders for the roles you pick.",
            color=0x5865F2
        )
        embed.add_field(
            name="📋 Commands",
            value=(
                "`/events list` - Upcoming events; filter by topic or place, page through\n"
                "`/events next` - Everything in the next 30 days\n"
                "`/events search` - Find an event by name or city\n"
                "`/events submit` - Suggest an event; a moderator reviews it\n"
                "`/events mine` - Your submissions and what happened to them"
            ),
            inline=False
        )
        embed.add_field(
            name="🔔 Reminders",
            value=(
                "Approved events are announced 30, 7 and 1 days out. Pick the topics and "
                "places you care about from the role panels and only those roles get mentioned."
            ),
            inline=False
        )
        embed.set_footer(text="📅 Events • Never miss a conference!")
```

In `penguin-overlord/cogs/admin.py`, replace page 5 (from `# Page 5: Event Pinger` through its `embeds.append(embed)`) with:

```python
        # Page 5: Events - community calendar
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Events - conference and meetup reminders",
            color=0x5865F2
        )
        embed.add_field(
            name="📅 Event Commands",
            value=(
                "`/events list` - Upcoming events, filter by topic or place\n"
                "`/events next` - The next 30 days\n"
                "`/events search` - Find an event by name or city\n"
                "`/events submit` - Suggest an event for moderator review\n"
                "`/events mine` - Your submissions"
            ),
            inline=False
        )
        embed.add_field(
            name="🔔 How reminders work",
            value=(
                "Approved events are posted 30, 7 and 1 days out, mentioning the topic role "
                "and the state, province or country role. Pick yours from the role panels."
            ),
            inline=False
        )
        embed.set_footer(text="Page 5 of 6 • Use buttons to navigate")
        embeds.append(embed)
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_logic.py tests/unit/test_events_cog.py tests/unit/test_cog_imports.py tests/unit/test_cog_loading.py tests/unit/test_help_pages.py -q -p no:cacheprovider`
Expected: all pass. The cog loads disabled with no store and no loops; the help pages only name `/events`.

- [ ] **Step 7: Commit**

```bash
git add -A penguin-overlord/cogs/events.py penguin-overlord/cogs/eventpinger.py penguin-overlord/cogs/help_categorized.py penguin-overlord/cogs/admin.py penguin-overlord/utils/events_logic.py tests/unit/test_events_logic.py tests/unit/test_events_cog.py
git commit -m "feat(events): /events list, next, search, submit and mine; retire eventpinger commands

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 8: Moderation: review cards, buttons, modals, mod commands, one-shot notices

**Files:**
- Modify: `penguin-overlord/utils/events_logic.py` (add `location_field`)
- Modify: `penguin-overlord/cogs/events.py`
- Test: `tests/unit/test_events_logic.py` (append), `tests/unit/test_events_cog.py` (extend fakes, append)

**Interfaces:**
- Consumes: Task 7's cog, `EventsStore.decide/cancel/update/set_review_message/list_pending/claim_reminder/mark_reminder_sent/release_reminder/dated_reminder_sent` (Task 5), `cards.review_card/reminder_embed/reminder_text/allowed_mentions` (Task 6), `parse_dates_field`, `parse_location_field`, `role_names_for`, `days_until` (Tasks 2, 3), metrics (Task 4).
- Produces:
  - `events_logic.location_field(event) -> str` (inverse of `parse_location_field`: `'Grand Rapids, US-MI'`, `'Las Vegas, US-NV, national'`, `'Berlin, DE'`, `'Online'`)
  - `cogs.events.EventButton` (DynamicItem, template `event:<id>:<approve|reject|edit>`), `review_view(event_id) -> discord.ui.View`, `RejectModal`, `EditModal`
  - On `Events`: `post_review_card(event) -> int | None` (real), `handle_button(interaction, event_id, verb)`, `decide(interaction, event_id, status, reason=None)`, `apply_edit(interaction, event_id, changes)`, `parse_edit(*, title, dates, location, url, notes) -> dict`, `refresh_card(event)`, `notify(event, window, *, changed=False) -> bool`, `resolve_roles(guild, names) -> (roles, missing)`, `decided_line(event) -> str`, commands `events_pending`, `events_approve`, `events_reject`, `events_edit`, `events_cancel`; `cog_load` now registers `EventButton` with `bot.add_dynamic_items`.
  - Reminder windows are the strings `'30'`, `'7'`, `'1'` (from `due_window`), plus `'changed'` and `'cancelled'`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_events_logic.py`:

```python
@pytest.mark.parametrize('over, expected', [
    ({}, 'Grand Rapids, US-MI'),
    ({'scope': 'national', 'region_code': 'US-NV', 'city': 'Las Vegas'}, 'Las Vegas, US-NV, national'),
    ({'region_code': None, 'country_code': 'DE', 'city': 'Berlin', 'scope': 'national'}, 'Berlin, DE'),
    ({'region_code': None, 'country_code': None, 'city': 'Online'}, 'Online'),
])
def test_location_field_round_trips(over, expected):
    ev = {'city': 'Grand Rapids', 'region_code': 'US-MI', 'country_code': 'US', 'scope': 'regional', **over}
    assert logic.location_field(ev) == expected
    city, region, country, scope = logic.parse_location_field(expected, logic.load_regions())
    assert (city, region, country, scope) == (ev['city'], ev['region_code'], ev['country_code'], ev['scope'])
```

In `tests/unit/test_events_cog.py`, replace `FakeResponse` and `interaction` with these (the Task 7 tests keep passing; they only gain `send_modal`, `is_done`, a client, channels and a guild registry):

```python
class FakeResponse:
    def __init__(self):
        self.sent = []

    def is_done(self):
        return bool(self.sent)

    async def send_message(self, content=None, *, embed=None, embeds=None, ephemeral=False,
                           allowed_mentions=None, view=None):
        self.sent.append(types.SimpleNamespace(content=content, embed=embed, embeds=embeds,
                                               ephemeral=ephemeral, allowed_mentions=allowed_mentions,
                                               view=view, modal=None))

    async def send_modal(self, modal):
        self.sent.append(types.SimpleNamespace(content=None, embed=None, ephemeral=True, modal=modal))

    async def defer(self, *, ephemeral=False, thinking=False):
        self.sent.append(types.SimpleNamespace(content=None, embed=None, deferred=True, ephemeral=ephemeral,
                                               modal=None))


class FakeFollowup:
    def __init__(self, response):
        self.response = response

    async def send(self, content=None, *, embed=None, ephemeral=False, allowed_mentions=None, view=None):
        await self.response.send_message(content, embed=embed, ephemeral=ephemeral,
                                         allowed_mentions=allowed_mentions, view=view)


class FakeMessage:
    def __init__(self, mid):
        self.id = mid
        self.edits = []

    async def edit(self, *, embed=None, view=None, content=None):
        self.edits.append(types.SimpleNamespace(embed=embed, view=view, content=content))


class FakeChannel:
    def __init__(self, cid, *, fail=False):
        self.id = cid
        self.sent = []
        self.messages = {}
        self.fail = fail
        self._next = 1000

    def permissions_for(self, member):
        return discord.Permissions(mention_everyone=not self.fail)

    async def send(self, content=None, *, embed=None, view=None, allowed_mentions=None):
        if self.fail:
            raise discord.HTTPException(types.SimpleNamespace(status=500, reason='boom'), 'boom')
        self._next += 1
        self.sent.append(types.SimpleNamespace(content=content, embed=embed, view=view,
                                               allowed_mentions=allowed_mentions, id=self._next))
        self.messages[self._next] = FakeMessage(self._next)
        return self.messages[self._next]

    async def fetch_message(self, mid):
        if mid not in self.messages:
            raise discord.NotFound(types.SimpleNamespace(status=404, reason='gone'), 'gone')
        return self.messages[mid]


ROLE_NAMES = ('Cybersecurity Events', 'Ham Radio Events', 'FOSS Events', 'Michigan', 'Ohio', 'United States')


def make_guild(role_names=ROLE_NAMES, guild_id=GUILD):
    roles = [types.SimpleNamespace(name=n, id=i, mention=f'<@&{i}>') for i, n in enumerate(role_names, start=100)]
    return types.SimpleNamespace(id=guild_id, roles=roles, me=types.SimpleNamespace(id=1))


def wire(cog, *, guild=None, channels=None):
    """Give the cog's bot a guild and channels: the review channel (6000)
    and the events channel (5000) by default."""
    guild = guild or make_guild()
    channels = channels if channels is not None else {5000: FakeChannel(5000), 6000: FakeChannel(6000)}
    cog.bot.get_guild = lambda gid: guild if gid == guild.id else None
    cog.bot.get_channel = lambda cid: channels.get(cid)
    cog.bot.get_cog = lambda name: cog if name == 'Events' else None
    return guild, channels


def interaction(user_id=42, *, guild=None, guild_id=GUILD, mod=False, client=None):
    guild = guild or make_guild(guild_id=guild_id)
    user = types.SimpleNamespace(id=user_id, mention=f'<@{user_id}>', display_name=f'user{user_id}',
                                 guild_permissions=discord.Permissions(moderate_members=mod))
    response = FakeResponse()
    return types.SimpleNamespace(guild=guild, guild_id=guild.id, user=user, response=response,
                                 followup=FakeFollowup(response), client=client, channel=None, message=None)
```

Then append:

```python
# -- review cards and buttons -------------------------------------------------

from cogs.events import EditModal, EventButton, RejectModal, review_view  # noqa: E402


async def submit(cog, user_id=42, **over):
    """A member submission through the real command, with the card posted
    to the wired review channel."""
    fields = dict(title='Queen City Con', topic='cyber', start='2026-10-10', end='2026-10-11',
                  city='Cincinnati', where='US-OH', url='https://queencitycon.org')
    fields.update(over)
    i = interaction(user_id=user_id)
    await cog.events_submit.callback(cog, i, **fields)
    return i


async def test_submission_posts_a_card_with_three_buttons(cog):
    guild, channels = wire(cog)
    await submit(cog)
    card = channels[6000].sent[0]
    assert card.embed.title == 'Event #1: Queen City Con'
    assert 'Submitted by <@42>' in card.embed.description
    assert [b.custom_id for b in card.view.children] == ['event:1:approve', 'event:1:reject', 'event:1:edit']
    assert card.allowed_mentions.users is False
    assert (await cog.store.get(1))['review_message_id'] == card.id


async def test_card_posting_failure_does_not_lose_the_submission(cog):
    wire(cog, channels={5000: FakeChannel(5000), 6000: FakeChannel(6000, fail=True)})
    i = await submit(cog)
    assert 'review queue' in i.response.sent[0].content
    row = await cog.store.get(1)
    assert row['status'] == 'pending' and row['review_message_id'] is None


async def test_button_template_round_trips():
    button = EventButton(12, 'approve')
    assert button.custom_id == 'event:12:approve'
    match = EventButton.__discord_ui_compiled_template__.match('event:12:reject')
    rebuilt = await EventButton.from_custom_id(None, None, match)
    assert (rebuilt.event_id, rebuilt.verb) == (12, 'reject')
    assert len(review_view(12).children) == 3


async def test_non_moderator_click_is_refused(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=99, mod=False)
    await cog.handle_button(i, 1, 'approve')
    assert 'moderator' in i.response.sent[0].content.lower() and i.response.sent[0].ephemeral
    assert (await cog.store.get(1))['status'] == 'pending'


async def test_approve_click_decides_and_rewrites_the_card(cog):
    guild, channels = wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'approve')
    row = await cog.store.get(1)
    assert row['status'] == 'approved' and row['decided_by'] == 7
    edit = channels[6000].messages[channels[6000].sent[0].id].edits[-1]
    assert edit.view is None and 'Approved by <@7>' in edit.embed.footer.text
    assert 'approved' in i.response.sent[0].content.lower()


async def test_second_click_reports_who_decided(cog):
    wire(cog)
    await submit(cog)
    await cog.handle_button(interaction(user_id=7, mod=True), 1, 'approve')
    i = interaction(user_id=8, mod=True)
    await cog.handle_button(i, 1, 'reject')
    assert 'Already decided' in i.response.sent[0].content and '<@7>' in i.response.sent[0].content


async def test_reject_click_opens_a_modal_and_the_modal_decides(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'reject')
    modal = i.response.sent[0].modal
    assert isinstance(modal, RejectModal)
    modal.reason._value = 'Duplicate of the BSides listing'
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    row = await cog.store.get(1)
    assert row['status'] == 'rejected' and row['reject_reason'] == 'Duplicate of the BSides listing'


async def test_edit_click_opens_a_prefilled_modal(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'edit')
    modal = i.response.sent[0].modal
    assert isinstance(modal, EditModal)
    assert modal.title_field.default == 'Queen City Con'
    assert modal.dates.default == '2026-10-10 to 2026-10-11'
    assert modal.location.default == 'Cincinnati, US-OH'


async def test_edit_modal_applies_changes_and_keeps_status(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.title_field._value = 'Queen City Con 2026'
    modal.dates._value = '2026-10-10 to 2026-10-12'
    modal.location._value = 'Cincinnati, US-OH, national'
    modal.url._value = 'https://queencitycon.org'
    modal.notes._value = ''
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    row = await cog.store.get(1)
    assert row['title'] == 'Queen City Con 2026' and row['end_date'] == '2026-10-12'
    assert row['scope'] == 'national' and row['status'] == 'pending'
    assert 'updated' in j.response.sent[0].content.lower()


async def test_edit_modal_bad_dates_are_reported_not_saved(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.dates._value = 'October 10'
    modal.title_field._value = 'Queen City Con'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    assert 'YYYY-MM-DD' in j.response.sent[0].content
    assert (await cog.store.get(1))['end_date'] == '2026-10-11'


# -- one-shot notices ---------------------------------------------------------

async def test_notify_posts_with_role_mentions_only(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    assert await cog.notify(await cog.store.get(eid), '7') is True
    post = channels[5000].sent[0]
    mentions = {r.name for r in post.allowed_mentions.roles}
    assert mentions == {'Cybersecurity Events', 'Michigan'}
    assert post.allowed_mentions.users is False and post.allowed_mentions.everyone is False
    assert post.content.startswith('<@&100> <@&103>')
    assert post.embed.title == 'GrrCON in 21 days'
    assert await cog.store.dated_reminder_sent(eid) is True
    assert await cog.notify(await cog.store.get(eid), '7') is False      # once ever


async def test_notify_names_missing_roles_in_plain_text(cog):
    guild, channels = wire(cog, guild=make_guild(('Cybersecurity Events',)))
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    post = channels[5000].sent[0]
    assert [r.name for r in post.allowed_mentions.roles] == ['Cybersecurity Events']
    assert 'Michigan' in post.content


async def test_notify_send_failure_releases_the_claim(cog):
    wire(cog, channels={5000: FakeChannel(5000, fail=True), 6000: FakeChannel(6000)})
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    assert await cog.notify(await cog.store.get(eid), '30') is False
    assert await cog.store.claim_reminder(eid, '30', 5000) is not None    # nothing left behind


async def test_notify_dry_run_logs_and_records_nothing(cog, caplog):
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'dry_run': True})
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    with caplog.at_level('INFO', logger='penguin.events'):
        assert await cog.notify(await cog.store.get(eid), '30') is True
    assert channels[5000].sent == []
    assert any('DRY RUN events reminder' in r.message for r in caplog.records)
    assert await cog.store.dated_reminder_sent(eid) is False


# -- mod commands -------------------------------------------------------------

def test_mod_commands_require_moderate_members(cog):
    for cmd in (cog.events_pending, cog.events_approve, cog.events_reject, cog.events_edit, cog.events_cancel):
        assert cmd.checks, cmd.name


async def test_pending_lists_and_reposts_lost_cards(cog):
    guild, channels = wire(cog)
    await submit(cog)
    await submit(cog, title='Second', start='2026-11-01', end=None)
    channels[6000].messages.clear()                        # both cards deleted by hand
    i = interaction(user_id=7, mod=True)
    await cog.events_pending.callback(cog, i, repost=True)
    text = i.response.sent[0].content
    assert '#1' in text and '#2' in text and i.response.sent[0].ephemeral
    assert len(channels[6000].sent) == 4                   # two originals, two reposts
    assert (await cog.store.get(1))['review_message_id'] == channels[6000].sent[2].id


async def test_approve_and_reject_commands(cog):
    wire(cog)
    await submit(cog)
    await submit(cog, title='Second', start='2026-11-01', end=None)
    i = interaction(user_id=7, mod=True)
    await cog.events_approve.callback(cog, i, event_id=1)
    assert (await cog.store.get(1))['status'] == 'approved'
    i = interaction(user_id=7, mod=True)
    await cog.events_reject.callback(cog, i, event_id=2, reason='not a real con')
    assert (await cog.store.get(2))['reject_reason'] == 'not a real con'
    i = interaction(user_id=7, mod=True)
    await cog.events_approve.callback(cog, i, event_id=2)
    assert 'Already decided' in i.response.sent[0].content


async def test_edit_command_opens_the_modal(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.events_edit.callback(cog, i, event_id=1)
    assert isinstance(i.response.sent[0].modal, EditModal)


async def test_cancel_posts_a_notice_only_if_a_reminder_went_out(cog):
    guild, channels = wire(cog)
    a = await cog.store.insert(event(), actor_id=0, action='import')
    b = await cog.store.insert(event(title='Quiet', fingerprint='quiet:2026'), actor_id=0, action='import')
    await cog.notify(await cog.store.get(a), '30')
    i = interaction(user_id=7, mod=True)
    await cog.events_cancel.callback(cog, i, event_id=a, reason='venue lost')
    i = interaction(user_id=7, mod=True)
    await cog.events_cancel.callback(cog, i, event_id=b, reason='never announced')
    posts = channels[5000].sent
    assert len(posts) == 2                                 # the reminder, then one cancellation
    assert posts[1].embed.title == 'Cancelled: GrrCON'
    assert (await cog.store.get(b))['status'] == 'cancelled'


async def test_edit_of_an_announced_event_posts_a_change_notice(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'start_date': '2026-09-25', 'end_date': '2026-09-26'})
    posts = channels[5000].sent
    assert len(posts) == 2 and posts[1].embed.title.startswith('Updated: GrrCON')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'notes': 'parking is free'})
    assert len(channels[5000].sent) == 2                   # notes are not a schedule change
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_logic.py tests/unit/test_events_cog.py -q -p no:cacheprovider`
Expected: `location_field` missing; `ImportError: cannot import name 'EditModal' from 'cogs.events'`.

- [ ] **Step 3: Add `location_field` to `utils/events_logic.py`** (after `parse_location_field`)

```python
def location_field(event: Mapping) -> str:
    """The edit modal's prefilled location line; parse_location_field
    reads it back."""
    code = event.get('region_code') or event.get('country_code')
    if not code:
        return event.get('city') or 'Online'
    text = f"{event['city']}, {code}"
    if event.get('scope') == 'national' and event.get('region_code'):
        text += ', national'
    return text
```

- [ ] **Step 4: Add the components and the moderation half of the cog**

Update the imports at the top of `cogs/events.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.events_logic import (TOPIC_LABELS, days_until, load_regions, local_today, location_field,
                                parse_dates_field, parse_location_field, region_choices, resolve_place,
                                role_names_for, validate_submission)
from utils.metrics import (EVENTS_DECISIONS, EVENTS_PENDING, EVENTS_POST_ERRORS, EVENTS_REMINDERS,
                           EVENTS_ROLE_MISSING, EVENTS_SUBMISSIONS)
```

Add the components after `TOPIC_CHOICES` and before `class Events`:

```python
MOD_ONLY_TEXT = 'Only moderators can do that.'
PROVENANCE_LINES = {
    'member': 'Submitted by <@{submitted_by}>',
    'calendar': 'Imported from the calendar',
    'rollover': 'Rolled over from #{parent_event_id}; dates are estimated until confirmed',
    'ai': 'Suggested by the discovery job',
}


class EventButton(discord.ui.DynamicItem[discord.ui.Button],
                  template=r'event:(?P<event_id>[0-9]+):(?P<verb>approve|reject|edit)'):
    """Persistent review button: the event id lives in the custom_id, so
    the card still works after a restart."""

    STYLES = {'approve': (discord.ButtonStyle.success, 'Approve'),
              'reject': (discord.ButtonStyle.danger, 'Reject'),
              'edit': (discord.ButtonStyle.secondary, 'Edit')}

    def __init__(self, event_id: int, verb: str):
        style, label = self.STYLES[verb]
        super().__init__(discord.ui.Button(style=style, label=label, custom_id=f'event:{event_id}:{verb}'))
        self.event_id = event_id
        self.verb = verb

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match['event_id']), match['verb'])

    async def callback(self, interaction: discord.Interaction):
        logger.info('Event button %s:%s clicked by %s', self.event_id, self.verb, interaction.user)
        cog = interaction.client.get_cog('Events')
        if cog is None or cog.store is None:
            await interaction.response.send_message(DISABLED_TEXT, ephemeral=True)
            return
        await cog.handle_button(interaction, self.event_id, self.verb)


def review_view(event_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for verb in ('approve', 'reject', 'edit'):
        view.add_item(EventButton(event_id, verb))
    return view


class RejectModal(discord.ui.Modal, title='Reject event'):
    reason = discord.ui.TextInput(label='Reason (the submitter sees this)', max_length=200)

    def __init__(self, cog, event_id: int):
        super().__init__()
        self.cog = cog
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.decide(interaction, self.event_id, 'rejected', reason=self.reason.value.strip())


class EditModal(discord.ui.Modal):
    """Moderator edit of any event, any status. Free-text fields that the
    logic module parses back; a parse failure is reported and nothing is
    saved."""

    def __init__(self, cog, event: dict):
        super().__init__(title=f"Edit event #{event['id']}")
        self.cog = cog
        self.event_id = event['id']
        dates = event['start_date'] if event['start_date'] == event['end_date'] \
            else f"{event['start_date']} to {event['end_date']}"
        self.title_field = discord.ui.TextInput(label='Title', default=event['title'], max_length=120)
        self.dates = discord.ui.TextInput(label='Dates: YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD',
                                          default=dates, max_length=24)
        self.location = discord.ui.TextInput(label='Location: City, US-MI[, national] or Online',
                                             default=location_field(event), max_length=80)
        self.url = discord.ui.TextInput(label='URL', default=event['url'] or '', required=False, max_length=300)
        self.notes = discord.ui.TextInput(label='Notes', style=discord.TextStyle.paragraph,
                                          default=event['notes'] or '', required=False, max_length=500)
        for item in (self.title_field, self.dates, self.location, self.url, self.notes):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            changes = self.cog.parse_edit(title=self.title_field.value, dates=self.dates.value,
                                          location=self.location.value, url=self.url.value,
                                          notes=self.notes.value)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await self.cog.apply_edit(interaction, self.event_id, changes)
```

In `Events.__init__` add `self._warned_roles: dict = {}` (role name to the local date it was last warned about). In `cog_load`, after `await self.attach()`, add `self.bot.add_dynamic_items(EventButton)`.

Replace the `post_review_card` stub and add the moderation methods and commands to `Events` (after `events_mine`):

```python
    # -- moderator surface -----------------------------------------------------

    async def _channel(self, channel_id: Optional[int]):
        if not channel_id:
            return None
        channel = self.bot.get_channel(channel_id)
        if channel is None and hasattr(self.bot, 'fetch_channel'):
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                channel = None
        return channel

    def _local(self, iso: Optional[str]) -> str:
        if not iso:
            return 'unknown time'
        stamp = datetime.fromisoformat(iso).astimezone(ZoneInfo(self.cfg.timezone))
        return stamp.strftime('%Y-%m-%d %H:%M ') + ('ET' if self.cfg.timezone == 'America/New_York'
                                                    else stamp.strftime('%Z'))

    def decided_line(self, event: dict) -> str:
        who = 'the sweep' if not event.get('decided_by') else f"<@{event['decided_by']}>"
        text = f"{event['status'].capitalize()} by {who} at {self._local(event.get('decided_at'))}"
        if event.get('reject_reason'):
            text += f": {event['reject_reason']}"
        return text

    def _card(self, event: dict) -> discord.Embed:
        line = PROVENANCE_LINES.get(event['provenance'], 'Unknown source').format(**event)
        decided = self.decided_line(event) if event['status'] != 'pending' else None
        return cards.review_card(event, self.regions, provenance_line=line, decided=decided)

    async def post_review_card(self, event: dict) -> Optional[int]:
        channel = await self._channel(self.cfg.review_channel_id)
        if channel is None:
            logger.warning('Event #%d: no review channel (%s); card not posted',
                           event['id'], self.cfg.review_channel_id)
            return None
        try:
            message = await channel.send(embed=self._card(event), view=review_view(event['id']),
                                         allowed_mentions=cards.allowed_mentions([]))
        except discord.HTTPException as e:
            logger.error('Event #%d: review card failed: %s', event['id'], e)
            return None
        return message.id

    async def refresh_card(self, event: dict) -> None:
        """Rewrite the card after a decision or edit; buttons come off once
        the row is no longer pending."""
        channel = await self._channel(self.cfg.review_channel_id)
        if channel is None or not event.get('review_message_id'):
            return
        try:
            message = await channel.fetch_message(event['review_message_id'])
            view = review_view(event['id']) if event['status'] == 'pending' else None
            await message.edit(embed=self._card(event), view=view)
        except discord.HTTPException as e:
            logger.warning('Event #%d: card refresh failed: %s', event['id'], e)

    @staticmethod
    def _is_mod(interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, 'guild_permissions', None)
        return bool(perms and perms.moderate_members)

    async def _reply(self, interaction: discord.Interaction, text: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    async def handle_button(self, interaction: discord.Interaction, event_id: int, verb: str) -> None:
        if not self._is_mod(interaction):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        event = await self.store.get(event_id)
        if event is None:
            await self._reply(interaction, f'Event #{event_id} no longer exists.')
            return
        if verb == 'edit':
            await interaction.response.send_modal(EditModal(self, event))
            return
        if event['status'] != 'pending':
            await self._reply(interaction, f'Already decided. {self.decided_line(event)}')
            return
        if verb == 'approve':
            await self.decide(interaction, event_id, 'approved')
        else:
            await interaction.response.send_modal(RejectModal(self, event_id))

    async def decide(self, interaction: discord.Interaction, event_id: int, status: str,
                     reason: Optional[str] = None) -> None:
        done = await self.store.decide(event_id, status=status, moderator_id=interaction.user.id, reason=reason)
        event = await self.store.get(event_id)
        if not done:
            text = f'Already decided. {self.decided_line(event)}' if event else f'Event #{event_id} no longer exists.'
            await self._reply(interaction, text)
            return
        EVENTS_DECISIONS.labels(decision=status).inc()
        EVENTS_PENDING.set(await self.store.pending_count(event['guild_id']))
        logger.info('Event #%d %s by %s%s', event_id, status, interaction.user.id,
                    f': {reason}' if reason else '')
        await self.refresh_card(event)
        await self._reply(interaction, f"#{event_id} {event['title']} {status}.")

    def parse_edit(self, *, title: str, dates: str, location: str, url: str, notes: str) -> dict:
        title = (title or '').strip()
        if not title:
            raise ValueError('A title is required.')
        start, end = parse_dates_field(dates)
        city, region_code, country_code, scope = parse_location_field(location, self.regions)
        url = (url or '').strip() or None
        if url and not url.lower().startswith(('http://', 'https://')):
            raise ValueError('The url must start with http:// or https://.')
        return {
            'title': title, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'city': city, 'region_code': region_code, 'country_code': country_code, 'scope': scope,
            'url': url, 'notes': (notes or '').strip() or None,
        }

    SCHEDULE_FIELDS = ('start_date', 'end_date', 'city', 'region_code', 'country_code')

    async def apply_edit(self, interaction: discord.Interaction, event_id: int, changes: dict) -> None:
        before = await self.store.get(event_id)
        if before is None:
            await self._reply(interaction, f'Event #{event_id} no longer exists.')
            return
        after = await self.store.update(event_id, changes, actor_id=interaction.user.id)
        await self.refresh_card(after)
        logger.info('Event #%d edited by %s: %s', event_id, interaction.user.id, sorted(changes))
        await self._reply(interaction, f"#{event_id} {after['title']} updated.")
        schedule_changed = any(before[k] != after[k] for k in self.SCHEDULE_FIELDS)
        if after['status'] == 'approved' and schedule_changed and await self.store.dated_reminder_sent(event_id):
            await self.notify(after, 'changed', changed=True)

    # -- posting ---------------------------------------------------------------

    def resolve_roles(self, guild, names: list) -> tuple[list, list]:
        """(roles found, names missing). Missing names are warned once per
        role per local day: the fix is a moderator creating the role, and
        the log should not scream every run."""
        by_name = {r.name: r for r in getattr(guild, 'roles', [])}
        roles, missing = [], []
        for name in names:
            if name in by_name:
                roles.append(by_name[name])
            else:
                missing.append(name)
                today = self.today()
                if self._warned_roles.get(name) != today:
                    self._warned_roles[name] = today
                    logger.warning('Events: role %r does not exist in guild %s; mentioning by name only',
                                   name, getattr(guild, 'id', None))
        return roles, missing

    async def notify(self, event: dict, window: str, *, changed: bool = False) -> bool:
        """Post one member-facing notice for (event, window), once ever.
        True when it went out (or was logged in dry run)."""
        days = days_until(event['start_date'], self.today())
        names = role_names_for(event, self.regions)
        guild = self.bot.get_guild(event['guild_id'])
        roles, missing = self.resolve_roles(guild, names)
        if self.cfg.dry_run:
            logger.info('DRY RUN events reminder: #%d %s window=%s roles=%s missing=%s',
                        event['id'], event['title'], window, [r.name for r in roles], missing)
            return True
        reminder_id = await self.store.claim_reminder(event['id'], window, self.cfg.channel_id)
        if reminder_id is None:
            return False
        channel = await self._channel(self.cfg.channel_id)
        if channel is None:
            await self.store.release_reminder(reminder_id)
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: channel %s not found; reminder #%d/%s not sent',
                         self.cfg.channel_id, event['id'], window)
            return False
        try:
            message = await channel.send(
                cards.reminder_text(event, [r.mention for r in roles], missing),
                embed=cards.reminder_embed(event, self.regions, days, changed=changed),
                allowed_mentions=cards.allowed_mentions(roles))
        except discord.HTTPException as e:
            await self.store.release_reminder(reminder_id)
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: reminder #%d/%s failed: %s', event['id'], window, e)
            return False
        await self.store.mark_reminder_sent(reminder_id, message.id, ', '.join(names))
        EVENTS_REMINDERS.labels(window=window).inc()
        for name in missing:
            EVENTS_ROLE_MISSING.labels(role=name).inc()
        logger.info('Events: reminder #%d/%s posted (%s)', event['id'], window, ', '.join(names) or 'no roles')
        return True

    # -- mod commands ----------------------------------------------------------

    @events.command(name='pending', description='Submissions waiting for review')
    @app_commands.describe(repost='Post review cards again for any whose card is gone')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_pending(self, interaction: discord.Interaction, repost: bool = False):
        if await self._refuse_if_off(interaction):
            return
        rows = await self.store.list_pending(interaction.guild_id)
        if not rows:
            await interaction.response.send_message('Nothing is waiting for review.', ephemeral=True)
            return
        lines = [f"#{r['id']} {r['title']} ({r['start_date']}) from <@{r['submitted_by']}>"
                 if r['submitted_by'] else f"#{r['id']} {r['title']} ({r['start_date']}), {r['provenance']}"
                 for r in rows]
        await interaction.response.send_message('\n'.join(lines), ephemeral=True,
                                                allowed_mentions=cards.allowed_mentions([]))
        if not repost:
            return
        channel = await self._channel(self.cfg.review_channel_id)
        reposted = 0
        for row in rows:
            present = False
            if channel is not None and row.get('review_message_id'):
                try:
                    await channel.fetch_message(row['review_message_id'])
                    present = True
                except discord.HTTPException:
                    present = False
            if present:
                continue
            message_id = await self.post_review_card(row)
            if message_id:
                await self.store.set_review_message(row['id'], message_id)
                reposted += 1
        await interaction.followup.send(f'Reposted {reposted} review card(s).', ephemeral=True)

    @events.command(name='approve', description='Approve a pending event by id')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_approve(self, interaction: discord.Interaction, event_id: int):
        if await self._refuse_if_off(interaction):
            return
        await self.decide(interaction, event_id, 'approved')

    @events.command(name='reject', description='Reject a pending event by id')
    @app_commands.describe(reason='The submitter sees this')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_reject(self, interaction: discord.Interaction, event_id: int,
                            reason: app_commands.Range[str, 1, 200]):
        if await self._refuse_if_off(interaction):
            return
        await self.decide(interaction, event_id, 'rejected', reason=reason.strip())

    @events.command(name='edit', description='Edit an event (any status)')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_edit(self, interaction: discord.Interaction, event_id: int):
        if await self._refuse_if_off(interaction):
            return
        event = await self.store.get(event_id)
        if event is None or event['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(f'No event #{event_id} here.', ephemeral=True)
            return
        await interaction.response.send_modal(EditModal(self, event))

    @events.command(name='cancel', description='Cancel an approved event')
    @app_commands.describe(reason='Shown in the cancellation notice')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_cancel(self, interaction: discord.Interaction, event_id: int,
                            reason: app_commands.Range[str, 1, 200]):
        if await self._refuse_if_off(interaction):
            return
        announced = await self.store.dated_reminder_sent(event_id)
        done = await self.store.cancel(event_id, moderator_id=interaction.user.id, reason=reason.strip())
        if not done:
            await interaction.response.send_message(
                f'#{event_id} is not an approved event, so there is nothing to cancel.', ephemeral=True)
            return
        event = await self.store.get(event_id)
        EVENTS_DECISIONS.labels(decision='cancelled').inc()
        await self.refresh_card(event)
        await interaction.response.send_message(f"#{event_id} {event['title']} cancelled.", ephemeral=True)
        if announced:
            await self.notify(event, 'cancelled')

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        logger.exception('Events command failed: %s', error)
        try:
            await self._reply(interaction, 'That did not work; the error is in the log.')
        except discord.HTTPException:
            pass
```

`interaction.guild_id` scoping: `events_approve`, `events_reject` and `events_cancel` act on the id alone. `store.get` returns rows from any guild; add a guild check identical to the one in `events_edit` at the top of each (fetch the row, compare `guild_id`, reply `No event #N here.`) so a moderator in one guild cannot decide another guild's rows. Include it in all three.

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_logic.py tests/unit/test_events_cog.py tests/unit/test_cog_loading.py -q -p no:cacheprovider`
Expected: all pass.

`test_edit_modal_applies_changes_and_keeps_status` passes `Cincinnati, US-OH, national` and expects scope `national`; `test_notify_posts_with_role_mentions_only` expects mentions `<@&100> <@&103>` because `make_guild` numbers roles from 100 in `ROLE_NAMES` order (Cybersecurity Events = 100, Michigan = 103).

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check penguin-overlord/cogs/events.py penguin-overlord/utils tests/unit/test_events_cog.py
git add penguin-overlord/cogs/events.py penguin-overlord/utils/events_logic.py tests/unit/test_events_logic.py tests/unit/test_events_cog.py
git commit -m "feat(events): review cards, buttons, edit and reject modals, mod commands, one-shot notices

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 9: The clock loops: daily poster, Monday digest, nightly sweep, `/events status`

**Files:**
- Modify: `penguin-overlord/cogs/events.py`
- Test: `tests/unit/test_events_cog.py` (append)

**Interfaces:**
- Consumes: `notify` (Task 8), `approved_between`, `retire_ended`, `has_rollover`, `expire_pending`, `purge_rejected`, `counts` (Task 5), `due_window`, `days_until`, `next_annual_dates`, `fingerprint`, `local_today` (Task 2), `cards.digest_embed` (Task 6), `EVENT_COLUMNS` (Task 1), `database.aiosqlite.IntegrityError`.
- Produces on `Events`: loops `poster` and `sweeper` (`discord.ext.tasks.Loop`, built in `__init__`, started in `cog_load` only when enabled, cancelled in `cog_unload`); seams `run_poster(today=None) -> int`, `run_digest(today=None) -> bool`, `run_sweep(today=None, now=None) -> dict` (keys `retired`, `rolled`, `expired`, `purged`); command `events_status`.
- Constants: `SWEEP_AT = (3, 0)`, `DIGEST_DAYS = 30`, `REJECTED_KEEP_DAYS = 180`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_events_cog.py`)

```python
# -- the loops ----------------------------------------------------------------

import asyncio  # noqa: E402
import datetime as dt  # noqa: E402

from discord.ext import commands  # noqa: E402


def _freeze(cog, y, m, d):
    cog.today = lambda: dt.date(y, m, d)


async def test_poster_fires_each_window_once(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')            # 2026-09-24
    _freeze(cog, 2026, 8, 25)                                                # 30 days out
    assert await cog.run_poster() == 1
    assert await cog.run_poster() == 0                                       # same day again: nothing
    _freeze(cog, 2026, 8, 26)
    assert await cog.run_poster() == 0                                       # 29 days: no window
    _freeze(cog, 2026, 9, 17)
    assert await cog.run_poster() == 1                                       # 7
    _freeze(cog, 2026, 9, 23)
    assert await cog.run_poster() == 1                                       # 1
    windows = [p.embed.title for p in channels[5000].sent]
    assert windows == ['GrrCON in 30 days', 'GrrCON in 7 days', 'GrrCON tomorrow']


async def test_poster_skips_pending_and_cancelled_rows(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(status='pending', submitted_by=42), actor_id=42, action='submit')
    await cog.store.insert(event(title='Gone', fingerprint='gone:2026', status='cancelled'),
                           actor_id=0, action='import')
    _freeze(cog, 2026, 8, 25)
    assert await cog.run_poster() == 0 and channels[5000].sent == []


async def test_poster_after_a_missed_day_does_not_backfill(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 8, 27)                                                # 28 days: the 30 was missed
    assert await cog.run_poster() == 0


async def test_monday_digest_goes_out_without_mentions(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 9, 7)                                                 # a Monday, 17 days out
    await cog.run_poster()
    digest = [p for p in channels[5000].sent if p.embed.title == 'This month in events']
    assert len(digest) == 1
    assert digest[0].allowed_mentions.roles == [] and digest[0].content is None
    assert 'GrrCON' in digest[0].embed.description


async def test_digest_respects_the_flag_and_the_weekday(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 9, 8)                                                 # Tuesday
    await cog.run_poster()
    assert channels[5000].sent == []
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'digest_enabled': False})
    _freeze(cog, 2026, 9, 7)
    await cog.run_poster()
    assert channels[5000].sent == []


async def test_sweep_retires_rolls_over_and_posts_a_card(cog):
    guild, channels = wire(cog)
    old = await cog.store.insert(event(start_date='2026-05-30', end_date='2026-05-30'),
                                 actor_id=0, action='import')
    once = await cog.store.insert(event(title='One off', fingerprint='one off:2026', recurrence='none',
                                        start_date='2026-06-01', end_date='2026-06-01'),
                                  actor_id=0, action='import')
    result = await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert result['retired'] == 2 and result['rolled'] == 1
    assert (await cog.store.get(old))['status'] == 'retired'
    assert (await cog.store.get(once))['status'] == 'retired'
    child = await cog.store.find_fingerprint(GUILD, 'grrcon:2027')
    assert child['start_date'] == '2027-05-29' and child['date_status'] == 'estimated'
    assert child['status'] == 'pending' and child['provenance'] == 'rollover'
    assert child['parent_event_id'] == old and child['submitted_by'] is None
    card = channels[6000].sent[0]
    assert f'Rolled over from #{old}' in card.embed.description
    assert child['review_message_id'] == card.id
    # a second sweep does not roll the same parent again
    again = await cog.run_sweep(today=dt.date(2026, 9, 4))
    assert again['rolled'] == 0


async def test_sweep_rollover_collision_is_skipped(cog):
    wire(cog)
    old = await cog.store.insert(event(start_date='2026-05-30', end_date='2026-05-30'),
                                 actor_id=0, action='import')
    await cog.store.insert(event(title='GrrCON', fingerprint='grrcon:2027', start_date='2027-05-29',
                                 end_date='2027-05-29'), actor_id=0, action='import')  # already listed
    result = await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert result['rolled'] == 0 and (await cog.store.get(old))['status'] == 'retired'


async def test_sweep_expires_stale_pending_and_purges_old_rejected(cog):
    guild, channels = wire(cog)
    await submit(cog)                                                        # pending, created now
    now = dt.datetime.now(dt.timezone.utc)
    result = await cog.run_sweep(today=dt.date(2026, 9, 3), now=now)
    assert result['expired'] == 0
    result = await cog.run_sweep(today=dt.date(2026, 9, 3), now=now + dt.timedelta(days=31))
    assert result['expired'] == 1
    row = await cog.store.get(1)
    assert row['status'] == 'rejected' and row['reject_reason'] == 'expired'
    edit = channels[6000].messages[channels[6000].sent[0].id].edits[-1]
    assert edit.view is None and 'the sweep' in edit.embed.footer.text
    result = await cog.run_sweep(today=dt.date(2026, 9, 3), now=now + dt.timedelta(days=31 + 181))
    assert result['purged'] == 1 and await cog.store.get(1) is None


async def test_status_reports_flags_counts_and_missing_roles(cog):
    guild, channels = wire(cog, guild=make_guild(('Cybersecurity Events', 'Michigan')))
    await cog.store.insert(event(), actor_id=0, action='import')
    await submit(cog)
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    text = i.response.sent[0].content
    assert 'dry run: off' in text and 'approved: 1' in text and 'pending: 1' in text
    assert '09:00 America/New_York' in text and '30, 7, 1' in text
    # needed = 3 topic roles + 64 regions + 24 countries = 91; the guild has 2
    assert 'missing roles: 89' in text
    assert 'role mentions: allowed' in text
    assert i.response.sent[0].ephemeral


async def test_status_flags_a_channel_where_the_bot_cannot_mention_roles(cog):
    guild, channels = wire(cog, channels={5000: FakeChannel(5000, fail=True), 6000: FakeChannel(6000)})
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    assert 'role mentions: BLOCKED' in i.response.sent[0].content


async def test_enabled_cog_starts_and_stops_its_loops_on_a_real_bot(tmp_data_dir, monkeypatch):
    monkeypatch.setenv('EVENTS_ENABLED', 'true')
    monkeypatch.setenv('EVENTS_CHANNEL_ID', '5000')
    database.reset_database()
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.default())

    async def parked():
        await asyncio.Event().wait()
    bot.wait_until_ready = parked
    try:
        await bot.load_extension('cogs.events')
        c = bot.get_cog('Events')
        assert c.poster.is_running() and c.sweeper.is_running()
        assert c.poster.time[0].hour == 9 and c.sweeper.time[0].hour == 3
        await bot.unload_extension('cogs.events')
        assert not c.poster.is_running() and not c.sweeper.is_running()
        await c.store.db.close()
    finally:
        await bot.close()
        database.reset_database()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_cog.py -q -p no:cacheprovider -k "poster or digest or sweep or status or loops"`
Expected: `AttributeError: 'Events' object has no attribute 'run_poster'` and friends.

- [ ] **Step 3: Add the loops**

Imports at the top of `cogs/events.py`:

```python
from datetime import date, datetime, timedelta
from discord.ext import commands, tasks
from utils import database
from utils.events_logic import (..., due_window, fingerprint, next_annual_dates, ...)
from utils.events_store import EVENT_COLUMNS, EventsStore
```

Constants after `TOPIC_CHOICES`:

```python
SWEEP_AT = (3, 0)
DIGEST_DAYS = 30
REJECTED_KEEP_DAYS = 180
```

In `Events.__init__`, after `self.regions = load_regions()`:

```python
        tz = ZoneInfo(self.cfg.timezone)
        self.poster = tasks.loop(time=datetime_time(*self.cfg.post_at, tzinfo=tz))(self._poster_tick)
        self.sweeper = tasks.loop(time=datetime_time(*SWEEP_AT, tzinfo=tz))(self._sweep_tick)
        self.poster.before_loop(self._wait_ready)
        self.sweeper.before_loop(self._wait_ready)
```

with `from datetime import time as datetime_time` added to the imports (the cog already uses `time`-free names; the alias keeps `datetime.time` from shadowing anything).

`cog_load`, after `self.bot.add_dynamic_items(EventButton)`:

```python
        self.poster.start()
        self.sweeper.start()
```

and add:

```python
    async def cog_unload(self):
        self.poster.cancel()
        self.sweeper.cancel()

    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    async def _poster_tick(self):
        try:
            await self.run_poster()
        except Exception:
            logger.exception('Events poster failed')

    async def _sweep_tick(self):
        try:
            await self.run_sweep()
        except Exception:
            logger.exception('Events sweep failed')
```

Then the seams (after `notify`):

```python
    # -- scheduled work ----------------------------------------------------------

    async def run_poster(self, today: Optional[date] = None) -> int:
        """Post every reminder whose window lands today. No backfill: a
        window missed while the bot was down stays missed, on purpose."""
        today = today or self.today()
        horizon = today + timedelta(days=max(self.cfg.reminder_days))
        posted = 0
        for event in await self.store.approved_between(today.isoformat(), horizon.isoformat()):
            window = due_window(days_until(event['start_date'], today), self.cfg.reminder_days)
            if window and await self.notify(event, window):
                posted += 1
        logger.info('Events poster: %d reminder(s) for %s', posted, today)
        if self.cfg.digest_enabled and today.weekday() == 0:
            await self.run_digest(today)
        return posted

    async def run_digest(self, today: Optional[date] = None) -> bool:
        today = today or self.today()
        rows = await self.store.approved_between(today.isoformat(),
                                                 (today + timedelta(days=DIGEST_DAYS)).isoformat())
        embed = cards.digest_embed(rows, self.regions, today=today.isoformat())
        if self.cfg.dry_run:
            logger.info('DRY RUN events digest: %d event(s)', len(rows))
            return True
        channel = await self._channel(self.cfg.channel_id)
        if channel is None:
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: channel %s not found; digest not sent', self.cfg.channel_id)
            return False
        try:
            await channel.send(embed=embed, allowed_mentions=cards.allowed_mentions([]))
        except discord.HTTPException as e:
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: digest failed: %s', e)
            return False
        logger.info('Events digest posted: %d event(s)', len(rows))
        return True

    def _rollover_row(self, parent: dict) -> dict:
        start, end = next_annual_dates(date.fromisoformat(parent['start_date']),
                                       date.fromisoformat(parent['end_date']))
        child = {col: parent.get(col) for col in EVENT_COLUMNS}
        child.update({
            'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'fingerprint': fingerprint(parent['title'], start), 'date_status': 'estimated',
            'status': 'pending', 'provenance': 'rollover', 'parent_event_id': parent['id'],
            'submitted_by': None, 'review_message_id': None, 'decided_by': None, 'decided_at': None,
            'reject_reason': None, 'last_verified_at': None,
        })
        return child

    async def run_sweep(self, today: Optional[date] = None, now: Optional[datetime] = None) -> dict:
        """Nightly: retire ended events, roll annual ones into next year's
        pending row, expire stale submissions, purge old rejections."""
        today = today or self.today()
        now = now or datetime.now(ZoneInfo('UTC'))
        retired = await self.store.retire_ended(today.isoformat())
        rolled = 0
        for row in retired:
            if row['recurrence'] != 'annual' or row['status'] != 'approved':
                continue
            if await self.store.has_rollover(row['id']):
                continue
            child = self._rollover_row(row)
            try:
                child_id = await self.store.insert(child, actor_id=0, action='rollover')
            except database.aiosqlite.IntegrityError:
                logger.info('Events: rollover of #%d skipped, %s already listed', row['id'], child['fingerprint'])
                continue
            EVENTS_SUBMISSIONS.labels(provenance='rollover').inc()
            event = await self.store.get(child_id)
            message_id = await self.post_review_card(event)
            if message_id:
                await self.store.set_review_message(child_id, message_id)
            rolled += 1
        expired_ids = await self.store.expire_pending(
            (now - timedelta(days=self.cfg.pending_expire_days)).isoformat())
        for event_id in expired_ids:
            EVENTS_DECISIONS.labels(decision='expired').inc()
            await self.refresh_card(await self.store.get(event_id))
        purged = await self.store.purge_rejected((now - timedelta(days=REJECTED_KEEP_DAYS)).isoformat())
        result = {'retired': len(retired), 'rolled': rolled, 'expired': len(expired_ids), 'purged': purged}
        logger.info('Events sweep for %s: %s', today, result)
        return result
```

And the status command (with the other mod commands):

```python
    @events.command(name='status', description='Events system health')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_status(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        counts = await self.store.counts(interaction.guild_id)
        needed = set(TOPIC_ROLES.values()) | set(self.regions.regions.values()) | set(self.regions.countries.values())
        have = {r.name for r in interaction.guild.roles}
        missing = sorted(needed - have)
        next_post = self.poster.next_iteration
        next_sweep = self.sweeper.next_iteration
        channel = await self._channel(self.cfg.channel_id)
        can_mention = bool(channel) and channel.permissions_for(interaction.guild.me).mention_everyone
        lines = [
            f"dry run: {'on' if self.cfg.dry_run else 'off'}; channel <#{self.cfg.channel_id}>; "
            f"review <#{self.cfg.review_channel_id}>",
            f"posts at {self.cfg.post_at[0]:02d}:{self.cfg.post_at[1]:02d} {self.cfg.timezone}; "
            f"reminders {', '.join(str(d) for d in self.cfg.reminder_days)} days out; "
            f"digest {'on' if self.cfg.digest_enabled else 'off'}",
            'counts: ' + (', '.join(f'{k}: {v}' for k, v in sorted(counts.items())) or 'no events yet'),
            f"next post: {self._local(next_post.isoformat()) if next_post else 'loop not running'}; "
            f"next sweep: {self._local(next_sweep.isoformat()) if next_sweep else 'loop not running'}",
            f"missing roles: {len(missing)}" + (f" ({', '.join(missing[:8])}{', ...' if len(missing) > 8 else ''})"
                                                 if missing else ''),
            'role mentions: ' + ('allowed' if can_mention else 'BLOCKED, grant Mention @everyone, @here and All Roles '
                                                              'in the events channel'),
        ]
        await interaction.response.send_message('\n'.join(lines), ephemeral=True)
```

`TOPIC_ROLES` joins the `events_logic` import list.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_cog.py tests/unit/test_cog_loading.py -q -p no:cacheprovider`
Expected: all pass. If `test_status_reports_flags_counts_and_missing_roles` is off by a few, recount: `len(TOPIC_ROLES) + len(regions.regions) + len(regions.countries) - 2` against the shipped `regions.json`.

`test_enabled_cog_starts_and_stops_its_loops_on_a_real_bot` exercises `Loop.time`: discord.py stores the `time=` argument as a list of `datetime.time`, hence `c.poster.time[0].hour`.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check penguin-overlord/cogs/events.py tests/unit/test_events_cog.py
git add penguin-overlord/cogs/events.py tests/unit/test_events_cog.py
git commit -m "feat(events): daily poster, Monday digest, nightly sweep with annual rollover, /events status

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 10: The one-time CSV import script

**Files:**
- Create: `scripts/import-events-csv.py`
- Test: `tests/unit/test_events_import.py`

**Interfaces:**
- Consumes: `csv_row_to_event(row, guild_id)` (Task 3), `EventsStore.insert/find_fingerprint/audit` (Tasks 1, 5), `database.get_database()`; the database path comes from `BOT_DATABASE_PATH` or `DATA_DIR`, exactly as the bot resolves it.
- Produces: `import_csv(guild_id: int, csv_path: Path) -> tuple[int, int]` (inserted, skipped) importable from the script module; CLI `python scripts/import-events-csv.py --guild <id> --csv events/security_and_ham_events_2026_with_types.csv`.

The script is hermetic by construction: it never loads `.env`, never imports the bot, and only touches the database the environment points it at. Run it on the box with the bot stopped (the deploy notes in Task 11 say so).

- [ ] **Step 1: Write the failing test**

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The calendar import: the 29 shipped rows land as approved annual
events, and running it twice changes nothing."""

import importlib.util
import json
from pathlib import Path

import pytest

from utils import database
from utils.events_store import EventsStore

REPO = Path(__file__).resolve().parents[2]
CSV = REPO / 'events' / 'security_and_ham_events_2026_with_types.csv'


def _load_script():
    spec = importlib.util.spec_from_file_location('import_events_csv', REPO / 'scripts' / 'import-events-csv.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def store(tmp_data_dir):
    database.reset_database()
    db = await database.get_database()
    yield EventsStore(db)
    await db.close()
    database.reset_database()


async def test_import_lands_every_row_as_approved_calendar_annual(store):
    script = _load_script()
    inserted, skipped = await script.import_csv(1, CSV)
    assert (inserted, skipped) == (29, 0)
    rows = await store.list_upcoming(1, today='2026-01-01', days=400)
    assert len(rows) == 29
    assert {r['status'] for r in rows} == {'approved'}
    assert {r['provenance'] for r in rows} == {'calendar'}
    assert {r['recurrence'] for r in rows} == {'annual'}
    assert {r['decided_by'] for r in rows} == {0}
    by_title = {r['title']: r for r in rows}
    defcon = by_title['DEF CON 34']
    assert defcon['scope'] == 'national' and defcon['region_code'] == 'US-NV'
    ottawa = by_title['Ottawa Amateur Radio Club Hamfest 2026']
    assert ottawa['region_code'] == 'CA-ON' and ottawa['country_code'] == 'CA' and ottawa['topic'] == 'ham'
    warren = by_title['Warren Hamfest 2026']
    assert warren['end_date'] == warren['start_date'] == '2026-08-16'
    assert sum(r['topic'] == 'cyber' for r in rows) == 16
    assert sum(r['date_status'] == 'estimated' for r in rows) == 10
    assert all(r['scope'] == 'regional' for r in rows if r['title'] != 'DEF CON 34')


async def test_import_is_idempotent_and_leaves_an_audit_row(store):
    script = _load_script()
    await script.import_csv(1, CSV)
    assert await script.import_csv(1, CSV) == (0, 29)
    cursor = await store.db.conn.execute(
        "SELECT after_json FROM event_audit WHERE event_id = 0 AND action = 'import' ORDER BY id")
    runs = [json.loads(r[0]) for r in await cursor.fetchall()]
    assert [(r['inserted'], r['skipped']) for r in runs] == [(29, 0), (0, 29)]
    cursor = await store.db.conn.execute('SELECT COUNT(*) FROM events')
    assert (await cursor.fetchone())[0] == 29


async def test_import_reuses_the_bots_database_singleton(store):
    """The script opens whatever get_database() points at, which the
    fixture has pinned to the temp DATA_DIR; nothing else on disk is
    touched."""
    script = _load_script()
    await script.import_csv(1, CSV)
    assert Path(store.db.path).parent.name == 'data'
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/unit/test_events_import.py -q -p no:cacheprovider`
Expected: `FileNotFoundError` for `scripts/import-events-csv.py`.

- [ ] **Step 3: Write the script**

```python
#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One-time import of the old events/*.csv calendar into the events table.

    python scripts/import-events-csv.py --guild 123456789012345678 \
        --csv events/security_and_ham_events_2026_with_types.csv

Every row becomes an approved, annual, calendar-provenance event decided
by actor 0. Rows whose (guild, fingerprint) already exist are skipped, so
running it again is harmless. Uses the same database the bot does
(BOT_DATABASE_PATH, else DATA_DIR/penguin_overlord.db); stop the bot first
so the two do not share the file. Does not read .env and never talks to
Discord.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

from utils import database  # noqa: E402
from utils.events_logic import csv_row_to_event  # noqa: E402
from utils.events_store import EventsStore  # noqa: E402


async def import_csv(guild_id: int, csv_path: Path) -> tuple[int, int]:
    db = await database.get_database()
    store = EventsStore(db)
    inserted = skipped = 0
    with csv_path.open(newline='', encoding='utf-8') as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            try:
                event = csv_row_to_event(row, guild_id)
            except (KeyError, ValueError) as e:
                raise SystemExit(f'{csv_path.name} line {line}: {e}') from None
            if await store.find_fingerprint(guild_id, event['fingerprint']):
                skipped += 1
                continue
            await store.insert(event, actor_id=0, action='import')
            inserted += 1
    # One trail row for the run itself, under the reserved event id 0.
    await store.audit(0, 0, 'import', None,
                      {'file': csv_path.name, 'guild_id': guild_id, 'inserted': inserted, 'skipped': skipped})
    return inserted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--guild', type=int, required=True, help='guild id the events belong to')
    parser.add_argument('--csv', type=Path, required=True, help='path to the calendar CSV')
    args = parser.parse_args()
    if not args.csv.is_file():
        print(f'FAIL: {args.csv} is not a file', file=sys.stderr)
        return 1
    inserted, skipped = asyncio.run(_run(args.guild, args.csv))
    print(f'OK: inserted {inserted}, skipped {skipped} (already present)')
    return 0


async def _run(guild_id: int, csv_path: Path) -> tuple[int, int]:
    try:
        return await import_csv(guild_id, csv_path)
    finally:
        db = await database.get_database()
        await db.close()


if __name__ == '__main__':
    sys.exit(main())
```

`chmod +x scripts/import-events-csv.py`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/unit/test_events_import.py -q -p no:cacheprovider`
Expected: all pass. If the first test's `list_upcoming` returns fewer than 29 rows, the window is the problem, not the import: `today='2026-01-01', days=400` must cover every 2026 start date.

- [ ] **Step 5: Commit**

```bash
git add scripts/import-events-csv.py tests/unit/test_events_import.py
git commit -m "feat(events): idempotent CSV import script for the old calendar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 11: Cutover: build files, docs, env template

**Files:**
- Modify: `Dockerfile:66-69`
- Modify: `docker-compose.yml:30-31`
- Modify: `README.md:237-246`, `README.md:284-289`, `README.md:428`, `README.md:436`, `README.md:510`, `README.md:515`, `README.md:525`, `README.md:531`
- Modify: `docs/reference/COMMANDS.md:189-199`
- Modify: `QUICK_REFERENCE.md:47`
- Modify: `docs/ROADMAP.md:27`, `docs/ROADMAP.md:54`
- Modify: `docs/features/ROLE_PICKER.md:84-85`
- Create: `docs/features/EVENTS.md`
- Modify: `.env.example` (append only, see Step 8)
- Test: `tests/unit/test_help_pages.py` and `tests/unit/test_cog_imports.py` already cover the code side; this task has a doc-consistency check in Step 9.

**Interfaces:**
- Consumes: the command names, env names and behaviours defined in Tasks 4, 7, 8, 9, 10. Nothing later depends on this task.

No em dashes anywhere in this task's text. Line numbers are from the tree at plan time; find the quoted text if they drifted.

- [ ] **Step 1: Dockerfile**

Replace lines 66-69 (the three `COPY --chown` lines after `# Copy application code`) with:

```dockerfile
COPY --chown=penguin:penguin penguin-overlord/ ./penguin-overlord/
COPY --chown=penguin:penguin events/ ./events/
COPY --chown=penguin:penguin .env.example ./.env.example
COPY --chown=penguin:penguin scripts/healthcheck.py ./scripts/healthcheck.py
COPY --chown=penguin:penguin scripts/import-events-csv.py ./scripts/import-events-csv.py
```

The CSV stays in the image so the one-time import can run from the container; the bot itself no longer reads it.

- [ ] **Step 2: docker-compose.yml**

Delete the line `      - ./events:/app/events:ro` under `volumes:` (line 31). Leave the `penguin-data` mount alone.

- [ ] **Step 3: README.md**

Replace the `### �📅 Event Pinger` block (lines 237-246, through `- 📻 HAM radio events (...)`) with:

```markdown
### 📅 Events
A crowd-sourced calendar of cyber, ham, and FOSS events with a moderator
approval queue. Members opt in by topic and region through the role picker
and get channel reminders 30, 7, and 1 days out that tag those roles.
- `/events list [topic] [where] [page]` - the year ahead, filtered
- `/events next` - the next 30 days
- `/events search <query>` - by title or city
- `/events submit` - propose one; moderators approve it from a review card
- `/events mine` - your submissions and their status

See **[Events Guide](docs/features/EVENTS.md)** for setup, moderation, and the one-time import.
```

Replace the `docker run` block (lines 284-289) with:

```bash
docker run -d --name penguin-overlord \
  --env-file .env \
  -v penguin-data:/app/data \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

Line 428: change `fortune.py, manpage.py, patchgremlin.py, eventpinger.py` to `fortune.py, manpage.py, patchgremlin.py, events.py`.

Line 436: change `├── events/                     # Event CSV (until the events database lands)` to `├── events/                     # Seed CSV for the one-time events import`.

Line 510: change `(quotes, events, help)` to `(quotes, help)`.

Line 515: replace `- ✅ **Event reminder system** (29 events, CSV-based)` with `- ✅ **Events calendar**: member submissions, moderator review cards, reminders that tag the picker roles, Monday digest ([guide](docs/features/EVENTS.md))`.

Line 531: delete `- 🔲 Events database with a mod approval queue, member filters, and reminders that tag the picker roles (replaces the CSV)` and add in its place `- 🔲 Events phase 2: Gemini-backed date verification and discovery of new events (spec section 10)`.

- [ ] **Step 4: docs/reference/COMMANDS.md**

Replace lines 189-199 (`## Events (hybrid, everyone)` through the `searchevent` row) with:

```markdown
## Events (slash only)

Backed by the events table; see [EVENTS.md](../features/EVENTS.md).
Reminders tag the picker roles for the event's topic, region and country.

| Command | Arguments | What it does | Who |
| --- | --- | --- | --- |
| `/events list [topic] [where] [page]` | topic: cyber, ham, foss, other; where: a state, province, country or Online | Approved events in the next year, five per page. | everyone |
| `/events next` | | The next 30 days. | everyone |
| `/events search <query>` | title or city | Search approved events. | everyone |
| `/events submit <title> <topic> <start> <city> <where> [end] [url] [notes] [national]` | dates as YYYY-MM-DD | Propose an event; it lands in the review queue. Up to three open submissions per member. | everyone |
| `/events mine` | | Your submissions and their status. | everyone |
| `/events pending [repost]` | repost: re-send the review cards | The review queue. | moderators |
| `/events approve <id>`, `/events reject <id> <reason>` | | Decide a pending event (the card's buttons do the same). | moderators |
| `/events edit <id>` | | Open the edit modal for any live event. | moderators |
| `/events cancel <id> <reason>` | | Cancel an approved event; members who were told about it get one notice. | moderators |
| `/events status` | | Config, counts, next post and sweep, missing roles. | moderators |
```

Also on line 27 the help description still says `Events`: leave it, the page still exists.

- [ ] **Step 5: QUICK_REFERENCE.md**

Line 47: replace `| `/events`, `/nextevent` | Upcoming cyber and ham events |` with `| `/events next`, `/events submit` | Upcoming events; propose one for review |`.

- [ ] **Step 6: docs/ROADMAP.md and docs/features/ROLE_PICKER.md**

ROADMAP line 27, the events row: change the status cell (third column) to `Sub-project 2. Phase 1 shipped (no AI): schema v3, /events, review cards, poster, digest, sweep, CSV import; eventpinger.py deleted. Phase 2 adds the Gemini key pool, verify and discovery. Later tracks (DEF CON track, DC Groups directory, static search site, onboarding, LinkShield replacement) are section 15 of the spec.`

ROADMAP line 54: change `3. **Events database** (above), then delete `eventpinger.py`.` to `3. **Events database phase 2** (Gemini verify and discovery; phase 1 shipped).`

ROLE_PICKER.md lines 84-85: replace the two-line bullet starting `- The events system treats every region role` with:

```markdown
- The events system treats every region role a member holds as a place
  they want pings for; there is no separate "home" role. Topic opt-in is
  the fourth panel, `event_topics` (Cyber, Ham, FOSS), posted the same way.
```

- [ ] **Step 7: docs/features/EVENTS.md**

```markdown
# Events calendar

Crowd-sourced conferences, hamfests and meetups with a moderator approval
queue. Phase 1 of `docs/superpowers/specs/2026-09-03-conference-database-design.md`:
no AI, no external lookups. Members propose, moderators approve, the bot
reminds the roles that opted in.

## How it works

- **Submit.** `/events submit` takes a title, topic (cyber, ham, foss,
  other), start date, city, a place from the autocomplete list (state,
  province, country, or Online), and optionally an end date, URL, notes
  and a `national` flag for the DEF CON tier. Duplicates are caught by a
  fingerprint of the normalised title plus start date. A member can have
  three submissions open at once.
- **Review.** Every submission posts a card to the review channel
  (`EVENTS_REVIEW_CHANNEL_ID`, falling back to `MOD_ALERT_CHANNEL_ID`)
  with Approve, Reject and Edit buttons. Reject asks for a reason, which
  goes into the audit trail and is shown to the submitter under
  `/events mine`. Pending cards untouched for `EVENTS_PENDING_EXPIRE_DAYS`
  expire on their own.
- **Remind.** Each day at `EVENTS_POST_AT` (default 09:00 in
  `EVENTS_TIMEZONE`) the poster sends one message per approved event whose
  start is exactly 30, 7 or 1 days away (`EVENTS_REMINDER_DAYS`). The
  message tags the topic role plus the region and country roles the role
  picker defines, and nothing else: no `@everyone`, no individual mentions.
  Missing roles are logged once a day and counted in
  `penguin_events_role_missing_total`. A reminder that failed to send is
  retried the next day; one that was sent is never sent again.
- **Digest.** Mondays at the same time, a list of the next 30 days with no
  mentions at all (`EVENTS_DIGEST_ENABLED`).
- **Sweep.** 03:00 local nightly: ended events retire; annual ones that
  ended come back as a pending row one year later, marked estimated, for a
  moderator to confirm or reject. Expired and old rejected rows are pruned.
- **Cancel or reschedule.** `/events cancel` and the Edit button post one
  notice to the channel if the event had already been announced.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `EVENTS_ENABLED` | `false` | Load the cog and its loops. |
| `EVENTS_DRY_RUN` | `true` | Log what would be posted; send nothing, record nothing. |
| `EVENTS_CHANNEL_ID` | | Reminder and digest channel. Required when enabled. |
| `EVENTS_REVIEW_CHANNEL_ID` | `MOD_ALERT_CHANNEL_ID` | Where review cards go. |
| `EVENTS_TIMEZONE` | `America/New_York` | Local time for posts, sweeps and countdowns. |
| `EVENTS_POST_AT` | `09:00` | Daily poster and Monday digest time. |
| `EVENTS_REMINDER_DAYS` | `30,7,1` | Days-out windows. |
| `EVENTS_DIGEST_ENABLED` | `true` | Monday digest on or off. |
| `EVENTS_MAX_PENDING_PER_MEMBER` | `3` | Open submissions per member. |
| `EVENTS_PENDING_EXPIRE_DAYS` | `30` | Untouched pending rows expire after this. |

The bot needs **Mention @everyone, @here and All Roles** in the events
channel or the role tags render as plain text.

## Roles

Reminders resolve role names from `assets/events/regions.json` (regions and
countries, the same names the role picker provisions) and the topic panel
`assets/role_panels/event_topics.json`. Post the topic panel with
`/roles post event_topics`. `/events status` lists every role the guild
is missing.

## One-time import

The old CSV calendar (`events/security_and_ham_events_2026_with_types.csv`)
imports as approved annual events. Run it once with the bot stopped, against
the same data volume:

```bash
docker run --rm -e DATA_DIR=/app/data -v penguin-data:/app/data \
  ghcr.io/chiefgyk3d/penguin-overlord:latest \
  python scripts/import-events-csv.py --guild <guild id> \
    --csv events/security_and_ham_events_2026_with_types.csv
```

It prints `OK: inserted 29, skipped 0`; a second run skips all 29. Rows
whose dates have already passed retire on the first sweep and come back
as pending 2027 rows for moderators to confirm, so expect a batch of
review cards the morning after the first night.

## Rollout

1. Deploy with `EVENTS_ENABLED=true` and `EVENTS_DRY_RUN=true`, set
   `EVENTS_CHANNEL_ID`, drop the old `events/` bind mount from the service.
2. Run the import, post `event_topics`, grant the mention permission.
3. Watch the dry-run log (`DRY RUN events reminder: ...`) until the role
   names it resolves look right, then set `EVENTS_DRY_RUN=false`.

## Metrics

`penguin_events_submissions_total{provenance}`,
`penguin_events_decisions_total{decision}`,
`penguin_events_reminders_total{window}`, `penguin_events_post_errors_total`,
`penguin_events_role_missing_total{role}`, gauge `penguin_events_pending`.
```

- [ ] **Step 8: .env.example**

Reads of this file are permission-blocked in this environment; append without reading, from the repo root:

```bash
cat >> .env.example <<'EOF'

# =============================================================================
# Events calendar (docs/features/EVENTS.md)
# =============================================================================
# Crowd-sourced events with a moderator review queue. Off by default; dry
# run by default when on (logs what it would post, sends nothing).
EVENTS_ENABLED=false
EVENTS_DRY_RUN=true
# Reminder and digest channel. Required when EVENTS_ENABLED=true.
EVENTS_CHANNEL_ID=
# Review cards go here; falls back to MOD_ALERT_CHANNEL_ID.
EVENTS_REVIEW_CHANNEL_ID=
# Local time for posts, sweeps and countdowns, and the daily post time.
EVENTS_TIMEZONE=America/New_York
EVENTS_POST_AT=09:00
# Days-out reminder windows, Monday digest, per-member open submissions,
# and how long an untouched pending submission lives.
EVENTS_REMINDER_DAYS=30,7,1
EVENTS_DIGEST_ENABLED=true
EVENTS_MAX_PENDING_PER_MEMBER=3
EVENTS_PENDING_EXPIRE_DAYS=30
EOF
```

Then `grep -c "^EVENTS_" .env.example` must print `10`; if it prints `20`, the block was appended twice: `git checkout .env.example` and append once.

- [ ] **Step 9: Consistency check**

Run from the repo root:

```bash
grep -rn "eventpinger\|allevents\|nextevent\|searchevent" --include='*.py' --include='*.md' --include='*.yml' --include='Dockerfile' . | grep -v "docs/superpowers/\|\.git/"
grep -rn "—" README.md QUICK_REFERENCE.md docs/features/EVENTS.md docs/reference/COMMANDS.md .env.example || true
python3 -m pytest tests/unit/test_help_pages.py tests/unit/test_cog_imports.py -q -p no:cacheprovider
```

Expected: the first grep prints nothing (the spec and plan under `docs/superpowers/` are history and may keep the old names); the second prints nothing; the tests pass.

- [ ] **Step 10: Commit**

```bash
git add Dockerfile docker-compose.yml README.md QUICK_REFERENCE.md docs/reference/COMMANDS.md \
  docs/ROADMAP.md docs/features/ROLE_PICKER.md docs/features/EVENTS.md .env.example
git commit -m "docs(events): cut docs and build files over to the events calendar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 12: Whole-suite verification and self-review

**Files:** none new. This task gates the PR.

- [ ] **Step 1: Full suite and lint**

```bash
python3 -m pytest tests/unit -q -p no:cacheprovider
.venv/bin/ruff check penguin-overlord tests scripts
```

Expected: every test passes, ruff clean. `test_cog_loading.py` loads `cogs/events.py` into an offline Bot with `EVENTS_ENABLED` unset, so the cog must construct and `cog_load` must return quietly when disabled (Task 7 Step 3 does this). Fix failures at the root; do not skip or xfail.

- [ ] **Step 2: Hermetic check of the runner rule**

Nothing in this plan executes `bot.py`. Confirm no test or script added by Tasks 1-11 imports `bot` or calls `load_dotenv`:

```bash
grep -rn "load_dotenv\|^import bot\|from bot import" tests/unit/test_events_*.py scripts/import-events-csv.py penguin-overlord/cogs/events.py penguin-overlord/utils/events_*.py
```

Expected: nothing.

- [ ] **Step 3: Copy review**

Read every user-facing string in `cogs/events.py` and `utils/events_cards.py` once for: no em dashes, all times labelled local, no individual mentions (`allowed_mentions` roles only, `users=False`, `everyone=False`), rejection reasons never shown to anyone but moderators and the submitter.

```bash
grep -n "—" penguin-overlord/cogs/events.py penguin-overlord/utils/events_cards.py penguin-overlord/utils/events_logic.py || echo "no em dashes"
```

- [ ] **Step 4: Schema migration smoke test**

A v2 database from the deployed bot must open on v3 without touching existing tables:

```bash
python3 - <<'EOF'
import asyncio, os, sys, tempfile
sys.path.insert(0, 'penguin-overlord')
os.environ['DATA_DIR'] = tempfile.mkdtemp()
from utils import database

async def main():
    db = database.ModerationDatabase()
    await db.connect()
    cur = await db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    names = [r[0] for r in await cur.fetchall()]
    assert 'events' in names and 'event_reminders' in names and 'event_audit' in names, names
    cur = await db.conn.execute('SELECT version FROM schema_version')
    assert (await cur.fetchone())[0] == 3
    await db.close()
    # Reopen: idempotent.
    db = database.ModerationDatabase()
    await db.connect()
    await db.close()
    print('schema v3 ok')

asyncio.run(main())
EOF
```

Expected: `schema v3 ok`. The upgrade path from a real v2 file is covered by `tests/unit/test_database.py` style migration tests only if one exists for v2 to v3; `_migrate` stamps the version after the `CREATE IF NOT EXISTS` statements have already run, so a v2 file gains the tables on first connect.

- [ ] **Step 5: Push and open a draft PR**

```bash
git -c credential.helper='!gh auth git-credential' push -u origin feat/events-phase1
gh pr create --draft --base main --title "feat: events calendar phase 1 (schema v3, /events, review cards, poster, sweep, import)" --body-file - <<'EOF'
Phase 1 of docs/superpowers/specs/2026-09-03-conference-database-design.md, per docs/superpowers/plans/2026-09-03-events-phase1.md.

- Schema v3: events, event_reminders, event_audit (plus the phase 2 tables, unused)
- `/events list|next|search|submit|mine` for members; `pending|approve|reject|edit|cancel|status` for moderators
- Review cards with Approve / Reject / Edit buttons, persistent across restarts
- Daily poster (30/7/1 day reminders tagging picker roles only), Monday digest, nightly sweep with annual rollover
- `scripts/import-events-csv.py`: idempotent import of the 29-row CSV
- `cogs/eventpinger.py` deleted; `/events`, `/allevents`, `/nextevent`, `/searchevent` are gone
- New `event_topics` role panel; `assets/events/regions.json`
- Default off; dry run by default when on

Deploy notes are in docs/features/EVENTS.md (Rollout).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

The operator merges.
