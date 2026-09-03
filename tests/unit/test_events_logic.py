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
