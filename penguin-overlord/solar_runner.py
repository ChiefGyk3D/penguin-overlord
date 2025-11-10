#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Solar/Propagation Runner - Standalone execution for systemd timers

Fetches NOAA space weather data and posts to configured Discord channel.
Runs independently of the main bot process for reliability.

Usage:
    python solar_runner.py
    
Environment Variables:
    DISCORD_TOKEN - Required
    SOLAR_POST_CHANNEL_ID - Required (channel ID for posting)
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

import discord
import aiohttp
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('solar_runner')


STATE_FILE = Path('data/solar_state.json')


def load_state() -> dict:
    """Load solar state from file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading solar state: {e}")
    return {}


def save_state(state: dict):
    """Save solar state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving solar state: {e}")


async def fetch_solar_data(session: aiohttp.ClientSession) -> dict | None:
    """Fetch solar/propagation data from NOAA."""
    try:
        async with session.get('https://services.swpc.noaa.gov/products/noaa-scales.json', timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                # Extract current conditions
                r_scale = 'N/A'
                s_scale = 'N/A'
                g_scale = 'N/A'
                
                if isinstance(data, dict) and '0' in data:
                    current = data['0']
                    r_scale = current.get('R', {}).get('Scale', 'N/A') or 'N/A'
                    s_scale = current.get('S', {}).get('Scale', 'N/A') or 'N/A'
                    g_scale = current.get('G', {}).get('Scale', 'N/A') or 'N/A'
                
                # Fetch SFI and other indices
                async with session.get('https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt', timeout=10) as resp2:
                    sfi = 'N/A'
                    a_index = 'N/A'
                    k_index = 'N/A'
                    
                    if resp2.status == 200:
                        text = await resp2.text()
                        lines = text.strip().split('\n')
                        if len(lines) > 1:
                            last_line = lines[-1].split()
                            if len(last_line) >= 8:
                                sfi = last_line[3]
                                a_index = last_line[6]
                                k_index = last_line[7]
                
                return {
                    'r_scale': r_scale,
                    's_scale': s_scale,
                    'g_scale': g_scale,
                    'sfi': sfi,
                    'a_index': a_index,
                    'k_index': k_index
                }
    
    except Exception as e:
        logger.error(f"Error fetching solar data: {e}")
    
    return None


async def post_solar_update():
    """Fetch and post solar/propagation update."""
    token = os.getenv('DISCORD_TOKEN')
    channel_id = os.getenv('SOLAR_POST_CHANNEL_ID')
    
    if not token:
        logger.error("DISCORD_TOKEN not set")
        return False
    
    if not channel_id:
        logger.error("SOLAR_POST_CHANNEL_ID not set")
        return False
    
    try:
        channel_id = int(channel_id)
    except ValueError:
        logger.error(f"Invalid SOLAR_POST_CHANNEL_ID: {channel_id}")
        return False
    
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
            
            # Fetch solar data
            async with aiohttp.ClientSession() as session:
                data = await fetch_solar_data(session)
            
            if not data:
                logger.error("Failed to fetch solar data")
                await client.close()
                return
            
            # Create embed
            embed = discord.Embed(
                title="☀️ Solar Weather & Propagation Report",
                description="Current space weather conditions from NOAA",
                color=0xFF6F00
            )
            
            # NOAA Scales
            embed.add_field(
                name="📡 Radio Blackout (R-Scale)",
                value=f"**{data['r_scale']}** - HF radio impacts",
                inline=True
            )
            
            embed.add_field(
                name="🛰️ Solar Radiation (S-Scale)",
                value=f"**{data['s_scale']}** - Satellite/crew impacts",
                inline=True
            )
            
            embed.add_field(
                name="🌍 Geomagnetic Storm (G-Scale)",
                value=f"**{data['g_scale']}** - Power grid/aurora",
                inline=True
            )
            
            # Indices
            embed.add_field(
                name="📊 Solar Flux Index (SFI)",
                value=f"**{data['sfi']}** - Higher is better for HF",
                inline=True
            )
            
            embed.add_field(
                name="🧲 A-Index",
                value=f"**{data['a_index']}** - Geomagnetic activity",
                inline=True
            )
            
            embed.add_field(
                name="⚡ K-Index",
                value=f"**{data['k_index']}** - Local magnetic field",
                inline=True
            )
            
            # Band recommendations based on time and SFI
            now_hour = datetime.utcnow().hour
            if 12 <= now_hour <= 22:
                best_bands = "**Best Bands:** 20m, 17m, 15m, 40m"
            else:
                best_bands = "**Best Bands:** 80m, 40m, 30m"
            
            embed.add_field(
                name="📻 Recommended Bands",
                value=best_bands,
                inline=False
            )
            
            embed.set_footer(text="73 de Penguin Overlord! • Use /solar for detailed info • Posts every 12 hours")
            
            # Send message
            await channel.send(embed=embed)
            logger.info(f"Solar update posted to channel {channel_id}")
            
            # Update state
            state = load_state()
            state['last_posted'] = datetime.utcnow().isoformat()
            save_state(state)
            
        except Exception as e:
            logger.error(f"Error posting solar update: {e}", exc_info=True)
        
        finally:
            await client.close()
    
    try:
        await client.start(token)
        return True
    except Exception as e:
        logger.error(f"Error running client: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    logger.info("Solar runner starting...")
    try:
        asyncio.run(post_solar_update())
        logger.info("Solar runner completed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
