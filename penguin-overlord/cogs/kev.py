# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
KEV Cog - Tracks and posts CISA Known Exploited Vulnerabilities.
High priority vulnerabilities that are actively being exploited in the wild.
"""

import logging
import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)


KEV_SOURCES = {
    'cisa_kev': {
        'name': 'CISA Known Exploited Vulnerabilities',
        'url': 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json',
        'type': 'json',
        'color': 0xC41230,
        'icon': '🚨'
    }
}


class KEVNews(commands.Cog):
    """CISA Known Exploited Vulnerabilities tracking and notification system."""
    
    NEWS_SOURCES = KEV_SOURCES  # For compatibility with NewsManager
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/kev_state.json'
        self.state = self._load_state()
        self.kev_auto_poster.start()
    
    def _load_state(self):
        """Load KEV poster state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading KEV state: {e}")
        
        return {
            'last_posted': {},
            'last_check': None,
            'posted_kevs': [],  # Track CVE IDs to avoid duplicates
            'enabled': False,
            'channel_id': None
        }
    
    def _save_state(self):
        """Save KEV poster state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving KEV state: {e}")
    
    async def cog_load(self):
        """Create aiohttp session when cog loads."""
        self.session = aiohttp.ClientSession()
    
    def cog_unload(self):
        """Close aiohttp session and stop auto-poster when cog unloads."""
        self.kev_auto_poster.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())
    
    async def _fetch_kevs(self) -> list:
        """Fetch CISA Known Exploited Vulnerabilities."""
        try:
            async with self.session.get(KEV_SOURCES['cisa_kev']['url'], timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch CISA KEV: HTTP {resp.status}")
                    return []
                
                data = await resp.json()
                vulnerabilities = data.get('vulnerabilities', [])
                
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
            logger.error(f"Error fetching CISA KEV: {e}")
            return []
    
    @commands.hybrid_command(name='kev', description='Get CISA Known Exploited Vulnerabilities')
    async def kev(self, ctx: commands.Context):
        """
        Get CISA Known Exploited Vulnerabilities (KEV).
        
        These are vulnerabilities that are actively being exploited in the wild
        and require immediate attention.
        
        Usage:
            !kev
            /kev
        """
        await ctx.defer()
        
        items = await self._fetch_kevs()
        
        if not items:
            await ctx.send("❌ No KEV data found. CISA feed may be temporarily unavailable.")
            return
        
        # Show latest 5
        for item in items[:5]:
            src_info = KEV_SOURCES['cisa_kev']
            
            embed = discord.Embed(
                title=f"{src_info['icon']} {item['cve_id']}: {item['title'][:100]}",
                url=item['link'],
                description=item['description'][:300],
                color=src_info['color'],
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="Severity",
                value="🔴 CRITICAL (Actively Exploited)",
                inline=True
            )
            
            if item['date_added']:
                embed.add_field(
                    name="Date Added",
                    value=item['date_added'][:10],
                    inline=True
                )
            
            if item['due_date']:
                embed.add_field(
                    name="Due Date",
                    value=item['due_date'][:10],
                    inline=True
                )
            
            if item['vendor'] and item['product']:
                embed.add_field(
                    name="Affected Product",
                    value=f"{item['vendor']} {item['product']}",
                    inline=False
                )
            
            if item['required_action']:
                embed.add_field(
                    name="Required Action",
                    value=item['required_action'][:200],
                    inline=False
                )
            
            embed.set_footer(text=f"Source: {src_info['name']}")
            
            await ctx.send(embed=embed)
    
    @tasks.loop(hours=4)
    async def kev_auto_poster(self):
        """Automatically post new KEVs."""
        try:
            # Get configuration from NewsManager
            manager = self.bot.get_cog('NewsManager')
            if not manager:
                # Fallback to state file
                if not self.state.get('enabled', False):
                    return
            else:
                config = manager.get_category_config('kev')
                if not config.get('enabled'):
                    return
            
            # Get channel from NewsManager or state
            channel_id = None
            if manager:
                config = manager.get_category_config('kev')
                channel_id = config.get('channel_id')
                # Update interval dynamically
                interval = config.get('interval_hours', 4)
                if interval != self.kev_auto_poster.hours:
                    self.kev_auto_poster.change_interval(hours=interval)
            else:
                channel_id = self.state.get('channel_id')
            
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"KEV auto-poster: Channel not found")
                return
            
            posted_kevs = set(self.state.get('posted_kevs', []))
            
            # Check if source is enabled
            if manager and not manager.is_source_enabled('kev', 'cisa_kev'):
                return
            
            items = await self._fetch_kevs()
            
            # Post only new KEVs we haven't posted before
            for item in items:
                cve_id = item['cve_id']
                
                if cve_id not in posted_kevs:
                    src_info = KEV_SOURCES['cisa_kev']
                    
                    embed = discord.Embed(
                        title=f"{src_info['icon']} {item['cve_id']}: {item['title'][:100]}",
                        url=item['link'],
                        description=item['description'][:300],
                        color=src_info['color'],
                        timestamp=datetime.utcnow()
                    )
                    
                    embed.add_field(
                        name="Severity",
                        value="🔴 CRITICAL (Actively Exploited)",
                        inline=True
                    )
                    
                    if item['date_added']:
                        embed.add_field(
                            name="Date Added",
                            value=item['date_added'][:10],
                            inline=True
                        )
                    
                    if item['due_date']:
                        embed.add_field(
                            name="Due Date",
                            value=item['due_date'][:10],
                            inline=True
                        )
                    
                    if item['vendor'] and item['product']:
                        embed.add_field(
                            name="Affected Product",
                            value=f"{item['vendor']} {item['product']}",
                            inline=False
                        )
                    
                    if item['required_action']:
                        embed.add_field(
                            name="Required Action",
                            value=item['required_action'][:200],
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Source: {src_info['name']} • KEV Auto-Poster")
                    
                    await channel.send(embed=embed)
                    
                    posted_kevs.add(cve_id)
                    logger.info(f"KEV auto-poster: Posted {cve_id}")
            
            # Keep only last 500 KEV IDs to prevent state file from growing too large
            self.state['posted_kevs'] = list(posted_kevs)[-500:]
            self.state['last_check'] = datetime.utcnow().isoformat()
            self._save_state()
        
        except Exception as e:
            logger.error(f"KEV auto-poster error: {e}")
    
    @kev_auto_poster.before_loop
    async def before_kev_auto_poster(self):
        """Wait for the bot to be ready before starting the auto-poster."""
        await self.bot.wait_until_ready()
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    @commands.hybrid_command(name='kev_set_channel', description='Set the channel for automatic KEV alerts')
    @commands.has_permissions(manage_guild=True)
    async def kev_set_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """
        Set the channel where KEV alerts will be posted every 4 hours.
        
        Usage:
            !kev_set_channel #security-critical
            /kev_set_channel channel:#security-critical
        
        Requires: Manage Server permission
        """
        channel = channel or ctx.channel
        self.state['channel_id'] = channel.id
        self._save_state()
        await ctx.send(f"✅ KEV alerts will be posted to {channel.mention} every 4 hours.\n"
                      f"Use `/kev_enable` to start automatic posting.")
    
    @commands.hybrid_command(name='kev_enable', description='Enable automatic KEV alerts')
    @commands.is_owner()
    async def kev_enable(self, ctx: commands.Context):
        """
        Enable automatic KEV (Known Exploited Vulnerabilities) alerts every 4 hours.
        
        Usage:
            !kev_enable
            /kev_enable
        
        Requires: Bot owner only
        """
        if not self.state.get('channel_id'):
            await ctx.send("❌ Please set a channel first with `/kev_set_channel`")
            return
        
        self.state['enabled'] = True
        self._save_state()
        
        if not self.kev_auto_poster.is_running():
            self.kev_auto_poster.start()
        
        channel = self.bot.get_channel(self.state['channel_id'])
        await ctx.send(f"✅ KEV auto-posting **enabled** in {channel.mention if channel else 'the configured channel'}!\n"
                      f"🚨 **High Priority:** CISA Known Exploited Vulnerabilities are actively being exploited.\n"
                      f"Updates will be posted every 4 hours.")
    
    @commands.hybrid_command(name='kev_disable', description='Disable automatic KEV alerts')
    @commands.is_owner()
    async def kev_disable(self, ctx: commands.Context):
        """
        Disable automatic KEV alerts.
        
        Usage:
            !kev_disable
            /kev_disable
        
        Requires: Bot owner only
        """
        self.state['enabled'] = False
        self._save_state()
        
        if self.kev_auto_poster.is_running():
            self.kev_auto_poster.cancel()
        
        await ctx.send("✅ KEV auto-posting **disabled**.")
    
    @commands.hybrid_command(name='kev_status', description='Check KEV auto-poster status')
    async def kev_status(self, ctx: commands.Context):
        """
        Check the status of the KEV auto-poster.
        
        Usage:
            !kev_status
            /kev_status
        """
        channel_id = self.state.get('channel_id')
        channel = self.bot.get_channel(channel_id) if channel_id else None
        enabled = self.state.get('enabled', False)
        posted_count = len(self.state.get('posted_kevs', []))
        
        embed = discord.Embed(
            title="🚨 KEV Auto-Poster Status",
            description="CISA Known Exploited Vulnerabilities - Actively Exploited CVEs",
            color=0xC41230 if enabled else 0x757575
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
            value="Every 4 hours",
            inline=True
        )
        
        embed.add_field(
            name="Priority",
            value="🔴 CRITICAL",
            inline=True
        )
        
        embed.add_field(
            name="KEVs Tracked",
            value=f"{posted_count}",
            inline=True
        )
        
        embed.add_field(
            name="Source",
            value="🚨 CISA Known Exploited Vulnerabilities",
            inline=False
        )
        
        embed.set_footer(text="Use /kev_set_channel and /kev_enable to configure")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the KEV cog."""
    await bot.add_cog(KEVNews(bot))
    logger.info("KEV (Known Exploited Vulnerabilities) cog loaded")
