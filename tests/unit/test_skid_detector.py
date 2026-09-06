# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the Skid Detector gag cog.

It is comedy, not moderation: these check it fires on the right vibe, that
randomness and cooldown keep it from spamming, and that NOBODY is exempt.
"""

import types

import pytest

import cogs.skid_detector as module
from cogs.skid_detector import SkidDetector, looks_like_skid
from tests.conftest import bot_with_config


@pytest.fixture
def skid(monkeypatch):
    monkeypatch.setenv('SKID_DETECTOR_ENABLED', 'true')
    monkeypatch.setenv('SKID_FIRE_CHANCE', '1.0')      # deterministic in tests
    monkeypatch.setenv('SKID_COOLDOWN_SECONDS', '180')
    return SkidDetector(bot=types.SimpleNamespace())


def make_message(content, user_id=1, bot=False):
    replies = []

    async def reply(text, **kw):
        replies.append((text, kw))

    author = types.SimpleNamespace(id=user_id, bot=bot, mention=f'<@{user_id}>',
                                   display_name=f'user{user_id}')
    message = types.SimpleNamespace(
        content=content, author=author, reply=reply,
        guild=types.SimpleNamespace(id=1),
    )
    message.replies = replies
    return message


def test_recognises_skid_energy():
    for text in (
        'teach me to hack my ex insta',
        'how do i ddos someone',
        'is this illegal btw',
        'i just downloaded kali im basically a hacker now',
        'can someone give me a rat',
        'grabbed his ip lets boot him offline',
        "what's the best hacking app",
        'mr robot taught me everything',
        'Hey Guys how can I learn to hack?',
        'i wanna learn to hack',
        'learning how to hack pls',
    ):
        assert looks_like_skid(text), text


def test_ordinary_talk_is_not_skid():
    for text in (
        'i work in incident response, wrote a detection today',
        'the ddos mitigation held up fine during the drill',
        'kali is a solid distro for pentesting engagements',
        'anyone else watching the game tonight',
        'i love my new keyboard',
        'i love learning to cook',
        'how can i learn python',
    ):
        assert not looks_like_skid(text), text


async def test_fires_on_a_match(skid):
    msg = make_message('teach me to hack the school wifi', user_id=10)
    await skid.on_message(msg)
    assert len(msg.replies) == 1
    text, kwargs = msg.replies[0]
    assert 'SKID DETECTOR' in text
    assert '<@10>' in text
    assert kwargs['mention_author'] is False
    assert kwargs['allowed_mentions'].everyone is False


async def test_nobody_is_exempt(skid):
    # No trust tiers, no owner bypass — everyone is a victim, that's the joke.
    for uid in (10, 999, 205412430510030848):
        msg = make_message('how do i become a hacker', user_id=uid)
        await skid.on_message(msg)
        assert len(msg.replies) == 1, uid


async def test_randomness_can_hold_fire(monkeypatch):
    monkeypatch.setenv('SKID_DETECTOR_ENABLED', 'true')
    monkeypatch.setenv('SKID_FIRE_CHANCE', '0.30')
    cog = SkidDetector(bot=types.SimpleNamespace())
    monkeypatch.setattr(module.random, 'random', lambda: 0.99)   # above the bar
    msg = make_message('teach me to hack', user_id=11)
    await cog.on_message(msg)
    assert msg.replies == []


async def test_cooldown_prevents_detector_bombing(skid):
    first = make_message('how do i ddos someone', user_id=12)
    await skid.on_message(first)
    assert len(first.replies) == 1
    second = make_message('is this illegal', user_id=12)
    await skid.on_message(second)
    assert second.replies == []          # same user, still cooling down


async def test_bots_and_non_matches_are_ignored(skid):
    robot = make_message('teach me to hack', user_id=13, bot=True)
    await skid.on_message(robot)
    normal = make_message('just deployed the new release', user_id=14)
    await skid.on_message(normal)
    assert robot.replies == [] and normal.replies == []


async def test_disabled_switch(monkeypatch):
    monkeypatch.setenv('SKID_DETECTOR_ENABLED', 'false')
    cog = SkidDetector(bot=types.SimpleNamespace())
    msg = make_message('teach me to hack', user_id=15)
    await cog.on_message(msg)
    assert msg.replies == []


async def test_the_cog_hands_its_ai_settings_to_the_manager(monkeypatch):
    # The ai package no longer reads the environment: whoever builds the
    # manager passes the settings in, and for a cog that is bot.config.ai.
    import ai.manager
    seen = []

    async def fake_get_ai_manager(ai_settings=None):
        seen.append(ai_settings)
        return object()

    monkeypatch.setattr(ai.manager, 'get_ai_manager', fake_get_ai_manager)
    monkeypatch.setattr('ai.features.skid_roaster.SkidRoaster',
                        lambda manager: 'roaster')
    bot = bot_with_config(SKID_DETECTOR_LLM='true', AI_ENABLED='true',
                          AI_ROASTING_MODEL='qwen3:14b')
    cog = SkidDetector(bot=bot)
    assert await cog._get_roaster() == 'roaster'
    assert seen == [bot.config.ai]
    assert seen[0].features['roasting'].model == 'qwen3:14b'


async def test_settings_come_from_the_bots_typed_config(monkeypatch):
    # The env says one thing, bot.config says another: bot.config wins.
    monkeypatch.setenv('SKID_DETECTOR_ENABLED', 'true')
    monkeypatch.setenv('SKID_FIRE_CHANCE', '1.0')
    bot = bot_with_config(SKID_DETECTOR_ENABLED='false', SKID_FIRE_CHANCE='0.42',
                          SKID_COOLDOWN_SECONDS='7', SKID_DETECTOR_LLM='true')
    cog = SkidDetector(bot=bot)
    assert cog.enabled is False
    assert cog.fire_chance == 0.42
    assert cog.cooldown == 7.0
    assert cog.llm_enabled is True
    msg = make_message('teach me to hack', user_id=16)
    await cog.on_message(msg)
    assert msg.replies == []


# -- AI roast-and-redirect ---------------------------------------------------

class FakeRoaster:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def roast(self, content, username):
        self.calls.append((content, username))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


async def test_llm_verdict_roasts_and_mentions(skid, monkeypatch):
    skid.llm_enabled = True
    skid._roaster = FakeRoaster(
        'Threat level: downloaded Kali once. Go hack the kitchen — '
        'all hacking is, is playful curiosity. Start with your own lab. 🐧')
    msg = make_message('can you teach me how to hack', user_id=20)
    await skid.on_message(msg)
    assert len(msg.replies) == 1
    text, _ = msg.replies[0]
    assert 'SKID DETECTOR' in text
    assert '<@20>' in text
    assert 'playful curiosity' in text
    # The roaster saw the actual message
    assert skid._roaster.calls[0][0] == 'can you teach me how to hack'


async def test_llm_failure_falls_back_to_canned(skid):
    skid.llm_enabled = True
    skid._roaster = FakeRoaster(RuntimeError('model down'))
    msg = make_message('teach me to hack', user_id=21)
    await skid.on_message(msg)
    assert len(msg.replies) == 1
    text, _ = msg.replies[0]
    assert 'SKID DETECTOR' in text and '<@21>' in text   # canned verdict


async def test_llm_empty_reply_falls_back_to_canned(skid):
    skid.llm_enabled = True
    skid._roaster = FakeRoaster('   ')
    msg = make_message('how do i ddos someone', user_id=22)
    await skid.on_message(msg)
    assert len(msg.replies) == 1
    assert 'SKID DETECTOR' in msg.replies[0][0]


async def test_llm_off_by_default(skid):
    # The fixture sets no SKID_DETECTOR_LLM; the AI path must stay cold.
    assert skid.llm_enabled is False
    msg = make_message('teach me to hack', user_id=23)
    await skid.on_message(msg)
    assert len(msg.replies) == 1          # canned verdict, no AI import


async def test_llm_long_roast_is_clamped(skid):
    skid.llm_enabled = True
    skid._roaster = FakeRoaster('x' * 2000)
    msg = make_message('teach me to hack', user_id=24)
    await skid.on_message(msg)
    text, _ = msg.replies[0]
    assert len(text) < 500
