# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the newcomer helper.

A bot that replies to things that were not questions is worse than one that
stays quiet, so most of these are about NOT speaking.
"""

import types
from datetime import datetime, timedelta, timezone

import pytest

from cogs.newcomer_helper import NewcomerHelper, looks_like_resource_request

WATCHED = 1016382144882409594
RESOURCES = 1543285278381449288
RULES = 1543285278381449289
TRUSTED_ROLE = 1018625656055136347


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setenv('HELPER_ENABLED', 'true')
    monkeypatch.setenv('HELPER_CHANNELS', str(WATCHED))
    monkeypatch.setenv('HELPER_RESOURCE_CHANNEL_ID', str(RESOURCES))
    monkeypatch.setenv('HELPER_RULES_CHANNEL_ID', str(RULES))
    monkeypatch.setenv('HELPER_USE_LLM', 'false')
    monkeypatch.setenv('MOD_TRUSTED_ROLES', str(TRUSTED_ROLE))
    monkeypatch.delenv('HELPER_MESSAGE', raising=False)
    return NewcomerHelper(bot=types.SimpleNamespace())


def make_message(content, *, days=1, channel_id=WATCHED, bot=False, roles=()):
    replies = []

    async def reply(text, **kw):
        replies.append((text, kw))

    author = types.SimpleNamespace(
        id=111, bot=bot, display_name='newbie', mention='<@111>',
        joined_at=datetime.now(timezone.utc) - timedelta(days=days),
        roles=[types.SimpleNamespace(id=r) for r in roles],
    )
    author.__str__ = lambda self: 'newbie#0'
    message = types.SimpleNamespace(
        content=content, author=author,
        channel=types.SimpleNamespace(id=channel_id, name='general'),
        guild=types.SimpleNamespace(id=42), reply=reply,
    )
    message.replies = replies
    return message


# -- the pattern layer -------------------------------------------------------

def test_recognises_asking_for_direction():
    for text in (
        'hey where do i start with all this?',
        'How do I get into cybersecurity as a total beginner',
        'what should i learn first, coming from sysadmin work',
        'any good resources for someone new here?',
        'can anyone recommend some courses on this stuff',
        'just joined, any advice on where to begin?',
        'whats the best way to learn pentesting',
        'could someone point me in the right direction',
        'where can i find guides for this',
    ):
        assert looks_like_resource_request(text), text


def test_ignores_everything_that_is_not_a_request():
    for text in (
        'i learned that the hard way yesterday lol',
        'here are some resources i put together for you all',
        'this course was terrible honestly',
        'starting my new job on monday',
        'the book i keep on my desk is great',
        'anyone else watching the stream tonight',
        'i started using arch btw',
    ):
        assert not looks_like_resource_request(text), text


def test_specific_support_questions_are_not_orientation():
    # These want a human with an answer, not a signpost to the pinned channel.
    for text in (
        'any resources on why my nmap scan fails to resolve hostnames?',
        'got a traceback when i run the tool, any guides for that error',
        'my container wont start, any tutorials on debugging this',
    ):
        assert not looks_like_resource_request(text), text


# -- the cog -----------------------------------------------------------------

async def test_new_member_asking_gets_pointed(helper):
    message = make_message('where do i start with cybersecurity?', days=1)
    await helper.on_message(message)

    assert len(message.replies) == 1
    text, kwargs = message.replies[0]
    assert f'<#{RESOURCES}>' in text
    assert f'<#{RULES}>' in text
    assert 'Welcome' in text
    # never pings the room, and does not force a reply-ping either
    assert kwargs['mention_author'] is False
    assert kwargs['allowed_mentions'].everyone is False


async def test_established_member_is_left_alone(helper):
    # Default HELPER_TIERS=new: a two-year regular asking is just chat.
    message = make_message('where do i start with rust?', days=800)
    await helper.on_message(message)
    assert message.replies == []


async def test_channel_cooldown_stops_chatter(helper):
    first = make_message('where do i start?')
    await helper.on_message(first)
    assert len(first.replies) == 1

    second = make_message('any resources for beginners?')
    second.author.id = 222          # different person, same channel
    await helper.on_message(second)
    assert second.replies == []


async def test_user_cooldown_outlasts_the_channel_one(helper):
    helper.cooldown = 0             # channel is free again immediately
    first = make_message('where do i start?')
    await helper.on_message(first)
    assert len(first.replies) == 1

    again = make_message('any tutorials someone can recommend?')
    await helper.on_message(again)   # same author id
    assert again.replies == []


async def test_unwatched_channels_and_bots_are_ignored(helper):
    elsewhere = make_message('where do i start?', channel_id=999999999)
    await helper.on_message(elsewhere)
    assert elsewhere.replies == []

    robot = make_message('where do i start?', bot=True)
    await helper.on_message(robot)
    assert robot.replies == []


async def test_short_messages_are_ignored(helper):
    message = make_message('resources?')
    await helper.on_message(message)
    assert message.replies == []


async def test_disabled_without_a_resource_channel(monkeypatch):
    monkeypatch.setenv('HELPER_ENABLED', 'true')
    monkeypatch.setenv('HELPER_CHANNELS', str(WATCHED))
    monkeypatch.delenv('HELPER_RESOURCE_CHANNEL_ID', raising=False)
    cog = NewcomerHelper(bot=types.SimpleNamespace())
    assert cog.enabled is False


async def test_disabled_without_an_allowlist(monkeypatch):
    monkeypatch.setenv('HELPER_ENABLED', 'true')
    monkeypatch.delenv('HELPER_CHANNELS', raising=False)
    monkeypatch.setenv('HELPER_RESOURCE_CHANNEL_ID', str(RESOURCES))
    cog = NewcomerHelper(bot=types.SimpleNamespace())
    assert cog.enabled is False


# -- message template --------------------------------------------------------

def test_custom_template_is_used(monkeypatch, helper):
    helper.template = 'yo {user}, try {resources}'
    message = make_message('where do i start?')
    assert helper.render(message.author) == f'yo <@111>, try <#{RESOURCES}>'


def test_template_without_a_rules_channel_reads_cleanly(helper):
    helper.rules_channel_id = None
    text = helper.render(make_message('x').author)
    assert 'None' not in text and '<#' in text


def test_bad_placeholder_falls_back_instead_of_going_silent(helper):
    helper.template = 'hello {nonexistent}'
    text = helper.render(make_message('x').author)
    assert f'<#{RESOURCES}>' in text


async def test_llm_veto_is_respected(helper):
    helper.use_llm = True

    async def veto(content, username):
        return False
    helper._confirms = veto

    message = make_message('where do i start with this?')
    await helper.on_message(message)
    assert message.replies == []


async def test_llm_failure_keeps_the_regex_match(helper):
    # A downed second model must not silently disable the feature.
    helper.use_llm = True
    message = make_message('where do i start with this?')
    await helper.on_message(message)
    assert len(message.replies) == 1
