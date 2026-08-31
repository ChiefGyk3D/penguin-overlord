# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the welcome greeter and rules sync."""

import json
import types

import pytest

from cogs.welcome_greeter import WelcomeGreeter

GENERAL = 1016382144882409594
RULES = 1018640640814366802
RESOURCES = 1275242331632566323
ROLES_CH = 1258855607281127424
ACCESS_ROLE = 555000111222333444


@pytest.fixture
def greeter(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_RULES_CHANNEL_ID', str(RULES))
    monkeypatch.setenv('WELCOME_RESOURCE_CHANNEL_ID', str(RESOURCES))
    monkeypatch.setenv('WELCOME_ROLES_CHANNEL_ID', str(ROLES_CH))
    monkeypatch.delenv('WELCOME_MESSAGE', raising=False)

    sent = []

    class Channel:
        id = GENERAL

        async def send(self, text, **kw):
            sent.append((text, kw))

    channel = Channel()
    cog = WelcomeGreeter(bot=types.SimpleNamespace(
        get_channel=lambda cid: channel if cid == GENERAL else None))
    cog.sent = sent
    return cog


def member(user_id=42, roles=(), bot=False):
    m = types.SimpleNamespace(
        id=user_id, bot=bot, mention=f'<@{user_id}>',
        roles=[types.SimpleNamespace(id=r) for r in roles],
    )
    m.__str__ = lambda self: f'user{user_id}'
    return m


async def test_greets_once_on_gaining_the_access_role(greeter):
    await greeter.on_member_update(member(roles=()), member(roles=(ACCESS_ROLE,)))
    assert len(greeter.sent) == 1
    text, kwargs = greeter.sent[0]
    assert '<@42>' in text
    assert f'<#{RULES}>' in text and f'<#{RESOURCES}>' in text
    assert kwargs['allowed_mentions'].everyone is False

    # role churn (removed, re-granted) must not greet again — ever
    await greeter.on_member_update(member(roles=()), member(roles=(ACCESS_ROLE,)))
    assert len(greeter.sent) == 1


async def test_greeted_set_survives_restart(greeter, monkeypatch, tmp_path):
    await greeter.on_member_update(member(roles=()), member(roles=(ACCESS_ROLE,)))
    fresh = WelcomeGreeter(bot=greeter.bot)
    assert 42 in fresh._welcomed


async def test_unrelated_role_changes_are_ignored(greeter):
    await greeter.on_member_update(member(roles=(1,)), member(roles=(1, 2)))
    await greeter.on_member_update(member(roles=(ACCESS_ROLE,)),
                                   member(roles=(ACCESS_ROLE, 2)))
    robot = member(roles=(ACCESS_ROLE,), bot=True)
    await greeter.on_member_update(member(roles=(), bot=True), robot)
    assert greeter.sent == []


async def test_bulk_role_sync_does_not_flood_general(greeter):
    greeter.max_per_minute = 3
    for user_id in range(100, 110):
        await greeter.on_member_update(
            member(user_id, roles=()), member(user_id, roles=(ACCESS_ROLE,)))
    # capped at the flood guard; the skipped members are marked greeted so a
    # later role touch cannot greet them out of context
    assert len(greeter.sent) == 3
    assert len(greeter._welcomed) == 10


async def test_disabled_without_role_or_channel(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.delenv('WELCOME_ROLE_ID', raising=False)
    monkeypatch.setenv('WELCOME_CHANNEL_ID', str(GENERAL))
    cog = WelcomeGreeter(bot=types.SimpleNamespace())
    assert cog.enabled is False


def test_custom_template_and_fallback(greeter):
    greeter.template = 'hey {user}, roles live in {roles}'
    text = greeter.render(member())
    assert text == f'hey <@42>, roles live in <#{ROLES_CH}>'
    greeter.template = 'broken {nope}'
    assert f'<#{RULES}>' in greeter.render(member())


# -- rules cache -> moderation prompt ----------------------------------------

def test_cached_rules_reach_the_moderation_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    (tmp_path / 'server_rules.json').write_text(json.dumps({
        'text': 'Rule 1: Be excellent to each other.\nRule 2: No doxxing.',
        'channel_id': RULES, 'synced_at': 'x',
    }))
    import ai.features.moderation as mod
    monkeypatch.setattr(mod, '_RULES_CACHE', None)
    prompt = mod.moderation_system_prompt()
    assert "THIS SERVER'S OWN RULES" in prompt
    assert 'Be excellent to each other' in prompt
    # rules come before the generic instructions
    assert prompt.index('OWN RULES') < prompt.index('content moderation assistant')


def test_missing_rules_cache_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    import ai.features.moderation as mod
    monkeypatch.setattr(mod, '_RULES_CACHE', None)
    assert "OWN RULES" not in mod.moderation_system_prompt()
