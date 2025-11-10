# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tech News Cog - General technology and developer news aggregator.
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

logger = logging.getLogger(__name__)


NEWS_SOURCES = {
    'arstechnica': {
        'name': 'Ars Technica (Main)',
        'url': 'https://feeds.arstechnica.com/arstechnica/index',
        'color': 0xFF4F00,
        'icon': '🔬'
    },
    'theverge': {
        'name': 'The Verge',
        'url': 'https://www.theverge.com/rss/index.xml',
        'color': 0xFA4B2A,
        'icon': '📱'
    },
    'techcrunch': {
        'name': 'TechCrunch',
        'url': 'https://techcrunch.com/feed/',
        'color': 0x0AB34F,
        'icon': '🚀'
    },
    'engadget': {
        'name': 'Engadget',
        'url': 'https://www.engadget.com/rss.xml',
        'color': 0x2E5C8A,
        'icon': '📡'
    },
    'phoronix': {
        'name': 'Phoronix (Linux/Hardware)',
        'url': 'https://www.phoronix.com/rss.php',
        'color': 0x15A0DD,
        'icon': '🐧'
    },
    'lwn': {
        'name': 'LWN.net (Linux Weekly News)',
        'url': 'https://lwn.net/headlines/rss',
        'color': 0x336699,
        'icon': '📰'
    },
    'hackaday': {
        'name': 'Hackaday',
        'url': 'https://hackaday.com/blog/feed/',
        'color': 0xF4D03F,
        'icon': '🔧'
    },
    'ieee_spectrum': {
        'name': 'IEEE Spectrum',
        'url': 'https://spectrum.ieee.org/feed',
        'color': 0x00629B,
        'icon': '⚡'
    },
    'tomshardware': {
        'name': "Tom's Hardware",
        'url': 'https://www.tomshardware.com/feeds/all',
        'color': 0xD02B2D,
        'icon': '💻'
    },
    'anandtech': {
        'name': 'AnandTech',
        'url': 'https://www.anandtech.com/rss',
        'color': 0xE74C3C,
        'icon': '🖥️'
    },
    'infoq': {
        'name': 'InfoQ',
        'url': 'https://feeds.infoq.com/',
        'color': 0x1E88E5,
        'icon': '👨‍💻'
    },
    'github_blog': {
        'name': 'GitHub Blog',
        'url': 'https://github.blog/feed/',
        'color': 0x24292E,
        'icon': '🐙'
    },
    'google_dev': {
        'name': 'Google Developers Blog',
        'url': 'https://developers.googleblog.com/feeds/posts/default',
        'color': 0x4285F4,
        'icon': '🔍'
    },
    'cloudflare_eng': {
        'name': 'Cloudflare Engineering',
        'url': 'https://blog.cloudflare.com/tag/engineering/rss/',
        'color': 0xF38020,
        'icon': '☁️'
    },
    'venturebeat': {
        'name': 'VentureBeat (AI/Tech)',
        'url': 'https://venturebeat.com/feed/',
        'color': 0x0A7CFF,
        'icon': '🤖'
    },
    'bbc_tech': {
        'name': 'BBC News - Technology',
        'url': 'http://feeds.bbci.co.uk/news/technology/rss.xml',
        'color': 0xBB1919,
        'icon': '🇬🇧'
    },
    'bbc_science': {
        'name': 'BBC News - Science & Environment',
        'url': 'http://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
        'color': 0xBB1919,
        'icon': '🔬'
    }
}


class TechNews(commands.Cog):
    """Tech news aggregator and poster."""
    
    NEWS_SOURCES = NEWS_SOURCES
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/tech_news_state.json'
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
                logger.error(f"Failed to load tech news state: {e}")
        
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
            logger.error(f"Failed to save tech news state: {e}")
    
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
                
                # Parse RSS/Atom feed
                item_pattern = r'<item>(.*?)</item>' if '<item>' in content else r'<entry>(.*?)</entry>'
                items = re.findall(item_pattern, content, re.DOTALL)
                
                if not items:
                    return None, None, None
                
                item = items[0]
                
                # Extract title
                title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                title = unescape(title_match.group(1).strip()) if title_match else "No title"
                
                # Extract link
                link_match = re.search(r'<link(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                if not link_match:
                    link_match = re.search(r'<link\s+href="([^"]+)"', item)
                link = link_match.group(1).strip() if link_match else source['url']
                
                # Extract description
                desc_match = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
                if not desc_match:
                    desc_match = re.search(r'<summary>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</summary>', item, re.DOTALL)
                
                description = ""
                if desc_match:
                    desc = desc_match.group(1).strip()
                    desc = re.sub(r'<[^>]+>', '', desc)
                    desc = unescape(desc)
                    description = desc[:300] + "..." if len(desc) > 300 else desc
                
                return title, link, description
        
        except Exception as e:
            logger.error(f"Error fetching {source['name']}: {e}")
            return None, None, None
    
    @tasks.loop(hours=6)
    async def news_auto_poster(self):
        """Automatically post tech news."""
        try:
            manager = self.bot.get_cog('NewsManager')
            if not manager:
                return
            
            config = manager.get_category_config('tech')
            
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
                if not manager.is_source_enabled('tech', source_key):
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
            logger.error(f"Error in tech news auto-poster: {e}")
    
    @news_auto_poster.before_loop
    async def before_news_auto_poster(self):
        await self.bot.wait_until_ready()
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    @app_commands.command(name="tech", description="Fetch latest tech news from a specific source")
    @app_commands.describe(source="News source to fetch from")
    async def tech_news(self, interaction: discord.Interaction, source: str):
        """Manually fetch news from a specific source."""
        if source not in NEWS_SOURCES:
            await interaction.response.send_message(
                f"❌ Unknown source. Use `/news list_sources tech` to see available sources.",
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
    await bot.add_cog(TechNews(bot))
    logger.info("Tech News cog loaded")
