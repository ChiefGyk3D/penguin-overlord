# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Gaming News Cog - Gaming industry news aggregator.
"""

import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import re
import json
import os
from datetime import datetime
from html import unescape
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


NEWS_SOURCES = {
    'ign': {
        'name': 'IGN',
        'url': 'https://feeds.ign.com/ign/all',
        'color': 0xD91F26,
        'icon': '🎮'
    },
    'gameinformer': {
        'name': 'Game Informer',
        'url': 'https://www.gameinformer.com/rss',
        'color': 0xFFCC00,
        'icon': '🎯'
    },
    'polygon': {
        'name': 'Polygon',
        'url': 'https://www.polygon.com/rss/index.xml',
        'color': 0xFF3C68,
        'icon': '🔺'
    },
    'pcgamer': {
        'name': 'PC Gamer',
        'url': 'https://www.pcgamer.com/rss/',
        'color': 0xC41230,
        'icon': '💻'
    },
    'eurogamer': {
        'name': 'Eurogamer',
        'url': 'https://www.eurogamer.net/?format=rss',
        'color': 0x003C6C,
        'icon': '🇪🇺'
    },
    'rockpapershotgun': {
        'name': 'Rock Paper Shotgun',
        'url': 'https://www.rockpapershotgun.com/feed',
        'color': 0x2D5677,
        'icon': '✂️'
    },
    'gamespot': {
        'name': 'GameSpot',
        'url': 'https://www.gamespot.com/feeds/mashup/',
        'color': 0xE50914,
        'icon': '🎪'
    },
    'kotaku': {
        'name': 'Kotaku',
        'url': 'https://kotaku.com/rss',
        'color': 0xFF5C00,
        'icon': '🗾'
    },
    'destructoid': {
        'name': 'Destructoid',
        'url': 'https://www.destructoid.com/feed/',
        'color': 0x39B54A,
        'icon': '🤖'
    },
    'nichegamer': {
        'name': 'Niche Gamer',
        'url': 'https://nichegamer.com/feed/',
        'color': 0x9B59B6,
        'icon': '🎲'
    }
}


class GamingNews(commands.Cog):
    """Gaming news aggregator and poster."""
    
    NEWS_SOURCES = NEWS_SOURCES
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/gaming_news_state.json'
        self.state = self._load_state()
        self.news_auto_poster.start()
    
    def cog_unload(self):
        self.news_auto_poster.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())
    
    async def cog_load(self):
        self.session = aiohttp.ClientSession()
    
    def _load_state(self) -> dict:
        """Load state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load gaming news state: {e}")
        
        return {
            'last_posted': {},
            'last_check': None
        }
    
    def _save_state(self):
        """Save state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save gaming news state: {e}")
    
    async def _fetch_rss_feed(self, source_key: str) -> tuple[str, str, str]:
        """Fetch latest article from an RSS feed."""
        source = NEWS_SOURCES.get(source_key)
        if not source:
            return None, None, None
        
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(source['url'], timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {source['name']}: HTTP {response.status}")
                    return None, None, None
                
                content = await response.text()
                
                # Parse RSS/Atom feed using proper XML parser
                # This handles item tags with attributes (e.g., <item rdf:about="...">)
                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    logger.warning(f"XML parse error for {source['name']}: {e}")
                    return None, None, None
                
                # Find items (supports both <item> and <entry> tags)
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if not items:
                    items = root.findall('.//item')
                
                if not items:
                    return None, None, None
                
                item = items[0]
                
                # Extract title
                title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                if title_elem is None:
                    title_elem = item.find('title')
                title = unescape(title_elem.text.strip()) if title_elem is not None and title_elem.text else "No title"
                
                # Extract link
                link_elem = item.find('.//{http://www.w3.org/2005/Atom}link')
                if link_elem is not None and 'href' in link_elem.attrib:
                    link = link_elem.attrib['href'].strip()
                else:
                    link_elem = item.find('link')
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else source['url']
                
                # Extract description
                desc_elem = item.find('.//{http://www.w3.org/2005/Atom}summary')
                if desc_elem is None:
                    desc_elem = item.find('description')
                
                description = ""
                if desc_elem is not None and desc_elem.text:
                    desc = desc_elem.text.strip()
                    desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                    desc = unescape(desc)
                    description = desc[:300] + "..." if len(desc) > 300 else desc
                
                return title, link, description
        
        except Exception as e:
            logger.error(f"Error fetching {source['name']}: {e}")
            return None, None, None
    
    @tasks.loop(hours=6)
    async def news_auto_poster(self):
        """Automatically post gaming news."""
        try:
            manager = self.bot.get_cog('NewsManager')
            if not manager:
                return
            
            config = manager.get_category_config('gaming')
            
            if not config.get('enabled'):
                return
            
            channel_id = config.get('channel_id')
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            # Update interval dynamically
            interval = config.get('interval_hours', 6)
            if interval != self.news_auto_poster.hours:
                self.news_auto_poster.change_interval(hours=interval)
            
            # Post from each enabled source
            for source_key in NEWS_SOURCES.keys():
                if not manager.is_source_enabled('gaming', source_key):
                    continue
                
                title, link, description = await self._fetch_rss_feed(source_key)
                
                if not title or not link:
                    continue
                
                # Check if already posted
                if self.state['last_posted'].get(source_key) == link:
                    continue
                
                source = NEWS_SOURCES[source_key]
                
                embed = discord.Embed(
                    title=f"{source['icon']} {title}",
                    url=link,
                    description=description,
                    color=source['color'],
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text=f"Source: {source['name']}")
                
                try:
                    await channel.send(embed=embed)
                    self.state['last_posted'][source_key] = link
                    self._save_state()
                except Exception as e:
                    logger.error(f"Failed to post from {source['name']}: {e}")
        
        except Exception as e:
            logger.error(f"Error in gaming news auto-poster: {e}")
    
    @news_auto_poster.before_loop
    async def before_news_auto_poster(self):
        await self.bot.wait_until_ready()
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    @app_commands.command(name="gaming", description="Fetch latest gaming news from a specific source")
    @app_commands.describe(source="News source to fetch from")
    async def gaming_news(self, interaction: discord.Interaction, source: str):
        """Manually fetch news from a specific source."""
        if source not in NEWS_SOURCES:
            await interaction.response.send_message(
                f"❌ Unknown source. Use `/news list_sources gaming` to see available sources.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(thinking=True)
        
        title, link, description = await self._fetch_rss_feed(source)
        
        if not title:
            await interaction.followup.send("❌ Failed to fetch news from this source.")
            return
        
        source_info = NEWS_SOURCES[source]
        
        embed = discord.Embed(
            title=f"{source_info['icon']} {title}",
            url=link,
            description=description,
            color=source_info['color'],
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Source: {source_info['name']}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GamingNews(bot))
    logger.info("Gaming News cog loaded")
