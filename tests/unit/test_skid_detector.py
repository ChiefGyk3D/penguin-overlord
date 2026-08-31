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

    author = types.SimpleNamespace(id=user_id, bot=bot, mention=f'<@{user_id}>')
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
    ):
        assert looks_like_skid(text), text


def test_ordinary_talk_is_not_skid():
    for text in (
        'i work in incident response, wrote a detection today',
        'the ddos mitigation held up fine during the drill',
        'kali is a solid distro for pentesting engagements',
        'anyone else watching the game tonight',
        'i love my new keyboard',
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
