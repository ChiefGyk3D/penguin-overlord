# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Profile Screen — usernames and display names get the same look messages do.

A member who arrives as "Aydolf hitler" has told you everything before
typing a word, yet nothing looked at the name: the greeter tagged it warmly
and moderators found out when they found out. This cog screens every
member's username, global display name, and server nickname at join and on
every change, and when a name is unacceptable it:

  1. HOLDS the welcome greeter for that member (no warm welcome until a
     moderator decides), and
  2. posts a Profile alert to the moderation alert channel with Ban / Kick /
     Dismiss buttons. Dismiss releases the hold; Ban and Kick act at once.

Screening is two-stage, cheap first:
  - terms: the shared moderation deny-list (leetspeak- and separator-aware)
    plus a short list of name-only terms (`hitler`, `nazi`, ...) that would
    be ordinary in conversation but are not ordinary as a NAME, plus staff
    and owner impersonation ("Discord Moderator", the owner's handle).
  - model: names that pass the term screen get one focused question to the
    local second-stage model (the same plumbing the newcomer helper uses).
    Only a confident 'hateful' or 'impersonation' verdict flags; 'clean' or
    an unavailable model stays quiet, because alerting on every join is
    noise, not moderation.

What bots cannot see: the "About Me" bio. Discord exposes it to no bot, MEE6
included. Discord's own AutoMod CAN screen it through a member-profile
keyword rule, and `/profile sync-automod` writes one from the same term
lists, so bios are covered without a second word list to maintain.

Configuration:
    PROFILE_SCREEN_ENABLED=false      master switch
    PROFILE_SCREEN_LLM=true           ask the second-stage model after the
                                      term screen (needs AI moderation set up)
    PROFILE_SCREEN_HOLD_GREETING=true park the welcome while a flag is open
    PROFILE_SCREEN_PROTECTED_NAMES=   extra impersonation targets, comma
                                      separated (the owner's names are
                                      always protected)
    MOD_ALERT_CHANNEL_ID=             reused: where Profile alerts go
    MOD_PING_ROLE_ID=                 reused: role pinged on an alert
    data/profile_blocklist.txt        optional operator name-only terms,
                                      one per line, # comments
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ai.guardrails import _DENY_TERMS, _load_operator_blocklist, find_blocked_terms, strip_invisible
from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)

# Fine in a sentence, not fine as a name. Matched with the deny-list's
# boundary rules, so 'Nazim' and 'Adolfo' pass while 'heil hitler' does not.
NAME_TERMS = (
    'hitler', 'adolf', 'nazi', 'nazis', 'heil', 'sieg heil', 'kkk', 'klansman',
    'himmler', 'goebbels', 'mengele', 'swastika', 'gas the jews', 'jew killer',
    'rapist', 'pedo', 'pedophile', 'paedophile', 'child lover', 'lolicon',
    'school shooter', 'mass shooter',
)

# Whole-word staff claims. 'mod' and 'admin' alone hit too many gamer tags;
# these do not.
_IMPERSONATION = (
    'moderator', 'administrator', 'discord staff', 'discord support',
    'discord admin', 'discord mod', 'server admin', 'server owner',
    'official discord', 'system message',
)

PROFILE_PROMPT = """You screen Discord profile names for a friendly hacker community. You are
given a member's username, display name, and nickname. Decide whether the
NAMES THEMSELVES are unacceptable:

- hateful: slurs; references to genocide or its perpetrators (Hitler, Nazi
  imagery, 1488, 88 paired with white-power cues); dehumanizing content about
  a protected group; glorifying mass violence or child abuse. This includes
  leetspeak, spacing tricks, and deliberate misspellings meant to slip past a
  filter (e.g. "Aydolf", "h1tl3r", "n1gg4").
- impersonation: claims to be Discord staff, a moderator or administrator of
  this server, or a specific known person here.
- clean: everything else. Edgy jokes, gamer tags, foreign words, and names
  that merely CONTAIN a bad substring by accident (Nazim, Adolfo, kkkaty,
  Scunthorpe) are clean. When in doubt, clean.

Respond with exactly one line and nothing else:
VERDICT: hateful | impersonation | clean"""

_PROFILE_VERDICTS = frozenset({'hateful', 'impersonation', 'clean'})

_COLORS = {'hate_speech': 0xD32F2F, 'impersonation': 0xF57C00}


@dataclass
class ProfileVerdict:
    category: str            # hate_speech | impersonation
    reason: str
    source: str              # denylist | model


