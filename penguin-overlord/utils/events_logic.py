# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pure decisions for the events system: no Discord, no database.

Everything time-related takes an explicit `today` so tests pin the clock.
"Today" for reminder math is the calendar date in EVENTS_TIMEZONE, not the
event's own zone: a Saturday con gets its reminder on the same Eastern
morning wherever it is.
"""

import calendar
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

TOPICS = ('cyber', 'ham', 'foss', 'other')
TOPIC_LABELS = {'cyber': 'Cybersecurity', 'ham': 'Ham Radio', 'foss': 'FOSS', 'other': 'Other'}
TOPIC_ROLES = {'cyber': 'Cybersecurity Events', 'ham': 'Ham Radio Events', 'foss': 'FOSS Events'}
STATUSES = ('pending', 'approved', 'rejected', 'cancelled', 'retired')
DATE_STATUSES = ('confirmed', 'estimated')
PROVENANCES = ('member', 'calendar', 'ai', 'rollover')

MAX_NOTES = 500
MAX_TITLE = 120
MAX_YEARS_AHEAD = 2

_ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'events'
_PUNCT = re.compile(r'[^a-z0-9 ]+')
_NUMBER_WORD = re.compile(r'\b\d+\b')          # a year or an edition number on its own
_SPACES = re.compile(r'\s+')


# -- fingerprint ---------------------------------------------------------------

def normalize_title(title: str) -> str:
    """Lowercase ASCII, punctuation gone, standalone numbers gone (years and
    edition numbers), whitespace collapsed. 'DEF CON 34' and 'DEF CON 35'
    collide on purpose; the start year in fingerprint() separates them."""
    text = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    text = _PUNCT.sub(' ', text.lower())
    text = _NUMBER_WORD.sub(' ', text)
    return _SPACES.sub(' ', text).strip()


def fingerprint(title: str, start_date: date) -> str:
    return f'{normalize_title(title)}:{start_date.year}'


# -- dates ---------------------------------------------------------------------

def parse_date(text: str) -> date:
    text = (text or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        raise ValueError(f'{text!r} is not a date in YYYY-MM-DD form')
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f'{text!r} is not a real calendar date') from None


def local_today(tz_name: str, now: Optional[datetime] = None) -> date:
    now = now or datetime.now(ZoneInfo('UTC'))
    return now.astimezone(ZoneInfo(tz_name)).date()


def days_until(start_date, today: date) -> int:
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    return (start_date - today).days


def due_window(days: int, windows: Sequence[int]) -> Optional[str]:
    """The reminder window a countdown lands on, as the string key used in
    event_reminders.window, or None."""
    return str(days) if days in windows else None


def next_annual_dates(start: date, end: date) -> tuple[date, date]:
    """Same ordinal weekday next year (third Saturday stays third Saturday);
    a fifth occurrence that does not exist becomes the last one. Duration
    is preserved."""
    ordinal = (start.day - 1) // 7 + 1
    year = start.year + 1
    first_weekday, days_in_month = calendar.monthrange(year, start.month)
    first_match = 1 + (start.weekday() - first_weekday) % 7
    day = first_match + 7 * (ordinal - 1)
    while day > days_in_month:
        day -= 7
    new_start = date(year, start.month, day)
    return new_start, new_start + (end - start)


# -- submissions ---------------------------------------------------------------

def validate_submission(*, title: str, topic: str, start: str, end: Optional[str],
                        city: str, url: Optional[str], notes: Optional[str],
                        today: date) -> tuple[Optional[dict], Optional[str]]:
    """Returns (clean_fields, None) or (None, reason). The reason is member-
    facing, so it says exactly which field and why."""
    title = (title or '').strip()
    if not title:
        return None, 'A title is required.'
    if len(title) > MAX_TITLE:
        return None, f'The title is over {MAX_TITLE} characters.'
    if topic not in TOPICS:
        return None, f'Unknown topic; pick one of {", ".join(TOPICS)}.'
    try:
        start_date = parse_date(start)
        end_date = parse_date(end) if end and end.strip() else start_date
    except ValueError as e:
        return None, f'{e}. Dates are YYYY-MM-DD.'
    if end_date < start_date:
        return None, 'The end date is before the start date.'
    if start_date < today:
        return None, 'That start date is in the past.'
    if start_date > today.replace(year=today.year + MAX_YEARS_AHEAD):
        return None, 'That start is more than two years out.'
    city = (city or '').strip()
    if not city:
        return None, 'A city is required (use Online for virtual events).'
    url = (url or '').strip() or None
    if url and not url.lower().startswith(('http://', 'https://')):
        return None, 'The url must start with http:// or https://.'
    notes = (notes or '').strip() or None
    if notes and len(notes) > MAX_NOTES:
        return None, f'Notes are limited to {MAX_NOTES} characters.'
    return {
        'title': title, 'fingerprint': fingerprint(title, start_date), 'topic': topic,
        'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(),
        'city': city, 'url': url, 'notes': notes,
    }, None


def parse_dates_field(text: str) -> tuple[date, date]:
    """'2026-09-24' or '2026-09-24 to 2026-09-25' (the edit modal's field)."""
    parts = [p.strip() for p in re.split(r'\s+(?:to|-)\s+|\s*/\s*', (text or '').strip()) if p.strip()]
    if not 1 <= len(parts) <= 2:
        raise ValueError('Dates are YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD.')
    start = parse_date(parts[0])
    end = parse_date(parts[1]) if len(parts) == 2 else start
    if end < start:
        raise ValueError('The end date is before the start date.')
    return start, end
