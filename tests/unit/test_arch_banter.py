# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the Arch/Nix banter cog and roaster personas."""

import types

import pytest

from cogs.arch_banter import ArchBanter
from tests.conftest import bot_with_config


@pytest.fixture
def banter(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ARCH_BANTER_LLM', 'false')
    cog = ArchBanter(bot=types.SimpleNamespace())
    cog.cooldown_seconds = 0
    return cog


def test_llm_switch_comes_from_the_bots_typed_config(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ARCH_BANTER_LLM', 'false')      # env says off
    cog = ArchBanter(bot=bot_with_config(ARCH_BANTER_LLM='true'))
    assert cog.llm_enabled is True


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
    from ai.features.roast_loader import load_roast_data

    # The stereotype list moved out of the prompt into the data file's
    # `angles`; the prompt template keeps a placeholder for the rotation.
    assert '{angles}' in NIX_ROAST_SYSTEM_PROMPT
    assert any('declarative' in a for a in load_roast_data('nix').angles)
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
    system = manager.calls[0]['system_prompt']
    assert 'NixOS users' in system and '{angles}' not in system
    assert any(a in system for a in load_roast_data('nix').angles)


# -- data-driven jokes ------------------------------------------------------

def test_joke_banks_come_from_the_shipped_data(banter):
    from ai.features.roast_loader import load_roast_data
    assert list(banter.ARCH_JOKES) == list(load_roast_data('arch').fallback_jokes)
    assert list(banter.NIX_JOKES) == list(load_roast_data('nix').fallback_jokes)
    assert len(banter.HOUSE_JOKES) == 3
    assert (len(banter.ARCH_JOKES), len(banter.NIX_JOKES)) == (149, 16)
    assert banter.HOUSE_JOKE_CHANCE == 0.12


def test_class_attributes_still_work_without_an_instance():
    assert len(ArchBanter.ARCH_JOKES) == 149 and len(ArchBanter.HOUSE_JOKES) == 3
    assert ArchBanter.HOUSE_JOKE_CHANCE == 0.12


def test_operator_override_dir_replaces_the_joke_bank(monkeypatch, tmp_path):
    import json
    from tests.unit.test_roast_data import good
    (tmp_path / 'ov').mkdir()
    (tmp_path / 'ov' / 'nix.json').write_text(json.dumps(good(fallback_jokes=['override nix joke'])))
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    cog = ArchBanter(bot=bot_with_config(ARCH_BANTER_DATA_DIR=str(tmp_path / 'ov')))
    assert list(cog.NIX_JOKES) == ['override nix joke']
    assert len(cog.ARCH_JOKES) == 149                      # no arch override: shipped


def test_invalid_override_keeps_the_shipped_bank(monkeypatch, tmp_path):
    (tmp_path / 'nix.json').write_text('{ not json')
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    cog = ArchBanter(bot=bot_with_config(ARCH_BANTER_DATA_DIR=str(tmp_path)))
    assert len(cog.NIX_JOKES) == 16


async def test_stats_embed_still_counts_jokes(banter):
    sent = []

    async def send(*args, **kw):
        sent.append(kw.get('embed'))

    ctx = types.SimpleNamespace(send=send)
    await banter.arch_banter_stats.callback(banter, ctx)
    values = [f.value for f in sent[0].fields]
    assert '149 unique roasts' in values


async def test_roaster_gets_the_cogs_data_and_settings(monkeypatch, tmp_path):
    import ai.manager as manager_module
    monkeypatch.setenv('DATA_DIR', str(tmp_path))

    async def fake_get_manager(_settings=None):
        return object()

    monkeypatch.setattr(manager_module, 'get_ai_manager', fake_get_manager)
    cog = ArchBanter(bot=bot_with_config(
        ARCH_BANTER_LLM='true', ARCH_BANTER_ANGLES_PER_CALL='3', ARCH_BANTER_TEMPERATURE='0.7'))
    roaster = await cog._get_roaster('nix')
    assert roaster._settings.angles_per_call == 3 and roaster._settings.temperature == 0.7
    assert roaster._data.fallback_jokes == tuple(cog.NIX_JOKES)
    assert await cog._get_roaster('nix') is roaster


async def test_ai_none_falls_back_to_the_static_bank(monkeypatch, tmp_path):
    import ai.manager as manager_module
    monkeypatch.setenv('DATA_DIR', str(tmp_path))

    class DeadManager:
        async def generate(self, **kw):
            return None

    async def fake_get_manager(_settings=None):
        return DeadManager()

    monkeypatch.setattr(manager_module, 'get_ai_manager', fake_get_manager)
    cog = ArchBanter(bot=bot_with_config(ARCH_BANTER_LLM='true'))
    cog.cooldown_seconds = 0
    msg = make_message('finally installed NixOS', user_id=60)
    await cog.on_message(msg)
    assert msg.sent[0].replace('<@60> ', '') in cog.NIX_JOKES
