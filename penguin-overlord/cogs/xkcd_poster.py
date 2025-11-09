# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Automated XKCD Poster Cog

Periodically polls the XKCD API and posts new comics to a configured
Discord channel. State is persisted to `data/xkcd_state.json` so the
bot remembers the last posted comic across restarts.

Configuration:
- XKCD_POST_CHANNEL_ID (env) - optional channel ID to post to
- XKCD_POLL_INTERVAL_MINUTES (env) - polling interval (default 30)

Commands (admin only):
- !xkcd_set_channel <channel_id|#channel> - set posting channel
- !xkcd_enable / !xkcd_disable - enable/disable automatic posting
- !xkcd_post_now - force post latest XKCD immediately
"""

import os
import json
import asyncio
import logging
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class XKCDPoster(commands.Cog):
    STATE_PATH = os.getenv('XKCD_STATE_PATH', os.path.join(os.getcwd(), 'data', 'xkcd_state.json'))
    API_URL = 'https://xkcd.com/info.0.json'

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_minutes = int(os.getenv('XKCD_POLL_INTERVAL_MINUTES', '30'))
        # Ensure data directory exists
        state_file = Path(self.STATE_PATH)
        state_file.parent.mkdir(parents=True, exist_ok=True)

        # Load or initialize state
        if state_file.exists():
            try:
                with state_file.open('r', encoding='utf-8') as fh:
                    self.state = json.load(fh)
            except Exception:
                logger.exception('Failed to load XKCD state file; resetting')
                self.state = {'last_posted': 0, 'channel_id': None, 'enabled': True}
        else:
            self.state = {'last_posted': 0, 'channel_id': None, 'enabled': True}
            self._write_state()

        # Optionally allow env var to override channel
        env_chan = os.getenv('XKCD_POST_CHANNEL_ID')
        if env_chan and env_chan.isdigit():
            self.state['channel_id'] = int(env_chan)

        # Change loop interval dynamically before starting
        self.poll_loop.change_interval(minutes=self.poll_minutes)
        
        # Start background task
        self.poll_loop.start()

    def cog_unload(self):
        try:
            self.poll_loop.cancel()
        except Exception:
            pass

    def _write_state(self):
        try:
            with open(self.STATE_PATH, 'w', encoding='utf-8') as fh:
                json.dump(self.state, fh)
        except Exception:
            logger.exception('Failed to write XKCD state file')

    async def _fetch_latest(self) -> dict | None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.API_URL, timeout=20) as resp:
                    if resp.status != 200:
                        logger.warning('XKCD fetch returned status %s', resp.status)
                        return None
                    return await resp.json()
        except asyncio.TimeoutError:
            logger.warning('Timeout fetching XKCD')
            return None
        except Exception:
            logger.exception('Error fetching XKCD')
            return None

    def _create_embed(self, comic: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"#{comic['num']}: {comic['title']}",
            url=f"https://xkcd.com/{comic['num']}",
            color=discord.Color.blue()
        )
        embed.set_image(url=comic['img'])
        if comic.get('alt'):
            embed.description = f"_{comic['alt']}_"
        try:
            year = int(comic.get('year', 0))
            month = int(comic.get('month', 0))
            day = int(comic.get('day', 0))
            embed.set_footer(text=f"Published: {year}-{month:02d}-{day:02d}")
        except Exception:
            pass
        return embed

    @tasks.loop(minutes=30)
    async def poll_loop(self):
        """Poll XKCD API and post new comics if found."""
        try:
            # Skip if disabled
            if not self.state.get('enabled', True):
                return

            latest = await self._fetch_latest()
            if latest and isinstance(latest, dict):
                latest_num = int(latest.get('num', 0))
                last_posted = int(self.state.get('last_posted', 0) or 0)
                if latest_num > last_posted:
                    chan_id = self.state.get('channel_id')
                    if chan_id:
                        channel = self.bot.get_channel(int(chan_id))
                        if channel is None:
                            # Try fetch
                            try:
                                channel = await self.bot.fetch_channel(int(chan_id))
                            except Exception:
                                logger.exception('Failed to fetch channel %s', chan_id)
                                return

                        if channel:
                            embed = self._create_embed(latest)
                            try:
                                await channel.send(embed=embed)
                                logger.info('Posted XKCD #%s to channel %s', latest_num, chan_id)
                                self.state['last_posted'] = latest_num
                                self._write_state()
                            except Exception:
                                logger.exception('Failed to send XKCD to channel')
                    else:
                        logger.info('XKCD new comic %s but no channel configured', latest_num)
        except Exception:
            logger.exception('Error in XKCD poll loop')

    @poll_loop.before_loop
    async def before_poll(self):
        # Delay initial poll slightly to stagger startup
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)

    # Admin commands to manage the poster
    @commands.hybrid_command(name='xkcd_set_channel', description='Set channel ID for automated XKCD posts')
    async def xkcd_set_channel(self, ctx: commands.Context, channel: str):
        # Permission: owner or manage_guild
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        is_manager = ctx.guild and ctx.author.guild_permissions.manage_guild
        if not (is_owner or is_manager):
            await ctx.send('❌ You do not have permission to run this command')
            return

        # Accept channel mention like <#1234> or raw ID
        chan_id = None
        if channel.startswith('<#') and channel.endswith('>'):
            chan_id = channel[2:-1]
        else:
            chan_id = channel

        if not chan_id.isdigit():
            await ctx.send('❌ Please specify a valid channel ID or mention')
            return

        self.state['channel_id'] = int(chan_id)
        self._write_state()
        await ctx.send(f'✅ XKCD auto-post channel set to <#{chan_id}>')

    @commands.hybrid_command(name='xkcd_enable', description='Enable automatic XKCD posting')
    async def xkcd_enable(self, ctx: commands.Context):
        """Enable automatic XKCD posting (owner only)"""
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        if not is_owner:
            await ctx.send('❌ Only the bot owner can enable/disable auto-posting')
            return
        self.state['enabled'] = True
        self._write_state()
        await ctx.send('✅ Enabled automatic XKCD posting')

    @commands.hybrid_command(name='xkcd_disable', description='Disable automatic XKCD posting')
    async def xkcd_disable(self, ctx: commands.Context):
        """Disable automatic XKCD posting (owner only)"""
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        if not is_owner:
            await ctx.send('❌ Only the bot owner can enable/disable auto-posting')
            return
        self.state['enabled'] = False
        self._write_state()
        await ctx.send('✅ Disabled automatic XKCD posting')

    @commands.hybrid_command(name='xkcd_post_now', description='Force post the latest XKCD now')
    async def xkcd_post_now(self, ctx: commands.Context):
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        is_manager = ctx.guild and ctx.author.guild_permissions.manage_guild
        if not (is_owner or is_manager):
            await ctx.send('❌ You do not have permission to run this command')
            return

        latest = await self._fetch_latest()
        if not latest:
            await ctx.send('❌ Could not fetch latest XKCD')
            return

        embed = self._create_embed(latest)
        # If channel configured, send there; otherwise send in invoking channel
        chan_id = self.state.get('channel_id')
        target = None
        if chan_id:
            target = self.bot.get_channel(int(chan_id))
            if target is None:
                try:
                    target = await self.bot.fetch_channel(int(chan_id))
                except Exception:
                    target = None

        if target:
            await target.send(embed=embed)
            self.state['last_posted'] = int(latest.get('num', 0))
            self._write_state()
            await ctx.send(f'✅ Posted latest XKCD #{latest.get("num")} to <#{chan_id}>')
        else:
            await ctx.send(embed=embed)
            self.state['last_posted'] = int(latest.get('num', 0))
            self._write_state()


async def setup(bot: commands.Bot):
    await bot.add_cog(XKCDPoster(bot))
    logger.info('XKCDPoster cog loaded')
