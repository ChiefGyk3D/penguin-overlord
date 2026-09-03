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


def test_validate_submission_leap_year_feb29_within_window():
    # 2028 is a leap year; 2029 is not, 2030 is not. Feb 29 2028 + 2 years = Feb 28 2030.
    # Start of 2029-03-01 should be valid (within 2 years of Feb 29 2028).
    clean, problem = _submit(today=date(2028, 2, 29), start='2029-03-01', end='2029-03-01')
    assert problem is None
    assert clean is not None
    assert clean['start_date'] == '2029-03-01'


def test_validate_submission_leap_year_feb29_outside_window():
    # 2028 is a leap year; 2030 is not. Feb 29 2028 + 2 years = Feb 28 2030.
    # Start of 2031-01-01 should be invalid (more than 2 years out).
    clean, problem = _submit(today=date(2028, 2, 29), start='2031-01-01', end='2031-01-01')
    assert clean is None
    assert 'two years' in problem


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


# -- submit: resolving the "where" autocomplete value -------------------------

@pytest.mark.parametrize('where, national, expected', [
    ('US-MI', False, ('US-MI', 'US', 'regional')),
    ('US-NV', True, ('US-NV', 'US', 'national')),
    ('DE', False, (None, 'DE', 'national')),
    ('online', False, (None, None, 'regional')),
    ('Online', True, (None, None, 'regional')),
])
def test_resolve_place(where, national, expected):
    assert el.resolve_place(where, national, el.load_regions()) == expected


def test_resolve_place_rejects_free_text():
    with pytest.raises(ValueError, match='Pick'):
        el.resolve_place('Michigan', False, el.load_regions())