def _env(name: str, default: str = '') -> str:
    return os.getenv(name, default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _load_profile_blocklist() -> tuple:
    path = Path(resolve_data_dir()) / 'profile_blocklist.txt'
    try:
        if path.exists():
            return tuple(
                line.strip().lower()
                for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.strip().startswith('#'))
    except OSError:
        pass
    return ()


def _name_terms() -> tuple:
    return NAME_TERMS + _load_operator_blocklist() + _load_profile_blocklist()


def _plain(name: str) -> str:
    """Lowercase, separators to spaces, for whole-word impersonation checks."""
    name = strip_invisible(name or '').lower()
    return re.sub(r'[\W_]+', ' ', name).strip()


def screen_terms(names: list, protected: tuple = ()) -> ProfileVerdict | None:
    """The cheap stage: deny-list + name-only terms + impersonation. Pure."""
    for name in names:
        hits = find_blocked_terms(name, extra_terms=_name_terms())
        if hits:
            return ProfileVerdict('hate_speech',
                                  f'name "{name}" matches: {", ".join(hits)}',
                                  'denylist')
    for name in names:
        plain = _plain(name)
        for term in _IMPERSONATION:
            if re.search(rf'\b{re.escape(term)}\b', plain):
                return ProfileVerdict('impersonation',
                                      f'name "{name}" claims "{term}"',
                                      'denylist')
        squashed = plain.replace(' ', '')
        for target in protected:
            t = _plain(target).replace(' ', '')
            if t and t in squashed:
                return ProfileVerdict('impersonation',
                                      f'name "{name}" imitates "{target}"',
                                      'denylist')
    return None


def automod_keywords() -> list:
    """Keyword list for Discord's member-profile AutoMod rule: the same terms
    this cog screens with, within Discord's limits (1000 words, 60 chars)."""
    seen = []
    for term in list(_DENY_TERMS) + list(_name_terms()):
        term = term.strip().lower()
        if term and len(term) <= 60 and term not in seen:
            seen.append(term)
    return seen[:1000]


AUTOMOD_RULE_NAME = 'Penguin Overlord: profile screen'
AUTOMOD_EVENT = discord.AutoModRuleEventType.member_update


def automod_trigger() -> discord.AutoModTrigger:
    """Discord has two keyword-shaped triggers: `keyword` (type 1) only pairs
    with message_send, and `member_profile` (type 6) is the one that reads
    names and bios on member_update. Passing keyword_filter alone defaults
    to type 1 and the API rejects the rule, so the type is explicit."""
    return discord.AutoModTrigger(
        type=discord.AutoModRuleTriggerType.member_profile,
        keyword_filter=automod_keywords())


def automod_actions() -> list:
    return [discord.AutoModRuleAction(
        type=discord.AutoModRuleActionType.block_member_interactions)]


class ProfileButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=r'profile:(?P<verb>ban|kick|dismiss):(?P<user_id>[0-9]+)'):
    """Persistent alert button: the target lives in the custom_id, so it
    survives restarts like the moderation review buttons."""

    _STYLE = {'ban': discord.ButtonStyle.danger,
              'kick': discord.ButtonStyle.primary,
              'dismiss': discord.ButtonStyle.secondary}

    def __init__(self, verb: str, user_id: int):
        super().__init__(discord.ui.Button(
            style=self._STYLE[verb], label=verb.title(),
            custom_id=f'profile:{verb}:{user_id}'))
        self.verb = verb
        self.user_id = user_id

    @property
    def label(self) -> str:
        return self.item.label

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match['verb'], int(match['user_id']))

    async def callback(self, interaction: discord.Interaction):
        logger.info('Profile button %s:%s clicked by %s',
                    self.verb, self.user_id, interaction.user)
        perms = interaction.user.guild_permissions
        allowed = {'ban': perms.ban_members, 'kick': perms.kick_members,
                   'dismiss': perms.kick_members or perms.manage_messages}
        if not allowed[self.verb]:
            await interaction.response.send_message(
                f'You need permission to {self.verb} members for that.',
                ephemeral=True)
            return
        cog = interaction.client.get_cog('ProfileScreen')
        if cog is None:
            await interaction.response.send_message(
                'Profile screen cog is not loaded.', ephemeral=True)
            return
        outcome = await cog.resolve(interaction.guild, self.user_id,
                                    self.verb, moderator=str(interaction.user))
        embed = None
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.set_footer(text=f'Resolved: {outcome}')
        await interaction.response.edit_message(embed=embed, view=None)


