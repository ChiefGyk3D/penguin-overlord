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
