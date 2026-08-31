# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the Arch/Nix banter cog and roaster personas."""

import types

import pytest

from cogs.arch_banter import ArchBanter


@pytest.fixture
def banter(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ARCH_BANTER_LLM', 'false')
    cog = ArchBanter(bot=types.SimpleNamespace())
    cog.cooldown_seconds = 0
    return cog


def make_message(content, user_id=1):
    sent = []

    async def send(text, **kw):
        sent.append(text)

    author = types.SimpleNamespace(id=user_id, bot=False, name=f'u{user_id}',
                                   display_name=f'u{user_id}',
                                   mention=f'<@{user_id}>')
    message = types.SimpleNamespace(
        content=content, author=author,
        guild=types.SimpleNamespace(id=1, name='g'),
        channel=types.SimpleNamespace(id=2, name='general', send=send),
    )
    message.sent = sent
    return message


async def test_arch_mention_gets_an_arch_joke(banter):
    msg = make_message('i use arch btw', user_id=10)
    await banter.on_message(msg)
    assert len(msg.sent) == 1
    joke = msg.sent[0].replace('<@10> ', '')
    assert joke in banter.ARCH_JOKES or joke in banter.HOUSE_JOKES


async def test_nix_mention_gets_a_nix_joke(banter):
    msg = make_message('rewrote my whole flake.nix again last night', user_id=11)
    await banter.on_message(msg)
    assert len(msg.sent) == 1
    joke = msg.sent[0].replace('<@11> ', '')
    assert joke in banter.NIX_JOKES


async def test_nixos_and_home_manager_trigger(banter):
    for i, text in enumerate((
        'finally installed NixOS on the laptop',
        'home-manager broke my shell again',
        'nix-shell -p makes me feel powerful',
    )):
        msg = make_message(text, user_id=20 + i)
        await banter.on_message(msg)
        assert len(msg.sent) == 1, text


async def test_nix_slang_and_unix_do_not_trigger(banter):
    # 'nix' the verb and 'unix' the word must not summon the roaster
    for i, text in enumerate((
        'lets nix that idea entirely',
        'unix philosophy is underrated',
        'the phoenix rises again',
    )):
        msg = make_message(text, user_id=30 + i)
        await banter.on_message(msg)
        assert msg.sent == [], text


async def test_arch_wins_when_both_are_mentioned(banter):
    msg = make_message('migrating from arch linux to nixos this weekend', user_id=40)
    await banter.on_message(msg)
    assert len(msg.sent) == 1
    joke = msg.sent[0].replace('<@40> ', '')
    assert joke in banter.ARCH_JOKES or joke in banter.HOUSE_JOKES


async def test_house_joke_surfaces_on_its_rotation(banter, monkeypatch):
    import cogs.arch_banter as module
    monkeypatch.setattr(module.random, 'random', lambda: 0.0)   # force the gag
    msg = make_message('arch is the best distro', user_id=50)
    await banter.on_message(msg)
    joke = msg.sent[0]
    assert 'no-shower' in joke or 'no-touch-grass' in joke or 'touch-grass' in joke


def test_house_joke_chance_is_occasional_not_constant(banter):
    assert 0 < banter.HOUSE_JOKE_CHANCE <= 0.2


async def test_nix_roaster_persona_exists():
    from ai.features.arch_roaster import (
        ARCH_ROAST_SYSTEM_PROMPT, ArchRoaster, NIX_ROAST_SYSTEM_PROMPT,
    )
    assert 'declarative' in NIX_ROAST_SYSTEM_PROMPT
    assert 'no-shower' not in NIX_ROAST_SYSTEM_PROMPT     # the gag is Arch-only
    assert 'no-shower' in ARCH_ROAST_SYSTEM_PROMPT        # ...and Arch has it

    class FakeManager:
        def __init__(self):
            self.calls = []

        async def generate(self, **kw):
            self.calls.append(kw)
            return 'declared bankruptcy, declaratively ❄️'

    manager = FakeManager()
    roaster = ArchRoaster(manager, distro='nix')
    result = await roaster.roast('my flake broke', 'someone')
    assert result
    assert 'NixOS' in manager.calls[0]['prompt']
    assert 'declarative' in manager.calls[0]['system_prompt']
