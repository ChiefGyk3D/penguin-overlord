# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared pytest fixtures. Makes the bot package importable and keeps all
state writes inside a temp directory so tests never touch real data/."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BOT_ROOT = REPO_ROOT / "penguin-overlord"

# Cogs import each other as top-level modules (e.g. `from utils.secrets import ...`),
# mirroring how bot.py runs with CWD=penguin-overlord/.
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Point DATA_DIR (and CWD-relative 'data/') at a temp directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.chdir(tmp_path)
    return data_dir
