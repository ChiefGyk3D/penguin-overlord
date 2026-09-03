#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Standalone News Runner - Fetch and post news without keeping bot running.

This script can be run by cron or systemd timers for efficient resource usage.
Each run fetches news for one category and exits. All eleven categories are
supported: cybersecurity, tech, gaming, apple_google, cve, kev, us_legislation,
eu_legislation, uk_legislation, general_news and vendor_alerts.

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
    python3 news_runner.py --category vendor_alerts
"""

import sys
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
from utils.logging_setup import configure_logging
from utils.config import Config, ConfigError, load_config

# INFO by default; --verbose (or LOG_LEVEL=DEBUG) turns on the HTML-stripping
# detail this used to log unconditionally, on every timer run, forever.
logger = configure_logging('news_runner')


class StandaloneNewsRunner:
    """Standalone news fetcher and poster."""
    
    def __init__(self, category: str, settings: Config = None):
        self.category = category
        self.project_root = Path(__file__).parent.parent / "penguin-overlord"
        # Typed environment (token, channel ids); validated once in main().
        self.settings = settings or load_config()
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
        
        # NEWS_<CATEGORY>_CHANNEL_ID from the secrets manager or environment
        # (already validated as a Discord id) overrides the JSON file.
        channel_id = self.settings.news.channel_id(self.category)
        if channel_id is not None:
            logger.info(f"Using channel ID from secrets for {self.category}")
            # Ensure category exists in config
            if self.category not in config:
                config[self.category] = {
                    'enabled': True,  # Auto-enable when channel is configured via env/secrets
                    'channel_id': None,
                    'interval_hours': 3,
                    'sources': {},
                    'concurrency_limit': 5
                }
            config[self.category]['channel_id'] = channel_id
            # Auto-enable if channel is set (for fresh installs)
            if not config[self.category].get('enabled'):
                config[self.category]['enabled'] = True
        
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
            'general_news': 'cogs.general_news',
            'vendor_alerts': 'cogs.vendor_alerts'
        }
        
        module_name = source_map.get(self.category)
        if not module_name:
            raise ValueError(f"No source module for category: {self.category}")
        
        try:
            module = __import__(module_name, fromlist=['NEWS_SOURCES', 'CVE_SOURCES', 'KEV_SOURCES', 'LEGISLATION_SOURCES', 'VENDOR_ALERT_SOURCES'])
            return (getattr(module, 'NEWS_SOURCES', None) or 
                    getattr(module, 'CVE_SOURCES', None) or 
                    getattr(module, 'KEV_SOURCES', None) or
                    getattr(module, 'LEGISLATION_SOURCES', None) or
                    getattr(module, 'VENDOR_ALERT_SOURCES', None))
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
        
        token = self.settings.discord.bot_token.reveal()

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
        
        # IMPORTANT: Reverse items so oldest posts first, newest posts last
        # This ensures newest content appears at bottom (most recent) in Discord
        new_items.reverse()
        
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
        choices=['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts'],
        help='News category to fetch'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='DEBUG logging (feed parsing, HTML stripping)',
    )
    args = parser.parse_args()
    if args.verbose:
        configure_logging('news_runner', level=logging.DEBUG)

    logger.info(f"Starting news runner for category: {args.category}")

    try:
        settings = load_config()
    except ConfigError as e:
        logger.error("Refusing to run:\n%s", e)
        sys.exit(1)

    runner = StandaloneNewsRunner(args.category, settings)
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
