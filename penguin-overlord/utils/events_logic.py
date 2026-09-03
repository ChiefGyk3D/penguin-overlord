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
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

_ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'events'

TOPICS = ('cyber', 'ham', 'foss', 'other')
TOPIC_LABELS = {'cyber': 'Cybersecurity', 'ham': 'Ham Radio', 'foss': 'FOSS', 'other': 'Other'}
TOPIC_ROLES = {'cyber': 'Cybersecurity Events', 'ham': 'Ham Radio Events', 'foss': 'FOSS Events'}
STATUSES = ('pending', 'approved', 'rejected', 'cancelled', 'retired')
DATE_STATUSES = ('confirmed', 'estimated')
PROVENANCES = ('member', 'calendar', 'ai', 'rollover')

MAX_NOTES = 500
MAX_TITLE = 120
MAX_YEARS_AHEAD = 2

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
    try:
        cutoff = today.replace(year=today.year + MAX_YEARS_AHEAD)
    except ValueError:
        # Feb 29 in a leap year, target year is not a leap year
        cutoff = today.replace(year=today.year + MAX_YEARS_AHEAD, day=28)
    if start_date > cutoff:
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


# -- regions and roles ---------------------------------------------------------

@dataclass(frozen=True)
class Regions:
    regions: Mapping[str, str]      # 'US-MI' -> 'Michigan'
    countries: Mapping[str, str]    # 'US' -> 'United States'

    def name(self, code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        return self.regions.get(code) or self.countries.get(code)

    @staticmethod
    def country_of(region_code: str) -> str:
        return region_code.split('-', 1)[0]


def load_regions(path: Optional[Path] = None) -> Regions:
    data = json.loads((path or _ASSETS / 'regions.json').read_text(encoding='utf-8'))
    return Regions(regions=dict(data['regions']), countries=dict(data['countries']))


def role_names_for(event: Mapping, regions: Regions) -> list[str]:
    """Role names a reminder mentions: the topic role (none for 'other'),
    then the region role for regional events or the country role for
    national ones. Online events (no codes) get the topic role only."""
    names = []
    topic_role = TOPIC_ROLES.get(event.get('topic'))
    if topic_role:
        names.append(topic_role)
    if event.get('scope') == 'national':
        geo = regions.countries.get(event.get('country_code') or '')
    else:
        geo = regions.regions.get(event.get('region_code') or '')
        if geo is None and not event.get('region_code'):
            geo = regions.countries.get(event.get('country_code') or '')
    if geo:
        names.append(geo)
    return names


def region_choices(regions: Regions, current: str, limit: int = 25) -> list[tuple[str, str]]:
    """Autocomplete rows: (label, value). Online first (there are more
    regions than the Discord option cap, so it would never survive the
    truncation below otherwise), then regions, then countries; a prefix
    on the name or a substring of the code matches."""
    needle = (current or '').strip().lower()
    rows = [('Online', 'online')]
    rows += [(f'{name} ({code})', code) for code, name in regions.regions.items()]
    rows += [(f'{name} ({code})', code) for code, name in regions.countries.items()]
    if needle:
        rows = [(label, value) for label, value in rows
                if label.lower().startswith(needle) or needle in value.lower()
                or any(word.startswith(needle) for word in label.lower().split())]
    return rows[:limit]


def resolve_place(where: str, national: bool, regions: Regions) -> tuple[Optional[str], Optional[str], str]:
    """The /events submit `where` value (an autocomplete code, or 'online')
    to (region_code, country_code, scope). A country code alone is a
    national event; `national` promotes a regional code to the country
    role."""
    code = (where or '').strip()
    if code.lower() == 'online':
        return None, None, 'regional'
    code = code.upper()
    if code in regions.regions:
        return code, Regions.country_of(code), 'national' if national else 'regional'
    if code in regions.countries:
        return None, code, 'national'
    raise ValueError('Pick a place from the list (start typing a state, province or country), or Online.')


def parse_location_field(text: str, regions: Regions) -> tuple[str, Optional[str], Optional[str], str]:
    """The edit modal's location line: 'City, US-MI[, national]', 'City, DE'
    (country only, national), or 'Online'. Returns (city, region_code,
    country_code, scope)."""
    parts = [p.strip() for p in (text or '').split(',') if p.strip()]
    if not parts:
        raise ValueError('Location is City, CODE (for example Grand Rapids, US-MI) or Online.')
    city = parts[0]
    if len(parts) == 1:
        if city.lower() == 'online':
            return 'Online', None, None, 'regional'
        raise ValueError('Add the region or country code after the city, for example Grand Rapids, US-MI.')
    code = parts[1].upper()
    scope = parts[2].lower() if len(parts) > 2 else None
    if scope not in (None, 'regional', 'national'):
        raise ValueError('The third part, if given, is regional or national.')
    if code in regions.regions:
        return city, code, Regions.country_of(code), scope or 'regional'
    if code in regions.countries:
        return city, None, code, scope or 'national'
    raise ValueError(f'Unknown region or country code {code}.')


def location_field(event: Mapping) -> str:
    """The edit modal's prefilled location line; parse_location_field
    reads it back."""
    code = event.get('region_code') or event.get('country_code')
    if not code:
        return event.get('city') or 'Online'
    text = f"{event['city']}, {code}"
    if event.get('scope') == 'national' and event.get('region_code'):
        text += ', national'
    return text


# -- CSV import -----------------------------------------------------------------

CSV_TOPICS = {'cybersecurity': 'cyber', 'ham radio': 'ham', 'foss': 'foss'}
_CA_CODES = frozenset(('AB', 'BC', 'MB', 'NB', 'NL', 'NT', 'NS', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'))


def csv_row_to_event(row: Mapping[str, str], guild_id: int) -> dict:
    """One events/*.csv row (Event, Start Date, End Date, City, State, URL,
    Source, Type, Date Status) to an approved, annual, calendar-provenance
    row ready for EventsStore.insert(). Raises ValueError on a bad date."""
    title = row['Event'].strip()
    start = parse_date(row['Start Date'])
    end = parse_date(row['End Date']) if row.get('End Date', '').strip() else start
    code = row['State'].strip().upper()
    country = 'CA' if code in _CA_CODES else 'US'
    url = row.get('URL', '').strip() or None
    return {
        'guild_id': guild_id, 'title': title, 'fingerprint': fingerprint(title, start),
        'topic': CSV_TOPICS.get(row['Type'].strip().lower(), 'other'),
        'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'start_time': None, 'timezone': None,
        'date_status': row['Date Status'].strip().lower() or 'estimated',
        'city': row['City'].strip(), 'region_code': f'{country}-{code}', 'country_code': country,
        'scope': 'national' if normalize_title(title).startswith('def con') else 'regional',
        'url': url, 'notes': None, 'recurrence': 'annual', 'parent_event_id': None,
        'status': 'approved', 'provenance': 'calendar', 'submitted_by': None,
        'source_url': None, 'source_note': row.get('Source', '').strip() or None,
        'decided_by': 0, 'decided_at': None, 'reject_reason': None,
    }
