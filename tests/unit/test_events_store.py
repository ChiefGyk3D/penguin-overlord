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
