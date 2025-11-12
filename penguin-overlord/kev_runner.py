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
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from html import unescape

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
CISA_KEV_URL = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
EXPLOIT_DB_URL = 'https://www.exploit-db.com/rss.xml'


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


async def fetch_cisa_kevs(session: aiohttp.ClientSession) -> list:
    """Fetch CISA Known Exploited Vulnerabilities."""
    try:
        async with session.get(CISA_KEV_URL, timeout=30) as resp:
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
                    'link': f"https://nvd.nist.gov/vuln/detail/{vuln.get('cveID', '')}",
                    'source': 'CISA KEV',
                    'color': 0xC41230,
                    'icon': '🚨'
                })
            
            return items
    
    except Exception as e:
        logger.error(f"Error fetching CISA KEV: {e}", exc_info=True)
        return []


async def fetch_exploit_db(session: aiohttp.ClientSession) -> list:
    """Fetch Exploit Database RSS feed."""
    try:
        async with session.get(EXPLOIT_DB_URL, timeout=30) as resp:
            if resp.status != 200:
                logger.error(f"Failed to fetch Exploit-DB: HTTP {resp.status}")
                return []
            
            content = await resp.text()
            
            # Parse RSS feed
            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                logger.error(f"Exploit-DB XML parse error: {e}")
                return []
            
            # Find all item elements
            items_xml = root.findall('.//item')
            if not items_xml:
                logger.debug("Exploit-DB: No items found")
                return []
            
            logger.info(f"Fetched {len(items_xml)} exploits from Exploit-DB")
            
            items = []
            for item in items_xml[:10]:  # Get first 10
                # Extract title
                title_elem = item.find('title')
                title = "Unknown Exploit"
                if title_elem is not None and title_elem.text:
                    title = unescape(title_elem.text.strip())
                
                # Extract link
                link_elem = item.find('link')
                link = EXPLOIT_DB_URL
                if link_elem is not None and link_elem.text:
                    link = link_elem.text.strip()
                
                # Extract description
                desc_elem = item.find('description')
                description = ""
                if desc_elem is not None and desc_elem.text:
                    desc = desc_elem.text.strip()
                    desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                    desc = unescape(desc)
                    description = desc[:300] + "..." if len(desc) > 300 else desc
                
                # Extract CVE if present in title or description
                cve_match = re.search(r'CVE-\d{4}-\d+', title + " " + description, re.IGNORECASE)
                cve_id = cve_match.group(0).upper() if cve_match else "N/A"
                
                items.append({
                    'cve_id': cve_id,
                    'title': title,
                    'description': description,
                    'severity': 'HIGH',  # Exploit-DB entries are exploitable
                    'date_added': '',
                    'due_date': '',
                    'required_action': 'Review exploit and patch if vulnerable',
                    'vendor': '',
                    'product': '',
                    'link': link,
                    'source': 'Exploit-DB',
                    'color': 0xE74C3C,
                    'icon': '💣'
                })
            
            return items
    
    except Exception as e:
        logger.error(f"Error fetching Exploit-DB: {e}", exc_info=True)
        return []


async def fetch_kevs() -> list:
    """Fetch vulnerabilities from all KEV sources."""
    async with aiohttp.ClientSession() as session:
        # Fetch from both sources
        cisa_items = await fetch_cisa_kevs(session)
        exploit_db_items = await fetch_exploit_db(session)
        
        # Combine results
        all_items = cisa_items + exploit_db_items
        return all_items


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
        logger.error("Invalid NEWS_KEV_CHANNEL_ID (not numeric)")
        return False
    
    # Load state
    state = load_state()
    posted_links = set(state.get('posted_links', []))
    # Keep old posted_cves for backwards compatibility
    if 'posted_cves' in state and not posted_links:
        posted_links = set(state.get('posted_cves', []))
    
    # Fetch KEVs
    kevs = await fetch_kevs()
    if not kevs:
        logger.error("Failed to fetch KEVs")
        return False
    
    # Filter to only new KEVs (using link as unique identifier)
    new_kevs = [k for k in kevs if k['link'] not in posted_links]
    
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
                # Use source-specific color and icon
                icon = kev.get('icon', '🚨')
                color = kev.get('color', 0xC41230)
                source_name = kev.get('source', 'CISA KEV')
                
                embed = discord.Embed(
                    title=f"{icon} {kev['cve_id']}: {kev['title']}",
                    description=kev['description'],
                    color=color,
                    url=kev['link']
                )
                
                # Severity display varies by source
                if kev['severity'] == 'CRITICAL':
                    severity_display = "🔴 **CRITICAL** (Actively Exploited)"
                elif kev['severity'] == 'HIGH':
                    severity_display = "🟠 **HIGH** (Exploit Available)"
                else:
                    severity_display = f"⚠️ **{kev['severity']}**"
                
                embed.add_field(
                    name="Severity",
                    value=severity_display,
                    inline=True
                )
                
                if kev['vendor'] and kev['product']:
                    embed.add_field(
                        name="Vendor/Product",
                        value=f"{kev['vendor']} - {kev['product']}",
                        inline=True
                    )
                
                if kev['date_added']:
                    embed.add_field(
                        name="Date Added",
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
                
                embed.set_footer(text=f"Source: {source_name}")
                
                await channel.send(embed=embed)
                logger.info(f"Posted KEV: {kev['cve_id']} from {source_name}")
                
                # Add to posted list (using link as unique identifier)
                posted_links.add(kev['link'])
                
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
            
            # Update state
            # Keep only last 500 links in memory
            state['posted_links'] = list(posted_links)[-500:]
            state['last_posted'] = datetime.utcnow().isoformat()
            # Remove old posted_cves field
            if 'posted_cves' in state:
                del state['posted_cves']
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
