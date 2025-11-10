#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
XKCD Runner - Standalone execution for systemd timers

Checks for new XKCD comics and posts to configured Discord channel.
Runs independently of the main bot process for reliability.

Usage:
    python xkcd_runner.py
    
Environment Variables:
    DISCORD_BOT_TOKEN - Required (supports Doppler via get_secret)
    XKCD_POST_CHANNEL_ID - Required (channel ID for posting)
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

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
logger = logging.getLogger('xkcd_runner')


STATE_FILE = Path('data/xkcd_state.json')


def load_state() -> dict:
    """Load XKCD state from file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading XKCD state: {e}")
    return {'enabled': False, 'last_posted': 0}


def save_state(state: dict):
    """Save XKCD state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving XKCD state: {e}")


async def fetch_latest_xkcd() -> dict | None:
    """Fetch latest XKCD comic."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://xkcd.com/info.0.json', timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Error fetching XKCD: {e}")
    return None


async def post_xkcd_update():
    """Check for new XKCD and post if found."""
    token = get_secret('DISCORD', 'BOT_TOKEN')
    channel_id = get_secret('XKCD', 'POST_CHANNEL_ID')
    
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set")
        return False
    
    if not channel_id:
        logger.error("XKCD_POST_CHANNEL_ID not set")
        return False
    
    # Load state
    state = load_state()
    if not state.get('enabled', False):
        logger.info("XKCD posting is disabled")
        return True
    
    try:
        channel_id = int(channel_id)
    except ValueError:
        logger.error("Invalid XKCD_POST_CHANNEL_ID (not numeric)")
        return False
    
    # Fetch latest comic
    comic = await fetch_latest_xkcd()
    if not comic:
        logger.error("Failed to fetch XKCD")
        return False
    
    latest_num = int(comic.get('num', 0))
    last_posted = int(state.get('last_posted', 0))
    
    if latest_num <= last_posted:
        logger.info(f"No new XKCD (latest: {latest_num}, last posted: {last_posted})")
        return True
    
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
            
            # Create embed
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
            
            # Send message
            await channel.send(embed=embed)
            logger.info(f"Posted XKCD #{latest_num} to channel {channel_id}")
            
            # Update state
            state['last_posted'] = latest_num
            save_state(state)
            
        except Exception as e:
            logger.error(f"Error posting XKCD: {e}", exc_info=True)
        
        finally:
            await client.close()
    
    try:
        await client.start(token)
        return True
    except Exception as e:
        logger.error(f"Error running client: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    logger.info("XKCD runner starting...")
    try:
        asyncio.run(post_xkcd_update())
        logger.info("XKCD runner completed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
