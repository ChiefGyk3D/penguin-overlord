# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Point newcomers at the resources channel when they ask where to start.

"Where do I begin with this?" gets asked constantly in a learning-oriented
server, usually by someone who has not found the pinned channels yet. This
answers once, politely, and then gets out of the way.

The design constraint is the same one that governs moderation here: a
false positive is expensive. A bot that replies to messages that were not
questions is worse than one that stays quiet, because members learn to
tune it out. So:

- Only members in the configured tiers (new by default) are eligible.
- A deterministic pattern must match first — no model call on ordinary chat.
- The second-stage model can then veto a borderline match (HELPER_USE_LLM),
  and when the model is unavailable the deterministic match stands.
- Two cooldowns: one per channel so the bot never chatters, one per person
  so nobody gets followed around.

Configuration (env / secrets, all HELPER_*):
    HELPER_ENABLED=false               master switch
    HELPER_CHANNELS=                   REQUIRED allowlist of channel IDs
    HELPER_TIERS=new                   which trust tiers get the nudge
    HELPER_COOLDOWN_SECONDS=60         per-channel quiet period
    HELPER_USER_COOLDOWN_SECONDS=1800  per-person quiet period
    HELPER_RESOURCE_CHANNEL_ID=        channel to point at
    HELPER_RULES_CHANNEL_ID=           optional second channel (rules)
    HELPER_MESSAGE=                    template; {user} {resources} {rules}
    HELPER_USE_LLM=true                let the model veto a weak match
    HELPER_MIN_LENGTH=12               ignore very short messages
