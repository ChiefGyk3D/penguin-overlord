# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin Cog - Administrative commands for bot management.
"""

import logging
import discord
from discord.ext import commands
from discord.ui import View, Button

logger = logging.getLogger(__name__)


class HelpPaginatorView(View):
    """View for paginated help embeds with navigation buttons."""
    
    def __init__(self, embeds: list, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.message = None
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page."""
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.embeds) - 1
        self.last_page.disabled = self.current_page == len(self.embeds) - 1
    
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: Button):
        """Go to first page."""
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        """Go to previous page."""
        self.current_page = max(0, self.current_page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        """Go to next page."""
        self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: Button):
        """Go to last page."""
        self.current_page = len(self.embeds) - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: Button):
        """Delete the help message."""
        await interaction.message.delete()
        self.stop()
    
    async def on_timeout(self):
        """Called when the view times out."""
        if self.message:
            try:
                await self.message.edit(view=None)
            except:
                pass


class Admin(commands.Cog):
    """Administrative commands - owner only."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='sync', hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """
        Manually sync slash commands with Discord (owner only).
        
        Usage:
            !sync - Sync commands globally
        """
        await ctx.send("🔄 Syncing slash commands...")
        
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Successfully synced {len(synced)} slash command(s)!")
            logger.info(f"Manual sync: {len(synced)} commands synced by {ctx.author}")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync commands: {e}")
            logger.error(f"Manual sync failed: {e}")
    
    @commands.hybrid_command(name='source_code', description='Get the link to the bot source code')
    async def source_code(self, ctx: commands.Context):
        """
        Get the link to the Penguin Overlord source code on GitHub.
        
        Usage:
            !source_code
            /source_code
        """
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Source Code",
            description="Penguin Overlord is open source! Check out the code, contribute, or report issues.",
            color=0x5865F2,
            url="https://github.com/ChiefGyk3D/penguin-overlord"
        )
        
        embed.add_field(
            name="📦 Repository",
            value="[github.com/ChiefGyk3D/penguin-overlord](https://github.com/ChiefGyk3D/penguin-overlord)",
            inline=False
        )
        
        embed.add_field(
            name="✨ Features",
            value=(
                "• 610+ tech quotes from 70+ legends\n"
                "• XKCD comic integration\n"
                "• Cyber fortune cookies\n"
                "• 250+ Linux command references\n"
                "• Patch Gremlin reminders\n"
                "• HAM radio propagation & solar weather\n"
                "• Aviation transponder & frequency lookup\n"
                "• SIGINT frequency monitoring & SDR tools"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🤝 Contribute",
            value="Pull requests and issues are welcome!\n"
                  "[Open an Issue](https://github.com/ChiefGyk3D/penguin-overlord/issues) | "
                  "[Submit a PR](https://github.com/ChiefGyk3D/penguin-overlord/pulls)",
            inline=False
        )
        
        embed.set_footer(text="Made with 🐧 and ❤️ • Licensed under MPL 2.0")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='help')
    async def help_command(self, ctx: commands.Context, *, command: str = None):
        """
        Display help information for all commands or a specific command.
        
        Usage:
            !help - Show all commands
            !help [command] - Show help for a specific command
        """
        if command:
            # Show help for a specific command
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
        
        # Show all commands grouped by cog
        embeds = []
        
        # Page 1: Overview and XKCD Commands
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Your friendly Discord bot for XKCD comics and tech wisdom!\n\n"
                       "**Navigation:** Use the buttons below to browse through all commands.\n"
                       "All commands work with both `!` prefix and `/` slash commands!",
            color=0x5865F2
        )
        embed.add_field(
            name="📖 XKCD Commands",
            value=(
                "`!xkcd` or `!xkcd [number]` - Get latest or specific XKCD comic\n"
                "`!xkcd_latest` - Get the latest XKCD comic\n"
                "`!xkcd_random` - Get a random XKCD comic\n"
                "`!xkcd_search [keyword]` - Search XKCD comics by keyword\n"
                "\n**🤖 Auto-Poster (Admin):**\n"
                "`!xkcd_set_channel <#channel>` - Set auto-post channel\n"
                "`!xkcd_enable` / `!xkcd_disable` - Toggle auto-posting\n"
                "`!xkcd_post_now` - Force post latest XKCD"
            ),
            inline=False
        )
        embed.add_field(
            name="🎨 Tech Comics",
            value=(
                "`!comic` or `!comic random` - Random tech comic\n"
                "`!comic xkcd` - Latest XKCD (tech/science)\n"
                "`!comic joyoftech` - Latest Joy of Tech (geek culture)\n"
                "`!comic turnoff` - Latest TurnOff.us (Git/DevOps)\n"
                "`!comic_trivia [xkcd_num]` - Explain an XKCD comic\n"
                "\n**📰 Daily Comics (Admin):**\n"
                "`!comic_set_channel <#channel>` - Set daily comic channel\n"
                "`!comic_enable` / `!comic_disable` - Toggle daily posting (9 AM UTC)\n"
                "`!daily_comic` - Force post today's comic"
            ),
            inline=False
        )
        embed.set_footer(text="Page 1 of 6 • Use buttons to navigate")
        embeds.append(embed)
        
        # Page 2: Tech Quote Commands
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Tech Quote commands - Wisdom from 70+ tech legends!",
            color=0x5865F2
        )
        embed.add_field(
            name="💡 Tech Quote Commands",
            value=(
                "`!techquote` - Get a random tech quote\n"
                "`!quote_list` - Browse all quote authors (interactive)\n"
                "`!quote_linus` - Get a quote from Linus Torvalds\n"
                "`!quote_stallman` - Get a quote from Richard Stallman\n"
                "`!quote_hopper` - Get a quote from Grace Hopper\n"
                "`!quote_shevinsky` - Get a quote from Elissa Shevinsky\n"
                "`!quote_may` - Get a quote from Timothy C. May"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 Quote Database",
            value="610+ quotes from over 70 tech legends including:\n"
                  "• Linus Torvalds, Richard Stallman, Steve Jobs\n"
                  "• Grace Hopper, Ada Lovelace, Alan Turing\n"
                  "• Donald Knuth, Edsger Dijkstra, Alan Kay\n"
                  "• And many more pioneers of computing!",
            inline=False
        )
        embed.set_footer(text="Page 2 of 6 • Use buttons to navigate")
        embeds.append(embed)
        
        # Page 3: Fun Commands
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Fun commands for entertainment and learning!",
            color=0x5865F2
        )
        embed.add_field(
            name="🍪 Cyber Fortune Cookie",
            value="`!fortune` - Get random infosec wisdom (sarcastic or real)",
            inline=False
        )
        embed.add_field(
            name="📖 Random Linux Commands",
            value="`!manpage` - Get random Linux command snippets",
            inline=False
        )
        embed.add_field(
            name="🧌 Patch Gremlin",
            value="`!patchgremlin` - Chaotic reminders about system updates",
            inline=False
        )
        embed.set_footer(text="Page 3 of 6 • Use buttons to navigate")
        embeds.append(embed)
        
        # Page 4: HAM Radio, Aviation & SIGINT Commands
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="HAM Radio, Aviation, and Signal Intelligence commands!",
            color=0x5865F2
        )
        embed.add_field(
            name="📻 Radiohead - HAM Radio",
            value=(
                "`!hamradio` - Get HAM radio trivia and facts\n"
                "`!frequency` - Get frequency band information\n"
                "`!propagation` - Get live solar/propagation conditions from NOAA\n"
                "`!solar` - Get detailed solar weather report and band predictions"
            ),
            inline=False
        )
        embed.add_field(
            name="✈️ Plane Spotter - Aviation",
            value=(
                "`!squawk [code]` - Look up transponder codes (or get random)\n"
                "`!aircraft` - Get random aircraft information\n"
                "`!avfreq` - Get aviation frequency information\n"
                "`!avfact` - Get aviation trivia and facts"
            ),
            inline=False
        )
        embed.add_field(
            name="🔍 SIGINT - Signal Intelligence",
            value=(
                "`!frequency_log` - Get interesting frequencies to monitor\n"
                "`!sdrtool` - Get SDR decoder software information\n"
                "`!sigintfact` - Get SIGINT facts and tips"
            ),
            inline=False
        )
        embed.set_footer(text="Page 4 of 6 • Use buttons to navigate")
        embeds.append(embed)
        
        # Page 5: Event Pinger - Cybersecurity Conferences
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Event Pinger - Cybersecurity conference reminders!",
            color=0x5865F2
        )
        embed.add_field(
            name="📅 Event Pinger Commands",
            value=(
                "`!events [days] [type]` - List upcoming events (default: 30 days, all types)\n"
                "`!allevents [type]` - Browse ALL events with pagination (interactive)\n"
                "`!nextevent` - Get the next upcoming event with countdown\n"
                "`!searchevent [query]` - Search events by name or location"
            ),
            inline=False
        )
        embed.add_field(
            name="🔐 Tracked Events",
            value=(
                "**Cybersecurity:** DEF CON, GrrCON, BSides conferences\n"
                "**Ham Radio:** Hamvention, HamCation, SEA-PAC, and more!\n"
                "• Automatically filters out past events\n"
                "• Shows confirmed vs estimated dates"
            ),
            inline=False
        )
        embed.add_field(
            name="💡 Examples",
            value=(
                "`!events` - Show events in next 30 days (limited to 10)\n"
                "`!allevents` - Browse ALL events with pagination\n"
                "`!allevents ham` - Browse all ham radio events\n"
                "`!events 60 cybersecurity` - Cybersecurity events in 60 days\n"
                "`!searchevent Dayton` - Find Dayton Hamvention"
            ),
            inline=False
        )
        embed.set_footer(text="Page 5 of 6 • Use buttons to navigate")
        embeds.append(embed)
        
        # Page 6: General Info and Admin
        embed = discord.Embed(
            title="🐧 Penguin Overlord - Help",
            description="Additional information and admin commands",
            color=0x5865F2
        )
        embed.add_field(
            name="ℹ️ General Commands",
            value=(
                "`!help` - Show this help message\n"
                "`!help [command]` - Get detailed help for a command\n"
                "`!source_code` - Get link to GitHub repository"
            ),
            inline=False
        )
        embed.add_field(
            name="🔧 Admin Commands (Owner Only)",
            value="`!sync` - Manually sync slash commands with Discord",
            inline=False
        )
        embed.add_field(
            name="📚 More Information",
            value=(
                "**Support:** [GitHub Issues](https://github.com/ChiefGyk3D/penguin-overlord/issues)\n"
                "**Source Code:** [GitHub Repository](https://github.com/ChiefGyk3D/penguin-overlord)\n"
                "**Prefix Commands:** Use `!command`\n"
                "**Slash Commands:** Use `/command`"
            ),
            inline=False
        )
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Interactive commands (like `!quote_list`) have navigation buttons\n"
                "• Buttons timeout after 3 minutes of inactivity\n"
                "• Use the 🗑️ button to delete bot messages"
            ),
            inline=False
        )
        embed.set_footer(text="Page 6 of 6 • Made with 🐧 and ❤️")
        embeds.append(embed)
        
        # Create paginator view and send
        view = HelpPaginatorView(embeds)
        message = await ctx.send(embed=embeds[0], view=view)
        view.message = message


async def setup(bot):
    """Load the Admin cog."""
    await bot.add_cog(Admin(bot))
    logger.info("Admin cog loaded")
