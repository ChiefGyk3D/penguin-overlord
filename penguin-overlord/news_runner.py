#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Standalone News Runner - Fetch and post news without keeping bot running.

This script can be run by cron or systemd timers for efficient resource usage.
Each run fetches news for one category and exits.

Usage:
    python3 news_runner.py --category cybersecurity
    python3 news_runner.py --category tech
    python3 news_runner.py --category gaming
    python3 news_runner.py --category apple_google
    python3 news_runner.py --category cve
    python3 news_runner.py --category kev
    python3 news_runner.py --category us_legislation
    python3 news_runner.py --category eu_legislation
    python3 news_runner.py --category uk_legislation
    python3 news_runner.py --category general_news
"""

import sys
import os
import argparse
import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "penguin-overlord"))

import discord
from discord.ext import commands
from utils.news_fetcher import OptimizedNewsFetcher
from utils.secrets import get_secret

# Configure logging - will be set to DEBUG if --verbose flag is used
logging.basicConfig(
    level=logging.DEBUG,  # Default to DEBUG so we can see HTML stripping
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StandaloneNewsRunner:
    """Standalone news fetcher and poster."""
    
    def __init__(self, category: str):
        self.category = category
        self.project_root = Path(__file__).parent.parent / "penguin-overlord"
        self.config = self._load_config()
        
        # Use /app/data for cache (mounted volume) instead of /app/penguin-overlord/data
        cache_dir = Path('/app/data')
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f'feed_cache_{category}.json'
        self.fetcher = OptimizedNewsFetcher(cache_file=str(cache_path))
        
        # Load category-specific config
        self.category_config = self.config.get(category, {})
        if not self.category_config:
            raise ValueError(f"Unknown category: {category}")
        
        # Set concurrency limit
        limit = self.category_config.get('concurrency_limit', 5)
        self.fetcher.set_concurrency_limit(limit)
    
    def _load_config(self) -> dict:
        """Load news configuration."""
        config_file = self.project_root / 'data/news_config.json'
        config = {}
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
        
        # Override channel_id from secrets manager (Doppler/AWS/Vault) or environment
        # Try secrets manager first (Doppler recommended for production)
        channel_id_str = get_secret('NEWS', f'{self.category.upper()}_CHANNEL_ID')
        
        # Fallback to direct env var if not in secrets manager
        if not channel_id_str:
            env_var_name = f"NEWS_{self.category.upper()}_CHANNEL_ID"
            channel_id_str = os.getenv(env_var_name)
        
        if channel_id_str and str(channel_id_str).isdigit():
            logger.info(f"Using channel ID from secrets for {self.category}")
            # Ensure category exists in config
            if self.category not in config:
                config[self.category] = {
                    'enabled': False,
                    'channel_id': None,
                    'interval_hours': 3,
                    'sources': {},
                    'concurrency_limit': 5
                }
            config[self.category]['channel_id'] = int(channel_id_str)
        
        return config
    
    def _get_sources(self) -> dict:
        """Get news sources for category."""
        # Import dynamically based on category
        source_map = {
            'cybersecurity': 'cogs.cybersecurity_news',
            'tech': 'cogs.tech_news',
            'gaming': 'cogs.gaming_news',
            'apple_google': 'cogs.apple_google_news',
            'cve': 'cogs.cve',
            'kev': 'cogs.kev',
            'us_legislation': 'cogs.us_legislation',
            'eu_legislation': 'cogs.eu_legislation',
            'uk_legislation': 'cogs.uk_legislation',
            'general_news': 'cogs.general_news'
        }
        
        module_name = source_map.get(self.category)
        if not module_name:
            raise ValueError(f"No source module for category: {self.category}")
        
        try:
            module = __import__(module_name, fromlist=['NEWS_SOURCES', 'CVE_SOURCES', 'LEGISLATION_SOURCES'])
            return (getattr(module, 'NEWS_SOURCES', None) or 
                    getattr(module, 'CVE_SOURCES', None) or 
                    getattr(module, 'LEGISLATION_SOURCES', None))
        except Exception as e:
            logger.error(f"Failed to import sources: {e}")
            return {}
    
    def _get_enabled_sources(self, all_sources: dict) -> list:
        """Get list of enabled sources."""
        disabled = self.category_config.get('sources', {})
        enabled = []
        
        for source_key in all_sources.keys():
            if disabled.get(source_key, True):  # Default to enabled
                enabled.append(source_key)
        
        return enabled
    
    async def fetch_and_post(self):
        """Fetch news and post to Discord."""
        # Check if category is enabled
        if not self.category_config.get('enabled', False):
            logger.info(f"Category {self.category} is disabled, skipping")
            return
        
        channel_id = self.category_config.get('channel_id')
        if not channel_id:
            logger.warning(f"No channel configured for {self.category}")
            return
        
        # Load bot token from secrets manager (Doppler/AWS/Vault) or env
        token = get_secret('DISCORD', 'BOT_TOKEN')
        if not token:
            # Fallback to direct env var
            token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
        
        if not token:
            logger.error("No Discord token found in secrets or environment")
            return
        
        # Get sources
        all_sources = self._get_sources()
        if not all_sources:
            logger.error(f"No sources found for {self.category}")
            return
        
        enabled_sources = self._get_enabled_sources(all_sources)
        logger.info(f"Fetching from {len(enabled_sources)} sources")
        
        # Fetch news with caching
        use_cache = self.category_config.get('use_etag_cache', True)
        new_items = await self.fetcher.fetch_multiple_feeds(
            all_sources,
            enabled_sources,
            use_cache=use_cache
        )
        
        if not new_items:
            logger.info(f"No new items for {self.category}")
            await self.fetcher.close()
            return
        
        logger.info(f"Found {len(new_items)} new items")
        
        # Create bot instance
        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix='!', intents=intents)
        
        @bot.event
        async def on_ready():
            """Post news when bot is ready."""
            try:
                channel = bot.get_channel(channel_id)
                if not channel:
                    logger.error(f"Channel not found for {self.category}")
                    await bot.close()
                    return
                
                posted_count = 0
                for title, link, description, guid, source in new_items:
                    try:
                        embed = discord.Embed(
                            title=f"{source.get('icon', '📰')} {title}",
                            url=link,
                            description=description,
                            color=source.get('color', 0x5865F2),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_footer(text=f"Source: {source['name']}")
                        
                        await channel.send(embed=embed)
                        posted_count += 1
                        
                        # Small delay between posts
                        await asyncio.sleep(0.5)
                    
                    except Exception as e:
                        logger.error(f"Failed to post {source['name']}: {e}")
                
                logger.info(f"Posted {posted_count} items to {self.category} channel")
            
            except Exception as e:
                logger.error(f"Error in on_ready: {e}")
            
            finally:
                await self.fetcher.close()
                await bot.close()
        
        # Run bot briefly to post and exit
        try:
            await bot.start(token)
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            await self.fetcher.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Standalone news fetcher')
    parser.add_argument(
        '--category',
        required=True,
        choices=['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'us_legislation', 'eu_legislation', 'general_news'],
        help='News category to fetch'
    )
    args = parser.parse_args()
    
    logger.info(f"Starting news runner for category: {args.category}")
    
    runner = StandaloneNewsRunner(args.category)
    await runner.fetch_and_post()
    
    logger.info(f"News runner completed for {args.category}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
