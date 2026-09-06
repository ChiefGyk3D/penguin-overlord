# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Async SQLite storage for moderation history.

Requires aiosqlite (in requirements.txt) — there is deliberately no
blocking sqlite3 fallback, because the moderation cog reads history on the
message hot path and a silent sync fallback would stall the event loop.

Stores:
- mod_infractions: every detection, the model's verdict, and (later) the
  human verdict — this is the calibration dataset that makes graduated
  enforcement possible.
- mod_pending_actions: escalations awaiting a moderator decision.
- events and its side tables: the conference database (utils/events_store.py owns the queries).

All queries are parameterized. WAL mode + busy_timeout so external readers
(backups, sqlite3 CLI) don't collide with the bot.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mod_infractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    proposed_action TEXT NOT NULL,
    action_taken TEXT NOT NULL DEFAULT 'none',
    excerpt TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    dry_run INTEGER NOT NULL DEFAULT 1,
    human_verdict TEXT,            -- 'confirmed' | 'false_positive' | NULL (unlabeled)
    verdict_moderator_id INTEGER,
    corrected_category TEXT,       -- set when a moderator recategorized the alert
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_infractions_user
    ON mod_infractions (guild_id, user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_infractions_message
    ON mod_infractions (message_id);

CREATE TABLE IF NOT EXISTS mod_pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    infraction_id INTEGER NOT NULL REFERENCES mod_infractions(id),
    proposed_action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | denied | expired
    review_message_id INTEGER,
    decided_by INTEGER,
    decided_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_status
    ON mod_pending_actions (status, created_at);

CREATE TABLE IF NOT EXISTS mod_review_votes (
    pending_id INTEGER NOT NULL REFERENCES mod_pending_actions(id),
    moderator_id INTEGER NOT NULL,
    verb TEXT NOT NULL,            -- 'approve' | 'deny'
    corrected_category TEXT,       -- an approve vote may carry a category fix
    created_at TEXT NOT NULL,
    PRIMARY KEY (pending_id, moderator_id)
);

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
    provenance TEXT NOT NULL,       -- member | calendar | ai | rollover | hackertracker
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
    claimed_at TEXT NOT NULL DEFAULT (datetime('now')),
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
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModerationDatabase:
    def __init__(self, path: str = None):
        # BOT_DATABASE_PATH, or penguin_overlord.db inside the resolved
        # DATA_DIR. Both come from the one config parser.
        from utils.config import load_paths_config
        self.path = path or str(load_paths_config().database_path)
        self._conn = None
        self._lock = asyncio.Lock()

    @property
    def conn(self):
        """The shared aiosqlite connection (EventsStore borrows it)."""
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        """Guards read-modify-write sequences across every store on this connection."""
        return self._lock

    async def connect(self):
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute('PRAGMA journal_mode=WAL')
        await self._conn.execute('PRAGMA busy_timeout=5000')
        await self._conn.executescript(_SCHEMA)
        cursor = await self._conn.execute('SELECT version FROM schema_version')
        row = await cursor.fetchone()
        if row is None:
            await self._conn.execute('INSERT INTO schema_version (version) VALUES (?)', (SCHEMA_VERSION,))
        elif row['version'] != SCHEMA_VERSION:
            # Refuse to run on a newer schema than we understand; migrate
            # forward from an older one.
            if row['version'] > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema v{row['version']} is newer than this bot understands (v{SCHEMA_VERSION})"
                )
            await self._migrate(row['version'])
        await self._conn.commit()

    async def _migrate(self, from_version: int):
        """Forward-only migrations. New tables arrive via _SCHEMA's CREATE IF
        NOT EXISTS; this handles what that cannot — ALTERs on existing
        tables — and then stamps the new version."""
        if from_version < 2:
            # v2: moderators can recategorize an alert instead of only
            # approving/dismissing it.
            cursor = await self._conn.execute('PRAGMA table_info(mod_infractions)')
            columns = {row[1] for row in await cursor.fetchall()}
            if 'corrected_category' not in columns:
                await self._conn.execute(
                    'ALTER TABLE mod_infractions ADD COLUMN corrected_category TEXT')
        # v3: events tables; CREATE IF NOT EXISTS in _SCHEMA is the whole migration.
        await self._conn.execute('UPDATE schema_version SET version = ?', (SCHEMA_VERSION,))
        logger.info('Moderation database migrated v%d -> v%d', from_version, SCHEMA_VERSION)
        logger.info(f"Moderation database ready: {self.path}")

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- infractions --------------------------------------------------------

    async def add_infraction(self, *, guild_id: int, channel_id: int, message_id: int,
                             user_id: int, username: str, category: str,
                             confidence: float, proposed_action: str,
                             action_taken: str = 'none', excerpt: str = '',
                             model: str = '', dry_run: bool = True) -> int:
        async with self._lock:
            cursor = await self._conn.execute(
                """INSERT INTO mod_infractions
                   (guild_id, channel_id, message_id, user_id, username, category,
                    confidence, proposed_action, action_taken, excerpt, model, dry_run, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, message_id, user_id, username, category,
                 confidence, proposed_action, action_taken, excerpt[:300], model,
                 1 if dry_run else 0, _utcnow()),
            )
            await self._conn.commit()
            return cursor.lastrowid

    async def get_user_infraction_count(self, guild_id: int, user_id: int,
                                        days: int = 30,
                                        exclude_false_positives: bool = True) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query = ("SELECT COUNT(*) AS n FROM mod_infractions "
                 "WHERE guild_id = ? AND user_id = ? AND created_at >= ?")
        if exclude_false_positives:
            query += " AND (human_verdict IS NULL OR human_verdict != 'false_positive')"
        cursor = await self._conn.execute(query, (guild_id, user_id, cutoff))
        row = await cursor.fetchone()
        return row['n'] if row else 0

    async def get_user_history(self, guild_id: int, user_id: int, limit: int = 5) -> list:
        cursor = await self._conn.execute(
            """SELECT id, category, confidence, proposed_action, human_verdict,
                      corrected_category, created_at
               FROM mod_infractions
               WHERE guild_id = ? AND user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (guild_id, user_id, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def set_human_verdict(self, infraction_id: int, verdict: str,
                                moderator_id: int,
                                corrected_category: str = None) -> bool:
        async with self._lock:
            cursor = await self._conn.execute(
                """UPDATE mod_infractions
                   SET human_verdict = ?, verdict_moderator_id = ?,
                       corrected_category = COALESCE(?, corrected_category)
                   WHERE id = ?""",
                (verdict, moderator_id, corrected_category, infraction_id),
            )
            await self._conn.commit()
            return cursor.rowcount > 0

    async def add_review_vote(self, pending_id: int, moderator_id: int,
                              verb: str, corrected_category: str = None) -> dict:
        """Record (or change) one moderator's vote on an open review.

        A moderator voting again replaces their earlier vote — changing your
        mind is allowed until the review resolves. Returns the tally:
        {'approve': n, 'deny': n, 'corrected_category': latest-or-None}.
        """
        async with self._lock:
            await self._conn.execute(
                """INSERT INTO mod_review_votes
                       (pending_id, moderator_id, verb, corrected_category, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (pending_id, moderator_id)
                   DO UPDATE SET verb = excluded.verb,
                                 corrected_category = excluded.corrected_category,
                                 created_at = excluded.created_at""",
                (pending_id, moderator_id, verb, corrected_category, _utcnow()),
            )
            await self._conn.commit()
        return await self.review_votes(pending_id)

    async def review_votes(self, pending_id: int) -> dict:
        cursor = await self._conn.execute(
            """SELECT verb, corrected_category, created_at
               FROM mod_review_votes WHERE pending_id = ?
               ORDER BY created_at""",
            (pending_id,),
        )
        rows = await cursor.fetchall()
        tally = {'approve': 0, 'deny': 0, 'corrected_category': None}
        for row in rows:
            tally[row['verb']] = tally.get(row['verb'], 0) + 1
            if row['verb'] == 'approve' and row['corrected_category']:
                tally['corrected_category'] = row['corrected_category']
        return tally

    async def find_infraction_by_alert(self, alert_message_id: int):
        cursor = await self._conn.execute(
            """SELECT i.*, p.id AS pending_id FROM mod_infractions i
               JOIN mod_pending_actions p ON p.infraction_id = i.id
               WHERE p.review_message_id = ?""",
            (alert_message_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def calibration_stats(self, guild_id: int, days: int = 14) -> dict:
        """Per-category precision from human labels — the Phase 2 exit metric."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await self._conn.execute(
            """SELECT category,
                      COUNT(*) AS total,
                      SUM(CASE WHEN human_verdict = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
                      SUM(CASE WHEN human_verdict = 'false_positive' THEN 1 ELSE 0 END) AS false_positives,
                      SUM(CASE WHEN human_verdict IS NULL THEN 1 ELSE 0 END) AS unlabeled
               FROM mod_infractions
               WHERE guild_id = ? AND created_at >= ?
               GROUP BY category ORDER BY total DESC""",
            (guild_id, cutoff),
        )
        return {row['category']: dict(row) for row in await cursor.fetchall()}

    async def purge_user(self, guild_id: int, user_id: int) -> int:
        async with self._lock:
            cursor = await self._conn.execute(
                "DELETE FROM mod_pending_actions WHERE infraction_id IN "
                "(SELECT id FROM mod_infractions WHERE guild_id = ? AND user_id = ?)",
                (guild_id, user_id),
            )
            cursor = await self._conn.execute(
                "DELETE FROM mod_infractions WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await self._conn.commit()
            return cursor.rowcount

    async def purge_older_than(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with self._lock:
            await self._conn.execute(
                "DELETE FROM mod_pending_actions WHERE infraction_id IN "
                "(SELECT id FROM mod_infractions WHERE created_at < ?)",
                (cutoff,),
            )
            cursor = await self._conn.execute(
                "DELETE FROM mod_infractions WHERE created_at < ?", (cutoff,),
            )
            await self._conn.commit()
            return cursor.rowcount

    # -- pending actions ----------------------------------------------------

    async def add_pending_action(self, infraction_id: int, proposed_action: str) -> int:
        async with self._lock:
            cursor = await self._conn.execute(
                """INSERT INTO mod_pending_actions (infraction_id, proposed_action, created_at)
                   VALUES (?, ?, ?)""",
                (infraction_id, proposed_action, _utcnow()),
            )
            await self._conn.commit()
            return cursor.lastrowid

    async def set_review_message(self, pending_id: int, review_message_id: int):
        async with self._lock:
            await self._conn.execute(
                "UPDATE mod_pending_actions SET review_message_id = ? WHERE id = ?",
                (review_message_id, pending_id),
            )
            await self._conn.commit()

    async def get_pending_action(self, pending_id: int):
        cursor = await self._conn.execute(
            """SELECT p.*, i.guild_id, i.channel_id, i.message_id, i.user_id,
                      i.username, i.category, i.confidence, i.excerpt
               FROM mod_pending_actions p
               JOIN mod_infractions i ON i.id = p.infraction_id
               WHERE p.id = ?""",
            (pending_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_pending_actions(self, guild_id: int, limit: int = 15) -> list:
        """Open reviews, oldest first — what `/mod pending` shows so a
        moderator can find alerts whose buttons were never answered."""
        cursor = await self._conn.execute(
            """SELECT p.id, p.proposed_action, p.review_message_id, p.created_at,
                      i.id AS infraction_id, i.username, i.category, i.confidence,
                      i.excerpt, i.channel_id
               FROM mod_pending_actions p
               JOIN mod_infractions i ON i.id = p.infraction_id
               WHERE p.status = 'pending' AND i.guild_id = ?
               ORDER BY p.id ASC LIMIT ?""",
            (guild_id, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def resolve_pending_action(self, pending_id: int, status: str, moderator_id: int) -> bool:
        """Atomically move pending -> decided; False if already decided."""
        async with self._lock:
            cursor = await self._conn.execute(
                """UPDATE mod_pending_actions
                   SET status = ?, decided_by = ?, decided_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (status, moderator_id, _utcnow(), pending_id),
            )
            await self._conn.commit()
            return cursor.rowcount > 0


_db = None
_db_lock = asyncio.Lock()


async def get_database() -> ModerationDatabase:
    """Process-wide database singleton (lock-guarded, connected)."""
    global _db
    if _db is None or _db._conn is None:
        async with _db_lock:
            if _db is None:
                _db = ModerationDatabase()
            if _db._conn is None:
                await _db.connect()
    return _db


def reset_database():
    """Testing hook."""
    global _db
    _db = None
