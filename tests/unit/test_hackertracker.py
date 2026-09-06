# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Hacker Tracker: Firestore wire format in, Conference rows out. No
network anywhere in this file; the fetch tests use a fake session."""

from datetime import date

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
