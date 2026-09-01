# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Skid Detector — a joke alarm that goes off when someone sounds like a
script kiddie.

This is comedy, NOT moderation. It never flags, logs, stores, or reports
anything; it just occasionally posts a deadpan "threat readout" ribbing a
message that pattern-matches classic skiddie energy ("teach me to hack",
"is this illegal", "i downloaded kali"). Everyone is a valid victim —
there is no trust exemption, and the operator gets caught by their own bot
like anyone else, which is the whole joke.

Two dials keep it from being annoying:
- It only *considers* messages that trip a skiddie pattern.
- Even then it fires with probability SKID_FIRE_CHANCE (default 0.30), so
  it stays a surprise rather than a reflex, and a per-user cooldown means
  nobody gets detector-bombed.

With SKID_DETECTOR_LLM on (and the AI roasting feature enabled), the
verdict body is generated per message: roast the skid ENERGY, then flip it
into the truth — hacking is tinkering and playful curiosity, here's how to
start for real ("go hack the kitchen"). The canned verdict list below is
always the fallback when AI is off or fails.

Configuration:
    SKID_DETECTOR_ENABLED=true    master switch (on by default — it's a gag)
    SKID_FIRE_CHANCE=0.30         probability a matching message triggers
    SKID_COOLDOWN_SECONDS=180     per-user quiet period
    SKID_DETECTOR_LLM=false       AI roast-and-redirect body (needs AI
                                  roasting enabled; canned lines otherwise)
"""

import logging
import os
import random
import re
import time

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

# Phrases that radiate script-kiddie energy. Deliberately broad and a little
# unfair — being occasionally wrong is funnier than being precise.
_SKID_PATTERNS = [
    r'\bteach me (?:how )?to hack\b',
    # "learn to hack" is the quintessential skid opener; catch it on its own
    # and after the usual "how do i / wanna / i want to" run-ups.
    r'\b(?:wanna|want to|trying to|tryna|gonna|how (?:do i|to|can i))?\s*learn(?:ing)? (?:how )?to (?:hack|ddos|dox|crack|breach|pwn|swat)\b',
    r'\bhow (?:do i|to|can i) (?:learn (?:how )?to )?(?:hack|ddos|dox|crack|breach|pwn|boot|swat)\b',
    r'\bhow (?:do i|to|can i) (?:get|become) (?:a )?hacker\b',
    r'\bhack (?:my|his|her|their|this|that|the) (?:ex|gf|bf|friend|account|insta|snap|wifi|school)\b',
    r'\b(?:give|send|got|need|want) (?:me )?(?:a )?(?:rat|botnet|stealer|logger|cheat|crypter|c2)\b',
    r'\b(?:free )?(?:booter|stresser|ip puller|token logger|account cracker)\b',
    r'\bis (?:this|it|that) (?:illegal|legal|a crime|traceable|untraceable)\b',
    r'\bcan i (?:go to jail|get caught|get traced|get v& |get vand)\b',
    r'\bi (?:just )?(?:downloaded|installed|got) kali\b',
    r'\bi(?:\'?m| am) (?:basically )?(?:a )?(?:hacker|pentester|red ?team)\b(?!.*\bjob\b)',
    r'\b(?:ip )?grab(?:bed|bing)? (?:his|her|their|your) ip\b',
    r'\bboot(?:ed|ing)? (?:him|her|them|you) offline\b',
    r'\bnigerian prince\b',
    r'\bhow much (?:for|to) (?:hack|a hack|ddos)\b',
    r'\b(?:sql ?inject|sqlmap|metasploit|hydra|aircrack|wireshark)\b.*\b(?:noob|newbie|how|help|easy)\b',
    r'\bwhat(?:\'?s| is) the best (?:hacking|hacker) (?:app|tool|software)\b',
    r'\bmr ?robot (?:taught|showed) me\b',
    r'\bdeauth (?:the|my|his|her|their) (?:whole )?(?:school|neighborhood|street)\b',
]
_SKID_RE = re.compile('|'.join(_SKID_PATTERNS), re.IGNORECASE)

# The gag output. Each is a deadpan mock "readout". {user} is the victim.
_VERDICTS = [
    "🚨 **SKID DETECTOR** 🚨\n{user}, our sensors detected **elite hacker energy**. "
    "Threat level: *downloaded Kali once*. Recommended action: read a man page. 🧢",

    "🚨 **SKID DETECTOR** 🚨\nAlert: {user} is radiating **1337 h4x0r** signals. "
    "Confidence: 420%. Actual skill: `sudo apt install courage`. 💀",

    "🚨 **SKID DETECTOR** 🚨\n{user} flagged for **advanced persistent skiddery**. "
    "Origin IP: 127.0.0.1. Payload: pure vibes. Mitigation: touch keyboard, not grass. ⌨️",

    "🚨 **SKID DETECTOR** 🚨\nSuspect {user} matched the profile: owns a hoodie, "
    "runs `nmap localhost`, calls it a pentest. Sentence: 6 hours on the Arch wiki. 🥷",

    "🚨 **SKID DETECTOR** 🚨\n{user}, your ports are showing. We ran a scan and found "
    "**one (1) open Discord and a dream**. Please close both. 🔍",

    "🚨 **SKID DETECTOR** 🚨\nIncoming threat: {user}. Weapon of choice: a YouTube "
    "tutorial paused at 0:37. Countermeasure deployed: this message. 📼",

    "🚨 **SKID DETECTOR** 🚨\n{user} has been identified as the hacker known as "
    "**4chan**. Interpol notified. (Interpol said 'lol no'.) 🌐",

    "🚨 **SKID DETECTOR** 🚨\nWARNING: {user} said the scary words. Our AI is 100% "
    "sure they own a Guy Fawkes mask still in the Amazon box. 🎭",

    "🚨 **SKID DETECTOR** 🚨\n{user} detected running **Mr. Robot: The Home Game**. "
    "Skill ceiling: `rm -rf` a folder they'll regret. Please don't. 🤖",

    "🚨 **SKID DETECTOR** 🚨\nThreat {user} neutralized. Turns out it was just someone "
    "who found the green-on-black terminal theme. We've all been there. 💚",
]


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def looks_like_skid(content: str) -> bool:
    """True if a message trips a skiddie pattern. Cheap; runs on every message."""
    return bool(content) and _SKID_RE.search(content) is not None


class SkidDetector(commands.Cog):
    """A joke alarm. No moderation, no logging of users — just bits."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = _env('SKID_DETECTOR_ENABLED', 'true').strip().lower() \
            in ('1', 'true', 'yes', 'on')
        self.fire_chance = float(_env('SKID_FIRE_CHANCE', '0.30'))
        self.cooldown = float(_env('SKID_COOLDOWN_SECONDS', '180'))
        self.llm_enabled = _env('SKID_DETECTOR_LLM', 'false').strip().lower() \
            in ('1', 'true', 'yes', 'on')
        self._roaster = None
        self._last: dict = {}

    async def _get_roaster(self):
        """Lazily build the AI roaster; None whenever AI is unavailable."""
        if not self.llm_enabled:
            return None
        if self._roaster is None:
            try:
                from ai.manager import get_ai_manager
                from ai.features.skid_roaster import SkidRoaster
                self._roaster = SkidRoaster(await get_ai_manager())
            except Exception as e:
                logger.error(f"Skid AI unavailable, using canned verdicts: {type(e).__name__}")
                self.llm_enabled = False
                return None
        return self._roaster

    async def _verdict(self, message: discord.Message) -> str:
        """AI roast-and-redirect when available; canned verdict otherwise."""
        roaster = await self._get_roaster()
        if roaster is not None:
            try:
                roast = await roaster.roast(message.content,
                                            message.author.display_name)
            except Exception as e:
                logger.warning(f"Skid roast failed, canned fallback: {type(e).__name__}")
                roast = None
            if roast and roast.strip():
                body = roast.strip()[:400]
                return (f"🚨 **SKID DETECTOR** 🚨\n"
                        f"{message.author.mention} {body}")
        return random.choice(_VERDICTS).format(user=message.author.mention)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.enabled or message.author.bot or not message.guild:
            return
        if not looks_like_skid(message.content):
            return

        # Random fire: a matching message is a candidate, not a guarantee —
        # the surprise is the bit.
        if random.random() >= self.fire_chance:
            return

        now = time.monotonic()
        last = self._last.get(message.author.id)
        if last is not None and now - last < self.cooldown:
            return
        self._last[message.author.id] = now
        if len(self._last) > 5000:
            self._last.clear()

        verdict = await self._verdict(message)
        try:
            await message.reply(
                verdict, mention_author=False,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, users=[message.author]),
            )
        except discord.HTTPException:
            logger.debug('Skid detector could not reply (harmless)')


async def setup(bot):
    await bot.add_cog(SkidDetector(bot))
    logger.info('SkidDetector cog loaded')
