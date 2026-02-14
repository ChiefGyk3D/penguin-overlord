# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Lightweight SQLite database for persistent bot data.

Provides async-safe access to:
    - Moderation offender tracking (infractions, actions, history)
    - Arch banter leaderboard (persistent across restarts)

Uses aiosqlite for non-blocking I/O in the async Discord event loop.
Falls back to synchronous sqlite3 if aiosqlite is unavailable.

The database file is stored at ``data/penguin_overlord.db`` by default,
configurable via the ``BOT_DATABASE_PATH`` environment variable.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Try async driver first
try:
    import aiosqlite
    _ASYNC_AVAILABLE = True
except ImportError:
    _ASYNC_AVAILABLE = False
    logger.warning(
        "aiosqlite not installed — database will use synchronous fallback. "
        "Install with: pip install aiosqlite"
    )

DEFAULT_DB_PATH = 'data/penguin_overlord.db'

# ── Schema ────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
-- Moderation infractions log
CREATE TABLE IF NOT EXISTS mod_infractions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT    NOT NULL,
    user_id     TEXT    NOT NULL,
    username    TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    reason      TEXT    NOT NULL DEFAULT '',
    action      TEXT    NOT NULL DEFAULT 'warn',
    confidence  REAL    NOT NULL DEFAULT 0.0,
    actor       TEXT    NOT NULL DEFAULT 'bot',
    actor_id    TEXT    NOT NULL DEFAULT '',
    message_content TEXT NOT NULL DEFAULT '',
    channel_id  TEXT    NOT NULL DEFAULT '',
    channel_name TEXT   NOT NULL DEFAULT '',
    message_id  TEXT    NOT NULL DEFAULT '',
    resolved    INTEGER NOT NULL DEFAULT 0,
    notes       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_infractions_guild_user
    ON mod_infractions(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_infractions_guild_created
    ON mod_infractions(guild_id, created_at);


-- Arch banter leaderboard (persistent)
CREATE TABLE IF NOT EXISTS arch_roast_stats (
    guild_id    TEXT    NOT NULL,
    user_id     TEXT    NOT NULL,
    username    TEXT    NOT NULL,
    roast_count INTEGER NOT NULL DEFAULT 0,
    first_roast TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_roast  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (guild_id, user_id)
);

-- Global roast counter per guild
CREATE TABLE IF NOT EXISTS arch_roast_totals (
    guild_id      TEXT PRIMARY KEY,
    total_roasts  INTEGER NOT NULL DEFAULT 0,
    first_roast   TEXT,
    last_roast    TEXT
);


-- Pending moderation actions awaiting human review
CREATE TABLE IF NOT EXISTS mod_pending_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT    NOT NULL,
    user_id     TEXT    NOT NULL,
    username    TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    reason      TEXT    NOT NULL DEFAULT '',
    category    TEXT    NOT NULL DEFAULT '',
    confidence  REAL    NOT NULL DEFAULT 0.0,
    message_content TEXT NOT NULL DEFAULT '',
    channel_id  TEXT    NOT NULL DEFAULT '',
    message_id  TEXT    NOT NULL DEFAULT '',
    review_message_id TEXT NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'pending',
    reviewer_id TEXT    NOT NULL DEFAULT '',
    reviewer_name TEXT  NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_guild_status
    ON mod_pending_actions(guild_id, status);


-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
"""


class BotDatabase:
    """
    Async-safe SQLite database for persistent bot data.

    Usage::

        db = BotDatabase()
        await db.initialize()

        # Record a moderation infraction
        await db.add_infraction(guild_id, user_id, username, 'harassment',
                                'Targeted another user', 'warn')

        # Get user history
        history = await db.get_user_infractions(guild_id, user_id)

        # Leaderboard
        await db.record_roast(guild_id, user_id, username)
        top = await db.get_roast_leaderboard(guild_id, limit=10)

        await db.close()
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or os.getenv('BOT_DATABASE_PATH', DEFAULT_DB_PATH)
        self._conn = None  # aiosqlite connection (or None)
        self._sync_conn = None  # sqlite3 fallback
        self._initialized = False

    async def initialize(self):
        """Create tables and connect to the database."""
        # Ensure directory exists
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        if _ASYNC_AVAILABLE:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.executescript(_SCHEMA_SQL)
            await self._conn.commit()
        else:
            self._sync_conn = sqlite3.connect(self._db_path)
            self._sync_conn.row_factory = sqlite3.Row
            self._sync_conn.executescript(_SCHEMA_SQL)
            self._sync_conn.commit()

        self._initialized = True
        logger.info(f"Bot database initialized at {self._db_path}")

    async def close(self):
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
        if self._sync_conn:
            self._sync_conn.close()
            self._sync_conn = None
        self._initialized = False

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute a write query."""
        if self._conn:
            async with self._conn.execute(sql, params) as cursor:
                await self._conn.commit()
                return cursor.lastrowid
        elif self._sync_conn:
            cursor = self._sync_conn.execute(sql, params)
            self._sync_conn.commit()
            return cursor.lastrowid
        return None

    async def _fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a read query and return all rows as dicts."""
        if self._conn:
            async with self._conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        elif self._sync_conn:
            cursor = self._sync_conn.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]
        return []

    async def _fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a read query and return one row as dict."""
        if self._conn:
            async with self._conn.execute(sql, params) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        elif self._sync_conn:
            cursor = self._sync_conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        return None

    # ── Moderation Infractions ────────────────────────────────────────────

    async def add_infraction(
        self,
        guild_id: str,
        user_id: str,
        username: str,
        category: str,
        reason: str,
        action: str = 'warn',
        confidence: float = 0.0,
        actor: str = 'bot',
        actor_id: str = '',
        message_content: str = '',
        channel_id: str = '',
        channel_name: str = '',
        message_id: str = '',
    ) -> Optional[int]:
        """Record a moderation infraction. Returns the infraction ID."""
        return await self._execute(
            """INSERT INTO mod_infractions
               (guild_id, user_id, username, category, reason, action,
                confidence, actor, actor_id, message_content, channel_id,
                channel_name, message_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, username, category, reason, action,
             confidence, actor, actor_id, message_content, channel_id,
             channel_name, message_id),
        )

    async def get_user_infractions(
        self,
        guild_id: str,
        user_id: str,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Get a user's infraction history in a guild, newest first."""
        return await self._fetchall(
            """SELECT * FROM mod_infractions
               WHERE guild_id = ? AND user_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (guild_id, user_id, limit),
        )

    async def get_user_infraction_count(
        self,
        guild_id: str,
        user_id: str,
    ) -> int:
        """Get total infraction count for a user in a guild."""
        row = await self._fetchone(
            "SELECT COUNT(*) as cnt FROM mod_infractions WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return row['cnt'] if row else 0

    async def get_recent_infractions(
        self,
        guild_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent infractions for a guild."""
        return await self._fetchall(
            """SELECT * FROM mod_infractions
               WHERE guild_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (guild_id, limit),
        )

    async def resolve_infraction(
        self,
        infraction_id: int,
        notes: str = '',
    ) -> None:
        """Mark an infraction as resolved with optional notes."""
        await self._execute(
            "UPDATE mod_infractions SET resolved = 1, notes = ? WHERE id = ?",
            (notes, infraction_id),
        )

    # ── Pending Moderation Actions (Human-in-the-loop) ────────────────────

    async def add_pending_action(
        self,
        guild_id: str,
        user_id: str,
        username: str,
        action: str,
        reason: str = '',
        category: str = '',
        confidence: float = 0.0,
        message_content: str = '',
        channel_id: str = '',
        message_id: str = '',
        review_message_id: str = '',
    ) -> Optional[int]:
        """Queue an action for human moderator review. Returns the pending ID."""
        return await self._execute(
            """INSERT INTO mod_pending_actions
               (guild_id, user_id, username, action, reason, category,
                confidence, message_content, channel_id, message_id,
                review_message_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, username, action, reason, category,
             confidence, message_content, channel_id, message_id,
             review_message_id),
        )

    async def resolve_pending_action(
        self,
        pending_id: int,
        status: str,
        reviewer_id: str,
        reviewer_name: str,
    ) -> None:
        """Approve or deny a pending action."""
        now = datetime.now(timezone.utc).isoformat()
        await self._execute(
            """UPDATE mod_pending_actions
               SET status = ?, reviewer_id = ?, reviewer_name = ?,
                   resolved_at = ?
               WHERE id = ?""",
            (status, reviewer_id, reviewer_name, now, pending_id),
        )

    async def get_pending_action(self, pending_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific pending action by ID."""
        return await self._fetchone(
            "SELECT * FROM mod_pending_actions WHERE id = ?",
            (pending_id,),
        )

    async def get_pending_actions(
        self,
        guild_id: str,
        status: str = 'pending',
    ) -> List[Dict[str, Any]]:
        """Get all pending actions for a guild."""
        return await self._fetchall(
            """SELECT * FROM mod_pending_actions
               WHERE guild_id = ? AND status = ?
               ORDER BY created_at DESC""",
            (guild_id, status),
        )

    # ── Arch Roast Leaderboard ────────────────────────────────────────────

    async def record_roast(
        self,
        guild_id: str,
        user_id: str,
        username: str,
    ) -> None:
        """Record a roast for the leaderboard (upsert)."""
        now = datetime.now(timezone.utc).isoformat()

        # Upsert user stats
        await self._execute(
            """INSERT INTO arch_roast_stats (guild_id, user_id, username, roast_count, first_roast, last_roast)
               VALUES (?, ?, ?, 1, ?, ?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET
                   roast_count = roast_count + 1,
                   last_roast = excluded.last_roast,
                   username = excluded.username""",
            (guild_id, user_id, username, now, now),
        )

        # Upsert guild totals
        await self._execute(
            """INSERT INTO arch_roast_totals (guild_id, total_roasts, first_roast, last_roast)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
                   total_roasts = total_roasts + 1,
                   last_roast = excluded.last_roast""",
            (guild_id, now, now),
        )

    async def get_roast_leaderboard(
        self,
        guild_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get the roast leaderboard for a guild, sorted by roast count."""
        return await self._fetchall(
            """SELECT user_id, username, roast_count, first_roast, last_roast
               FROM arch_roast_stats
               WHERE guild_id = ?
               ORDER BY roast_count DESC
               LIMIT ?""",
            (guild_id, limit),
        )

    async def get_roast_totals(self, guild_id: str) -> Dict[str, Any]:
        """Get total roast stats for a guild."""
        row = await self._fetchone(
            "SELECT * FROM arch_roast_totals WHERE guild_id = ?",
            (guild_id,),
        )
        if row:
            return row
        return {'total_roasts': 0, 'first_roast': None, 'last_roast': None}

    async def get_user_roast_stats(
        self,
        guild_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get roast stats for a specific user."""
        return await self._fetchone(
            "SELECT * FROM arch_roast_stats WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )

    async def reset_roast_leaderboard(self, guild_id: str) -> None:
        """Reset the entire roast leaderboard for a guild."""
        await self._execute(
            "DELETE FROM arch_roast_stats WHERE guild_id = ?",
            (guild_id,),
        )
        await self._execute(
            "DELETE FROM arch_roast_totals WHERE guild_id = ?",
            (guild_id,),
        )

    async def reset_user_roasts(self, guild_id: str, user_id: str) -> None:
        """Reset roast count for a specific user."""
        row = await self._fetchone(
            "SELECT roast_count FROM arch_roast_stats WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row:
            # Subtract from guild total
            await self._execute(
                """UPDATE arch_roast_totals
                   SET total_roasts = MAX(0, total_roasts - ?)
                   WHERE guild_id = ?""",
                (row['roast_count'], guild_id),
            )
        await self._execute(
            "DELETE FROM arch_roast_stats WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )


# ── Global singleton ──────────────────────────────────────────────────────

_db: Optional[BotDatabase] = None


async def get_database() -> BotDatabase:
    """
    Get or create the global BotDatabase singleton.

    Initializes on first call. Subsequent calls return the same instance.
    """
    global _db
    if _db is None:
        _db = BotDatabase()
        await _db.initialize()
    return _db
