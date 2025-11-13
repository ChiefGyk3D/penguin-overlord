# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
News Manager Cog - Centralized configuration for all news feeds.
Provides role-based source management across Cybersecurity, Tech, Gaming, and CVE feeds.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Optional, Literal
from utils.secrets import get_secret

logger = logging.getLogger(__name__)


class NewsManager(commands.Cog):
    """Centralized news feed configuration and management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config_file = 'data/news_config.json'
        self.config = self._load_config()
    
    def _get_channel_id_from_env(self, category: str) -> Optional[int]:
        """Get channel ID from environment variable or secrets manager."""
        # Try secrets manager first (Doppler/AWS/Vault)
        channel_id_str = get_secret('NEWS', f'{category.upper()}_CHANNEL_ID')
        
        # Fallback to direct env var if not in secrets manager
        if not channel_id_str:
            env_var_name = f"NEWS_{category.upper()}_CHANNEL_ID"
            channel_id_str = os.getenv(env_var_name)
        
        if channel_id_str and str(channel_id_str).isdigit():
            logger.info(f"Using channel ID from secrets for {category}")
            return int(channel_id_str)
        
        return None
    
    def _load_config(self) -> dict:
        """Load news configuration from file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                    # Override channel IDs with environment variables if present
                    for category in config:
                        env_channel_id = self._get_channel_id_from_env(category)
                        if env_channel_id:
                            config[category]['channel_id'] = env_channel_id
                    
                    return config
            except Exception as e:
                logger.error(f"Failed to load news config: {e}")
        
        # Default configuration with optimized staggered intervals
        # Check for environment variable overrides
        def get_default_category(name: str, hours: int, offset: int, concurrency: int = 5) -> dict:
            """Helper to create default category config with env var check."""
            channel_id = self._get_channel_id_from_env(name)
            # Auto-enable if channel is configured via environment variable
            enabled = channel_id is not None
            return {
                'enabled': enabled,
                'channel_id': channel_id,
                'interval_hours': hours,
                'minute_offset': offset,
                'sources': {},
                'approved_roles': [],
                'concurrency_limit': concurrency,
                'use_etag_cache': True
            }
        
        return {
            'cybersecurity': get_default_category('cybersecurity', hours=3, offset=1),
            'tech': get_default_category('tech', hours=4, offset=30),
            'gaming': get_default_category('gaming', hours=2, offset=15),
            'apple_google': get_default_category('apple_google', hours=3, offset=45),
            'cve': get_default_category('cve', hours=8, offset=0, concurrency=3),
            'kev': get_default_category('kev', hours=4, offset=30, concurrency=2),
            'us_legislation': get_default_category('us_legislation', hours=1, offset=5, concurrency=3),
            'eu_legislation': get_default_category('eu_legislation', hours=1, offset=10, concurrency=3),
            'uk_legislation': get_default_category('uk_legislation', hours=1, offset=15, concurrency=3),
            'general_news': get_default_category('general_news', hours=2, offset=20),
            'vendor_alerts': get_default_category('vendor_alerts', hours=0.5, offset=25, concurrency=5)
        }
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save news config: {e}")
    
    def get_category_config(self, category: str) -> dict:
        """Get configuration for a specific category."""
        return self.config.get(category, {})
    
    def is_source_enabled(self, category: str, source_key: str) -> bool:
        """Check if a specific source is enabled."""
        return self.config.get(category, {}).get('sources', {}).get(source_key, True)
    
    def has_permission(self, interaction: discord.Interaction, category: str) -> bool:
        """Check if user has permission to configure this category."""
        if interaction.user.guild_permissions.administrator:
            return True
        
        approved_roles = self.config.get(category, {}).get('approved_roles', [])
        user_role_ids = [role.id for role in interaction.user.roles]
        return any(role_id in approved_roles for role_id in user_role_ids)
    
    # News configuration commands group
    news_group = app_commands.Group(name="news", description="News feed configuration")
    
    @news_group.command(name="set_channel", description="Set the channel for a news category")
    @app_commands.describe(
        category="News category to configure",
        channel="Channel where news will be posted"
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts'],
        channel: discord.TextChannel
    ):
        """Set the posting channel for a news category."""
        if not self.has_permission(interaction, category):
            await interaction.response.send_message(
                "❌ You don't have permission to configure this news category.",
                ephemeral=True
            )
            return
        
        self.config[category]['channel_id'] = channel.id
        self._save_config()
        
        await interaction.response.send_message(
            f"✅ {category.title()} news will be posted to {channel.mention}",
            ephemeral=True
        )
    
    @news_group.command(name="enable", description="Enable auto-posting for a news category")
    @app_commands.describe(category="News category to enable")
    async def enable(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts']
    ):
        """Enable auto-posting for a category."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can enable/disable news categories.",
                ephemeral=True
            )
            return
        
        if not self.config[category].get('channel_id'):
            await interaction.response.send_message(
                f"❌ Please set a channel first using `/news set_channel {category}`",
                ephemeral=True
            )
            return
        
        self.config[category]['enabled'] = True
        self._save_config()
        
        await interaction.response.send_message(
            f"✅ {category.title()} news auto-posting enabled!",
            ephemeral=True
        )
    
    @news_group.command(name="disable", description="Disable auto-posting for a news category")
    @app_commands.describe(category="News category to disable")
    async def disable(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts']
    ):
        """Disable auto-posting for a category."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can enable/disable news categories.",
                ephemeral=True
            )
            return
        
        self.config[category]['enabled'] = False
        self._save_config()
        
        await interaction.response.send_message(
            f"✅ {category.title()} news auto-posting disabled.",
            ephemeral=True
        )
    
    @news_group.command(name="set_interval", description="Set posting interval for a category")
    @app_commands.describe(
        category="News category to configure",
        hours="Hours between posts (1-24)"
    )
    async def set_interval(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts'],
        hours: int
    ):
        """Set the posting interval for a category."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can change posting intervals.",
                ephemeral=True
            )
            return
        
        if not 1 <= hours <= 24:
            await interaction.response.send_message(
                "❌ Interval must be between 1 and 24 hours.",
                ephemeral=True
            )
            return
        
        self.config[category]['interval_hours'] = hours
        self._save_config()
        
        await interaction.response.send_message(
            f"✅ {category.title()} news will post every {hours} hour(s).",
            ephemeral=True
        )
    
    @news_group.command(name="toggle_source", description="Enable/disable a specific news source")
    @app_commands.describe(
        category="News category",
        source="Source key to toggle"
    )
    async def toggle_source(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts'],
        source: str
    ):
        """Toggle a specific news source on/off."""
        if not self.has_permission(interaction, category):
            await interaction.response.send_message(
                "❌ You don't have permission to configure this news category.",
                ephemeral=True
            )
            return
        
        current_state = self.config[category]['sources'].get(source, True)
        new_state = not current_state
        
        self.config[category]['sources'][source] = new_state
        self._save_config()
        
        status = "enabled" if new_state else "disabled"
        await interaction.response.send_message(
            f"✅ Source `{source}` {status} for {category.title()} news.",
            ephemeral=True
        )
    
    @news_group.command(name="add_role", description="Add an approved role for managing sources")
    @app_commands.describe(
        category="News category",
        role="Role to approve"
    )
    async def add_role(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts'],
        role: discord.Role
    ):
        """Add a role that can manage sources for this category."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can manage approved roles.",
                ephemeral=True
            )
            return
        
        if 'approved_roles' not in self.config[category]:
            self.config[category]['approved_roles'] = []
        
        if role.id in self.config[category]['approved_roles']:
            await interaction.response.send_message(
                f"❌ {role.mention} is already approved for {category.title()} news.",
                ephemeral=True
            )
            return
        
        self.config[category]['approved_roles'].append(role.id)
        self._save_config()
        
        await interaction.response.send_message(
            f"✅ {role.mention} can now manage {category.title()} news sources.",
            ephemeral=True
        )
    
    @news_group.command(name="remove_role", description="Remove an approved role")
    @app_commands.describe(
        category="News category",
        role="Role to remove"
    )
    async def remove_role(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts'],
        role: discord.Role
    ):
        """Remove a role from managing this category."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can manage approved roles.",
                ephemeral=True
            )
            return
        
        if role.id not in self.config[category].get('approved_roles', []):
            await interaction.response.send_message(
                f"❌ {role.mention} is not approved for {category.title()} news.",
                ephemeral=True
            )
            return
        
        self.config[category]['approved_roles'].remove(role.id)
        self._save_config()
        
        await interaction.response.send_message(
            f"✅ {role.mention} removed from {category.title()} news management.",
            ephemeral=True
        )
    
    @news_group.command(name="status", description="View configuration for a news category")
    @app_commands.describe(category="News category to view")
    async def status(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts']
    ):
        """Show current configuration for a category."""
        config = self.config.get(category, {})
        
        embed = discord.Embed(
            title=f"📰 {category.title()} News Configuration",
            color=0x5865F2
        )
        
        # Basic status
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if config.get('enabled') else "🔴 Disabled",
            inline=True
        )
        
        # Channel
        channel_id = config.get('channel_id')
        channel_text = f"<#{channel_id}>" if channel_id else "Not set"
        embed.add_field(name="Channel", value=channel_text, inline=True)
        
        # Interval
        interval = config.get('interval_hours', 6)
        embed.add_field(name="Interval", value=f"{interval} hours", inline=True)
        
        # Approved roles
        role_ids = config.get('approved_roles', [])
        if role_ids:
            roles_text = ", ".join([f"<@&{role_id}>" for role_id in role_ids])
        else:
            roles_text = "None (Admins only)"
        embed.add_field(name="Approved Roles", value=roles_text, inline=False)
        
        # Disabled sources
        disabled_sources = [k for k, v in config.get('sources', {}).items() if not v]
        if disabled_sources:
            embed.add_field(
                name="Disabled Sources",
                value=", ".join(f"`{s}`" for s in disabled_sources),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @news_group.command(name="list_sources", description="List all available sources for a category")
    @app_commands.describe(category="News category to list sources for")
    async def list_sources(
        self,
        interaction: discord.Interaction,
        category: Literal['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev', 'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news', 'vendor_alerts']
    ):
        """List all available news sources for a category."""
        # Get the appropriate cog
        cog_name_map = {
            'cybersecurity': 'CybersecurityNews',
            'tech': 'TechNews',
            'gaming': 'GamingNews',
            'apple_google': 'AppleGoogleNews',
            'cve': 'CVENews',
            'us_legislation': 'USLegislationNews',
            'eu_legislation': 'EULegislationNews',
            'general_news': 'GeneralNews'
        }
        
        cog = self.bot.get_cog(cog_name_map[category])
        if not cog:
            await interaction.response.send_message(
                f"❌ {category.title()} news cog not loaded.",
                ephemeral=True
            )
            return
        
        sources = getattr(cog, 'NEWS_SOURCES', {})
        if not sources:
            await interaction.response.send_message(
                f"❌ No sources available for {category.title()}.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"📋 {category.title()} News Sources",
            description=f"Total: {len(sources)} sources",
            color=0x5865F2
        )
        
        config = self.config.get(category, {})
        
        for key, source in sorted(sources.items()):
            enabled = config.get('sources', {}).get(key, True)
            status = "🟢" if enabled else "🔴"
            embed.add_field(
                name=f"{status} {source['name']}",
                value=f"Key: `{key}`",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Prefix command fallbacks (for when slash commands aren't synced yet)
    @commands.command(name='news_set_channel')
    @commands.has_permissions(manage_guild=True)
    async def news_set_channel_prefix(self, ctx: commands.Context, category: str, channel: discord.TextChannel):
        """
        Set the posting channel for a news category (prefix command fallback).
        
        Usage:
            !news_set_channel cybersecurity #security-news
            !news_set_channel tech #tech-news
            !news_set_channel gaming #gaming-news
            !news_set_channel apple_google #apple-google
            !news_set_channel cve #security-alerts
            !news_set_channel us_legislation #us-legislation
            !news_set_channel eu_legislation #eu-legislation
            !news_set_channel general_news #general-news
        
        Requires: Manage Server permission or approved role
        """
        valid_categories = ['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 
                           'us_legislation', 'eu_legislation', 'uk_legislation', 'uk_legislation', 'general_news']
        
        if category not in valid_categories:
            await ctx.send(f"❌ Invalid category. Valid options: {', '.join(valid_categories)}")
            return
        
        # Check permissions using the same logic as slash commands
        if not ctx.author.guild_permissions.administrator:
            approved_roles = self.config.get(category, {}).get('approved_roles', [])
            user_role_ids = [role.id for role in ctx.author.roles]
            if not any(role_id in approved_roles for role_id in user_role_ids):
                await ctx.send("❌ You don't have permission to configure this news category.")
                return
        
        self.config[category]['channel_id'] = channel.id
        self._save_config()
        
        await ctx.send(f"✅ {category.title()} news will be posted to {channel.mention}")
    
    @commands.command(name='news_enable')
    @commands.has_permissions(administrator=True)
    async def news_enable_prefix(self, ctx: commands.Context, category: str):
        """
        Enable auto-posting for a news category (prefix command fallback).
        
        Usage:
            !news_enable cybersecurity
            !news_enable tech
            !news_enable gaming
        
        Requires: Administrator permission
        """
        valid_categories = ['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve',
                           'us_legislation', 'eu_legislation', 'uk_legislation', 'uk_legislation', 'general_news']
        
        if category not in valid_categories:
            await ctx.send(f"❌ Invalid category. Valid options: {', '.join(valid_categories)}")
            return
        
        if category not in self.config:
            await ctx.send(f"❌ Category {category} not found in config.")
            return
        
        if not self.config[category].get('channel_id'):
            await ctx.send(
                f"❌ Please set a channel first: `!news_set_channel {category} #channel`"
            )
            return
        
        self.config[category]['enabled'] = True
        self._save_config()
        
        # Find and notify the cog
        cog_name = f"{category}_news"
        cog = self.bot.get_cog(cog_name)
        if cog and hasattr(cog, 'news_config'):
            cog.news_config['enabled'] = True
            logger.info(f"Enabled {category} news via prefix command")
        
        await ctx.send(f"✅ {category.title()} news auto-posting enabled!")
    
    @commands.command(name='news_disable')
    @commands.has_permissions(administrator=True)
    async def news_disable_prefix(self, ctx: commands.Context, category: str):
        """
        Disable auto-posting for a news category (prefix command fallback).
        
        Usage:
            !news_disable cybersecurity
            !news_disable tech
        
        Requires: Administrator permission
        """
        valid_categories = ['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve',
                           'us_legislation', 'eu_legislation', 'uk_legislation', 'uk_legislation', 'general_news']
        
        if category not in valid_categories:
            await ctx.send(f"❌ Invalid category. Valid options: {', '.join(valid_categories)}")
            return
        
        if category not in self.config:
            await ctx.send(f"❌ Category {category} not found in config.")
            return
        
        self.config[category]['enabled'] = False
        self._save_config()
        
        # Find and notify the cog
        cog_name = f"{category}_news"
        cog = self.bot.get_cog(cog_name)
        if cog and hasattr(cog, 'news_config'):
            cog.news_config['enabled'] = False
            logger.info(f"Disabled {category} news via prefix command")
        
        await ctx.send(f"✅ {category.title()} news auto-posting disabled.")
    
    @commands.command(name='news_status')
    async def news_status_prefix(self, ctx: commands.Context, category: str = None):
        """
        Show status of news categories (prefix command fallback).
        
        Usage:
            !news_status                # Show all categories
            !news_status cybersecurity  # Show specific category
        """
        if category:
            # Show specific category
            valid_categories = ['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve',
                               'us_legislation', 'eu_legislation', 'uk_legislation', 'uk_legislation', 'general_news']
            
            if category not in valid_categories:
                await ctx.send(f"❌ Invalid category. Valid options: {', '.join(valid_categories)}")
                return
            
            config = self.config.get(category, {})
            channel_id = config.get('channel_id')
            enabled = config.get('enabled', False)
            
            # Check if channel came from env var
            env_var_name = f"NEWS_{category.upper()}_CHANNEL_ID"
            env_channel = os.getenv(env_var_name)
            from_env = env_channel and channel_id == int(env_channel) if channel_id else False
            
            embed = discord.Embed(
                title=f"📰 {category.title()} News Status",
                color=0x00FF00 if enabled else 0xFF0000
            )
            
            embed.add_field(name="Status", value="🟢 Enabled" if enabled else "🔴 Disabled", inline=True)
            
            if channel_id:
                channel = ctx.guild.get_channel(channel_id)
                channel_info = channel.mention if channel else f"ID: {channel_id} (deleted?)"
                if from_env:
                    channel_info += f" (from {env_var_name})"
                embed.add_field(
                    name="Channel",
                    value=channel_info,
                    inline=True
                )
            else:
                embed.add_field(name="Channel", value="Not configured", inline=True)
            
            if channel_id and not enabled:
                embed.set_footer(text=f"ℹ️ Channel is set but posting is disabled. Use !news_enable {category} to enable.")
            
            await ctx.send(embed=embed)
        else:
            # Show all categories
            embed = discord.Embed(
                title="📰 All News Categories Status",
                description="Use `!news_status <category>` for details",
                color=0x5865F2
            )
            
            ready_to_enable = []
            
            for cat in ['cybersecurity', 'tech', 'gaming', 'apple_google', 'cve',
                       'us_legislation', 'eu_legislation', 'uk_legislation', 'uk_legislation', 'general_news']:
                config = self.config.get(cat, {})
                enabled = config.get('enabled', False)
                channel_id = config.get('channel_id')
                
                status = "🟢 Enabled" if enabled else "🔴 Disabled"
                
                # Check if from env var
                env_var = f"NEWS_{cat.upper()}_CHANNEL_ID"
                env_value = os.getenv(env_var)
                from_env = env_value and channel_id == int(env_value) if channel_id else False
                
                if from_env:
                    channel_info = "✅ Configured (env)"
                elif channel_id:
                    channel_info = "✅ Configured"
                else:
                    channel_info = "❌ No channel"
                
                if channel_id and not enabled:
                    ready_to_enable.append(cat)
                
                embed.add_field(
                    name=cat.replace('_', ' ').title(),
                    value=f"{status}\n{channel_info}",
                    inline=True
                )
            
            if ready_to_enable:
                embed.set_footer(text=f"ℹ️ {len(ready_to_enable)} categories have channels set but are disabled. Use !news_enable <category> to enable.")
            
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(NewsManager(bot))
    logger.info("News Manager cog loaded")
