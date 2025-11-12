# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
CVE Cog - Tracks and posts Common Vulnerabilities and Exposures from NVD and Ubuntu.
For CISA Known Exploited Vulnerabilities (high priority), see the KEV cog.
"""

import logging
import discord
from discord.ext import commands, tasks
import aiohttp
import re
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape

logger = logging.getLogger(__name__)


CVE_SOURCES = {
    'nvd': {
        'name': 'NVD Recent CVEs',
        'url': 'https://services.nvd.nist.gov/rest/json/cves/2.0',
        'type': 'json_api',
        'color': 0x1C4E80,
        'icon': '📊'
    },
    'ubuntu': {
        'name': 'Ubuntu Security Notices',
        'url': 'https://ubuntu.com/security/notices/rss.xml',
        'type': 'rss',
        'color': 0xE95420,
        'icon': '🐧'
    },
    'cert_pl': {
        'name': 'CERT.PL',
        'url': 'https://cert.pl/en/atom.xml',
        'type': 'rss',
        'color': 0xDC143C,
        'icon': '🇵🇱'
    },
    'cert_fr': {
        'name': 'CERT-FR (ANSSI)',
        'url': 'https://www.cert.ssi.gouv.fr/cti/feed/',
        'type': 'rss',
        'color': 0x0055A4,
        'icon': '🇫🇷'
    },
    'cert_ca': {
        'name': 'Canadian Centre for Cyber Security',
        'url': 'https://www.cyber.gc.ca/api/cccs/atom/v1/get?feed=alerts_advisories&lang=en',
        'type': 'rss',
        'color': 0xFF0000,
        'icon': '🇨🇦'
    },
    'jpcert': {
        'name': 'JPCERT/CC',
        'url': 'https://blogs.jpcert.or.jp/en/atom.xml',
        'type': 'rss',
        'color': 0xBC002D,
        'icon': '🇯🇵'
    },
    'cisa_alerts': {
        'name': 'CISA Alerts',
        'url': 'https://us-cert.cisa.gov/ncas/alerts.xml',
        'type': 'rss',
        'color': 0x002868,
        'icon': '🚨'
    },
    'cisa_current': {
        'name': 'CISA Current Activity',
        'url': 'https://us-cert.cisa.gov/ncas/current-activity.xml',
        'type': 'rss',
        'color': 0x0033A0,
        'icon': '📢'
    }
}


class CVENews(commands.Cog):
    """CVE tracking and notification system."""
    
    NEWS_SOURCES = CVE_SOURCES  # For compatibility with NewsManager
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/cve_state.json'
        self.state = self._load_state()
        self.cve_auto_poster.start()
    
    def _load_state(self):
        """Load CVE poster state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading CVE state: {e}")
        
        return {
            'last_posted': {},
            'last_check': None,
            'posted_cves': []  # Track CVE IDs to avoid duplicates
        }
    
    def _save_state(self):
        """Save CVE poster state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving CVE state: {e}")
    
    async def cog_load(self):
        """Create aiohttp session when cog loads."""
        self.session = aiohttp.ClientSession()
    
    def cog_unload(self):
        """Close aiohttp session and stop auto-poster when cog unloads."""
        self.cve_auto_poster.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())
    
    async def _fetch_nvd_cves(self) -> list:
        """Fetch recent CVEs from NVD (last 7 days)."""
        try:
            # Build URL with date parameters for recent CVEs
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=7)
            
            start_str = start_date.strftime('%Y-%m-%dT%H:%M:%S.000')
            end_str = end_date.strftime('%Y-%m-%dT%H:%M:%S.000')
            
            url = f"{CVE_SOURCES['nvd']['url']}?pubStartDate={start_str}&pubEndDate={end_str}&resultsPerPage=10"
            
            async with self.session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch NVD CVEs: HTTP {resp.status}")
                    return []
                
                data = await resp.json()
                vulnerabilities = data.get('vulnerabilities', [])
                
                items = []
                for vuln_wrapper in vulnerabilities[:5]:  # Get latest 5
                    vuln = vuln_wrapper.get('cve', {})
                    cve_id = vuln.get('id', 'Unknown')
                    
                    # Get description
                    descriptions = vuln.get('descriptions', [])
                    desc = next((d['value'] for d in descriptions if d.get('lang') == 'en'), 'No description')
                    desc = desc[:300] + '...' if len(desc) > 300 else desc
                    
                    # Get CVSS score if available
                    metrics = vuln.get('metrics', {})
                    cvss_data = metrics.get('cvssMetricV31', [])
                    severity = 'UNKNOWN'
                    if cvss_data:
                        severity = cvss_data[0].get('cvssData', {}).get('baseSeverity', 'UNKNOWN')
                    
                    # Get published date
                    published = vuln.get('published', '')
                    
                    items.append({
                        'cve_id': cve_id,
                        'title': f"CVE {cve_id}",
                        'description': desc,
                        'severity': severity,
                        'date_added': published,
                        'source': 'nvd',
                        'link': f"https://nvd.nist.gov/vuln/detail/{cve_id}"
                    })
                
                return items
        
        except Exception as e:
            logger.error(f"Error fetching NVD CVEs: {e}")
            return []
    
    async def _fetch_ubuntu_cves(self) -> list:
        """Fetch Ubuntu Security Notices."""
        try:
            async with self.session.get(CVE_SOURCES['ubuntu']['url'], timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch Ubuntu USN: HTTP {resp.status}")
                    return []
                
                content = await resp.text()
                
                # Parse RSS feed using XML parser (replaces regex approach)
                # Fix for: RSS feeds with item tag attributes
                items = []
                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    logger.error(f"Ubuntu USN: XML parse error: {e}")
                    return []
                
                item_elements = root.findall('.//item')
                
                for item in item_elements[:5]:
                    # Extract title using XML parser
                    title_elem = item.find('title')
                    if title_elem is None or not title_elem.text:
                        continue
                    
                    title = unescape(re.sub(r'<[^>]+>', '', title_elem.text.strip()))
                    
                    # Extract link using XML parser
                    link_elem = item.find('link')
                    if link_elem is None or not link_elem.text:
                        continue
                    
                    link = link_elem.text.strip()
                    
                    # Extract CVE ID from title if present
                    cve_match = re.search(r'(CVE-\d{4}-\d+)', title)
                    cve_id = cve_match.group(1) if cve_match else title.split(':')[0]
                    
                    # Clean description using XML parser
                    desc = ''
                    desc_elem = item.find('description')
                    if desc_elem is not None and desc_elem.text:
                        desc_text = desc_elem.text.strip()
                        desc_text = re.sub(r'<[^>]+>', '', desc_text)
                        desc_text = unescape(desc_text)
                        desc = desc_text[:300] + '...' if len(desc_text) > 300 else desc_text
                    
                    items.append({
                        'cve_id': cve_id,
                        'title': title,
                        'description': desc or 'No description',
                        'severity': 'MEDIUM',  # Ubuntu doesn't provide severity in RSS
                        'date_added': '',
                        'source': 'ubuntu',
                        'link': link
                    })
                
                return items
        
        except Exception as e:
            logger.error(f"Error fetching Ubuntu USN: {e}")
            return []
    
    async def _fetch_cves(self, source_key: str) -> list:
        """Fetch CVEs from specified source."""
        if source_key == 'nvd':
            return await self._fetch_nvd_cves()
        elif source_key == 'ubuntu':
            return await self._fetch_ubuntu_cves()
        return []
    
    def _get_severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level."""
        severity = severity.upper()
        if severity == 'CRITICAL':
            return '🔴'
        elif severity == 'HIGH':
            return '🟠'
        elif severity == 'MEDIUM':
            return '🟡'
        elif severity == 'LOW':
            return '🟢'
        else:
            return '⚪'
    
    @commands.hybrid_command(name='cve', description='Get recent CVEs from NVD and Ubuntu')
    async def cve(self, ctx: commands.Context, source: str = None):
        """
        Get recent Common Vulnerabilities and Exposures.
        
        For actively exploited vulnerabilities (KEV), use !kev instead.
        
        Usage:
            !cve                - Get CVEs from all sources (NVD + Ubuntu)
            !cve nvd           - Get recent NVD CVEs
            !cve ubuntu        - Get Ubuntu Security Notices
        """
        await ctx.defer()
        
        sources_to_fetch = []
        if source:
            source = source.lower()
            if source in CVE_SOURCES:
                sources_to_fetch = [source]
            else:
                await ctx.send(f"❌ Unknown source: `{source}`\nAvailable: {', '.join(CVE_SOURCES.keys())}")
                return
        else:
            sources_to_fetch = list(CVE_SOURCES.keys())
        
        all_items = []
        for src in sources_to_fetch:
            items = await self._fetch_cves(src)
            all_items.extend(items)
        
        if not all_items:
            await ctx.send("❌ No CVEs found. Sources may be temporarily unavailable.")
            return
        
        # Show latest 5 across all sources
        all_items = all_items[:5]
        
        for item in all_items:
            src_info = CVE_SOURCES[item['source']]
            severity_emoji = self._get_severity_emoji(item['severity'])
            
            embed = discord.Embed(
                title=f"{src_info['icon']} {item['cve_id']}: {item['title'][:100]}",
                url=item['link'],
                description=item['description'],
                color=src_info['color'],
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Severity",
                value=f"{severity_emoji} {item['severity']}",
                inline=True
            )
            
            if item['date_added']:
                embed.add_field(
                    name="Date",
                    value=item['date_added'][:10],
                    inline=True
                )
            
            embed.set_footer(text=f"Source: {src_info['name']}")
            
            await ctx.send(embed=embed)
    
    @tasks.loop(hours=8)
    async def cve_auto_poster(self):
        """Automatically post new CVEs from NVD and Ubuntu."""
        try:
            # Get configuration from NewsManager
            manager = self.bot.get_cog('NewsManager')
            if not manager:
                return
            
            config = manager.get_category_config('cve')
            
            if not config.get('enabled'):
                return
            
            channel_id = config.get('channel_id')
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"CVE auto-poster: Channel not found")
                return
            
            # Update interval dynamically
            interval = config.get('interval_hours', 8)
            if interval != self.cve_auto_poster.hours:
                self.cve_auto_poster.change_interval(hours=interval)
            
            posted_cves = set(self.state.get('posted_cves', []))
            
            # Post from each enabled source
            for source_key in CVE_SOURCES.keys():
                if not manager.is_source_enabled('cve', source_key):
                    continue
                
                items = await self._fetch_cves(source_key)
                
                # Post only new CVEs we haven't posted before
                for item in items:
                    cve_id = item['cve_id']
                    
                    if cve_id not in posted_cves:
                        src_info = CVE_SOURCES[source_key]
                        severity_emoji = self._get_severity_emoji(item['severity'])
                        
                        embed = discord.Embed(
                            title=f"{src_info['icon']} {item['cve_id']}: {item['title'][:100]}",
                            url=item['link'],
                            description=item['description'],
                            color=src_info['color'],
                            timestamp=datetime.utcnow()
                        )
                        
                        embed.add_field(
                            name="Severity",
                            value=f"{severity_emoji} {item['severity']}",
                            inline=True
                        )
                        
                        if item['date_added']:
                            embed.add_field(
                                name="Date",
                                value=item['date_added'][:10],
                                inline=True
                            )
                        
                        embed.set_footer(text=f"Source: {src_info['name']} • CVE Auto-Poster")
                        
                        await channel.send(embed=embed)
                        
                        posted_cves.add(cve_id)
                        logger.info(f"CVE auto-poster: Posted {cve_id} from {source_key}")
            
            # Keep only last 1000 CVE IDs to prevent state file from growing too large
            self.state['posted_cves'] = list(posted_cves)[-1000:]
            self.state['last_check'] = datetime.utcnow().isoformat()
            self._save_state()
        
        except Exception as e:
            logger.error(f"CVE auto-poster error: {e}")
    
    @cve_auto_poster.before_loop
    async def before_cve_auto_poster(self):
        """Wait for the bot to be ready before starting the auto-poster."""
        await self.bot.wait_until_ready()
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    @commands.hybrid_command(name='cve_set_channel', description='Set the channel for automatic CVE updates')
    @commands.has_permissions(manage_guild=True)
    async def cve_set_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """
        Set the channel where CVE alerts will be posted every 8 hours.
        
        For critical exploited vulnerabilities (KEV), use !kev_set_channel instead.
        
        Usage:
            !cve_set_channel #security-alerts
            /cve_set_channel channel:#security-alerts
        
        Requires: Manage Server permission
        """
        channel = channel or ctx.channel
        self.state['channel_id'] = channel.id
        self._save_state()
        await ctx.send(f"✅ CVE alerts will be posted to {channel.mention} every 8 hours.\n"
                      f"Use `/cve_enable` to start automatic posting.\n"
                      f"💡 For high-priority exploited vulnerabilities, configure KEV separately with `/kev_set_channel`")
    
    @commands.hybrid_command(name='cve_enable', description='Enable automatic CVE alerts')
    @commands.is_owner()
    async def cve_enable(self, ctx: commands.Context):
        """
        Enable automatic CVE alerts every 8 hours.
        
        Usage:
            !cve_enable
            /cve_enable
        
        Requires: Bot owner only
        """
        if not self.state.get('channel_id'):
            await ctx.send("❌ Please set a channel first with `/cve_set_channel`")
            return
        
        self.state['enabled'] = True
        self._save_state()
        
        if not self.cve_auto_poster.is_running():
            self.cve_auto_poster.start()
        
        channel = self.bot.get_channel(self.state['channel_id'])
        await ctx.send(f"✅ CVE auto-posting **enabled** in {channel.mention if channel else 'the configured channel'}!\n"
                      f"Updates will be posted every 8 hours from {len(CVE_SOURCES)} sources (NVD + Ubuntu).\n"
                      f"💡 Don't forget to enable KEV auto-posting separately for critical exploited vulnerabilities!")
    
    @commands.hybrid_command(name='cve_disable', description='Disable automatic CVE alerts')
    @commands.is_owner()
    async def cve_disable(self, ctx: commands.Context):
        """
        Disable automatic CVE alerts.
        
        Usage:
            !cve_disable
            /cve_disable
        
        Requires: Bot owner only
        """
        self.state['enabled'] = False
        self._save_state()
        
        if self.cve_auto_poster.is_running():
            self.cve_auto_poster.cancel()
        
        await ctx.send("✅ CVE auto-posting **disabled**.")
    
    @commands.hybrid_command(name='cve_status', description='Check CVE auto-poster status')
    async def cve_status(self, ctx: commands.Context):
        """
        Check the status of the CVE auto-poster.
        
        Usage:
            !cve_status
            /cve_status
        """
        channel_id = self.state.get('channel_id')
        channel = self.bot.get_channel(channel_id) if channel_id else None
        enabled = self.state.get('enabled', False)
        sources = self.state.get('sources', list(CVE_SOURCES.keys()))
        posted_count = len(self.state.get('posted_cves', []))
        
        embed = discord.Embed(
            title="� CVE Auto-Poster Status",
            description="General CVE Awareness (NVD + Ubuntu)\nFor critical exploited vulnerabilities, use /kev_status",
            color=0x1C4E80 if enabled else 0x757575
        )
        
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if enabled else "🔴 Disabled",
            inline=True
        )
        
        embed.add_field(
            name="Channel",
            value=channel.mention if channel else "Not set",
            inline=True
        )
        
        embed.add_field(
            name="Frequency",
            value="Every 8 hours",
            inline=True
        )
        
        embed.add_field(
            name="Active Sources",
            value=f"{len(sources)}/{len(CVE_SOURCES)}",
            inline=True
        )
        
        embed.add_field(
            name="CVEs Tracked",
            value=f"{posted_count}",
            inline=True
        )
        
        # List sources
        source_list = []
        for src in sources:
            info = CVE_SOURCES[src]
            source_list.append(f"{info['icon']} {info['name']}")
        
        embed.add_field(
            name="Sources",
            value="\n".join(source_list) if source_list else "None",
            inline=False
        )
        
        embed.set_footer(text="Use /cve_set_channel and /cve_enable to configure")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the CVE cog."""
    await bot.add_cog(CVENews(bot))
    logger.info("CVE News cog loaded")
