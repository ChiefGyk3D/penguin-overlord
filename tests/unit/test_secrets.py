# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for utils/secrets.py — env fallback, Doppler caching, and defaults."""

import sys
import types

import pytest

from utils import secrets as secrets_mod
from utils.secrets import get_secret, load_secrets_from_doppler


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    secrets_mod.clear_doppler_cache()
    for var in ("DOPPLER_TOKEN", "DOPPLER_PROJECT", "DOPPLER_CONFIG", "SECRETS_MANAGER"):
        monkeypatch.delenv(var, raising=False)
    yield
    secrets_mod.clear_doppler_cache()


def test_env_fallback(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
    assert get_secret("DISCORD", "BOT_TOKEN") == "env-token"


def test_missing_secret_returns_none():
    assert get_secret("DISCORD", "DOES_NOT_EXIST") is None


class FakeSecretsAPI:
    def __init__(self, store, counter):
        self._store = store
        self._counter = counter

    def list(self, project, config):
        self._counter["calls"] += 1
        self._counter["project"] = project
        response = types.SimpleNamespace()
        response.secrets = {k: {"computed": v} for k, v in self._store.items()}
        return response


@pytest.fixture
def fake_doppler(monkeypatch):
    """Install a fake dopplersdk module and return its call counter."""
    counter = {"calls": 0, "project": None}
    store = {"DISCORD_BOT_TOKEN": "doppler-token", "OWNER_ID": "12345"}

    class FakeSDK:
        def set_access_token(self, token):
            self.token = token

        @property
        def secrets(self):
            return FakeSecretsAPI(store, counter)

    module = types.ModuleType("dopplersdk")
    module.DopplerSDK = FakeSDK
    monkeypatch.setitem(sys.modules, "dopplersdk", module)
    monkeypatch.setenv("DOPPLER_TOKEN", "fake-token")
    return counter


def test_doppler_lookup_and_cache(fake_doppler):
    assert get_secret("DISCORD", "BOT_TOKEN") == "doppler-token"
    assert get_secret("DISCORD", "BOT_TOKEN") == "doppler-token"
    assert get_secret("ANY", "OWNER_ID") == "12345"  # bare-key fallback
    # One API fetch total — the old implementation fetched per lookup.
    assert fake_doppler["calls"] == 1


def test_doppler_project_defaults_to_penguin_overlord(fake_doppler):
    get_secret("DISCORD", "BOT_TOKEN")
    assert fake_doppler["project"] == "penguin-overlord"


def test_doppler_beats_env(fake_doppler, monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
    assert get_secret("DISCORD", "BOT_TOKEN") == "doppler-token"


def test_load_secrets_from_doppler_prefix(fake_doppler):
    result = load_secrets_from_doppler("discord")
    assert result == {"bot_token": "doppler-token"}
