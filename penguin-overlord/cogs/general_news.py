# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
General News Tracker - Monitor general news from major outlets
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
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

NEWS_SOURCES = {
    'npr_news': {
        'name': 'NPR News',
        'url': 'https://feeds.npr.org/1001/rss.xml',
        'emoji': '📻'
    },
    'pbs_economy': {
        'name': 'PBS NewsHour - Economy',
        'url': 'https://www.pbs.org/newshour/feeds/rss/economy',
        'emoji': '📺'
    },
    'financial_times': {
        'name': 'Financial Times',
        'url': 'https://www.ft.com/news-feed?format=rss',
        'emoji': '💼'
    },
    'pew_research': {
        'name': 'Pew Research Center',
        'url': 'https://www.pewresearch.org/feed/',
        'emoji': '📊'
    },
    'nyt_homepage': {
        'name': 'New York Times - Homepage',
        'url': 'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml',
        'emoji': '📰'
    },
    'foreign_affairs': {
        'name': 'Foreign Affairs',
        'url': 'https://www.foreignaffairs.com/rss.xml',
        'emoji': '🌍'
    },
    'politico': {
        'name': 'Politico',
        'url': 'https://www.politico.com/rss/politicopicks.xml',
        'emoji': '🏛️'
    },
    'bbc_health': {
        'name': 'BBC News - Health',
        'url': 'http://feeds.bbci.co.uk/news/health/rss.xml',
        'emoji': '🏥'
    },
    'bbc_uk': {
        'name': 'BBC News - UK',
        'url': 'http://feeds.bbci.co.uk/news/uk/rss.xml',
        'emoji': '🇬🇧'
    },
    'bbc_world': {
        'name': 'BBC News - World',
        'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',
        'emoji': '🌍'
    },
    'bbc_news': {
        'name': 'BBC News - Top Stories',
        'url': 'http://feeds.bbci.co.uk/news/rss.xml',
        'emoji': '📰'
    },
    'bbc_politics': {
        'name': 'BBC News - Politics',
        'url': 'http://feeds.bbci.co.uk/news/politics/rss.xml',
        'emoji': '🏛️'
    }
}


class GeneralNews(commands.Cog):
    """Track general news from major news outlets"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/general_news_state.json'
        self.posted_items = self._load_state()
        # Global BBC deduplication - track URLs across all BBC feeds
        self.bbc_posted_urls = set()
        self.news_auto_poster.start()
        logger.info("General News cog loaded")
    
    def cog_unload(self):
        self.news_auto_poster.cancel()
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
        if source_key not in NEWS_SOURCES:
            return None
        
        source = NEWS_SOURCES[source_key]
        await self._ensure_session()
        
        try:
            async with self.session.get(source['url']) as response:
                if response.status != 200:
                    logger.warning(f"{source['name']}: HTTP {response.status}")
                    return None
                
                content = await response.text()
                
                # Parse RSS/Atom feed using proper XML parser
                # This handles item tags with attributes (e.g., <item rdf:about="...">)
                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    logger.warning(f"XML parse error for {source['name']}: {e}")
                    return None
                
                # Find items (supports both <item> and <entry> tags)
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if not items:
                    items = root.findall('.//item')
                
                if not items:
                    logger.debug(f"{source['name']}: No items found")
                    return None
                
                # Check each item until we find a recent one that hasn't been posted
                for item in items[:10]:  # Check up to 10 most recent items
                    # Convert item to string for date checking (maintains old behavior)
                    item_str = ET.tostring(item, encoding='unicode')
                    
                    # Check if item is recent enough
                    if not self._is_recent(item_str, max_days):
                        continue  # Skip old items
                    
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
                    
                    # Check if already posted
                    if source_key not in self.posted_items:
                        self.posted_items[source_key] = []
                    
                    if link in self.posted_items[source_key]:
                        continue  # Skip already posted
                    
                    # For BBC feeds, also check global deduplication across all BBC feeds
                    if source_key.startswith('bbc_'):
                        if link in self.bbc_posted_urls:
                            logger.debug(f"Skipping BBC duplicate across feeds: {title}")
                            continue
                    
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
                    
                    # Mark as posted
                    self.posted_items[source_key].append(link)
                    self.posted_items[source_key] = self.posted_items[source_key][-50:]  # Keep last 50
                    
                    # Track BBC URLs globally to prevent cross-feed duplicates
                    if source_key.startswith('bbc_'):
                        self.bbc_posted_urls.add(link)
                        # Keep BBC dedup set reasonable size (last 200 URLs)
                        if len(self.bbc_posted_urls) > 200:
                            # Convert to list, keep last 200, back to set
                            self.bbc_posted_urls = set(list(self.bbc_posted_urls)[-200:])
                    
                    # Track BBC URLs globally to prevent cross-feed duplicates
                    if source_key.startswith('bbc_'):
                        self.bbc_posted_urls.add(link)
                        # Keep BBC dedup set reasonable size (last 200 URLs)
                        if len(self.bbc_posted_urls) > 200:
                            # Convert to list, keep last 200, back to set
                            self.bbc_posted_urls = set(list(self.bbc_posted_urls)[-200:])
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
    
    async def _post_news(self, channel_id: int, source_key: str):
        """Post news item to a channel"""
        result = await self._fetch_rss_feed(source_key)
        
        if not result:
            return
        
        title, link, description, source = result
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Channel not found for general news")
            return
        
        embed = discord.Embed(
            title=title,
            url=link,
            description=description,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_footer(text=f"{source['emoji']} {source['name']}")
        
        try:
            await channel.send(embed=embed)
            logger.info(f"Posted: {title[:50]}...")
        except Exception as e:
            logger.error(f"Failed to post: {e}")
    
    @tasks.loop(hours=2)
    async def news_auto_poster(self):
        """Automatically post news items every 2 hours"""
        try:
            # Get config from NewsManager
            news_manager = self.bot.get_cog('NewsManager')
            if not news_manager:
                logger.warning("NewsManager not found, skipping auto-post")
                return
            
            config = news_manager.config.get('general_news', {})
            
            if not config.get('enabled', False):
                return
            
            channel_id = config.get('channel_id')
            if not channel_id:
                logger.warning("No channel configured for general news")
                return
            
            logger.info("Checking general news sources...")
            
            # Check each source
            for source_key in NEWS_SOURCES:
                # Check if source is enabled
                sources_config = config.get('sources', {})
                if source_key in sources_config and not sources_config[source_key].get('enabled', True):
                    continue
                
                await self._post_news(channel_id, source_key)
                await asyncio.sleep(2)  # Rate limiting
        
        except Exception as e:
            logger.error(f"Error in news auto-poster: {e}")
    
    @news_auto_poster.before_loop
    async def before_news_auto_poster(self):
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="generalnews", description="Manually fetch latest general news")
    @app_commands.describe(source="News source to fetch")
    async def fetch_news(
        self,
        interaction: discord.Interaction,
        source: Literal['npr_news', 'pbs_economy', 'financial_times', 'pew_research', 'nyt_homepage', 'foreign_affairs', 'politico']
    ):
        """Manually fetch latest general news from a source"""
        await interaction.response.defer(thinking=True)
        
        result = await self._fetch_rss_feed(source)
        
        if not result:
            await interaction.followup.send(
                f"❌ No recent news found from {NEWS_SOURCES[source]['name']}",
                ephemeral=True
            )
            return
        
        title, link, description, src = result
        
        embed = discord.Embed(
            title=title,
            url=link,
            description=description,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_footer(text=f"{src['emoji']} {src['name']}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GeneralNews(bot))
