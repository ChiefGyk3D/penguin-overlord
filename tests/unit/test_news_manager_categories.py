# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""NewsManager must agree with the real cogs about categories and class names.

Historical bugs: /news list_sources kept a hand-written category -> cog class
map that lacked kev, uk_legislation and vendor_alerts (KeyError) and named the
legislation cogs USLegislationNews/EULegislationNews when the classes are
USLegislation/EULegislation. The prefix fallbacks carried their own category
lists (missing kev and vendor_alerts, uk_legislation twice) and looked up
cogs as f"{category}_news", which matches nothing.
"""

import importlib
from typing import get_args
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from cogs import news_manager
from cogs.news_manager import NEWS_CATEGORIES, NEWS_CATEGORY_COGS, NewsManager
from tests.conftest import bot_with_config

KEV_CHANNEL = '123456789012345678'
TECH_CHANNEL = '234567890123456789'

EXPECTED_CATEGORIES = {
    'cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev',
    'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news',
    'vendor_alerts',
}


def test_category_list_covers_all_eleven():
    assert set(NEWS_CATEGORIES) == EXPECTED_CATEGORIES
    assert len(NEWS_CATEGORIES) == len(set(NEWS_CATEGORIES)), "duplicate category"


def test_slash_literal_matches_category_list():
    """Every /news subcommand offers exactly the shared category list."""
    for command in NewsManager.news_group.commands:
        param = command._params.get('category')
        assert param is not None, f"/news {command.name} has no category param"
        offered = {choice.value for choice in param.choices}
        assert offered == set(NEWS_CATEGORIES), f"/news {command.name}"
    assert set(get_args(news_manager.NewsCategory)) == set(NEWS_CATEGORIES)


def test_default_config_covers_every_category(tmp_data_dir):
    manager = NewsManager(MagicMock())
    assert set(manager.config) == set(NEWS_CATEGORIES)


def test_channel_ids_come_from_the_bots_typed_config(tmp_data_dir, monkeypatch):
    # The environment says one channel, bot.config says another.
    monkeypatch.setenv('NEWS_KEV_CHANNEL_ID', '999999999999999999')
    bot = bot_with_config(NEWS_KEV_CHANNEL_ID=KEV_CHANNEL,
                          NEWS_TECH_CHANNEL_ID=TECH_CHANNEL)
    manager = NewsManager(bot)
    assert manager.config['kev']['channel_id'] == int(KEV_CHANNEL)
    assert manager.config['kev']['enabled'] is True
    assert manager.config['tech']['channel_id'] == int(TECH_CHANNEL)
    # A category with no configured channel stays off.
    assert manager.config['gaming']['channel_id'] is None
    assert manager.config['gaming']['enabled'] is False


@pytest.mark.parametrize("category", sorted(EXPECTED_CATEGORIES))
def test_cog_map_points_at_a_real_cog_class(category):
    """Derived from the real modules so a renamed class fails here, not in prod."""
    module_name, class_name = NEWS_CATEGORY_COGS[category]
    module = importlib.import_module(f"cogs.{module_name}")
    cls = getattr(module, class_name, None)
    assert cls is not None, f"cogs.{module_name} has no class {class_name}"
    assert issubclass(cls, commands.Cog)
    # get_cog() keys on the class name, so the mapped name must be the real one.
    assert cls.__cog_name__ == class_name
    assert getattr(cls, 'NEWS_SOURCES', None) or getattr(module, 'NEWS_SOURCES', None)


def _fake_bot(loaded: dict):
    bot = MagicMock()
    bot.get_cog = MagicMock(side_effect=lambda name: loaded.get(name))
    return bot


def _interaction(admin=True):
    interaction = MagicMock()
    interaction.user.guild_permissions.administrator = admin
    interaction.user.roles = []
    interaction.response.send_message = AsyncMock()
    return interaction


@pytest.mark.parametrize("category", sorted(EXPECTED_CATEGORIES))
async def test_list_sources_finds_the_loaded_cog(tmp_data_dir, category):
    _, class_name = NEWS_CATEGORY_COGS[category]
    cog = MagicMock()
    cog.NEWS_SOURCES = {'example': {'name': 'Example', 'url': 'https://example.invalid/rss'}}
    manager = NewsManager(_fake_bot({class_name: cog}))
    interaction = _interaction()

    await NewsManager.list_sources.callback(manager, interaction, category)

    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert 'embed' in kwargs, interaction.response.send_message.call_args


def _ctx(admin=True):
    ctx = MagicMock()
    ctx.author.guild_permissions.administrator = admin
    ctx.author.roles = []
    ctx.send = AsyncMock()
    return ctx


@pytest.mark.parametrize("category", ['kev', 'vendor_alerts'])
async def test_prefix_enable_accepts_every_category(tmp_data_dir, category):
    manager = NewsManager(_fake_bot({}))
    manager.config[category]['channel_id'] = 123
    ctx = _ctx()

    await NewsManager.news_enable_prefix.callback(manager, ctx, category)

    assert manager.config[category]['enabled'] is True
    sent = ctx.send.call_args.args[0]
    assert 'Invalid category' not in sent


async def test_prefix_disable_looks_up_the_real_cog_name(tmp_data_dir):
    bot = _fake_bot({})
    manager = NewsManager(bot)
    ctx = _ctx()

    await NewsManager.news_disable_prefix.callback(manager, ctx, 'kev')

    assert manager.config['kev']['enabled'] is False
    looked_up = [call.args[0] for call in bot.get_cog.call_args_list]
    assert 'KEVNews' in looked_up
    assert 'kev_news' not in looked_up


async def test_prefix_set_channel_rejects_unknown_but_lists_all(tmp_data_dir):
    manager = NewsManager(_fake_bot({}))
    ctx = _ctx()
    channel = MagicMock()
    channel.id = 42

    await NewsManager.news_set_channel_prefix.callback(manager, ctx, 'nope', channel)

    sent = ctx.send.call_args.args[0]
    assert 'Invalid category' in sent
    for category in EXPECTED_CATEGORIES:
        assert category in sent
    assert sent.count('uk_legislation') == 1