"""

import logging
import re
import time

import discord
from discord.ext import commands

from utils import metrics
from utils.config import section_config

logger = logging.getLogger(__name__)

DEFAULT_MESSAGE = (
    "Welcome {user}! {rules_clause}{resources} is the best place to start."
)

# Deterministic first pass. Every pattern is a request for direction, not
# merely a message containing the word "learn" — 'i learned that yesterday'
# must not trip it.
_ASK_PATTERNS = [
    re.compile(r'(?i)\bwhere\s+(?:do|should|would|can)\s+i\s+(?:start|begin|learn)'),
    re.compile(r'(?i)\bhow\s+(?:do|should|can)\s+i\s+(?:get\s+(?:started|into)|start|learn|begin)'),
    re.compile(r'(?i)\bwhat\s+(?:should|do)\s+i\s+(?:learn|study|read|start\s+with)'),
    re.compile(r'(?i)\b(?:any|got|have)\s+(?:good\s+)?'
               r'(?:resources?|recommendations?|recs|tutorials?|courses?|guides?|books?|'
               r'material|reading)\b'),
    re.compile(r'(?i)\b(?:recommend|suggest)\s+(?:me\s+)?(?:a\s+|any\s+|some\s+)?'
               r'(?:resources?|tutorials?|courses?|guides?|books?|reading|places?)\b'),
    re.compile(r'(?i)\b(?:new|newbie|noob|beginner|just\s+joined|just\s+got\s+here)\b.{0,40}'
               r'\b(?:start|begin|learn|advice|help|resources?)\b'),
    re.compile(r'(?i)\b(?:best|good)\s+way\s+to\s+(?:learn|start|get\s+into)\b'),
    re.compile(r'(?i)\bpoint\s+me\s+(?:to|at|in\s+the\s+right\s+direction)\b'),
    re.compile(r'(?i)\bwhere\s+(?:can|do)\s+i\s+(?:find|look)\b.{0,30}'
               r'\b(?:resources?|guides?|tutorials?|info|information)\b'),
]

# Asking about a specific technical problem is support, not orientation —
# those deserve a human answer, not a signpost.
_SPECIFIC_HELP = re.compile(
    r'(?i)\b(?:error|exception|traceback|stack\s?trace|not\s+working|broken|'
    r'fails?\s+to|why\s+(?:is|does|do)\s+my|my\s+\w+\s+(?:wont|won\'t|isn\'t|is\s+not))\b')

_LLM_QUESTION = (
    "You judge whether a Discord message is a NEWCOMER ASKING FOR DIRECTION "
    "— where to start, what to learn, or which resources to use — as opposed "
    "to anything else, including a specific technical support question, a "
    "statement, a joke, or someone offering resources to others.\n"
    "Respond in EXACTLY this format:\n"
    "VERDICT: asking/not_asking/uncertain\n"
    "REASON: <one short sentence>"
)


def looks_like_resource_request(content: str) -> bool:
    """Deterministic first pass — cheap, and it runs on every message."""
    if not content or _SPECIFIC_HELP.search(content):
        return False
    return any(pattern.search(content) for pattern in _ASK_PATTERNS)


class NewcomerHelper(commands.Cog):
    """Answers 'where do I start?' once, then stays quiet."""

    def __init__(self, bot):
        self.bot = bot
        settings = section_config(bot, 'helper')
        self.enabled = settings.enabled
        self.channels = set(settings.channels)
        self.tiers = set(settings.tiers)
        self.cooldown = settings.cooldown_seconds
        self.user_cooldown = settings.user_cooldown_seconds
        self.min_length = settings.min_length
        self.use_llm = settings.use_llm

        self.resource_channel_id = settings.resource_channel_id
        self.rules_channel_id = settings.rules_channel_id
        self.template = settings.message or DEFAULT_MESSAGE

        # Tier inputs are shared with moderation so one member is one tier.
        moderation = section_config(bot, 'moderation')
        self.member_days = moderation.member_days
        self.veteran_days = moderation.veteran_days
        self.trusted_roles = set(moderation.trusted_roles)
        self.creator_roles = set(moderation.creator_roles)

        self._channel_last = {}
        self._user_last = {}
        self._manager = None

        if not self.enabled:
            return
        if not self.channels:
            logger.error('HELPER_ENABLED=true but HELPER_CHANNELS is empty — '
                         'the helper watches nothing until channels are allowlisted')
            self.enabled = False
        elif self.resource_channel_id is None:
            logger.error('HELPER_ENABLED=true but HELPER_RESOURCE_CHANNEL_ID is '
                         'not set — nothing to point at')
            self.enabled = False

    async def cog_load(self):
        if self.enabled:
            logger.info('Newcomer helper active: watching %d channel(s), tiers=%s, '
                        'cooldown %.0fs/channel %.0fs/user',
                        len(self.channels), ','.join(sorted(self.tiers)),
                        self.cooldown, self.user_cooldown)

    def _tier(self, member) -> str:
        from utils.trust import trust_tier
        return trust_tier(
            member, member_days=self.member_days, veteran_days=self.veteran_days,
            trusted_roles=self.trusted_roles, creator_roles=self.creator_roles,
        )

    def _mention(self, channel_id):
        return f'<#{channel_id}>' if channel_id else None

    def render(self, member) -> str:
        """Fill the configured template. Missing channels degrade gracefully
        rather than leaving a dangling '#None' in a welcome message."""
        resources = self._mention(self.resource_channel_id) or 'the resources channel'
        rules = self._mention(self.rules_channel_id)
        rules_clause = f'Please have a look at {rules}, and ' if rules else ''
        user = getattr(member, 'mention', None) or getattr(member, 'display_name', 'there')
        try:
            return self.template.format(
                user=user, resources=resources, rules=rules or '',
                rules_clause=rules_clause,
            )
        except (KeyError, IndexError):
            # An operator's template referencing an unknown placeholder must
            # not silence the feature — fall back to the shipped wording.
            logger.warning('HELPER_MESSAGE has an unknown placeholder; using the default')
            return DEFAULT_MESSAGE.format(
                user=user, resources=resources, rules=rules or '',
                rules_clause=rules_clause,
            )

    def _cooling_down(self, message, now: float) -> bool:
        """Never-seen must not read as just-seen.

        `time.monotonic()` counts from boot, so a 0 default meant that on a
        freshly started machine `now - 0` was smaller than the cooldown and
        the helper stayed silent for the first minute (and half hour) of its
        life. CI on a fresh runner found this; a rebooted homelab box would
        have hit exactly the same thing.
        """
        last_channel = self._channel_last.get(message.channel.id)
        if last_channel is not None and now - last_channel < self.cooldown:
            return True
        last_user = self._user_last.get(message.author.id)
        return last_user is not None and now - last_user < self.user_cooldown

    async def _confirms(self, content: str, username: str) -> bool:
        """Second-stage veto for a borderline match.

        Returns True when the model agrees or cannot be reached — the
        deterministic pattern already matched, and a downed model should not
        turn the feature off silently.
        """
        if not self.use_llm:
            return True
        try:
            if self._manager is None:
                from ai.manager import get_ai_manager
                self._manager = await get_ai_manager(section_config(self.bot, 'ai'))
            from ai.features.moderation import ModerationAnalyzer
            analyzer = ModerationAnalyzer(
                self._manager, moderation=section_config(self.bot, 'moderation'),
                ai=section_config(self.bot, 'ai'))
            verdict = await analyzer.adjudicate_custom(
                _LLM_QUESTION, content, username,
                allowed={'asking', 'not_asking', 'uncertain'},
            )
            return verdict != 'not_asking'
        except Exception:
            logger.debug('Helper LLM check unavailable; keeping the regex match')
            return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.enabled or message.author.bot or not message.guild:
            return
        if message.channel.id not in self.channels:
            return
        content = (message.content or '').strip()
        if len(content) < self.min_length:
            return
        if self._tier(message.author) not in self.tiers:
            return
        if not looks_like_resource_request(content):
            return

        now = time.monotonic()
        if self._cooling_down(message, now):
            logger.debug('Helper suppressed by cooldown in #%s',
                         getattr(message.channel, 'name', message.channel.id))
            return
        if not await self._confirms(content, message.author.display_name):
            return

        try:
            await message.reply(
                self.render(message.author),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, users=[message.author]),
            )
        except discord.HTTPException:
            logger.exception('Could not send the newcomer pointer')
            return

        self._channel_last[message.channel.id] = now
        self._user_last[message.author.id] = now
        metrics.HELPER_REPLIES.inc()
        logger.info('Pointed %s at the resources channel', message.author)


async def setup(bot):
    await bot.add_cog(NewcomerHelper(bot))
    logger.info('NewcomerHelper cog loaded')
