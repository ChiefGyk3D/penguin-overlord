# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Required secrets fail closed (ChiefGyk3D/penguin-overlord#339).

One placeholder rule (utils/placeholders.py) is used everywhere a secret is
read: the config loader, the Doppler backend and the Vault backend. An
empty, unset or placeholder DISCORD_BOT_TOKEN refuses to start; a
placeholder DISCORD_OWNER_ID grants nobody admin; a placeholder
DOPPLER_TOKEN is treated as unset and never sent to Doppler. No error
message or log line carries a secret value.
"""

import logging
import sys
import types

import pytest

from utils import secrets as secrets_mod
from utils.config import ConfigError, load_config
from utils.placeholders import is_placeholder

REAL_TOKEN = 'MTIzNDU2Nzg5.fake-token-value.not-real-but-secret'
REAL_ID = '123456789012345678'

PLACEHOLDERS = [
    '', '   ',
    'your_bot_token_here', 'YOUR_BOT_TOKEN_HERE', 'Your_Doppler_Token_Here',
    'changeme', 'ChangeMe-please', 'changeme123',
    '<token>', '<your token>', '  <paste here>  ',
    'example', 'EXAMPLE', 'placeholder', 'PlaceHolder-value',
    'xxx', 'XXXXXXXX', 'xxx-token',
    'dp.st.your_service_token', 'DP.ST.YOUR_SERVICE_TOKEN',
]

REAL_LOOKING = [
    REAL_TOKEN, 'dp.st.prd.AbCdEf123456', 'hvs.CAESIJ1234567890',
    'AIza-fake-gemini-key', '<@123456789012345678>',  # a mention is not a placeholder
]


@pytest.mark.parametrize('value', PLACEHOLDERS)
def test_placeholder_rule_rejects(value):
    assert is_placeholder(value)


@pytest.mark.parametrize('value', REAL_LOOKING)
def test_placeholder_rule_accepts_real_looking_values(value):
    assert not is_placeholder(value)


@pytest.mark.parametrize('value', [v for v in PLACEHOLDERS])
def test_placeholder_bot_token_refuses_to_start(value):
    with pytest.raises(ConfigError) as excinfo:
        load_config({'DISCORD_BOT_TOKEN': value})
    message = str(excinfo.value)
    assert 'DISCORD_BOT_TOKEN' in message
    if value.strip():
        # the message legitimately names the file `.env.example`
        assert value.strip() not in message.replace('.env.example', '')


def test_unset_bot_token_refuses_to_start():
    with pytest.raises(ConfigError, match='DISCORD_BOT_TOKEN'):
        load_config({})


def test_real_bot_token_is_accepted_and_never_printed():
    config = load_config({'DISCORD_BOT_TOKEN': REAL_TOKEN})
    assert config.discord.bot_token.reveal() == REAL_TOKEN
    assert REAL_TOKEN not in repr(config) and REAL_TOKEN not in str(config.discord)


@pytest.mark.parametrize('value', PLACEHOLDERS)
def test_placeholder_owner_id_grants_nobody_admin(value):
    config = load_config({'DISCORD_BOT_TOKEN': REAL_TOKEN, 'DISCORD_OWNER_ID': value})
    assert config.discord.owner_id is None


@pytest.mark.parametrize('value', ['abc', '12', 'admin', '-1', '0'])
def test_non_numeric_owner_id_refuses_to_start_without_echoing_a_secret_sized_value(value):
    with pytest.raises(ConfigError, match='DISCORD_OWNER_ID'):
        load_config({'DISCORD_BOT_TOKEN': REAL_TOKEN, 'DISCORD_OWNER_ID': value})


def test_real_owner_id_is_accepted():
    config = load_config({'DISCORD_BOT_TOKEN': REAL_TOKEN, 'DISCORD_OWNER_ID': REAL_ID})
    assert config.discord.owner_id == int(REAL_ID)


@pytest.mark.parametrize('value', ['your_doppler_token_here', 'changeme', '<token>', 'dp.st.your_x', ''])
def test_placeholder_doppler_token_is_never_sent_anywhere(monkeypatch, caplog, value):
    secrets_mod.clear_doppler_cache()
    monkeypatch.setenv('DOPPLER_TOKEN', value)
    calls = []

    class FakeSDK:
        def set_access_token(self, token):
            calls.append(token)

    monkeypatch.setitem(sys.modules, 'dopplersdk', types.SimpleNamespace(DopplerSDK=FakeSDK))
    with caplog.at_level(logging.DEBUG):
        assert secrets_mod._fetch_doppler_secrets('p', 'c') is None
    assert calls == []
    if value:
        assert value not in caplog.text


def test_placeholder_doppler_token_logs_that_it_is_ignored(monkeypatch, caplog):
    secrets_mod.clear_doppler_cache()
    monkeypatch.setenv('DOPPLER_TOKEN', 'your_doppler_token_here')
    with caplog.at_level(logging.WARNING):
        assert secrets_mod._fetch_doppler_secrets('p', 'c') is None
    assert 'DOPPLER_TOKEN' in caplog.text
    assert 'your_doppler_token_here' not in caplog.text


def test_placeholder_doppler_token_falls_back_to_env(monkeypatch):
    secrets_mod.clear_doppler_cache()
    monkeypatch.setenv('DOPPLER_TOKEN', 'your_doppler_token_here')
    monkeypatch.setenv('DISCORD_BOT_TOKEN', REAL_TOKEN)
    monkeypatch.delenv('SECRETS_MANAGER', raising=False)
    assert secrets_mod.get_secret('DISCORD', 'BOT_TOKEN') == REAL_TOKEN


def test_placeholder_env_value_is_not_returned_by_get_secret(monkeypatch):
    secrets_mod.clear_doppler_cache()
    monkeypatch.delenv('DOPPLER_TOKEN', raising=False)
    monkeypatch.delenv('SECRETS_MANAGER', raising=False)
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'your_bot_token_here')
    assert secrets_mod.get_secret('DISCORD', 'BOT_TOKEN') is None


def test_placeholder_vault_token_is_not_used(monkeypatch, caplog):
    monkeypatch.setenv('SECRETS_VAULT_URL', 'https://vault.example.invalid')
    monkeypatch.setenv('SECRETS_VAULT_TOKEN', 'your_vault_token_here')
    with caplog.at_level(logging.WARNING):
        assert secrets_mod.load_secrets_from_vault('secret/data/x') == {}
    assert 'SECRETS_VAULT_TOKEN' in caplog.text
    assert 'your_vault_token_here' not in caplog.text
