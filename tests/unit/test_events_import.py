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
