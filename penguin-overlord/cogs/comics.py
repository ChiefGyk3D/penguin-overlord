# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Comics Cog - Tech humor from multiple sources

Integrates various tech-focused webcomics:
- XKCD (tech/science/cyber humor)
- Joy of Tech (Apple, Linux, geek culture)
- TurnOff.us (Git, DevOps, programmer humor)

Commands:
- !comic random - Random comic from any source
- !comic <source> - Get comic from specific source (xkcd, joyoftech, turnoff)
- !comic_trivia <xkcd_number> - Explain an XKCD comic via explainxkcd API
- !daily_comic - Force post today's tech comic

Admin commands:
- !comic_set_channel <#channel> - Set daily comic channel
- !comic_enable / !comic_disable - Toggle daily posting
"""

import os
import json
import random
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

import aiohttp
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class Comics(commands.Cog):
    """Tech comics from multiple sources"""
    
    DATA_DIR = os.getenv('DATA_DIR') or ('/app/data' if os.path.exists('/app/data') else os.path.join(os.getcwd(), 'data'))
    STATE_PATH = os.getenv('COMIC_STATE_PATH', os.path.join(DATA_DIR, 'comic_state.json'))
    
    # Comic source URLs
    XKCD_API = "https://xkcd.com/info.0.json"
    JOYOFTECH_RSS = "https://www.joyoftech.com/joyoftech/jotblog/index.xml"
    TURNOFF_RSS = "https://turnoff.us/feed.xml"
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None
        self._session_lock = asyncio.Lock()
        self.state_file = Path(self.STATE_PATH)
        
        # Ensure data directory exists
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.error(f'Cannot create data directory {self.state_file.parent} - check Docker volume permissions')
        
        # Load or initialize state
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as fh:
                    self.state = json.load(fh)
            except Exception:
                logger.exception('Failed to load comic state file; resetting')
                self.state = {'last_posted': None, 'channel_id': None, 'enabled': False, 'source': 'random'}
        else:
            self.state = {'last_posted': None, 'channel_id': None, 'enabled': False, 'source': 'random'}
            # Try to write initial state, but don't fail if we can't
            try:
                self._write_state()
            except PermissionError:
                logger.warning('Cannot write initial comic state file - will retry on first update')
        
        # Optionally allow env var to override channel
        env_chan = os.getenv('COMIC_POST_CHANNEL_ID')
        if env_chan and env_chan.isdigit():
            self.state['channel_id'] = int(env_chan)
        
        # Start daily poster (9 AM UTC)
        self.daily_comic_poster.start()
    
    async def _ensure_session(self):
        """Ensure aiohttp session is created"""
        if self.session is None or self.session.closed:
            async with self._session_lock:
                if self.session is None or self.session.closed:
                    self.session = aiohttp.ClientSession()
    
    async def cog_load(self):
        """Initialize aiohttp session when cog loads"""
        await self._ensure_session()
    
    async def cog_unload(self):
        """Cleanup when cog unloads"""
        try:
            self.daily_comic_poster.cancel()
        except Exception:
            pass
        if self.session:
            await self.session.close()
    
    def _write_state(self):
        try:
            with open(self.STATE_PATH, 'w', encoding='utf-8') as fh:
                json.dump(self.state, fh)
        except PermissionError:
            logger.error(f'Permission denied writing to {self.STATE_PATH} - check Docker volume permissions (needs write access)')
        except Exception:
            logger.exception('Failed to write comic state file')
    
    async def _fetch_xkcd(self) -> dict | None:
        """Fetch latest XKCD comic via JSON API"""
        await self._ensure_session()
        try:
            async with self.session.get(self.XKCD_API, timeout=15) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                
                return {
                    'source': 'xkcd',
                    'title': data.get('title', ''),
                    'url': f"https://xkcd.com/{data.get('num', '')}/",
                    'img': data.get('img', ''),
                    'alt': data.get('alt', '')
                }
        except Exception:
            logger.exception('Error fetching XKCD')
            return None
    
    async def _fetch_joyoftech(self) -> dict | None:
        """Fetch latest Joy of Tech comic via RSS"""
        await self._ensure_session()
        try:
            async with self.session.get(self.JOYOFTECH_RSS, timeout=15) as resp:
                if resp.status != 200:
                    return None
                
                xml = await resp.text()
                
                # Extract first item from RSS
                import re
                title_match = re.search(r'<item>.*?<title>(.*?)</title>', xml, re.DOTALL)
                link_match = re.search(r'<item>.*?<link>(.*?)</link>', xml, re.DOTALL)
                # Joy of Tech has img in description with CDATA
                desc_match = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', xml, re.DOTALL)
                
                if title_match and link_match and desc_match:
                    description = desc_match.group(1)
                    # Extract img src from description HTML
                    img_match = re.search(r'<img[^>]*src="([^"]+)"', description)
                    
                    if img_match:
                        return {
                            'source': 'joyoftech',
                            'title': title_match.group(1).strip(),
                            'url': link_match.group(1).strip(),
                            'img': img_match.group(1)
                        }
                return None
        except Exception:
            logger.exception('Error fetching Joy of Tech')
            return None
    
    async def _fetch_turnoff(self) -> dict | None:
        """Fetch latest TurnOff.us comic via RSS"""
        await self._ensure_session()
        try:
            async with self.session.get(self.TURNOFF_RSS, timeout=15) as resp:
                if resp.status != 200:
                    return None
                
                xml = await resp.text()
                
                # Extract first item from RSS
                import re
                title_match = re.search(r'<item>.*?<title>(.*?)</title>', xml, re.DOTALL)
                link_match = re.search(r'<item>.*?<link>(.*?)</link>', xml, re.DOTALL)
                # TurnOff.us has img in description
                desc_match = re.search(r'<item>.*?<description>(.*?)</description>', xml, re.DOTALL)
                
                if title_match and link_match and desc_match:
                    description = desc_match.group(1)
                    # Extract img src from description (may have HTML entities)
                    import html
                    description = html.unescape(description)
                    img_match = re.search(r'<img[^>]*src="([^"]+)"', description)
                    
                    if img_match:
                        return {
                            'source': 'turnoff',
                            'title': title_match.group(1).strip(),
                            'url': link_match.group(1).strip(),
                            'img': img_match.group(1)
                        }
                return None
        except Exception:
            logger.exception('Error fetching TurnOff.us')
            return None
    
    async def _fetch_xkcd_explain(self, comic_num: int) -> str | None:
        """Fetch XKCD explanation from explainxkcd.com"""
        await self._ensure_session()
        try:
            url = f"https://www.explainxkcd.com/wiki/api.php?action=query&prop=extracts&exintro&explaintext&titles={comic_num}&format=json"
            async with self.session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                pages = data.get('query', {}).get('pages', {})
                for page_id, page in pages.items():
                    if page_id != '-1':
                        extract = page.get('extract', '')
                        # Truncate to ~500 chars
                        if len(extract) > 500:
                            extract = extract[:497] + "..."
                        return extract
                return None
        except Exception:
            logger.exception('Error fetching XKCD explanation')
            return None
    
    def _create_embed(self, comic: dict) -> discord.Embed:
        """Create Discord embed for a comic"""
        source_icons = {
            'xkcd': '🤓',
            'joyoftech': '😂',
            'turnoff': '🔧'
        }
        
        source = comic.get('source', 'unknown')
        icon = source_icons.get(source, '📰')
        
        embed = discord.Embed(
            title=f"{icon} {comic.get('title', 'Tech Comic')}",
            url=comic.get('url'),
            color=discord.Color.blue()
        )
        
        embed.set_image(url=comic['img'])
        
        # Add alt text for XKCD if available
        if source == 'xkcd' and comic.get('alt'):
            embed.set_footer(text=f"Alt: {comic['alt'][:200]}")
        else:
            embed.set_footer(text=f"Source: {source.upper()} • Use !comic {source} for more")
        
        return embed
    
    @commands.hybrid_command(name='comic', description='Get a tech comic')
    async def comic(self, ctx: commands.Context, source: str = 'random'):
        """
        Get a tech comic from various sources.
        
        Usage:
            !comic - Random comic from any source
            !comic xkcd - Latest XKCD (tech/science/cyber humor)
            !comic joyoftech - Latest Joy of Tech (geek culture)
            !comic turnoff - Latest TurnOff.us (Git/DevOps humor)
        """
        await ctx.defer()
        
        source = source.lower()
        comic_data = None
        
        if source == 'random':
            # Pick random source
            source = random.choice(['xkcd', 'joyoftech', 'turnoff'])
        
        if source == 'xkcd':
            comic_data = await self._fetch_xkcd()
        elif source in ['joyoftech', 'joy', 'jot']:
            comic_data = await self._fetch_joyoftech()
        elif source in ['turnoff', 'turn']:
            comic_data = await self._fetch_turnoff()
        else:
            await ctx.send(f"❌ Unknown source: `{source}`. Try: `xkcd`, `joyoftech`, `turnoff`, or `random`")
            return
        
        if not comic_data:
            await ctx.send(f"❌ Could not fetch comic from {source}. Try again later.")
            return
        
        embed = self._create_embed(comic_data)
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='comic_trivia', description='Explain an XKCD comic')
    async def comic_trivia(self, ctx: commands.Context, comic_number: int):
        """
        Get an explanation for an XKCD comic from explainxkcd.com
        
        Usage:
            !comic_trivia 353
        """
        await ctx.defer()
        
        explanation = await self._fetch_xkcd_explain(comic_number)
        
        if explanation:
            embed = discord.Embed(
                title=f"🤓 XKCD #{comic_number} Explanation",
                description=explanation,
                url=f"https://www.explainxkcd.com/wiki/index.php/{comic_number}",
                color=discord.Color.green()
            )
            embed.set_footer(text="Source: explainxkcd.com")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Could not find explanation for XKCD #{comic_number}")
    
    @tasks.loop(hours=24)
    async def daily_comic_poster(self):
        """Post a daily tech comic at 9 AM UTC"""
        try:
            if not self.state.get('enabled', False):
                return
            
            chan_id = self.state.get('channel_id')
            if not chan_id:
                return
            
            channel = self.bot.get_channel(int(chan_id))
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(int(chan_id))
                except Exception:
                    logger.exception('Failed to fetch daily comic channel')
                    return
            
            # Pick a random source for daily comic
            source = random.choice(['xkcd', 'joyoftech', 'turnoff'])
            
            if source == 'xkcd':
                comic_data = await self._fetch_xkcd()
            elif source == 'joyoftech':
                comic_data = await self._fetch_joyoftech()
            else:
                comic_data = await self._fetch_turnoff()
            
            if comic_data:
                embed = self._create_embed(comic_data)
                embed.title = f"📰 Daily Tech Comic: {embed.title}"
                await channel.send(embed=embed)
                logger.info('Posted daily comic from %s to channel %s', source, chan_id)
                
                self.state['last_posted'] = datetime.utcnow().isoformat()
                self._write_state()
        except Exception:
            logger.exception('Error in daily comic poster')
    
    @daily_comic_poster.before_loop
    async def before_daily_poster(self):
        """Wait until 9 AM UTC"""
        await self.bot.wait_until_ready()
        
        now = datetime.utcnow()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # If it's past 9 AM today, target tomorrow
        if now.hour >= 9:
            target += timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        logger.info('Daily comic poster will start in %d seconds (at 9 AM UTC)', wait_seconds)
        await asyncio.sleep(wait_seconds)
    
    @commands.hybrid_command(name='daily_comic', description='Force post daily comic now')
    async def daily_comic(self, ctx: commands.Context):
        """Force post today's tech comic"""
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        is_manager = ctx.guild and ctx.author.guild_permissions.manage_guild
        if not (is_owner or is_manager):
            await ctx.send('❌ You do not have permission to run this command')
            return
        
        await ctx.defer()
        
        # Pick random source
        source = random.choice(['xkcd', 'joyoftech', 'turnoff'])
        
        if source == 'xkcd':
            comic_data = await self._fetch_xkcd()
        elif source == 'joyoftech':
            comic_data = await self._fetch_joyoftech()
        else:
            comic_data = await self._fetch_turnoff()
        
        if not comic_data:
            await ctx.send(f"❌ Could not fetch comic from {source}")
            return
        
        embed = self._create_embed(comic_data)
        embed.title = f"📰 Daily Tech Comic: {embed.title}"
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='comic_set_channel', description='Set daily comic channel')
    async def comic_set_channel(self, ctx: commands.Context, channel: str):
        """Set the channel for daily comic posts"""
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        is_manager = ctx.guild and ctx.author.guild_permissions.manage_guild
        if not (is_owner or is_manager):
            await ctx.send('❌ You do not have permission to run this command')
            return
        
        # Parse channel mention or ID
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
        await ctx.send(f'✅ Daily comic channel set to <#{chan_id}>')
    
    @commands.hybrid_command(name='comic_enable', description='Enable daily comic posting')
    async def comic_enable(self, ctx: commands.Context):
        """Enable automatic daily comic posting (owner only)"""
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        if not is_owner:
            await ctx.send('❌ Only the bot owner can enable/disable auto-posting')
            return
        
        self.state['enabled'] = True
        self._write_state()
        await ctx.send('✅ Enabled daily comic posting (9 AM UTC)')
    
    @commands.hybrid_command(name='comic_disable', description='Disable daily comic posting')
    async def comic_disable(self, ctx: commands.Context):
        """Disable automatic daily comic posting (owner only)"""
        is_owner = ctx.bot.owner_id and ctx.author.id == ctx.bot.owner_id
        if not is_owner:
            await ctx.send('❌ Only the bot owner can enable/disable auto-posting')
            return
        
        self.state['enabled'] = False
        self._write_state()
        await ctx.send('✅ Disabled daily comic posting')


async def setup(bot: commands.Bot):
    await bot.add_cog(Comics(bot))
    logger.info('Comics cog loaded')
