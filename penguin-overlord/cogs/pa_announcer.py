# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The warehouse PA system: every few hours, at a random moment, Penguin
Overlord comes over the speakers with one announcement.

Announcements are dealt from a shuffled bag, so none repeats until the whole
list has played. After each chime the next one is scheduled a random
PA_MIN_INTERVAL_SECONDS to PA_MAX_INTERVAL_SECONDS away. A restart re-rolls
the schedule rather than chiming right away.

Configuration:
    PA_ENABLED=false                 off by default
    PA_CHANNEL_ID=                   where to announce; defaults to the
                                     greeter's general / verify / welcome channel
    PA_MIN_INTERVAL_SECONDS=7200     shortest gap between announcements (2h)
    PA_MAX_INTERVAL_SECONDS=21600    longest gap between announcements (6h)
"""

import logging
import random
import time

import discord
from discord.ext import commands, tasks

from utils.config import section_config
from utils.pa_announcements import PA_ANNOUNCEMENTS

logger = logging.getLogger(__name__)


class PAAnnouncer(commands.Cog):
    """Random announcements over the warehouse PA."""

    def __init__(self, bot):
        self.bot = bot
        settings = section_config(bot, 'greeter')
        self.enabled = settings.pa_enabled
        self.channel_id = (settings.pa_channel_id
                           or settings.general_channel_id
                           or settings.verify_channel_id
                           or settings.channel_id)
        low = max(60.0, settings.pa_min_interval_seconds)
        self.min_interval = low
        self.max_interval = max(low, settings.pa_max_interval_seconds)
        self._bag: list = []
        self._next_at = 0.0

        if self.enabled and self.channel_id is None:
            logger.error('PA_ENABLED but no PA_CHANNEL_ID (or greeter channel) '
                         'is set, so the PA stays off')
            self.enabled = False

    def _schedule(self, now: float):
        self._next_at = now + random.uniform(self.min_interval, self.max_interval)

    def next_announcement(self) -> str:
        """The next line from the shuffled bag; refilled when it runs out."""
        if not self._bag:
            self._bag = list(PA_ANNOUNCEMENTS)
            random.shuffle(self._bag)
        return self._bag.pop()

    async def cog_load(self):
        if not self.enabled:
            return
        self._schedule(time.time())
        self.pa_tick.start()
        logger.info('PA announcer active: every %.0f to %.0f seconds in %s',
                    self.min_interval, self.max_interval, self.channel_id)

    async def cog_unload(self):
        self.pa_tick.cancel()

    async def _announce(self, now: float = None):
        if now is None:
            now = time.time()
        self._schedule(now)
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error('PA channel %s not found', self.channel_id)
            return
        try:
            await channel.send(
                f'📢 *{self.next_announcement()}*',
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logger.exception('Could not send the PA announcement')

    @tasks.loop(seconds=60)
    async def pa_tick(self):
        if time.time() >= self._next_at:
            await self._announce()

    @pa_tick.before_loop
    async def before_pa_tick(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PAAnnouncer(bot))
    logger.info('PAAnnouncer cog loaded')
