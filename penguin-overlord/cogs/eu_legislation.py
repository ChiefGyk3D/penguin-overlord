# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
EU Legislation Tracker - Monitor European Union legislative activity
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import asyncio
import re
import logging
import json
import os
from datetime import datetime
from html import unescape
from typing import Optional, Literal

logger = logging.getLogger(__name__)

LEGISLATION_SOURCES = {
    'eurlex_parliament_council': {
        'name': 'EUR-Lex - Parliament & Council Legislation',
        'url': 'https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162',
        'emoji': '🇪🇺'
    },
    'eurlex_proposals': {
        'name': 'EUR-Lex - Commission Proposals',
        'url': 'https://eur-lex.europa.eu/EN/display-feed.rss?rssId=161',
        'emoji': '📜'
    },
    'eurlex_official_journal': {
        'name': 'EUR-Lex - Official Journal (Binding Acts)',
        'url': 'https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222',
        'emoji': '📰'
    }
}

# For news manager compatibility
NEWS_SOURCES = LEGISLATION_SOURCES


class EULegislation(commands.Cog):
    """Track European Union legislative activity"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/eu_legislation_state.json'
        self.posted_items = self._load_state()
        self.legislation_auto_poster.start()
        logger.info("EU Legislation cog loaded")
    
    def cog_unload(self):
        self.legislation_auto_poster.cancel()
        if self.session:
            asyncio.create_task(self.session.close())
    
    def _load_state(self) -> dict:
        """Load posted items from state file"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
        return {}
    
    def _save_state(self):
        """Save posted items to state file"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.posted_items, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    def _is_recent(self, item: str, max_days: int = 7) -> bool:
        """Check if item is from the last N days"""
        try:
            from datetime import datetime, timedelta, timezone
            
            # Try to extract publication date
            date_patterns = [
                r'<pubDate>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</pubDate>',
                r'<published>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</published>',
                r'<updated>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</updated>',
                r'<dc:date>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</dc:date>'
            ]
            
            date_str = None
            for pattern in date_patterns:
                match = re.search(pattern, item, re.DOTALL | re.IGNORECASE)
                if match:
                    date_str = match.group(1).strip()
                    break
            
            if not date_str:
                # No date found, assume it's recent to avoid filtering
                return True
            
            # Parse date - handle multiple formats
            from email.utils import parsedate_to_datetime
            try:
                pub_date = parsedate_to_datetime(date_str)
            except:
                # Try ISO format
                try:
                    pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    # Can't parse, assume recent
                    return True
            
            # Check if within max_days
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
            return pub_date > cutoff
            
        except Exception as e:
            logger.debug(f"Error checking date: {e}")
            return True  # On error, assume recent
    
    async def _fetch_rss_feed(self, source_key: str, max_days: int = 7) -> Optional[tuple]:
        """
        Fetch and parse RSS feed for a source.
        
        Args:
            source_key: The source identifier
            max_days: Only return items from the last N days (default 7)
        """
        if source_key not in LEGISLATION_SOURCES:
            return None
        
        source = LEGISLATION_SOURCES[source_key]
        await self._ensure_session()
        
        try:
            async with self.session.get(source['url']) as response:
                if response.status != 200:
                    logger.warning(f"{source['name']}: HTTP {response.status}")
                    return None
                
                content = await response.text()
                
                # Parse RSS/Atom feed
                item_pattern = r'<item>(.*?)</item>' if '<item>' in content else r'<entry>(.*?)</entry>'
                items = re.findall(item_pattern, content, re.DOTALL)
                
                if not items:
                    logger.debug(f"{source['name']}: No items found")
                    return None
                
                # Check each item until we find a recent one that hasn't been posted
                for item in items[:10]:  # Check up to 10 most recent items
                    # Check if item is recent enough
                    if not self._is_recent(item, max_days):
                        continue  # Skip old items
                    
                    # Extract title
                    title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                    title = unescape(title_match.group(1).strip()) if title_match else "No title"
                    
                    # Extract link
                    link_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                    if not link_match:
                        link_match = re.search(r'<link\s+href="([^"]+)"', item)
                    link = link_match.group(1).strip() if link_match else source['url']
                    
                    # Check if already posted
                    if source_key not in self.posted_items:
                        self.posted_items[source_key] = []
                    
                    if link in self.posted_items[source_key]:
                        continue  # Skip already posted
                    
                    # Extract description
                    desc_match = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
                    if not desc_match:
                        desc_match = re.search(r'<summary>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</summary>', item, re.DOTALL)
                    
                    description = ""
                    if desc_match:
                        desc = desc_match.group(1).strip()
                        desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                        desc = unescape(desc)
                        description = desc[:300] + "..." if len(desc) > 300 else desc
                    
                    # Mark as posted
                    self.posted_items[source_key].append(link)
                    self.posted_items[source_key] = self.posted_items[source_key][-50:]  # Keep last 50
                    self._save_state()
                    
                    return title, link, description, source
                
                # No recent unposted items found
                return None
        
        except asyncio.TimeoutError:
            logger.warning(f"{source['name']}: Request timeout")
            return None
        except Exception as e:
            logger.error(f"{source['name']}: Error: {e}")
            return None
    
    @tasks.loop(hours=1)
    async def legislation_auto_poster(self):
        """Auto-post new legislation updates every hour"""
        try:
            # Check if news manager exists and get config
            manager = self.bot.get_cog('NewsManager')
            if manager:
                config = manager.get_category_config('eu_legislation')
                if not config.get('enabled', False):
                    return
                
                channel_id = config.get('channel_id')
                if not channel_id:
                    return
                
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logger.warning(f"Channel not found for EU legislation")
                    return
            else:
                # Fallback: no manager, skip auto-posting
                return
            
            logger.info("Checking EU legislation sources...")
            
            # Fetch all sources
            for source_key in LEGISLATION_SOURCES:
                # Check if source is enabled
                if manager and not manager.is_source_enabled('eu_legislation', source_key):
                    continue
                
                result = await self._fetch_rss_feed(source_key)
                if result:
                    title, link, description, source = result
                    
                    embed = discord.Embed(
                        title=f"{source['emoji']} {title}",
                        url=link,
                        description=description,
                        color=discord.Color.from_rgb(0, 51, 153),  # EU blue
                        timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text=f"Source: {source['name']}")
                    
                    await channel.send(embed=embed)
                    logger.info(f"Posted: {title[:50]}... from {source['name']}")
                    await asyncio.sleep(0.5)  # Rate limiting
        
        except Exception as e:
            logger.error(f"Error in legislation auto-poster: {e}")
    
    @legislation_auto_poster.before_loop
    async def before_legislation_auto_poster(self):
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="eulegislation", description="Manually fetch latest EU legislation")
    @app_commands.describe(source="Legislation source to fetch")
    async def fetch_legislation(
        self,
        interaction: discord.Interaction,
        source: Literal['eurlex', 'europarl_news', 'council_press']
    ):
        """Manually fetch latest legislation from a source"""
        await interaction.response.defer(thinking=True)
        
        result = await self._fetch_rss_feed(source)
        
        if not result:
            await interaction.followup.send(
                f"❌ No new legislation found from {LEGISLATION_SOURCES[source]['name']}"
            )
            return
        
        title, link, description, source_info = result
        
        embed = discord.Embed(
            title=f"{source_info['emoji']} {title}",
            url=link,
            description=description,
            color=discord.Color.from_rgb(0, 51, 153),  # EU blue
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Source: {source_info['name']}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EULegislation(bot))