class ProfileScreen(commands.Cog):
    """Screen names at join and on change; hold the welcome; alert mods."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = _env_bool('PROFILE_SCREEN_ENABLED', False)
        self.use_model = _env_bool('PROFILE_SCREEN_LLM', True)
        self.hold_greeting = _env_bool('PROFILE_SCREEN_HOLD_GREETING', True)
        alert = _env('MOD_ALERT_CHANNEL_ID')
        self.alert_channel_id = int(alert) if alert.isdigit() else None
        ping = _env('MOD_PING_ROLE_ID')
        self.ping_role_id = int(ping) if ping.isdigit() else None
        self.protected = tuple(
            t.strip() for t in _env('PROFILE_SCREEN_PROTECTED_NAMES').split(',')
            if t.strip())
        self.analyzer = None
        self._alerted: dict = {}       # user_id -> frozenset(names) alerted on
        self._open: dict = {}          # user_id -> ProfileVerdict awaiting a mod

        if self.enabled and self.alert_channel_id is None:
            logger.error('PROFILE_SCREEN_ENABLED=true but MOD_ALERT_CHANNEL_ID '
                         'is not set; profile screen stays off')
            self.enabled = False

    async def cog_load(self):
        self.bot.add_dynamic_items(ProfileButton)
        if not self.enabled:
            return
        if self.use_model:
            try:
                from ai.manager import get_ai_manager
                from ai.features.moderation import ModerationAnalyzer
                self.analyzer = ModerationAnalyzer(await get_ai_manager())
            except Exception as e:
                logger.error('Profile screen model stage unavailable, terms '
                             'only: %s', type(e).__name__)
        logger.info('Profile screen active: model=%s, hold greeting=%s, '
                    'alerts -> %s', self.analyzer is not None,
                    self.hold_greeting, self.alert_channel_id)

    # ------------------------------------------------------------ screening

    @staticmethod
    def _names(member) -> list:
        names = []
        for attr in ('name', 'global_name', 'nick'):
            value = getattr(member, attr, None)
            if value and value not in names:
                names.append(value)
        return names

    def _protected_for(self, member) -> tuple:
        owner = getattr(getattr(member, 'guild', None), 'owner', None)
        extra = tuple(
            v for v in (getattr(owner, 'name', None),
                        getattr(owner, 'display_name', None)) if v)
        return self.protected + extra

    async def screen(self, member) -> ProfileVerdict | None:
        names = self._names(member)
        if not names:
            return None
        verdict = screen_terms(names, protected=self._protected_for(member))
        if verdict is not None:
            return verdict
        if self.analyzer is None:
            return None
        content = ' / '.join(f'{label}: {value}' for label, value in (
            ('username', getattr(member, 'name', None)),
            ('display name', getattr(member, 'global_name', None)),
            ('nickname', getattr(member, 'nick', None))) if value)
        try:
            answer = await self.analyzer.adjudicate_custom(
                PROFILE_PROMPT, content, str(member),
                allowed=_PROFILE_VERDICTS, kind='profile')
        except Exception as e:
            logger.warning('Profile model check failed: %s', type(e).__name__)
            return None
        if answer == 'hateful':
            return ProfileVerdict('hate_speech',
                                  'second-stage model judged the name hateful',
                                  'model')
        if answer == 'impersonation':
            return ProfileVerdict('impersonation',
                                  'second-stage model judged the name an '
                                  'impersonation', 'model')
        return None

    async def _check(self, member, trigger: str):
        if not self.enabled or getattr(member, 'bot', False):
            return
        owner = getattr(getattr(member, 'guild', None), 'owner', None)
        if owner is not None and getattr(owner, 'id', None) == member.id:
            return
        names = frozenset(self._names(member))
        if self._alerted.get(member.id) == names:
            return
        verdict = await self.screen(member)
        if verdict is None:
            return
        self._alerted[member.id] = names
        if len(self._alerted) > 5000:
            self._alerted.clear()
        await self._flag(member, verdict, trigger)

    async def _flag(self, member, verdict: ProfileVerdict, trigger: str):
        self._open[member.id] = verdict
        if self.hold_greeting:
            greeter = self.bot.get_cog('WelcomeGreeter')
            if greeter is not None:
                greeter.hold(member.id)
        logger.warning('Profile flag (%s, %s) on %s at %s: %s', verdict.category,
                       verdict.source, member, trigger, verdict.reason)

        channel = self.bot.get_channel(self.alert_channel_id)
        if channel is None:
            logger.error('Alert channel %s not found', self.alert_channel_id)
            return

        names = ' · '.join(self._names(member))
        lines = [
            f'**User:** {member.mention} ({member})',
            f'**Names:** {names}',
            f'**Trigger:** {trigger}',
        ]
        created = getattr(member, 'created_at', None)
        if created is not None:
            age = (discord.utils.utcnow() - created).days
            lines.append(f'**Account age:** {age} day{"s" if age != 1 else ""}')
        lines.append(f'**Reason:** {verdict.reason}')
        lines.append(f'**Source:** {verdict.source}'
                     + (' (model call, scrutinize)' if verdict.source == 'model' else ''))
        embed = discord.Embed(
            title=f"🪪 Profile flag: {verdict.category.replace('_', ' ').title()}",
            description='\n'.join(lines),
            color=_COLORS.get(verdict.category, 0x9E9E9E))
        embed.set_footer(text='Ban / Kick act now. Dismiss releases their welcome.')

        view = discord.ui.View(timeout=None)
        for verb in ('ban', 'kick', 'dismiss'):
            view.add_item(ProfileButton(verb, member.id))

        content = None
        allowed = None
        if self.ping_role_id:
            content = f'<@&{self.ping_role_id}>'
            allowed = discord.AllowedMentions(
                everyone=False, users=False,
                roles=[discord.Object(id=self.ping_role_id)])
        try:
            await channel.send(content=content, embed=embed, view=view,
                               allowed_mentions=allowed)
        except discord.HTTPException:
            logger.exception('Could not post the profile alert')

    # ------------------------------------------------------------- resolve

    async def resolve(self, guild, user_id: int, verb: str, moderator: str) -> str:
        """Carry out a moderator's button choice; returns a short outcome
        for the alert footer. Always releases the greeting hold: after a
        ban there is nobody to greet, after a dismiss they are welcome."""
        self._open.pop(user_id, None)
        greeter = self.bot.get_cog('WelcomeGreeter')
        if greeter is not None:
            greeter.release(user_id)
        reason = f'Profile screen: {verb} by {moderator}'

        if verb == 'dismiss':
            return f'dismissed by {moderator}'

        member = None
        get_member = getattr(guild, 'get_member', None)
        if callable(get_member):
            member = get_member(user_id)
        if member is None and callable(getattr(guild, 'fetch_member', None)):
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                member = None
            except discord.HTTPException:
                return f'{verb} failed (Discord error), by {moderator}'

        try:
            if verb == 'kick':
                if member is None:
                    return f'kick: already left, by {moderator}'
                await member.kick(reason=reason)
                return f'kicked by {moderator}'
            if member is not None:
                await member.ban(reason=reason, delete_message_days=1)
            else:
                await guild.ban(discord.Object(id=user_id), reason=reason,
                                delete_message_days=1)
            return f'banned by {moderator}'
        except discord.Forbidden:
            return f'{verb} failed (missing permission), by {moderator}'
        except discord.HTTPException:
            return f'{verb} failed (Discord error), by {moderator}'

    # -------------------------------------------------------------- events

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._check(member, 'join')

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if self._names(before) == self._names(after):
            return
        await self._check(after, 'name change')

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        # Username / global display name changes arrive as user updates.
        if (before.name, before.global_name) == (after.name, after.global_name):
            return
        for guild in getattr(self.bot, 'guilds', []):
            member = guild.get_member(after.id)
            if member is not None:
                await self._check(member, 'name change')

    # ------------------------------------------------------------ commands

    profile = app_commands.Group(
        name='profile', description='Profile screening (owner tools)',
        default_permissions=discord.Permissions(administrator=True))

    @profile.command(name='status', description='Profile screen status')
    async def profile_status(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f'Profile screen: {"on" if self.enabled else "off"}, '
            f'model stage: {"on" if self.analyzer else "off"}, '
            f'open flags: {len(self._open)}, '
            f'name terms: {len(_name_terms())}, '
            f'AutoMod keywords: {len(automod_keywords())}',
            ephemeral=True)

    @profile.command(name='sync-automod',
                     description='Write the name terms into a Discord AutoMod '
                                 'member-profile rule (covers bios)')
    async def profile_sync_automod(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        trigger = automod_trigger()
        actions = automod_actions()
        try:
            existing = [r for r in await guild.fetch_automod_rules()
                        if r.name == AUTOMOD_RULE_NAME]
            if existing:
                await existing[0].edit(trigger=trigger, actions=actions,
                                       enabled=True,
                                       reason='Profile screen sync')
                what = 'updated'
            else:
                await guild.create_automod_rule(
                    name=AUTOMOD_RULE_NAME,
                    event_type=AUTOMOD_EVENT,
                    trigger=trigger, actions=actions, enabled=True,
                    reason='Profile screen sync')
                what = 'created'
        except discord.Forbidden:
            await interaction.followup.send(
                'I need the Manage Server permission to manage AutoMod rules.',
                ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f'AutoMod rule sync failed: {e.text or type(e).__name__}',
                ephemeral=True)
            return
        await interaction.followup.send(
            f'AutoMod member-profile rule {what} with '
            f'{len(trigger.keyword_filter)} keywords. Members whose username, '
            f'display name, nickname, or bio matches are blocked from '
            f'interacting until they change it.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileScreen(bot))
    logger.info('ProfileScreen cog loaded')
