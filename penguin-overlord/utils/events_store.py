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
from datetime import datetime, timedelta, timezone

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

    # -- member views -------------------------------------------------------

    async def count_open_submissions(self, guild_id: int, user_id: int) -> int:
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE guild_id = ? AND submitted_by = ? AND status = 'pending'",
            (guild_id, user_id))
        return (await cursor.fetchone())[0]

    async def list_upcoming(self, guild_id: int, *, today: str, days: int, topic=None,
                            region_code=None, country_code=None, online: bool = False) -> list[dict]:
        """Approved (and cancelled, shown struck through) events starting
        within `days` of `today`, soonest first. `online=True` restricts to
        events with no region or country code (how Online events are
        stored); it is independent of region_code/country_code."""
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
        if online:
            sql += ' AND region_code IS NULL AND country_code IS NULL'
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

    async def release_unposted_claims(self) -> int:
        """A claim with posted_at still NULL means the process died between
        claim_reminder's commit and the send that was supposed to follow it
        (every handled failure already calls release_reminder itself, so a
        survivor here is an unhandled crash). Freeing it lets the next
        poster run retry that window instead of treating it as sent
        forever. Returns how many were freed."""
        async with self.db.lock:
            cursor = await self._conn.execute('DELETE FROM event_reminders WHERE posted_at IS NULL')
            await self._conn.commit()
            return cursor.rowcount

    async def dated_reminder_sent(self, event_id: int) -> bool:
        """Has a 30/7/1-style window actually gone out? Decides whether a
        change or cancellation is worth a notice: nobody saw an event that
        was never announced. An explicit allowlist rather than excluding
        'changed'/'cancelled' by name: a change notice for a second edit is
        scoped to its own window (`changed:<start_date>`, so a repeat edit
        is not swallowed by the UNIQUE index on the first claim), and that
        scoped window must not be mistaken for a dated reminder either."""
        cursor = await self._conn.execute(
            """SELECT 1 FROM event_reminders
               WHERE event_id = ? AND posted_at IS NOT NULL AND window IN ('30', '7', '1')
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
