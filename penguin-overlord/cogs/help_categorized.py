# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Categorized Help System - Modern dropdown-based help for all commands
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select
import logging

logger = logging.getLogger(__name__)


class HelpCategorySelect(Select):
    """Dropdown menu for selecting help categories."""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Overview",
                description="Quick introduction to Penguin Overlord",
                emoji="🐧",
                value="overview"
            ),
            discord.SelectOption(
                label="Comics & Fun",
                description="XKCD, daily comics, tech quotes",
                emoji="🎨",
                value="comics"
            ),
            discord.SelectOption(
                label="News & CVE",
                description="Cybersecurity, tech, gaming, legislation news",
                emoji="📰",
                value="news"
            ),
            discord.SelectOption(
                label="HAM Radio",
                description="Propagation, solar weather, frequencies",
                emoji="📻",
                value="ham"
            ),
            discord.SelectOption(
                label="Aviation",
                description="Squawk codes, frequencies, aircraft info",
                emoji="✈️",
                value="aviation"
            ),
            discord.SelectOption(
                label="SIGINT",
                description="Frequency monitoring, SDR tools",
                emoji="🔍",
                value="sigint"
            ),
            discord.SelectOption(
                label="Events",
                description="Conference reminders (DEF CON, BSides, etc.)",
                emoji="📅",
                value="events"
            ),
            discord.SelectOption(
                label="Utilities",
                description="Fortune cookies, manpages, patch reminders",
                emoji="🛠️",
                value="utilities"
            ),
            discord.SelectOption(
                label="Admin",
                description="Configuration and admin commands",
                emoji="⚙️",
                value="admin"
            ),
        ]
        super().__init__(
            placeholder="📚 Choose a category to explore...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle category selection."""
        category = self.values[0]
        embed = get_category_embed(category)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(View):
    """View containing the help category dropdown."""
    
    def __init__(self, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.add_item(HelpCategorySelect())
        self.message = None
    
    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete the help message."""
        await interaction.message.delete()
        self.stop()
    
    async def on_timeout(self):
        """Remove view when timed out."""
        if self.message:
            try:
                await self.message.edit(view=None)
            except:
                pass


def get_category_embed(category: str) -> discord.Embed:
    """Generate embed for a specific help category."""
    
    if category == "overview":
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Your Tech Companion",
            description=(
                "Welcome to Penguin Overlord! A feature-rich Discord bot with:\n\n"
                "🎨 **Comics & Quotes** - XKCD comics, tech quotes from 70+ legends\n"
                "📰 **News Tracking** - 90+ sources across 8 categories\n"
                "📻 **HAM Radio** - Solar weather, propagation reports\n"
                "✈️ **Aviation** - Squawk codes, frequencies\n"
                "🔍 **SIGINT** - Frequency monitoring, SDR tools\n"
                "📅 **Events** - Conference reminders\n"
                "🛠️ **Utilities** - Fortune cookies, manpages, and more!\n\n"
                "**Use the dropdown menu above to explore each category!**"
            ),
            color=0x5865F2
        )
        embed.add_field(
            name="💡 Quick Start",
            value=(
                "• Use `!` prefix for traditional commands: `!xkcd`, `!fortune`\n"
                "• Use `/` for slash commands: `/xkcd`, `/techquote`\n"
                "• All commands work with both methods!"
            ),
            inline=False
        )
        embed.add_field(
            name="📖 Need Help?",
            value=(
                "• Select a category from the dropdown\n"
                "• Use `!help [command]` for specific command help\n"
                "• Visit [GitHub](https://github.com/ChiefGyk3D/penguin-overlord) for docs"
            ),
            inline=False
        )
        embed.set_footer(text="Made with 🐧 and ❤️ • Open Source (MPL 2.0)")
        
    elif category == "comics":
        embed = discord.Embed(
            title="🎨 Comics & Fun - Commands",
            description="XKCD comics, daily tech comics, and tech quotes!",
            color=0x5865F2
        )
        embed.add_field(
            name="📖 XKCD Commands",
            value=(
                "`!xkcd` - Latest XKCD comic\n"
                "`!xkcd [number]` - Specific XKCD by number\n"
                "`!xkcd_random` - Random XKCD\n"
                "`!xkcd_search [keyword]` - Search XKCD comics\n"
                "`!xkcd_latest` - Force fetch latest"
            ),
            inline=False
        )
        embed.add_field(
            name="🎨 Tech Comics",
            value=(
                "`!comic` - Random tech comic\n"
                "`!comic xkcd` - XKCD tech/science\n"
                "`!comic joyoftech` - Joy of Tech (geek culture)\n"
                "`!comic turnoff` - TurnOff.us (Git/DevOps)\n"
                "`!comic_trivia [num]` - Explain XKCD comic"
            ),
            inline=False
        )
        embed.add_field(
            name="💡 Tech Quotes",
            value=(
                "`!techquote` - Random quote from 70+ tech legends\n"
                "`!quote_list` - Browse all authors (interactive)\n"
                "`!quote_linus` - Quote from Linus Torvalds\n"
                "`!quote_stallman` - Quote from Richard Stallman\n"
                "`!quote_hopper` - Quote from Grace Hopper\n"
                "\n**610+ quotes** from pioneers like Steve Jobs, Ada Lovelace, Alan Turing, and more!"
            ),
            inline=False
        )
        embed.add_field(
            name="⚙️ Auto-Posting (Admin)",
            value=(
                "**XKCD:** `!xkcd_set_channel`, `!xkcd_enable/disable`\n"
                "**Comics:** `!comic_set_channel`, `!comic_enable/disable`\n"
                "Or set via env: `XKCD_POST_CHANNEL_ID`, `COMIC_POST_CHANNEL_ID`"
            ),
            inline=False
        )
        embed.set_footer(text="🎨 Comics & Fun • Use dropdown to explore other categories")
        
    elif category == "news":
        embed = discord.Embed(
            title="📰 News & CVE Tracking",
            description="Automated news from 90+ sources across 8 categories!",
            color=0x5865F2
        )
        embed.add_field(
            name="📊 News Categories (90 sources total)",
            value=(
                "🔒 **Cybersecurity** (18 sources) - Every 3h\n"
                "💻 **Tech** (15 sources) - Every 4h\n"
                "🎮 **Gaming** (10 sources) - Every 2h\n"
                "🍎 **Apple/Google** (27 sources) - Every 3h\n"
                "🛡️ **CVE** (3 sources) - Every 6h\n"
                "🏛️ **US Legislation** (5 sources) - Hourly\n"
                "🇪🇺 **EU Legislation** (3 sources) - Hourly\n"
                "🌍 **General News** (7 sources) - Every 2h"
            ),
            inline=False
        )
        embed.add_field(
            name="🔧 Configuration",
            value=(
                "`/news set_channel <category> #channel` - Set posting channel\n"
                "`/news enable <category>` - Enable auto-posting\n"
                "`/news disable <category>` - Disable auto-posting\n"
                "`/news toggle_source <category> <source>` - Toggle individual sources\n"
                "`/news status` - View current configuration"
            ),
            inline=False
        )
        embed.add_field(
            name="📰 Manual Fetching",
            value=(
                "`/cybersecuritynews <source>` - Fetch cybersecurity news\n"
                "`/technews <source>` - Fetch tech news\n"
                "`/gamingnews <source>` - Fetch gaming news\n"
                "`/applegooglenews <source>` - Fetch Apple/Google news\n"
                "`/uslegislation <source>` - Fetch US legislation\n"
                "`/eulegislation <source>` - Fetch EU legislation\n"
                "`/generalnews <source>` - Fetch general news\n"
                "`/cve <source>` - Fetch CVE alerts"
            ),
            inline=False
        )
        embed.add_field(
            name="🔐 Environment Variables (Optional)",
            value=(
                "Configure channels via `.env` or Doppler:\n"
                "`NEWS_CYBERSECURITY_CHANNEL_ID`\n"
                "`NEWS_TECH_CHANNEL_ID`\n"
                "`NEWS_GAMING_CHANNEL_ID`\n"
                "`NEWS_APPLE_GOOGLE_CHANNEL_ID`\n"
                "`NEWS_CVE_CHANNEL_ID`\n"
                "`NEWS_US_LEGISLATION_CHANNEL_ID`\n"
                "`NEWS_EU_LEGISLATION_CHANNEL_ID`\n"
                "`NEWS_GENERAL_NEWS_CHANNEL_ID`"
            ),
            inline=False
        )
        embed.add_field(
            name="✨ Features",
            value=(
                "• No API keys required (all public RSS)\n"
                "• Date filtering (7-day window)\n"
                "• Deduplication (never posts same item twice)\n"
                "• Error handling (failed feeds don't crash bot)\n"
                "• ETag caching (reduces bandwidth)"
            ),
            inline=False
        )
        embed.set_footer(text="📰 News & CVE • 90 sources, 0 API keys needed!")
        
    elif category == "ham":
        embed = discord.Embed(
            title="📻 HAM Radio - Commands",
            description="Solar weather, propagation reports, and radio information!",
            color=0x5865F2
        )
        embed.add_field(
            name="☀️ Solar & Propagation",
            value=(
                "`!solar` or `!propagation` - Detailed solar weather report and propagation conditions\n"
                "`!solar_set_channel #channel` - Set auto-post channel\n"
                "`!solar_enable` / `!solar_disable` - Toggle auto-posting (every 12h)\n"
                "`!solar_post_now` - Force post current conditions"
            ),
            inline=False
        )
        embed.add_field(
            name="📡 Radio Info",
            value=(
                "`!hamradio` - HAM radio trivia and facts\n"
                "`!frequency` - Frequency band information"
            ),
            inline=False
        )
        embed.add_field(
            name="🔐 Environment Variables",
            value=(
                "Set auto-post channel via env:\n"
                "`SOLAR_POST_CHANNEL_ID=your_channel_id`"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 Data Includes",
            value=(
                "• Solar Flux Index (SFI)\n"
                "• Sunspot Number (SSN)\n"
                "• A/K Index (geomagnetic activity)\n"
                "• Band conditions (80m, 40m, 20m, 15m, 10m, 6m, 2m)\n"
                "• ISM/WiFi effects (during R2+ events)\n"
                "• Propagation forecasts\n"
                "• Aurora activity"
            ),
            inline=False
        )
        embed.set_footer(text="📻 HAM Radio • Real-time solar data from NOAA")
        
    elif category == "aviation":
        embed = discord.Embed(
            title="✈️ Aviation - Commands",
            description="Transponder codes, frequencies, and aircraft information!",
            color=0x5865F2
        )
        embed.add_field(
            name="📡 Squawk Codes",
            value=(
                "`!squawk` - Random transponder code with explanation\n"
                "`!squawk [code]` - Look up specific squawk code\n"
                "\n**Famous codes:** 7500 (hijack), 7600 (radio fail), 7700 (emergency)"
            ),
            inline=False
        )
        embed.add_field(
            name="✈️ Aircraft Info",
            value=(
                "`!aircraft` - Random aircraft information\n"
                "Includes specifications, history, and fun facts"
            ),
            inline=False
        )
        embed.add_field(
            name="📻 Frequencies",
            value=(
                "`!avfreq` - Aviation frequency information\n"
                "Guard frequencies, tower frequencies, ATIS, and more"
            ),
            inline=False
        )
        embed.add_field(
            name="🎲 Trivia",
            value=(
                "`!avfact` - Random aviation trivia and facts\n"
                "Learn about aviation history, procedures, and technology"
            ),
            inline=False
        )
        embed.set_footer(text="✈️ Aviation • Plane spotting made easy!")
        
    elif category == "sigint":
        embed = discord.Embed(
            title="🔍 SIGINT - Signal Intelligence",
            description="Frequency monitoring and SDR tools!",
            color=0x5865F2
        )
        embed.add_field(
            name="📻 Frequency Monitoring",
            value=(
                "`!frequency_log` - Interesting frequencies to monitor\n"
                "\nIncludes:\n"
                "• Emergency services\n"
                "• Maritime channels\n"
                "• Aviation frequencies\n"
                "• Weather broadcasts\n"
                "• Satellite downlinks"
            ),
            inline=False
        )
        embed.add_field(
            name="📡 SDR Tools",
            value=(
                "`!sdrtool` - SDR decoder software information\n"
                "\nPopular tools:\n"
                "• GQRX - General purpose SDR\n"
                "• SDR# - Windows SDR software\n"
                "• dump1090 - ADS-B decoder\n"
                "• rtl_433 - 433MHz decoder\n"
                "• And many more!"
            ),
            inline=False
        )
        embed.add_field(
            name="💡 SIGINT Facts",
            value=(
                "`!sigintfact` - SIGINT tips and facts\n"
                "Learn about signal analysis, modulation types, and monitoring tips"
            ),
            inline=False
        )
        embed.add_field(
            name="⚠️ Legal Notice",
            value=(
                "Always follow local laws when monitoring radio frequencies. "
                "Many frequencies are legal to receive but not to transmit on."
            ),
            inline=False
        )
        embed.set_footer(text="🔍 SIGINT • Know your spectrum!")
        
    elif category == "events":
        embed = discord.Embed(
            title="📅 Event Pinger - Conference Tracker",
            description="Track cybersecurity and HAM radio conferences!",
            color=0x5865F2
        )
        embed.add_field(
            name="📋 Event Commands",
            value=(
                "`!events` - List upcoming events (next 30 days)\n"
                "`!events [days]` - List events in next X days\n"
                "`!events [days] [type]` - Filter by type (cybersecurity/ham)\n"
                "`!allevents` - Browse ALL events with pagination\n"
                "`!allevents [type]` - Browse all events of specific type\n"
                "`!nextevent` - Next upcoming event with countdown\n"
                "`!searchevent [query]` - Search events by name/location"
            ),
            inline=False
        )
        embed.add_field(
            name="🔐 Tracked Conferences",
            value=(
                "**Cybersecurity:**\n"
                "• DEF CON, Black Hat, RSA Conference\n"
                "• GrrCON, BSides conferences\n"
                "• ShmooCon, DerbyCon, and more!\n\n"
                "**HAM Radio:**\n"
                "• Dayton Hamvention\n"
                "• HamCation, SEA-PAC\n"
                "• Field Day events"
            ),
            inline=False
        )
        embed.add_field(
            name="💡 Examples",
            value=(
                "`!events` - Show next 30 days\n"
                "`!events 60 cybersecurity` - Cybersecurity in 60 days\n"
                "`!allevents ham` - All ham radio events\n"
                "`!searchevent Dayton` - Find Dayton Hamvention\n"
                "`!nextevent` - What's coming up next?"
            ),
            inline=False
        )
        embed.set_footer(text="📅 Events • Never miss a conference!")
        
    elif category == "utilities":
        embed = discord.Embed(
            title="🛠️ Utilities - Fun Tools",
            description="Fortune cookies, manpages, and system reminders!",
            color=0x5865F2
        )
        embed.add_field(
            name="🍪 Cyber Fortune Cookie",
            value=(
                "`!fortune` - Random infosec wisdom\n"
                "\nGet sarcastic or real cybersecurity advice. "
                "Perfect for daily motivation or comic relief!"
            ),
            inline=False
        )
        embed.add_field(
            name="📖 Random Manpages",
            value=(
                "`!manpage` - Random Linux command snippet\n"
                "\n250+ Linux commands with descriptions. "
                "Learn something new every time!"
            ),
            inline=False
        )
        embed.add_field(
            name="🧌 Patch Gremlin",
            value=(
                "`!patchgremlin` - Chaotic system update reminders\n"
                "\nGet playfully aggressive reminders to update your systems. "
                "Because security updates matter!"
            ),
            inline=False
        )
        embed.set_footer(text="🛠️ Utilities • Learn while you laugh!")
        
    elif category == "admin":
        embed = discord.Embed(
            title="⚙️ Admin & Configuration",
            description="Setup and management commands",
            color=0x5865F2
        )
        embed.add_field(
            name="🔧 Bot Management (Owner Only)",
            value=(
                "`!sync` - Sync slash commands with Discord\n"
                "`!listcogs` - List all loaded cogs and commands"
            ),
            inline=False
        )
        embed.add_field(
            name="📰 News Configuration",
            value=(
                "See **News & CVE** category for full commands\n"
                "Key commands:\n"
                "• `/news set_channel` - Set posting channels\n"
                "• `/news enable/disable` - Toggle categories\n"
                "• `/news status` - View configuration"
            ),
            inline=False
        )
        embed.add_field(
            name="🎨 Comic Auto-Posting",
            value=(
                "**XKCD:**\n"
                "`!xkcd_set_channel #channel` or env: `XKCD_POST_CHANNEL_ID`\n"
                "`!xkcd_enable` / `!xkcd_disable`\n\n"
                "**Daily Comics:**\n"
                "`!comic_set_channel #channel` or env: `COMIC_POST_CHANNEL_ID`\n"
                "`!comic_enable` / `!comic_disable`"
            ),
            inline=False
        )
        embed.add_field(
            name="📻 Solar Auto-Posting",
            value=(
                "`!solar_set_channel #channel` or env: `SOLAR_POST_CHANNEL_ID`\n"
                "`!solar_enable` / `!solar_disable` - Every 12h"
            ),
            inline=False
        )
        embed.add_field(
            name="🔐 Configuration Methods",
            value=(
                "**1. Discord Commands** - Runtime configuration\n"
                "**2. .env File** - Local environment variables\n"
                "**3. Doppler** - Cloud secrets management\n"
                "\nSee [DOPPLER_SETUP.md](https://github.com/ChiefGyk3D/penguin-overlord/blob/main/DOPPLER_SETUP.md)"
            ),
            inline=False
        )
        embed.add_field(
            name="ℹ️ General",
            value=(
                "`!help` - Show this help\n"
                "`!help [command]` - Specific command help\n"
                "`!source_code` - GitHub repository link"
            ),
            inline=False
        )
        embed.set_footer(text="⚙️ Admin • Configure your bot!")
    
    else:
        # Fallback
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Select a category from the dropdown menu above!",
            color=0x5865F2
        )
    
    return embed


class CategorizedHelp(commands.Cog):
    """Modern categorized help system with dropdown menus."""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("Categorized Help cog loaded")
    
    @commands.hybrid_command(name='help', description='Show categorized help')
    async def help_new(self, ctx: commands.Context, *, command: str = None):
        """
        Show categorized help with dropdown navigation.
        
        Usage:
            !help - Show interactive help menu
            !help [command] - Show help for specific command
        """
        if command:
            # For specific commands, show simple help
            cmd = self.bot.get_command(command)
            if cmd is None:
                await ctx.send(f"❌ Command `{command}` not found!")
                return
            
            embed = discord.Embed(
                title=f"Help: {cmd.name}",
                description=cmd.help or "No description available.",
                color=0x5865F2
            )
            
            if cmd.aliases:
                embed.add_field(name="Aliases", value=", ".join(cmd.aliases), inline=False)
            
            if hasattr(cmd, 'usage') and cmd.usage:
                embed.add_field(name="Usage", value=f"`!{cmd.name} {cmd.usage}`", inline=False)
            
            embed.set_footer(text="💡 All commands work with ! or / prefix")
            await ctx.send(embed=embed)
            return
        
        # Show categorized help with dropdown
        embed = get_category_embed("overview")
        view = HelpView()
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot):
    """Load the Categorized Help cog."""
    await bot.add_cog(CategorizedHelp(bot))
    logger.info("Categorized Help cog loaded")
