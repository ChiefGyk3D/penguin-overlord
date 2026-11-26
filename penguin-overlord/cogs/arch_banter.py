# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Arch Banter Cog - Playful jokes when someone mentions Arch Linux.
Because Arch users are the crossfit vegans of Linux!
"""

import logging
import random
import discord
from discord.ext import commands
import re
from datetime import datetime

from ai.features.roast_loader import load_roast_data
from utils.config import section_config
from utils.state import load_json_state, save_json_state, state_path

logger = logging.getLogger(__name__)

# Shipped roast data (jokes, house jokes). A malformed shipped file is a
# packaging bug and fails the import, which tests/unit/test_cog_loading.py catches.
_SHIPPED = {distro: load_roast_data(distro) for distro in ('arch', 'nix')}


class ArchBanter(commands.Cog):
    """Playful banter for Arch Linux mentions."""

    def __init__(self, bot):
        self.bot = bot
        # Track recent responses to avoid spam (user_id: timestamp)
        self.recent_responses = {}
        self.cooldown_seconds = 300  # 5 minutes between jokes per user

        # Track recently used jokes to avoid repetition (keep last 20)
        self.recent_jokes = []
        self.max_recent_jokes = 20

        # Optional AI-generated roasts (requires AI_ENABLED + AI_ROASTING_ENABLED
        # too); the static joke list below is always the fallback.
        banter = section_config(bot, 'banter')
        self.llm_enabled = banter.arch_llm
        self._roaster = None

        # Roast data: shipped files, each replaced wholesale by a valid
        # override file in ARCH_BANTER_DATA_DIR (invalid ones are logged and
        # ignored). Joke banks and the AI roaster both read from this.
        self._roast_data = {d: load_roast_data(d, banter.roast_data_dir) for d in ('arch', 'nix')}
        self.ARCH_JOKES = list(self._roast_data['arch'].fallback_jokes)
        self.NIX_JOKES = list(self._roast_data['nix'].fallback_jokes)
        house = self._roast_data['arch'].house_jokes
        if house:
            self.HOUSE_JOKES = list(house.jokes)
            self.HOUSE_JOKE_CHANCE = house.chance
        else:   # an override without a house section turns the gag off
            self.HOUSE_JOKES = []
            self.HOUSE_JOKE_CHANCE = 0.0

        # Persistent statistics file
        self.stats_file = state_path('arch_banter_stats.json')
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        # Load or initialize statistics
        self.stats = self._load_stats()

    async def _get_roaster(self, distro: str = 'arch'):
        """Lazily build the AI roaster for a distro; None when AI is off."""
        if not self.llm_enabled:
            return None
        if not isinstance(self._roaster, dict):
            self._roaster = {}
        if distro not in self._roaster:
            try:
                from ai.manager import get_ai_manager
                from ai.features.arch_roaster import ArchRoaster, RoastSettings
                manager = await get_ai_manager(section_config(self.bot, 'ai'))
                self._roaster[distro] = ArchRoaster(
                    manager, distro=distro, data=self._roast_data[distro],
                    settings=RoastSettings.from_banter(section_config(self.bot, 'banter')))
            except Exception as e:
                logger.error(f"Banter AI unavailable, using static jokes: {type(e).__name__}")
                self.llm_enabled = False
                return None
        return self._roaster[distro]
    
    # The joke banks live in the roast data files (ai/features/roast_data/),
    # loaded through the same loader the AI roaster uses. These class attributes
    # hold the shipped data; __init__ shadows them per instance when the
    # operator points ARCH_BANTER_DATA_DIR at override files.
    # The house joke surfaces on its own rotation (see HOUSE_JOKE_CHANCE), so it
    # lands "once in a while" even with the AI on.
    HOUSE_JOKES = list(_SHIPPED['arch'].house_jokes.jokes)
    HOUSE_JOKE_CHANCE = _SHIPPED['arch'].house_jokes.chance
    ARCH_JOKES = list(_SHIPPED['arch'].fallback_jokes)
    NIX_JOKES = list(_SHIPPED['nix'].fallback_jokes)

    def _load_stats(self) -> dict:
        """Load statistics from JSON file."""
        loaded = load_json_state(self.stats_file, default=None)
        if loaded is not None:
            return loaded
        
        # Default structure
        return {
            'total_roasts': 0,
            'users': {},  # user_id: {'username': str, 'roast_count': int, 'last_roast': str}
            'first_roast': None,
            'last_roast': None
        }
    
    def _save_stats(self):
        """Save statistics to JSON file."""
        save_json_state(self.stats_file, self.stats)
    
    def _record_roast(self, user_id: int, username: str):
        """Record a roast in statistics."""
        user_id_str = str(user_id)
        timestamp = datetime.now().isoformat()
        
        # Update total count
        self.stats['total_roasts'] += 1
        
        # Update user statistics
        if user_id_str not in self.stats['users']:
            self.stats['users'][user_id_str] = {
                'username': username,
                'roast_count': 0,
                'first_roast': timestamp
            }
        
        self.stats['users'][user_id_str]['roast_count'] += 1
        self.stats['users'][user_id_str]['last_roast'] = timestamp
        self.stats['users'][user_id_str]['username'] = username  # Update in case of username change
        
        # Update first/last roast timestamps
        if not self.stats['first_roast']:
            self.stats['first_roast'] = timestamp
        self.stats['last_roast'] = timestamp
        
        # Save to disk
        self._save_stats()
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for Arch Linux mentions and respond with banter."""
        
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Ignore DMs
        if not message.guild:
            return
        
        # Check if message mentions Arch (case-insensitive)
        content_lower = message.content.lower()
        
        # Pattern to match "arch" but avoid false positives like "search", "architecture", "march"
        # Look for "arch" as a standalone word or in common contexts
        arch_patterns = [
            r'\barch linux\b',
            r'\barch btw\b',
            r'\bi use arch\b',
            r'\busing arch\b',
            r'\barch user\b',
            r'\bon arch\b',
            r'\binstall arch\b',
            r'\barch wiki\b',
            r'\barch is\b',
            r'\b(?:pacman|yay|paru)\b',  # Arch package managers
            r'\baur\b',  # Arch User Repository
            r'\bmanjarno\b',  # Arch derivative joke
            r'\bmanjaro\b',  # Arch derivative
            r'\bartix\b',  # Arch derivative
            r'\bendeavou?r\s*os\b',  # Arch derivative
        ]
        
        nix_patterns = [
            r'\bnixos\b',
            r'\bnix\s+flakes?\b',
            r'\bflake\.nix\b',
            r'\bconfiguration\.nix\b',
            r'\bnixpkgs\b',
            r'\bhome-manager\b',
            r'\bnix-shell\b',
            r'\bnix\s+develop\b',
            r'\bnix-env\b',
            r'\bnix-collect-garbage\b',
            r'\bi\s+use\s+nix\b',
            r'\bon\s+nix\b(?!\w)',
        ]

        # Arch wins a tie ("migrating from Arch to NixOS") purely for
        # seniority; one message never earns two roasts.
        if any(re.search(pattern, content_lower) for pattern in arch_patterns):
            distro = 'arch'
        elif any(re.search(pattern, content_lower) for pattern in nix_patterns):
            distro = 'nix'
        else:
            return
        
        # Check cooldown for this user
        import time
        current_time = time.time()
        user_id = message.author.id
        
        if user_id in self.recent_responses:
            last_response_time = self.recent_responses[user_id]
            if current_time - last_response_time < self.cooldown_seconds:
                # Still in cooldown, don't respond
                return
        
        # Update cooldown tracker
        self.recent_responses[user_id] = current_time
        
        # The house joke surfaces on its own rotation — "once in a while",
        # even when the AI path is on and would otherwise always answer.
        joke = None
        used_ai = False
        if distro == 'arch' and self.HOUSE_JOKES and random.random() < self.HOUSE_JOKE_CHANCE:
            joke = random.choice(self.HOUSE_JOKES)

        # Try an AI-generated roast (opt-in); the static list is the fallback
        roaster = None if joke else await self._get_roaster(distro)
        if roaster:
            try:
                joke = await roaster.roast(
                    message.content,
                    message.author.display_name,
                    context=f"#{message.channel.name}",
                )
                used_ai = joke is not None
            except Exception as e:
                logger.error(f"AI roast failed, falling back to static joke: {type(e).__name__}")
                joke = None

        if not joke:
            jokes = self.ARCH_JOKES if distro == 'arch' else self.NIX_JOKES
            # Pick a random joke that hasn't been used recently
            available_jokes = [j for j in jokes if j not in self.recent_jokes]

            # If we've used most jokes recently, reset the recent list
            if len(available_jokes) < 10:
                self.recent_jokes = []
                available_jokes = jokes

            joke = random.choice(available_jokes)

            # Track this joke as recently used
            self.recent_jokes.append(joke)
            if len(self.recent_jokes) > self.max_recent_jokes:
                self.recent_jokes.pop(0)  # Remove oldest

        # Record the roast
        self._record_roast(user_id, message.author.name)

        # Create response with user mention
        response = f"{message.author.mention} {joke}"

        try:
            await message.channel.send(response)
            mode = 'AI' if used_ai else 'classic'
            logger.info(f"Responded to {distro} mention by {message.author.name} in {message.guild.name} [{mode}] (Total roasts: {self.stats['total_roasts']})")
        except discord.Forbidden:
            logger.warning(f"Missing permissions to send Arch banter in {message.channel.name}")
        except Exception as e:
            logger.error(f"Error sending Arch banter: {e}")
    
    @commands.hybrid_command(name='arch_banter_stats', description='Show Arch banter statistics')
    async def arch_banter_stats(self, ctx: commands.Context):
        """Show statistics about the Arch banter feature."""
        embed = discord.Embed(
            title="📊 Arch Banter Statistics",
            description="Keeping Arch users humble since 2025",
            color=0x1793D1  # Arch Linux blue
        )
        
        embed.add_field(
            name="🎲 Total Jokes Available",
            value=f"{len(self.ARCH_JOKES)} unique roasts",
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Cooldown",
            value=f"{self.cooldown_seconds // 60} minutes per user",
            inline=True
        )
        
        embed.add_field(
            name="🔥 Total Roasts Delivered",
            value=f"{self.stats['total_roasts']} times",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Triggers",
            value="Arch Linux mentions, BTW",
            inline=False
        )
        
        # Show first and last roast if available
        if self.stats['first_roast']:
            first_date = datetime.fromisoformat(self.stats['first_roast']).strftime('%Y-%m-%d')
            embed.add_field(
                name="📅 First Roast",
                value=first_date,
                inline=True
            )
        
        if self.stats['last_roast']:
            last_date = datetime.fromisoformat(self.stats['last_roast']).strftime('%Y-%m-%d %H:%M')
            embed.add_field(
                name="⏰ Last Roast",
                value=last_date,
                inline=True
            )
        
        embed.add_field(
            name="💡 Pro Tip",
            value="The bot is just joking! Arch is a great distro (but you still need to touch grass 🌱)",
            inline=False
        )
        
        embed.set_footer(text="BTW, I use Python • Use !arch_leaderboard for the hall of shame")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='arch_leaderboard', description='Show the Arch user hall of shame')
    async def arch_leaderboard(self, ctx: commands.Context):
        """Display the leaderboard of most-roasted Arch users."""
        embed = discord.Embed(
            title="🏆 Arch User Hall of Shame",
            description="The most devoted Arch evangelists",
            color=0x1793D1  # Arch Linux blue
        )
        
        if not self.stats['users']:
            embed.description = "No Arch users have been roasted yet... surprising! 🤔"
            await ctx.send(embed=embed)
            return
        
        # Sort users by roast count
        sorted_users = sorted(
            self.stats['users'].items(),
            key=lambda x: x[1]['roast_count'],
            reverse=True
        )
        
        # Show top 10
        leaderboard_text = []
        medals = ['🥇', '🥈', '🥉']
        
        for i, (user_id, data) in enumerate(sorted_users[:10], 1):
            medal = medals[i-1] if i <= 3 else f"**{i}.**"
            username = data['username']
            count = data['roast_count']
            
            # Try to mention the user if they're in the server
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_display = user.mention if user else username
            except Exception:
                user_display = username
            
            leaderboard_text.append(f"{medal} {user_display} - **{count}** roast{'s' if count != 1 else ''}")
        
        embed.add_field(
            name="📊 Top Arch Users",
            value="\n".join(leaderboard_text),
            inline=False
        )
        
        embed.add_field(
            name="📈 Total Statistics",
            value=(
                f"**Total Roasts:** {self.stats['total_roasts']}\n"
                f"**Unique Victims:** {len(self.stats['users'])}\n"
                f"**Jokes Used:** {len(self.ARCH_JOKES)} available"
            ),
            inline=False
        )
        
        embed.set_footer(text="BTW, they all use Arch • Wear your roasts with pride! 🌱")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the ArchBanter cog."""
    await bot.add_cog(ArchBanter(bot))
    logger.info("ArchBanter cog loaded")
