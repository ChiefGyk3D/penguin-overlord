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

logger = logging.getLogger(__name__)


class ArchBanter(commands.Cog):
    """Playful banter for Arch Linux mentions."""
    
    def __init__(self, bot):
        self.bot = bot
        # Track recent responses to avoid spam (user_id: timestamp)
        self.recent_responses = {}
        self.cooldown_seconds = 300  # 5 minutes between jokes per user
    
    # List of playful jokes
    ARCH_JOKES = [
        "needs to touch grass! 🌱",
        "is the crossfit vegan of Linux! 🏋️‍♂️🥗",
        "BTW, did you know they use Arch? Oh wait, they already told us. 😏",
        "has achieved enlightenment through pacman -Syu 🧘",
        "probably compiled their own joke from source 📦",
        "spent 6 hours configuring their rice instead of being productive 🍚✨",
        "thinks `yay` is a lifestyle, not just an AUR helper 🎉",
        "is still explaining why systemd is bloat 🗣️",
        "has more dotfiles than friends 📁",
        "reads the Arch Wiki for bedtime stories 📚",
        "probably broke their system updating last night and loved it 💔",
        "installs Gentoo when they want a 'user-friendly' distro 🤓",
        "thinks GUI installers are for weaklings 💪",
        "has memorized the installation guide but not their family's birthdays 🎂",
        "believes stability is for cowards 🎲",
        "spends more time on r/unixporn than actually working 🖼️",
        "uses `neofetch` more than a mirror 🖥️✨",
        "probably void where prohibited... oh wait, that's a different distro 😅",
        "types faster in vim than they talk IRL ⌨️💨",
        "has an i3 config longer than the Linux kernel source 🪟"
    ]
    
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
        
        # Check if any pattern matches
        if not any(re.search(pattern, content_lower) for pattern in arch_patterns):
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
        
        # Pick a random joke
        joke = random.choice(self.ARCH_JOKES)
        
        # Create response with user mention
        response = f"{message.author.mention} {joke}"
        
        try:
            await message.channel.send(response)
            logger.info(f"Responded to Arch mention by {message.author.name} in {message.guild.name}")
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
            name="🎯 Triggers",
            value="Arch Linux mentions, BTW",
            inline=True
        )
        
        embed.add_field(
            name="💡 Pro Tip",
            value="The bot is just joking! Arch is a great distro (but you still need to touch grass 🌱)",
            inline=False
        )
        
        embed.set_footer(text="BTW, I use Python")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the ArchBanter cog."""
    await bot.add_cog(ArchBanter(bot))
    logger.info("ArchBanter cog loaded")
