# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""data/news_config.example.json must describe every category and agree with
the defaults NewsManager builds and the systemd timers install-systemd.sh writes.

Historical bugs: the example lacked vendor_alerts entirely, and kev said
minute_offset 30 while the KEV timer fires at :00.
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cogs.news_manager import NEWS_CATEGORIES, NewsManager

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "penguin-overlord" / "data" / "news_config.example.json"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-systemd.sh"

# Fields whose values are pure documentation of the schedule; they must match
# the in-code defaults so a reader of either file gets the same answer.
SCHEDULE_FIELDS = ("interval_hours", "minute_offset", "concurrency_limit", "use_etag_cache")


@pytest.fixture(scope="module")
def example():
    return json.loads(EXAMPLE.read_text())


def test_example_lists_every_category(example):
    assert set(example) == set(NEWS_CATEGORIES)


def test_example_matches_code_defaults(tmp_data_dir, example):
    defaults = NewsManager(MagicMock()).config
    for category in NEWS_CATEGORIES:
        for field in SCHEDULE_FIELDS:
            assert example[category][field] == defaults[category][field], (category, field)


def _timers_from_install_script() -> dict:
    """category -> (interval_hours, first_minute) parsed from the OnCalendar strings."""
    text = INSTALL_SCRIPT.read_text()
    pattern = re.compile(
        r'create_(?:news|background)_timer\s+"(?P<name>[a-z_]+)"\s+"(?P<cal>[^"]+)"'
    )
    # Expand the shell variables the script uses for the calendar strings.
    assignments = dict(re.findall(r'^([A-Z_]+_CALENDAR)="([^"]+)"', text, re.MULTILINE))
    timers = {}
    for m in pattern.finditer(text):
        cal = m.group("cal")
        cal = re.sub(r"\$\{?([A-Z_]+)\}?", lambda v: assignments.get(v.group(1), v.group(0)), cal)
        _date, hours, minutes, _seconds = re.match(r"(\S+) ([^:]+):([^:]+):(\d+)$", cal).groups()
        per_day = 24 if hours == "*" else len(hours.split(","))
        runs_per_hour = len(minutes.split(","))
        interval = 24 / (per_day * runs_per_hour)
        timers[m.group("name")] = (interval, int(minutes.split(",")[0]))
    return timers


def test_example_matches_installed_timers(example):
    timers = _timers_from_install_script()
    for category in NEWS_CATEGORIES:
        assert category in timers, f"install-systemd.sh writes no timer for {category}"
        interval, minute = timers[category]
        assert example[category]["interval_hours"] == interval, category
        assert example[category]["minute_offset"] == minute, category
