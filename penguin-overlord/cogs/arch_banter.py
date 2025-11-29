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
        "has an i3 config longer than the Linux kernel source 🪟",
        "treats rolling releases like extreme sports 🎢",
        "considers a working system 'boring' 😴",
        "has RTFM tattooed somewhere we can't see 📖",
        "debugs systems for fun on weekends 🐛",
        "thinks 'deprecation warnings' are suggestions, not warnings ⚠️",
        "uses arch-chroot like it's a vacation home 🏠",
        "knows more about kernel modules than their own family tree 🌳",
        "writes bash aliases for bash aliases 🔄",
        "considers a GUI a 'crutch' 🩼",
        "has accidentally become a sysadmin through sheer stubbornness 💼",
        "runs `btop` just to watch the pretty colors 🌈",
        "thinks 'LTS' stands for 'Life's Too Short' ⏰",
        "uses tilix/kitty/alacritty because 'performance' (it's actually for the aesthetics) ✨",
        "probably has strong opinions about init systems 🔥",
        "considers a 2000-line .bashrc 'minimalist' 📝",
        "names their partitions like they're naming children 👶",
        "has more themes than clothes 👔",
        "documents their setup but never actually finishes it 📋",
        "thinks sleep is for systems with swap space 💤",
        "measures system boot time in milliseconds competitively ⏱️",
        "has a GitHub dotfiles repo with more stars than friends ⭐",
        "considers 'bloat' anything over 10MB 📦",
        "types 'sudo' before saying 'please' IRL 🙏",
        "has memorized more keybindings than phone numbers ⌨️",
        "thinks 'user-friendly' is an insult 😤",
        "probably runs their desktop on a potato... and it's still faster 🥔",
        "configures Polybar themes like they're diffusing bombs 💣",
        "has strong opinions about which AUR helper is 'superior' 🥊",
        "probably uses a tiling window manager on their grandma's computer too 👵",
        "dreams in hexadecimal color codes 🎨",
        "considers Ubuntu 'training wheels' 🚲",
        "probably has a custom kernel compiled with USE flags they don't understand 🔧",
        "thinks package managers with GUIs are 'dumbing down' Linux 📦",
        "can't remember their anniversary but knows every pacman flag by heart 💝",
        "spent more time choosing a terminal emulator than a career path 💼",
        "uses vim keybindings in their web browser 🌐",
        "has opinions about font rendering that nobody asked for 🔤",
        "considers mouse usage a 'weakness' 🖱️",
        "probably argues about display servers at parties 🎉",
        "thinks 'just works' is suspicious 🤨",
        "has a script for everything except social interaction 📜",
        "spent longer on their Grub theme than their resume 📄",
        "knows every Linux distro's package manager syntax except how to make friends 👥",
        "uses dmenu because 'why need a start menu' 📋",
        "has remapped Caps Lock and judges those who haven't ⌨️",
        "probably uses pass for password management and feels superior about it 🔐",
        "thinks Electron apps are a war crime ⚖️",
        "has more pride in their uptime than their accomplishments 📊",
        "considers systemctl mastery a personality trait 🎭",
        "writes scripts to automate tasks they do once a year 🤖",
        "uses lynx/w3m to browse and acts like it's superior 🕸️",
        "probably has ZSH with Oh-My-Zsh and 47 plugins for 'minimalism' 🐚",
        "thinks snap/flatpak are Satan's package managers 👿",
        "has broken X11 more times than they've been on a date 💔",
        "considers Discord's Electron wrapper a personal insult 😠",
        "probably named their hard drives after Norse gods 🔨",
        "uses ranger/lf because 'GUI file managers are bloat' 📁",
        "thinks firmware blobs are a conspiracy 👁️",
        "has customized their login manager more than their actual desktop 🖥️",
        "probably runs a minimal install with 200+ AUR packages 📦",
        "considers 'it just works' a red flag, not a feature 🚩",
        "has opinions about Wayland vs X11 that could fill a book 📚",
        "uses st (simple terminal) that took 6 hours to configure 'simply' ⏰",
        "thinks proprietary software gave them trust issues 🔒",
        "probably has their shell config version controlled with detailed commit messages 📝",
        "uses calcurse because Google Calendar is 'too mainstream' 📅",
        "has more aliases than a spy in witness protection 🕵️",
        "considers Python 'bloated' but has 50+ pip packages installed 🐍",
        "probably dual boots... with another Arch install for testing 🖥️🖥️",
        "uses newsboat for RSS because 'Feedly is bloatware' 📰",
        "thinks Systemd is literally 1984 📖",
        "has memorized the entire filesystem hierarchy standard 📂",
        "probably uses mpv with custom shaders for 'better video quality' 🎬",
        "considers desktop environments 'handholding' 🤝",
        "uses dunst for notifications with a config longer than most novels 🔔",
        "has strong feelings about PulseAudio vs PipeWire vs ALSA 🔊",
        "probably pipes everything through fzf 'for efficiency' 🔍",
        "uses qutebrowser and judges everyone still on Firefox 🦊",
        "thinks color schemes are worth heated debates 🎨",
        "has a dotfiles installation script that's longer than their will 💾",
        "considers Window Maker 'too modern' actually... 🪟",
        "uses signal-cli because the GUI 'wastes resources' 💬",
        "probably has tmux running inside tmux 🔄",
        "thinks 4GB of RAM is 'plenty' for a desktop 💾",
        "uses weechat with more plugins than their system has packages 💭",
        "considers file managers 'training wheels for cd' 📂",
        "has remapped every key and forgotten the defaults ⌨️",
        "probably uses rofi with a theme that took longer to make than most art 🎨",
        "thinks desktop icons are for people who can't use a terminal 🖼️",
        "uses htop religiously but never actually fixes anything 📊",
        "probably has a USB with 47 different Arch ISOs 💿",
        "considers 'stable' software old and boring 👴",
        "uses Mutt for email in the year 2025 📧",
        "has more opinion about text editors than life philosophy 📝",
        "probably has their window gaps measured to the pixel 📏",
        "thinks startup time under 3 seconds is 'slow' ⚡",
        "uses picom with so many effects it defeats the purpose of i3 ✨",
        "has argued about tabs vs spaces in their WM config 🔧",
        "probably has screenshots of their terminal more than actual photos 📸",
        "considers software with a website 'too commercial' 💼",
        "uses pfetch because neofetch was 'too much' 📊",
        "has a wiki page for their personal setup 📖",
        "thinks RGB is bloat but spends hours on terminal color schemes 🌈",
        "probably has multiple tiling WM configs 'just in case' 💼",
        "uses sxhkd with keybindings that require three hands ⌨️",
        "considers autocomplete 'cheating' 🎯",
        "has more experience with kernel panics than kernel features 💥",
        "probably thinks Snap is worse than malware 🦠",
        "uses cmus for music because Spotify 'phones home' 🎵",
        "has shell scripts older than some Linux users 👴",
        "thinks notification daemons need custom protocols 🔔",
        "probably has three different clipboard managers fighting each other 📋",
        "uses suckless tools that they've patched into complexity 🔨",
        "considers README files 'optional reading material' 📄",
        "has broken more systems than most people have installed 💔",
        "probably judges your choice of status bar 📊",
        "uses dmenu_run and acts like Spotlight search never existed 🔍",
        "thinks systemd-boot is 'too bloated' for a bootloader 🥾",
        "has opinions on filesystem choice that could start wars 💾",
        "probably has custom-compiled everything including their ego 🏗️",
        "uses ungoogled-chromium because regular Chrome is 'spyware' 🕵️",
        "considers mouse acceleration a human rights violation ⚖️",
        "has more dotfile commits than actual work commits 💻",
        "probably uses LaTeX for grocery lists 📝",
        "thinks predictive text is for people who can't type 📱",
        "has remapped so many keys they need a manual to use other computers 🗺️",
        "uses aerc for email because 'terminal emails are faster' ✈️",
        "probably has their shell startup time benchmarked to microseconds ⏱️",
        "considers Firefox ESR 'bleeding edge' 🦊"
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
