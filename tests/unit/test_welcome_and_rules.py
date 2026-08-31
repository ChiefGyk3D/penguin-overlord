# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the welcome greeter (batched) and rules sync."""

import json
import types

import pytest

import cogs.welcome_greeter as greeter_module
from cogs.welcome_greeter import WelcomeGreeter

GENERAL = 1016382144882409594
RULES = 1018640640814366802
RESOURCES = 1275242331632566323
ROLES_CH = 1258855607281127424
ACCESS_ROLE = 1018571935640199219


@pytest.fixture
def greeter(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_RULES_CHANNEL_ID', str(RULES))
    monkeypatch.setenv('WELCOME_RESOURCE_CHANNEL_ID', str(RESOURCES))
    monkeypatch.setenv('WELCOME_ROLES_CHANNEL_ID', str(ROLES_CH))
    monkeypatch.setenv('WELCOME_IMAGE', '')          # no file IO in tests
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


async def gains_role(cog, user_id=42):
    await cog.on_member_update(member(user_id, roles=()),
                               member(user_id, roles=(ACCESS_ROLE,)))


async def test_first_arrival_is_greeted_immediately(greeter):
    await gains_role(greeter)
    assert len(greeter.sent) == 1
    text, kwargs = greeter.sent[0]
    assert '<@42>' in text
    assert f'<#{RULES}>' in text and f'<#{RESOURCES}>' in text and f'<#{ROLES_CH}>' in text
    assert 'Happy Hacking' in text
    assert kwargs['allowed_mentions'].everyone is False


async def test_arrivals_inside_the_cooldown_are_batched(greeter, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(greeter_module.time, 'monotonic', lambda: clock[0])
    delays = []

    async def instant_sleep(d):
        delays.append(d)
    monkeypatch.setattr(greeter_module.asyncio, 'sleep', instant_sleep)

    await gains_role(greeter, 1)
    assert len(greeter.sent) == 1        # quiet minute: immediate

    clock[0] += 10
    await gains_role(greeter, 2)
    clock[0] += 5
    await gains_role(greeter, 3)
    await greeter._flush_task            # let the scheduled flush run

    assert len(greeter.sent) == 2        # ONE message for both arrivals
    text, kwargs = greeter.sent[1]
    assert '<@2>' in text and '<@3>' in text
    assert delays and 45 <= delays[0] <= 60


async def test_nobody_is_ever_greeted_twice(greeter):
    await gains_role(greeter)
    await gains_role(greeter)            # role churn / MEE6 hiccup
    assert len(greeter.sent) == 1
    # and it survives a restart
    fresh = WelcomeGreeter(bot=greeter.bot)
    assert 42 in fresh._welcomed


async def test_huge_batches_mention_a_few_and_count_the_rest(greeter):
    greeter.max_mentions = 3
    members = [member(i) for i in range(100, 120)]
    greeter._pending = members
    await greeter._flush()
    text, kwargs = greeter.sent[0]
    assert '<@100>' in text and '<@102>' in text and '<@103>' not in text
    assert 'and 17 more new friends' in text
    assert len(kwargs['allowed_mentions'].users) == 3


async def test_unrelated_changes_and_bots_are_ignored(greeter):
    await greeter.on_member_update(member(roles=(1,)), member(roles=(1, 2)))
    robot_before = member(roles=(), bot=True)
    robot_after = member(roles=(ACCESS_ROLE,), bot=True)
    await greeter.on_member_update(robot_before, robot_after)
    assert greeter.sent == []


async def test_disabled_without_role_or_channel(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.delenv('WELCOME_ROLE_ID', raising=False)
    monkeypatch.setenv('WELCOME_CHANNEL_ID', str(GENERAL))
    cog = WelcomeGreeter(bot=types.SimpleNamespace())
    assert cog.enabled is False


def test_custom_template_and_fallback(greeter):
    greeter.template = 'yo {users}, tags in {roles}'
    assert greeter.render([member()]) == f'yo <@42>, tags in <#{ROLES_CH}>'
    greeter.template = 'broken {nope}'
    assert f'<#{RULES}>' in greeter.render([member()])


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
