# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Load every cog into a real (offline) Bot instance.

Importing a cog module is not the same as loading it: setup()/add_cog can
still fail on duplicate command names, bad app-command groups, or task
wiring — and until now nothing outside production startup exercised that
path. No gateway connection is made.
"""

import discord
from discord.ext import commands

from .test_cog_imports import COG_MODULES


async def test_all_cogs_load_and_unload(tmp_data_dir):
    import asyncio

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.help_command = None

    # Auto-poster loops call wait_until_ready in before_loop, which raises on
    # an offline client; park them forever instead so unload cancels cleanly.
    async def parked_forever():
        await asyncio.Event().wait()

    bot.wait_until_ready = parked_forever

    try:
        for module_name in COG_MODULES:
            await bot.load_extension(module_name)

        # Every cog module must have registered exactly one cog
        assert len(bot.cogs) == len(COG_MODULES), (
            f"{len(COG_MODULES)} modules loaded but {len(bot.cogs)} cogs registered"
        )

        # Command-name collisions raise at load time; sanity-check we
        # actually registered a meaningful command surface.
        assert len(list(bot.walk_commands())) > 30
    finally:
        for module_name in list(bot.extensions):
            await bot.unload_extension(module_name)
        await bot.close()
