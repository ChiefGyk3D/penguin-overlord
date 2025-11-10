#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
KEV Runner - Standalone execution for systemd timers

Fetches CISA Known Exploited Vulnerabilities and posts to configured Discord channel.
Runs independently of the main bot process for reliability.

Usage:
    python kev_runner.py
    
Environment Variables:
    DISCORD_TOKEN - Required
    NEWS_KEV_CHANNEL_ID - Required (channel ID for posting)
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

from utils.secrets import get_secret

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
logger = logging.getLogger('kev_runner')


STATE_FILE = Path('data/kev_state.json')
KEV_URL = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'


def load_state() -> dict:
    """Load KEV state from file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading KEV state: {e}")
    return {'posted_cves': [], 'last_posted': None}


def save_state(state: dict):
    """Save KEV state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving KEV state: {e}")


async def fetch_kevs() -> list:
    """Fetch CISA Known Exploited Vulnerabilities."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(KEV_URL, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch CISA KEV: HTTP {resp.status}")
                    return []
                
                data = await resp.json()
                vulnerabilities = data.get('vulnerabilities', [])
                
                logger.info(f"Fetched {len(vulnerabilities)} KEVs from CISA")
                
                # Get the most recent ones (first 10, as array is ordered newest-first)
                recent = vulnerabilities[:10] if len(vulnerabilities) > 10 else vulnerabilities
                
                items = []
                for vuln in recent:
                    items.append({
                        'cve_id': vuln.get('cveID', 'Unknown'),
                        'title': vuln.get('vulnerabilityName', 'Unknown Vulnerability'),
                        'description': vuln.get('shortDescription', 'No description'),
                        'severity': 'CRITICAL',  # CISA KEV are all critical by nature
                        'date_added': vuln.get('dateAdded', ''),
                        'due_date': vuln.get('dueDate', ''),
                        'required_action': vuln.get('requiredAction', ''),
                        'vendor': vuln.get('vendorProject', ''),
                        'product': vuln.get('product', ''),
                        'link': f"https://nvd.nist.gov/vuln/detail/{vuln.get('cveID', '')}"
                    })
                
                return items
    
    except Exception as e:
        logger.error(f"Error fetching CISA KEV: {e}", exc_info=True)
        return []


async def post_kev_update():
    """Fetch and post KEV updates."""
    # Get secrets
    token = get_secret('DISCORD', 'BOT_TOKEN')
    if not token:
        token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not token:
        logger.error("DISCORD_TOKEN not found")
        return False
    
    channel_id_str = get_secret('NEWS', 'KEV_CHANNEL_ID')
    if not channel_id_str:
        channel_id_str = os.getenv('NEWS_KEV_CHANNEL_ID')
    
    if not channel_id_str:
        logger.error("NEWS_KEV_CHANNEL_ID not set")
        return False
    
    try:
        channel_id = int(channel_id_str)
    except ValueError:
        logger.error(f"Invalid NEWS_KEV_CHANNEL_ID: {channel_id_str}")
        return False
    
    # Load state
    state = load_state()
    posted_cves = set(state.get('posted_cves', []))
    
    # Fetch KEVs
    kevs = await fetch_kevs()
    if not kevs:
        logger.error("Failed to fetch KEVs")
        return False
    
    # Filter to only new KEVs
    new_kevs = [k for k in kevs if k['cve_id'] not in posted_cves]
    
    if not new_kevs:
        logger.info("No new KEVs to post")
        return True
    
    logger.info(f"Found {len(new_kevs)} new KEVs to post")
    
    # IMPORTANT: Reverse so oldest posts first, newest posts last
    # CISA API returns newest-first, we want oldest→newest in Discord
    new_kevs.reverse()
    
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
            
            # Post each new KEV
            for kev in new_kevs:
                embed = discord.Embed(
                    title=f"🚨 {kev['cve_id']}: {kev['title']}",
                    description=kev['description'],
                    color=0xC41230,  # Red for critical
                    url=kev['link']
                )
                
                embed.add_field(
                    name="Severity",
                    value="🔴 **CRITICAL**",
                    inline=True
                )
                
                embed.add_field(
                    name="Vendor/Product",
                    value=f"{kev['vendor']} - {kev['product']}",
                    inline=True
                )
                
                embed.add_field(
                    name="Date Added to KEV",
                    value=kev['date_added'],
                    inline=True
                )
                
                if kev['due_date']:
                    embed.add_field(
                        name="⚠️ Due Date",
                        value=kev['due_date'],
                        inline=True
                    )
                
                if kev['required_action']:
                    embed.add_field(
                        name="Required Action",
                        value=kev['required_action'],
                        inline=False
                    )
                
                embed.set_footer(text="CISA Known Exploited Vulnerabilities Catalog")
                
                await channel.send(embed=embed)
                logger.info(f"Posted KEV: {kev['cve_id']}")
                
                # Add to posted list
                posted_cves.add(kev['cve_id'])
                
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
            
            # Update state
            # Keep only last 500 CVEs in memory
            state['posted_cves'] = list(posted_cves)[-500:]
            state['last_posted'] = datetime.utcnow().isoformat()
            save_state(state)
            
            logger.info(f"Posted {len(new_kevs)} new KEVs")
            
        except Exception as e:
            logger.error(f"Error posting KEVs: {e}", exc_info=True)
        
        finally:
            await client.close()
    
    try:
        await client.start(token)
        return True
    except Exception as e:
        logger.error(f"Error running client: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    logger.info("KEV runner starting...")
    try:
        asyncio.run(post_kev_update())
        logger.info("KEV runner completed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
