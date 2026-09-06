# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`.env.example` must document exactly the `EVENTS_*` variables the config
loader reads: no missing line for an operator to discover the hard way, and
no leftover key the loader stopped reading.

The EVENTS_ block was written by hand and never checked against
`_load_events`. This test only ever reports variable NAMES; it never reads,
compares or prints a value from `.env.example`, which on a developer's
machine may sit next to a real `.env`.
"""

import re
from pathlib import Path
from typing import Mapping

from utils import config

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / '.env.example'

# KEY= at the start of a line, with or without an `export` prefix. The
# value is deliberately not captured.
_KEY_LINE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=')


class _Recorder(Mapping):
    """An empty environment that remembers which names were asked for, so
    the expected set comes from the loader itself rather than a list here
    that could drift away from it."""

    def __init__(self):
        self.names: set[str] = set()

    def __getitem__(self, key):
        self.names.add(key)
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


def _names_the_loader_reads() -> set[str]:
    recorder = _Recorder()
    config._load_events(config._Reader(recorder, None))
    return {name for name in recorder.names if name.startswith('EVENTS_')}


def _names_in_env_example() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE.read_text(encoding='utf-8').splitlines():
        if line.lstrip().startswith('#'):
            continue
        match = _KEY_LINE.match(line)
        if match:
            keys.add(match.group(1))
    return {name for name in keys if name.startswith('EVENTS_')}


def test_env_example_documents_every_events_variable():
    missing = sorted(_names_the_loader_reads() - _names_in_env_example())
    assert not missing, f'.env.example is missing: {", ".join(missing)}'


def test_env_example_has_no_events_variable_the_loader_ignores():
    unknown = sorted(_names_in_env_example() - _names_the_loader_reads())
    assert not unknown, f'.env.example documents keys _load_events never reads: {", ".join(unknown)}'


def test_the_loader_reads_the_documented_events_surface():
    # A guard on the guard: if _load_events stopped reading anything, or
    # the parser stopped finding keys, the two tests above would pass
    # vacuously on two empty sets.
    read = _names_the_loader_reads()
    assert 'EVENTS_ENABLED' in read and len(read) > 5
    assert len(_names_in_env_example()) > 5
