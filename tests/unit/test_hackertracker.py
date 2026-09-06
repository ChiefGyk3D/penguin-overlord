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
