# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Vendor Service Alerts Cog - Tracks status and service alerts from major vendors
Monitors incidents, maintenance, and advisories from cloud providers and security vendors.
"""

import logging
import discord
from discord.ext import commands, tasks
import aiohttp
import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


VENDOR_ALERT_SOURCES = {
    # Zscaler services
    'zscaler_maintenance': {
        'name': 'Zscaler Maintenance',
        'url': 'https://trust.zscaler.com/rss-feed/maintenance?_format=json',
        'type': 'json',
        'color': 0x0066CC,
        'icon': '🔧'
    },
    'zscaler_incidents': {
        'name': 'Zscaler Incidents',
        'url': 'https://trust.zscaler.com/rss-feed/incidents?_format=json',
        'type': 'json',
        'color': 0xFF0000,
        'icon': '🚨'
    },
    'zscaler_advisories': {
        'name': 'Zscaler Advisories',
        'url': 'https://trust.zscaler.com/rss-feed/advisories?_format=json',
        'type': 'json',
        'color': 0xFFA500,
        'icon': '⚠️'
    },
    'zscaler_urlcat': {
        'name': 'Zscaler URL Category',
        'url': 'https://trust.zscaler.com/rss-feed/url-category-notification?_format=json',
        'type': 'json',
        'color': 0x4169E1,
        'icon': '🔗'
    },
    'zscaler_cloudapp': {
        'name': 'Zscaler Cloud App',
        'url': 'https://trust.zscaler.com/rss-feed/cloud-app?_format=json',
        'type': 'json',
        'color': 0x1E90FF,
        'icon': '☁️'
    },
    
    # Avalor (Zscaler Risk 360)
    'avalor': {
        'name': 'Avalor/Zscaler Risk 360',
        'url': 'https://avalorstatus.statuspage.io/history.atom',
        'type': 'atom',
        'color': 0x6A5ACD,
        'icon': '📊'
    },
    
    # Datadog regions
    'datadog_us1': {
        'name': 'Datadog US-1',
        'url': 'https://status.datadoghq.com/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    'datadog_us3': {
        'name': 'Datadog US-3',
        'url': 'https://status.us3.datadoghq.com/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    'datadog_us5': {
        'name': 'Datadog US-5',
        'url': 'https://status.us5.datadoghq.com/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    'datadog_eu': {
        'name': 'Datadog EU',
        'url': 'https://status.datadoghq.eu/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    'datadog_ap1': {
        'name': 'Datadog AP-1',
        'url': 'https://status.ap1.datadoghq.com/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    'datadog_gov': {
        'name': 'Datadog GovCloud',
        'url': 'https://status.ddog-gov.com/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    'datadog_ap2': {
        'name': 'Datadog AP-2',
        'url': 'https://status.ap2.datadoghq.com/history.atom',
        'type': 'atom',
        'color': 0x632CA6,
        'icon': '🐕'
    },
    
    # Cloud providers
    'aws': {
        'name': 'Amazon Web Services',
        'url': 'https://aws.amazonstatus.com/history.atom',
        'type': 'atom',
        'color': 0xFF9900,
        'icon': '☁️'
    },
    'azure': {
        'name': 'Microsoft Azure',
        'url': 'https://rssfeed.azure.status.microsoft/en-us/status/feed/',
        'type': 'rss',
        'color': 0x0078D4,
        'icon': '☁️'
    },
    'gcp_status': {
        'name': 'Google Cloud Platform',
        'url': 'https://status.cloud.google.com/feed.atom',
        'type': 'atom',
        'color': 0x4285F4,
        'icon': '☁️'
    },
    'cloudflare': {
        'name': 'Cloudflare',
        'url': 'https://www.cloudflarestatus.com/history.atom',
        'type': 'atom',
        'color': 0xF38020,
        'icon': '☁️'
    },
    
    # Identity & Access Management
    'okta': {
        'name': 'Okta',
        'url': 'https://feeds.feedburner.com/OktaTrustRSS',
        'type': 'rss',
        'color': 0x007DC1,
        'icon': '🔐'
    },
    'jumpcloud': {
        'name': 'JumpCloud',
        'url': 'https://status.jumpcloud.com/history.atom',
        'type': 'atom',
        'color': 0x00A0DF,
        'icon': '🔑'
    },
    'duo': {
        'name': 'Duo Security',
        'url': 'https://status.duo.com/history.atom',
        'type': 'atom',
        'color': 0x6ABE45,
        'icon': '🔒'
    },
    'delinea': {
        'name': 'Delinea',
        'url': 'https://status.delinea.com/history.atom',
        'type': 'atom',
        'color': 0xFF6B35,
        'icon': '🛡️'
    },
    
    # Development & DevOps
    'doppler': {
        'name': 'Doppler',
        'url': 'https://www.dopplerstatus.com/history.atom',
        'type': 'atom',
        'color': 0xEF4444,
        'icon': '🔐'
    },
    'github': {
        'name': 'GitHub',
        'url': 'https://www.githubstatus.com/history.atom',
        'type': 'atom',
        'color': 0x181717,
        'icon': '🐙'
    },
    'gitlab': {
        'name': 'GitLab',
        'url': 'https://status.gitlab.com/pages/5b36dc6502d06804c08349f7/rss',
        'type': 'rss',
        'color': 0xFC6D26,
        'icon': '🦊'
    },
    
    # Atlassian products
    'atlassian_jira': {
        'name': 'Atlassian Jira Software',
        'url': 'https://jira-software.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '📋'
    },
    'atlassian_jsm': {
        'name': 'Atlassian Jira Service Management',
        'url': 'https://jira-service-management.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '🎫'
    },
    'atlassian_jwm': {
        'name': 'Atlassian Jira Work Management',
        'url': 'https://jira-work-management.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '📊'
    },
    'atlassian_jpd': {
        'name': 'Atlassian Jira Product Discovery',
        'url': 'https://jira-product-discovery.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '🔍'
    },
    'atlassian_confluence': {
        'name': 'Atlassian Confluence',
        'url': 'https://confluence.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x172B4D,
        'icon': '📝'
    },
    'atlassian_bitbucket': {
        'name': 'Atlassian Bitbucket',
        'url': 'https://bitbucket.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '🪣'
    },
    'atlassian_trello': {
        'name': 'Atlassian Trello',
        'url': 'https://trello.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '📌'
    },
    'atlassian_opsgenie': {
        'name': 'Atlassian Opsgenie',
        'url': 'https://opsgenie.status.atlassian.com/history.atom',
        'type': 'atom',
        'color': 0x0052CC,
        'icon': '🚨'
    },
    
    # Security platforms
    'wiz': {
        'name': 'Wiz',
        'url': 'https://status.wiz.io/history.atom',
        'type': 'atom',
        'color': 0x6B46C1,
        'icon': '☁️'
    },
    'tenable': {
        'name': 'Tenable',
        'url': 'https://status.tenable.com/history.atom',
        'type': 'atom',
        'color': 0x00A8E1,
        'icon': '🔍'
    }
}


class VendorAlerts(commands.Cog):
    """Vendor service alert and status monitoring system."""
    
    NEWS_SOURCES = VENDOR_ALERT_SOURCES  # For compatibility with NewsManager
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/vendor_alerts_state.json'
        self.state = self._load_state()
        self.vendor_alerts_auto_poster.start()
    
    def _load_state(self):
        """Load vendor alerts state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading vendor alerts state: {e}")
        
        return {
            'last_posted': {},
            'last_check': None,
            'posted_items': []
        }
    
    def _save_state(self):
        """Save vendor alerts state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving vendor alerts state: {e}")
    
    async def cog_load(self):
        """Create aiohttp session when cog loads."""
        self.session = aiohttp.ClientSession()
    
    def cog_unload(self):
        """Close aiohttp session and stop auto-poster when cog unloads."""
        self.vendor_alerts_auto_poster.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())
    
    async def _fetch_json_feed(self, source_key: str) -> list:
        """Fetch items from a JSON feed."""
        try:
            source = VENDOR_ALERT_SOURCES[source_key]
            async with self.session.get(source['url'], timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch {source_key}: HTTP {resp.status}")
                    return []
                
                data = await resp.json()
                
                # Handle different JSON structures
                items = []
                if isinstance(data, list):
                    items = data[:10]  # Limit to 10 most recent
                elif isinstance(data, dict):
                    items = data.get('items', data.get('entries', []))[:10]
                
                return items
                
        except Exception as e:
            logger.error(f"Error fetching JSON feed {source_key}: {e}")
            return []
    
    async def _fetch_rss_feed(self, source_key: str) -> list:
        """Fetch items from an RSS/Atom feed."""
        try:
            source = VENDOR_ALERT_SOURCES[source_key]
            async with self.session.get(source['url'], timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch {source_key}: HTTP {resp.status}")
                    return []
                
                content = await resp.text()
                root = ET.fromstring(content)
                
                # Parse RSS or Atom
                items = []
                rss_items = root.findall('.//item')
                atom_entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                
                if rss_items:
                    for item in rss_items[:10]:
                        title_elem = item.find('title')
                        link_elem = item.find('link')
                        desc_elem = item.find('description')
                        date_elem = item.find('pubDate')
                        
                        items.append({
                            'title': title_elem.text if title_elem is not None else 'No title',
                            'link': link_elem.text if link_elem is not None else '',
                            'description': desc_elem.text if desc_elem is not None else '',
                            'date': date_elem.text if date_elem is not None else ''
                        })
                
                elif atom_entries:
                    for entry in atom_entries[:10]:
                        title_elem = entry.find('{http://www.w3.org/2005/Atom}title')
                        link_elem = entry.find('{http://www.w3.org/2005/Atom}link')
                        content_elem = entry.find('{http://www.w3.org/2005/Atom}content')
                        date_elem = entry.find('{http://www.w3.org/2005/Atom}updated')
                        
                        items.append({
                            'title': title_elem.text if title_elem is not None else 'No title',
                            'link': link_elem.get('href', '') if link_elem is not None else '',
                            'description': content_elem.text if content_elem is not None else '',
                            'date': date_elem.text if date_elem is not None else ''
                        })
                
                return items
                
        except Exception as e:
            logger.error(f"Error fetching RSS feed {source_key}: {e}")
            return []
    
    @tasks.loop(minutes=30)
    async def vendor_alerts_auto_poster(self):
        """Automatically post new vendor service alerts every 30 minutes."""
        if not self.session:
            return
        
        try:
            from .news_manager import NewsManager
            news_manager = self.bot.get_cog('NewsManager')
            
            if not news_manager:
                logger.warning("NewsManager cog not found, cannot post vendor alerts")
                return
            
            for source_key in VENDOR_ALERT_SOURCES.keys():
                source_info = VENDOR_ALERT_SOURCES[source_key]
                
                # Fetch items based on type
                if source_info['type'] == 'json':
                    items = await self._fetch_json_feed(source_key)
                else:
                    items = await self._fetch_rss_feed(source_key)
                
                # Post new items
                for item in items:
                    item_id = f"{source_key}_{item.get('title', '')[:50]}"
                    
                    if item_id not in self.state['posted_items']:
                        embed = discord.Embed(
                            title=item.get('title', 'No title')[:256],
                            description=item.get('description', '')[:2048],
                            color=source_info['color'],
                            url=item.get('link', '')
                        )
                        embed.set_author(
                            name=f"{source_info['icon']} {source_info['name']}"
                        )
                        
                        if item.get('date'):
                            embed.set_footer(text=f"Published: {item['date']}")
                        
                        await news_manager._post_to_channels(embed, source_key, 'vendor_alerts')
                        
                        self.state['posted_items'].append(item_id)
                        
                        # Keep only last 500 posted items
                        if len(self.state['posted_items']) > 500:
                            self.state['posted_items'] = self.state['posted_items'][-500:]
            
            self.state['last_check'] = datetime.utcnow().isoformat()
            self._save_state()
            
        except Exception as e:
            logger.error(f"Error in vendor alerts auto-poster: {e}")
    
    @vendor_alerts_auto_poster.before_loop
    async def before_vendor_alerts_auto_poster(self):
        """Wait for bot to be ready before starting auto-poster."""
        await self.bot.wait_until_ready()
        if not self.session:
            self.session = aiohttp.ClientSession()


async def setup(bot):
    """Load the VendorAlerts cog."""
    await bot.add_cog(VendorAlerts(bot))
