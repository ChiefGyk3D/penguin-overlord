# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Categorized Help System - Modern dropdown-based help for all commands
"""

import discord
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
                label="Con Recon",
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
                "📰 **News Tracking** - 220+ sources across 11 categories\n"
                "📻 **HAM Radio** - Solar weather, propagation reports\n"
                "✈️ **Aviation** - Squawk codes, frequencies\n"
                "🔍 **SIGINT** - Frequency monitoring, SDR tools\n"
                "📅 **Con Recon** - Conference reminders\n"
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
            description="Automated news from 220+ sources across 11 categories!",
            color=0x5865F2
        )
        embed.add_field(
            name="📊 News Categories (229 sources total)",
            value=(
                "🔒 **Cybersecurity** (115 sources)\n"
                "🏭 **Vendor Alerts** (34 sources)\n"
                "🍎 **Apple/Google** (25 sources)\n"
                "💻 **Tech** (17 sources)\n"
                "🌍 **General News** (12 sources)\n"
                "🎮 **Gaming** (10 sources)\n"
                "🛡️ **CVE** (6 sources)\n"
                "🏛️ **US Legislation** (4 sources)\n"
                "🇪🇺 **EU Legislation** (3 sources)\n"
                "🚨 **KEV** (2 sources)\n"
                "🇬🇧 **UK Legislation** (1 source)\n"
                "Posting schedules are set by the server's timers."
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
                "`/news status <category>` - View current configuration\n"
                "`/news list_sources <category>` - List every source in a category"
            ),
            inline=False
        )
        embed.add_field(
            name="📰 Manual Fetching",
            value=(
                "`/cybersecurity <source>` - Fetch cybersecurity news\n"
                "`/tech <source>` - Fetch tech news\n"
                "`/gaming <source>` - Fetch gaming news\n"
                "`/applegoogle <source>` - Fetch Apple/Google news\n"
                "`/generalnews <source>` - Fetch general news\n"
                "`/uslegislation <source>` - Fetch US legislation\n"
                "`/eulegislation <source>` - Fetch EU legislation\n"
                "`/uklegislation <source>` - Fetch UK legislation\n"
                "`/cve <source>` - Fetch CVE alerts\n"
                "`/kev` - Latest CISA Known Exploited Vulnerabilities"
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
                "`NEWS_UK_LEGISLATION_CHANNEL_ID`\n"
                "`NEWS_GENERAL_NEWS_CHANNEL_ID`\n"
                "`NEWS_KEV_CHANNEL_ID`\n"
                "`NEWS_VENDOR_ALERTS_CHANNEL_ID`"
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
        embed.set_footer(text="📰 News & CVE • 220+ sources, 0 API keys needed!")
        
    elif category == "ham":
        embed = discord.Embed(
            title="📻 HAM Radio - Commands",
            description="Solar weather, propagation reports, and radio information!",
            color=0x5865F2
        )
        embed.add_field(
            name="☀️ Solar & Propagation",
            value=(
                "`!solar` or `!propagation` - Detailed solar weather report and band predictions\n"
                "`!xray [6h|1d|3d|7d]` - GOES Solar X-Ray Flux charts (flare activity)\n"
                "`!drap` - D-Region Absorption Prediction map (HF absorption)\n"
                "`!aurora` - Current auroral oval and 30-min forecast (VHF scatter)\n"
                "`!radio_maps` - Comprehensive propagation maps (D-RAP, aurora, X-ray)\n"
            ),
            inline=False
        )
        embed.add_field(
            name="⚙️ Solar Auto-Posting",
            value=(
                "`!solar_set_channel #channel` - Set auto-post channel\n"
                "`!solar_enable` / `!solar_disable` - Toggle auto-posting (every 30min)\n"
                "`!solar_status` - Check auto-poster configuration\n"
                "*Posts include: Solar report, X-ray chart, D-RAP, Aurora forecast*"
            ),
            inline=False
        )
        embed.add_field(
            name="🗺️ Grid Square & Tools (NEW!)",
            value=(
                "`!grid <lat> <lon>` - Convert coordinates to Maidenhead grid\n"
                "`!grid <grid>` - Show grid square details\n"
                "`!grid <grid1> <grid2>` - Distance & bearing between grids\n"
                "`!contests [days]` - Upcoming amateur radio contests\n"
                "`!satellite [grid]` - Active ham satellites & frequencies\n"
                "`!repeater [location]` - Find repeaters by ZIP/city/grid"
            ),
            inline=False
        )
        embed.add_field(
            name="📡 Radio Info & Bands",
            value=(
                "`!hamradio` - HAM radio trivia and facts\n"
                "`!ham_class <class>` - License class info (Tech/General/Extra)\n"
                "`!bandplan [band]` - ARRL band plan reference (160m-70cm)\n"
                "`!frequency [service]` - Frequency info for services (TV, FM, AM, satellite, etc.)"
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
            title="📅 Con Recon - Conference Calendar",
            description=("Con Recon is the community conference calendar: cybersecurity, ham radio and "
                         "FOSS events, with reminders for the roles you pick."),
            color=0x5865F2
        )
        embed.add_field(
            name="📋 Commands",
            value=(
                "`/events list` - Upcoming events; filter by topic or place, page through\n"
                "`/events next` - Everything in the next 30 days\n"
                "`/events search` - Find an event by name or city\n"
                "`/events submit` - Suggest an event; a moderator reviews it\n"
                "`/events mine` - Your submissions and what happened to them"
            ),
            inline=False
        )
        embed.add_field(
            name="🔔 Reminders",
            value=(
                "Approved events are announced 30, 7 and 1 days out. Pick the topics and "
                "places you care about from the role panels and only those roles get mentioned."
            ),
            inline=False
        )
        embed.set_footer(text="📅 Con Recon • Never miss a con!")
        
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
