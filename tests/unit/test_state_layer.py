# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the shared atomic state layer (utils/state.py)."""

import json
import os
from pathlib import Path

from utils.state import load_json_state, resolve_data_dir, save_json_state, state_path


def test_save_and_load_roundtrip(tmp_path):
    target = tmp_path / "state.json"
    data = {"a": 1, "items": ["x", "y"]}
    assert save_json_state(target, data)
    assert load_json_state(target) == data


def test_save_is_atomic_no_temp_left_behind(tmp_path):
    target = tmp_path / "state.json"
    save_json_state(target, {"v": 1})
    save_json_state(target, {"v": 2})
    assert load_json_state(target) == {"v": 2}
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []


def test_missing_file_returns_default(tmp_path):
    assert load_json_state(tmp_path / "nope.json", default={"d": True}) == {"d": True}
    assert load_json_state(tmp_path / "nope.json", default=None) is None


def test_corrupt_file_is_quarantined_not_swallowed(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"truncated": ')
    result = load_json_state(target, default={"fresh": True})
    assert result == {"fresh": True}
    # Original corrupt content must be preserved for post-mortem
    quarantined = [p for p in tmp_path.iterdir() if "corrupt" in p.name]
    assert len(quarantined) == 1
    assert quarantined[0].read_text() == '{"truncated": '
    assert not target.exists()


def test_resolve_data_dir_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "envdata"))
    assert resolve_data_dir() == Path(tmp_path / "envdata")


def test_resolve_data_dir_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    if not os.path.exists("/app/data"):
        assert resolve_data_dir() == Path("data")


def test_data_dir_is_parsed_in_one_place(monkeypatch, tmp_path):
    # utils/state, utils/database and the config module must agree, because
    # they used to each read DATA_DIR their own way. A pasted value with
    # stray whitespace is where they used to disagree: the config module
    # trims, the bare os.getenv did not, and a " /data " made a directory
    # with spaces in its name.
    from utils.config import load_paths_config
    monkeypatch.setenv("DATA_DIR", f"  {tmp_path / 'envdata'}  ")
    assert resolve_data_dir() == tmp_path / "envdata"
    assert resolve_data_dir() == load_paths_config().data_dir


def test_database_path_comes_from_the_paths_config(monkeypatch, tmp_path):
    from utils.database import ModerationDatabase
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BOT_DATABASE_PATH", raising=False)
    assert ModerationDatabase().path == str(tmp_path / "penguin_overlord.db")
    monkeypatch.setenv("BOT_DATABASE_PATH", "  /elsewhere/mod.db  ")
    assert ModerationDatabase().path == "/elsewhere/mod.db"
    # An explicit path still wins over both.
    assert ModerationDatabase("/given.db").path == "/given.db"


def test_state_path_strips_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert state_path("../../etc/passwd.json") == tmp_path / "passwd.json"
    assert state_path("foo.json") == tmp_path / "foo.json"


def test_save_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "state.json"
    assert save_json_state(target, {"ok": 1})
    assert json.loads(target.read_text()) == {"ok": 1}
