# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Metrics Cog - serves Prometheus metrics and tracks gateway health.

Loads as a no-op unless METRICS_ENABLED=true.
"""

import logging

from discord.ext import commands, tasks

from utils import metrics

logger = logging.getLogger(__name__)


class Metrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = metrics.start_metrics_server()
        if self.active:
            self.heartbeat.start()

    async def cog_unload(self):
        if self.heartbeat.is_running():
            self.heartbeat.cancel()

    @tasks.loop(seconds=15)
    async def heartbeat(self):
        connected = self.bot.is_ready() and not self.bot.is_closed()
        metrics.BOT_CONNECTED.set(1 if connected else 0)
        latency = self.bot.latency
        # latency is nan before the first heartbeat ack
        if latency == latency:
            metrics.GATEWAY_LATENCY.set(latency)
        metrics.GUILD_COUNT.set(len(self.bot.guilds))

    @heartbeat.before_loop
    async def before_heartbeat(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Metrics(bot))
    logger.info('Metrics cog loaded')
