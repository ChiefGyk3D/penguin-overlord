#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Comics Runner - Standalone execution for systemd timers

Posts daily tech comics from XKCD, Joy of Tech, and TurnOff.us.
Runs independently of the main bot process for reliability.

Usage:
    python comics_runner.py
    
Environment Variables:
    DISCORD_BOT_TOKEN - Required (supports Doppler via get_secret)
    COMIC_POST_CHANNEL_ID - Required (channel ID for posting)
"""

import os
import sys
import json
import asyncio
import logging
import re
from pathlib import Path
from datetime import datetime

import discord
import aiohttp
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
load_dotenv()

# Import secrets utility
from utils.secrets import get_secret

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('comics_runner')


DATA_DIR = os.getenv('DATA_DIR') or '/app/data' if os.path.exists('/app/data') else 'data'
STATE_FILE = Path(DATA_DIR) / 'comic_state.json'


def load_state() -> dict:
    """Load comics state from file."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading comics state: {e}")
    return {'enabled': False, 'last_posted': None, 'posted_urls': []}


def save_state(state: dict):
    """Save comics state to file."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving comics state: {e}")


async def fetch_xkcd(session: aiohttp.ClientSession) -> dict | None:
    """Fetch latest XKCD comic."""
    try:
        async with session.get('https://xkcd.com/info.0.json', timeout=15) as resp:
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
    except Exception as e:
        logger.error(f"Error fetching XKCD: {e}")
    return None


async def fetch_joyoftech(session: aiohttp.ClientSession) -> dict | None:
    """Fetch latest Joy of Tech comic."""
    try:
        async with session.get('https://www.joyoftech.com/joyoftech/jotblog/index.xml', timeout=15) as resp:
            if resp.status != 200:
                return None
            
            xml = await resp.text()
            
            # Extract first item from RSS
            title_match = re.search(r'<item>.*?<title>(.*?)</title>', xml, re.DOTALL)
            link_match = re.search(r'<item>.*?<link>(.*?)</link>', xml, re.DOTALL)
            desc_match = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', xml, re.DOTALL)
            
            if title_match and link_match and desc_match:
                description = desc_match.group(1)
                img_match = re.search(r'<img[^>]*src="([^"]+)"', description)
                
                if img_match:
                    return {
                        'source': 'joyoftech',
                        'title': title_match.group(1),
                        'url': link_match.group(1),
                        'img': img_match.group(1),
                        'alt': ''
                    }
    except Exception as e:
        logger.error(f"Error fetching Joy of Tech: {e}")
    return None


async def fetch_turnoff(session: aiohttp.ClientSession) -> dict | None:
    """Fetch latest TurnOff.us comic."""
    try:
        async with session.get('https://turnoff.us/feed.xml', timeout=15) as resp:
            if resp.status != 200:
                return None
            
            xml = await resp.text()
            
            # Extract first item
            title_match = re.search(r'<item>.*?<title>(.*?)</title>', xml, re.DOTALL)
            link_match = re.search(r'<item>.*?<link>(.*?)</link>', xml, re.DOTALL)
            desc_match = re.search(r'<description>(.*?)</description>', xml, re.DOTALL)
            
            if title_match and link_match and desc_match:
                description = desc_match.group(1)
                img_match = re.search(r'src="([^"]+)"', description)
                
                if img_match:
                    return {
                        'source': 'turnoff',
                        'title': title_match.group(1),
                        'url': link_match.group(1),
                        'img': img_match.group(1),
                        'alt': ''
                    }
    except Exception as e:
        logger.error(f"Error fetching TurnOff.us: {e}")
    return None


async def post_comic_update():
    """Fetch and post daily tech comic."""
    token = get_secret('DISCORD', 'BOT_TOKEN')
    # Prefer persisted channel in state if present (set via runtime command)
    state = load_state()
    channel_id = state.get('channel_id') or get_secret('COMIC', 'POST_CHANNEL_ID')
    
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set")
        return False
    
    if not channel_id:
        logger.error("COMIC_POST_CHANNEL_ID not set")
        return False
    
    if not state.get('enabled', False):
        logger.info("Comic posting is disabled")
        return True
    
    # Check if already posted today
    today = datetime.utcnow().date().isoformat()
    if state.get('last_posted') == today:
        logger.info(f"Comic already posted today ({today})")
        return True
    
    # Sanitize channel id if provided in formats like '<#12345>' or '12345' or '"12345"'
    try:
        if isinstance(channel_id, str):
            sanitized = ''.join(ch for ch in channel_id if ch.isdigit())
            channel_id = int(sanitized) if sanitized else None
        elif channel_id is None:
            channel_id = None
        else:
            channel_id = int(channel_id)
    except Exception:
        logger.error("Invalid COMIC_POST_CHANNEL_ID (not numeric)")
        return False
    
    # Fetch random comic from available sources
    # NOTE: XKCD removed - handled by dedicated xkcd_runner.py (every 30 min)
    comic = None
    async with aiohttp.ClientSession() as session:
        # Try all sources
        comics = await asyncio.gather(
            fetch_joyoftech(session),
            fetch_turnoff(session),
            return_exceptions=True
        )
        
        # Filter out None and exceptions
        valid_comics = [c for c in comics if isinstance(c, dict)]
        
        if not valid_comics:
            logger.error("Failed to fetch any comics")
            return False
        
        # Filter out already-posted comics
        posted_urls = state.get('posted_urls', [])
        new_comics = [c for c in valid_comics if c['url'] not in posted_urls]
        
        if not new_comics:
            logger.info(f"No new comics available (all {len(valid_comics)} comics already posted)")
            return True
        
        # Pick first new comic
        comic = new_comics[0]
    
    # Create Discord client
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        logger.info(f"Connected as {client.user}")
        
        try:
            channel = client.get_channel(channel_id)
            if not channel:
                channel = await client.fetch_channel(channel_id)
            
            if not channel:
                logger.error(f"Channel {channel_id} not found")
                await client.close()
                return
            
            # Source emojis and colors (XKCD removed - has dedicated runner)
            source_info = {
                'joyoftech': {'emoji': '😄', 'name': 'Joy of Tech', 'color': 0xFF6B6B},
                'turnoff': {'emoji': '💻', 'name': 'TurnOff.us', 'color': 0x4ECDC4}
            }
            
            info = source_info.get(comic['source'], {'emoji': '📰', 'name': comic['source'].title(), 'color': 0x95A5A6})
            
            # Create embed
            embed = discord.Embed(
                title=f"{info['emoji']} {comic['title']}",
                url=comic['url'],
                color=info['color']
            )
            embed.set_image(url=comic['img'])
            
            if comic.get('alt'):
                embed.description = f"_{comic['alt']}_"
            
            embed.set_footer(text=f"Daily Tech Comic from {info['name']} • Use !comic for more")
            
            # Send message
            await channel.send(embed=embed)
            logger.info(f"Posted {comic['source']} comic to channel {channel_id}")
            
            # Update state - track posted URL and date
            state['last_posted'] = today
            posted_urls = state.get('posted_urls', [])
            posted_urls.append(comic['url'])
            # Keep only last 100 URLs to prevent unbounded growth
            state['posted_urls'] = posted_urls[-100:]
            save_state(state)
            
        except Exception as e:
            logger.error(f"Error posting comic: {e}", exc_info=True)
        
        finally:
            await client.close()
    
    try:
        await client.start(token)
        return True
    except Exception as e:
        logger.error(f"Error running client: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    logger.info("Comics runner starting...")
    try:
        asyncio.run(post_comic_update())
        logger.info("Comics runner completed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
