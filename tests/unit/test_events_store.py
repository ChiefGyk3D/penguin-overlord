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


# -- listing -----------------------------------------------------------------------

async def _seed(store):
    ids = {}
    ids['grr'] = await store.insert(event(title='GrrCON', fingerprint='grrcon:2026',
                                          start_date='2026-09-24', end_date='2026-09-25',
                                          status='approved', submitted_by=None, city=None), actor_id=0, action='import')
    ids['ham'] = await store.insert(event(title='Ontario Hamfest', fingerprint='ontario hamfest:2026',
                                          topic='ham', start_date='2026-09-12', end_date='2026-09-12',
                                          region_code='CA-ON', country_code='CA', status='approved',
                                          submitted_by=None, city=None),
                                    actor_id=0, action='import')
    ids['pend'] = await store.insert(event(title='Queen City Con', fingerprint='queen city con:2026',
                                           start_date='2026-10-10', end_date='2026-10-11',
                                           region_code='US-OH'), actor_id=42, action='submit')
    ids['old'] = await store.insert(event(title='BSides SF', fingerprint='bsides sf:2026',
                                          start_date='2026-03-21', end_date='2026-03-22',
                                          region_code='US-CA', status='approved', submitted_by=None),
                                    actor_id=0, action='import')
    return ids


async def test_list_upcoming_filters_by_window_topic_and_place(store):
    await _seed(store)
    rows = await store.list_upcoming(1, today='2026-09-03', days=30)
    assert [r['title'] for r in rows] == ['Ontario Hamfest', 'GrrCON']       # pending and past excluded
    assert [r['title'] for r in await store.list_upcoming(1, today='2026-09-03', days=30, topic='ham')] == ['Ontario Hamfest']
    assert [r['title'] for r in await store.list_upcoming(1, today='2026-09-03', days=365, region_code='US-MI')] == ['GrrCON']
    assert [r['title'] for r in await store.list_upcoming(1, today='2026-09-03', days=365, country_code='CA')] == ['Ontario Hamfest']
    assert await store.list_upcoming(1, today='2026-09-03', days=5) == []


async def test_list_upcoming_online_filter_excludes_in_person_events(store):
    await store.insert(event(title='VirtualCon', fingerprint='virtualcon:2026', start_date='2026-09-24',
                             end_date='2026-09-24', status='approved', submitted_by=None,
                             region_code=None, country_code=None), actor_id=0, action='import')
    await store.insert(event(title='InPersonCon', fingerprint='inpersoncon:2026', start_date='2026-09-25',
                             end_date='2026-09-25', status='approved', submitted_by=None), actor_id=0, action='import')
    rows = await store.list_upcoming(1, today='2026-09-03', days=30, online=True)
    assert [r['title'] for r in rows] == ['VirtualCon']


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


async def _age_claim(store, reminder_id, expression="datetime('now', '-7 hours')"):
    """Backdate a claim so the reaper's six hour floor is behind it."""
    await store.db.conn.execute(
        f'UPDATE event_reminders SET claimed_at = {expression} WHERE id = ?', (reminder_id,))
    await store.db.conn.commit()


async def test_release_unposted_claims_drops_only_the_unsent_ones(store):
    ids = await _seed(store)
    orphan = await store.claim_reminder(ids['grr'], '30', channel_id=99)     # never followed by a send
    await _age_claim(store, orphan)
    sent = await store.claim_reminder(ids['grr'], '7', channel_id=99)
    await _age_claim(store, sent)
    await store.mark_reminder_sent(sent, message_id=1, roles_mentioned='')
    assert await store.release_unposted_claims() == 1
    assert await store.claim_reminder(ids['grr'], '30', channel_id=99) is not None   # freed, reclaimable
    assert orphan   # sanity: the claim really was taken before the release
    assert await store.dated_reminder_sent(ids['grr']) is True                       # the sent one survives


async def test_release_unposted_claims_spares_a_claim_the_poster_may_still_be_using(store):
    # The reaper and the poster can run in the same minute
    # (EVENTS_POST_AT=03:00 puts them on top of each other), so a claim
    # younger than six hours belongs to a send that may still be in
    # flight; only a claim old enough to be a crash survivor is freed.
    ids = await _seed(store)
    fresh = await store.claim_reminder(ids['grr'], '30', channel_id=99)
    assert await store.release_unposted_claims() == 0
    assert await store.claim_reminder(ids['grr'], '30', channel_id=99) is None   # still held
    await _age_claim(store, fresh)
    assert await store.release_unposted_claims() == 1
    assert await store.claim_reminder(ids['grr'], '30', channel_id=99) is not None


async def test_changed_window_does_not_count_as_dated(store):
    ids = await _seed(store)
    rid = await store.claim_reminder(ids['grr'], 'changed', channel_id=99)
    await store.mark_reminder_sent(rid, message_id=1, roles_mentioned='')
    assert await store.dated_reminder_sent(ids['grr']) is False


async def test_dated_reminder_sent_ignores_a_scoped_changed_window(store):
    # A second schedule change scopes its claim to the new date
    # ('changed:2026-10-02') so it is not swallowed by the UNIQUE index on
    # the first 'changed' claim; dated_reminder_sent must not mistake that
    # scoped window for a 30/7/1 reminder having gone out.
    ids = await _seed(store)
    rid = await store.claim_reminder(ids['grr'], 'changed:2026-10-02', channel_id=99)
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


async def test_expire_pending_leaves_rollover_rows_pending(store):
    # A rollover is the calendar's own next-year row, not a member's
    # forgotten suggestion: expiring it drops the annual event for good,
    # because the parent is already retired and has_rollover still sees
    # the rejected child.
    ids = await _seed(store)
    rollover = await store.insert(
        event(title='BSides SF', fingerprint='bsides sf:2027', start_date='2027-03-20',
              end_date='2027-03-21', provenance='rollover', submitted_by=None,
              parent_event_id=ids['old'], date_status='estimated'),
        actor_id=0, action='rollover')
    assert await store.expire_pending('2999-01-01T00:00:00+00:00') == [ids['pend']]
    assert (await store.get(rollover))['status'] == 'pending'


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
