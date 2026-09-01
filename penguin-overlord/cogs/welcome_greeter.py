# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Greet members in two stages — a big-box-store bit end to end.

New members arrive twice on this server. First they JOIN and land in
#welcome-newbies, where nothing else is visible yet. Then they VERIFY —
MEE6 grants a role from the #roles channel once they accept the terms — and
that role is what unlocks #general. Each moment gets its own greeting:

  Stage 1 — JOIN  → #welcome-newbies, the Micro Center greeter penguin.
                    "WELCOME TO MICRO CENTER, NERDS." Its whole job is to
                    make the verify steps unmissable.
  Stage 2 — VERIFY → #general, the Costco / Idiocracy penguin.
                    "WELCOME TO COSTCO. I LOVE YOU." A warm, silly intro to
                    the members who just earned their way in.

Both stages share the same batching engine (`_GreetStage`): members are
collected and flushed together at most once per stage per its window,
ALIGNED TO THE WALL CLOCK — the default 900s window means greetings go out
on the quarter hour (:00/:15/:30/:45), so a wave of arrivals is one message
naming several, and a quiet window is silence. The rendered message always
fits Discord's 2000-character limit; very large batches (a MEE6 bulk role
re-sync) mention the first few and count the rest.

Each member is greeted at most once per stage, persisted under `data/`
(join → `welcomed_newbies.json`, verify → `welcomed_users.json`), so role
churn or a re-join never produces a duplicate. The verify stage also gates
on tenure: a veteran who only now picks up the reaction role is not a new
arrival and is quietly marked instead of greeted.

Configuration:
    WELCOME_ENABLED=false            master switch for both stages
    WELCOME_MAX_MENTIONS=12          mention this many; the rest are a count

  Shared channel references (used in message placeholders):
    WELCOME_RULES_CHANNEL_ID=        {rules}
    WELCOME_ROLES_CHANNEL_ID=        {roles}
    WELCOME_RESOURCE_CHANNEL_ID=     {resources}
    WELCOME_WAGON_CHANNEL_ID=        {wagon}   (the #welcome-wagon terms)
    WELCOME_GENERAL_CHANNEL_ID=      {general} (defaults to the verify channel)

  Stage 1 — join (Micro Center → #welcome-newbies):
    WELCOME_JOIN_ENABLED=true        (within WELCOME_ENABLED)
    WELCOME_JOIN_CHANNEL_ID=         where newcomers first land
    WELCOME_JOIN_MESSAGE=            template: {users}{rules}{roles}{wagon}{general}
    WELCOME_JOIN_COOLDOWN_SECONDS=900  window length; flushes align to
                                     wall-clock multiples (900 = the quarter hour)
    WELCOME_JOIN_IMAGE=              attached image ('' = none)

  Stage 2 — verify (Costco → #general):
    WELCOME_VERIFY_ENABLED=true      (within WELCOME_ENABLED)
    WELCOME_ROLE_ID=                 the role whose grant means "verified"
    WELCOME_VERIFY_CHANNEL_ID=       where to greet (defaults to WELCOME_CHANNEL_ID)
    WELCOME_VERIFY_MESSAGE=          template: {users}{roles}
    WELCOME_VERIFY_COOLDOWN_SECONDS=900  window length; flushes align to
                                     wall-clock multiples (900 = the quarter hour)
    WELCOME_VERIFY_IMAGE=            attached image ('' = none)
    WELCOME_MAX_TENURE_DAYS=30       only greet members who JOINED this
                                     recently (0 disables the gate)
"""

import json
import logging
import os
import time
from pathlib import Path

import discord
from discord.ext import commands, tasks

from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)

_ASSETS = Path(__file__).resolve().parent.parent / 'assets'
MICROCENTER_IMAGE = str(_ASSETS / 'tux-micro-center.png')
COSTCO_IMAGE = str(_ASSETS / 'tux-costco-i-love-you.png')

# Stage 1: the Micro Center greeter, shown the moment someone joins. Its one
# job is to make the verify steps impossible to miss.
MICROCENTER_MESSAGE = (
    "🐧 **WELCOME TO MICRO CENTER, NERDS.** 🐧\n"
    "Hey {users}, welcome to **Renegade Penguin**! 🎉 Grab a cart — here's "
    "how to get checked out:\n\n"
    "**1️⃣ Read the terms & verify** → head to {wagon}, read it through, then "
    "in {roles} click the ✅ verification reaction role to agree.\n"
    "**2️⃣ Set your notifications** → while you're in {roles}, grab alerts for "
    "Twitch, TikTok, and YouTube.\n"
    "**3️⃣ Know the rules** → {rules} keeps this cozy corner warm and safe for "
    "everyone.\n\n"
    "The moment you verify, {general} and the rest of the store unlock. Need a "
    "hand? Open a ticket in discord-support and a blue-vest penguin will come "
    "running.\n"
    "Enjoy your stay and **Happy Hacking!** 🐧"
)

# Stage 2: the Costco / Idiocracy penguin, shown when they verify into #general.
COSTCO_MESSAGE = (
    "📣 **WELCOME TO COSTCO. I LOVE YOU.** 📣\n"
    "The doors just slid open and {users} walked in — verified and ready. 🎉\n\n"
    "Remember: **hydrate**. Drink your **Brawndo** — it's got electrolytes, "
    "it's what plants crave. 🥤 Life's a garden, dig it.\n\n"
    "Introduce yourself, grab any roles you missed in {roles}, and make "
    "yourself at home. Welcome to the warehouse — we've got you. 🐧❤️"
)


def _env(name: str, default: str = None) -> str:
    value = os.getenv(name)
    if value is None and name.startswith('WELCOME_'):
        from utils.secrets import get_secret
        value = get_secret('WELCOME', name[8:])
    return value if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_id(name: str):
    raw = _env(name, '')
    return int(raw) if raw and raw.isdigit() else None


class _GreetStage:
    """One batched greeting flow. Collects members, flushes them together at
    most once per `cooldown`-second window ALIGNED TO THE WALL CLOCK (900 →
    on the quarter hour), greets each at most once ever (persisted)."""

    def __init__(self, bot, *, name, enabled, channel_id, template,
                 default_template, image_path, cooldown, max_mentions,
                 welcomed_file, refs, max_tenure_days=0.0):
        self.bot = bot
        self.name = name
        self.enabled = enabled
        self.channel_id = channel_id
        self.template = template or default_template
        self.default_template = default_template
        self.image_path = image_path
        self.cooldown = cooldown
        self.max_mentions = max_mentions
        self.welcomed_file = welcomed_file
        self.refs = refs                     # {placeholder: channel_id}
        self.max_tenure_days = max_tenure_days
        self._welcomed = self._load()
        self._pending: list = []
        # The clock-aligned window we last flushed in (or booted in): members
        # queued during window N go out at the first tick of window N+1, so
        # greetings land ON the boundary (:00/:15/:30/:45 for 900s), never
        # mid-window right after a boot.
        self._last_period = int(time.time() // self.cooldown)
        self._queued_period = None           # window the pending batch started in

    # ------------------------------------------------------------ storage

    def _load(self) -> set:
        try:
            path = resolve_data_dir() / self.welcomed_file
            return set(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            return set()

    def _save(self):
        try:
            path = resolve_data_dir() / self.welcomed_file
            path.write_text(json.dumps(sorted(self._welcomed)), encoding='utf-8')
        except OSError:
            logger.exception('Could not persist the %s welcomed list', self.name)

    def seen(self, member_id: int) -> bool:
        return (member_id in self._welcomed
                or any(m.id == member_id for m in self._pending))

    def claim(self, member):
        """Mark greeted and queue for the next flush — claimed immediately so
        whatever happens to the send, nobody is greeted twice."""
        self._welcomed.add(member.id)
        self._save()
        if not self._pending:
            # Remember which window this batch started in: it flushes at the
            # first tick AFTER the next boundary, never mid-window (a quiet
            # stretch used to leave _last_period stale, letting the first
            # arrival of a fresh window fire within a minute of joining).
            self._queued_period = int(time.time() // self.cooldown)
        self._pending.append(member)

    def mark_only(self, member_id: int):
        """Record as greeted WITHOUT queueing — for members we deliberately
        skip (tenure gate) so later role churn can never ping them."""
        self._welcomed.add(member_id)
        self._save()

    # ------------------------------------------------------------- render

    def render(self, members: list) -> str:
        def ref(placeholder, fallback):
            cid = self.refs.get(placeholder)
            return f'<#{cid}>' if cid else fallback

        def build(mention_count: int) -> str:
            named = members[:mention_count]
            users = ', '.join(m.mention for m in named)
            overflow = len(members) - len(named)
            if overflow > 0:
                users += f' (and {overflow} more new friends)'
            values = {
                'users': users,
                'user': users,   # older templates used the singular
                'rules': ref('rules', 'the rules channel'),
                'roles': ref('roles', 'the roles channel'),
                'resources': ref('resources', 'the resources channel'),
                'wagon': ref('wagon', 'the welcome channel'),
                'general': ref('general', 'the main channel'),
            }
            try:
                return self.template.format(**values)
            except (KeyError, IndexError):
                logger.warning('%s WELCOME message has an unknown placeholder; '
                               'using the default', self.name)
                return self.default_template.format(**values)

        # Discord hard-caps messages at 2000 characters. Mentions are ~22
        # chars each, so shed names into the overflow count until it fits;
        # even one mention over budget falls back to a plain truncation.
        count = min(len(members), self.max_mentions)
        text = build(count)
        while len(text) > 1990 and count > 1:
            count -= 1
            text = build(count)
        return text[:1997] + '…' if len(text) > 2000 else text

    # -------------------------------------------------------------- flush

    def due(self, now: float) -> bool:
        """Members are waiting AND the wall clock has crossed a
        `cooldown`-aligned boundary since both the last flush and the moment
        the batch started queueing — greetings land ON :00/:15/:30/:45, at
        most one per window."""
        if not self._pending:
            return False
        period = int(now // self.cooldown)
        if self._queued_period is not None and period <= self._queued_period:
            return False
        return period > self._last_period

    async def _flush(self):
        if not self._pending:
            return
        members, self._pending = self._pending, []
        self._queued_period = None
        self._last_period = int(time.time() // self.cooldown)

        # Drive-by joins are real: a member who joined and LEFT before the
        # window boundary renders as @unknown-user in the greeting. Greet
        # only the people still here; if everyone bounced, say nothing.
        still_here = []
        for m in members:
            guild = getattr(m, 'guild', None)
            get_member = getattr(guild, 'get_member', None)
            if callable(get_member) and get_member(m.id) is None:
                continue
            still_here.append(m)
        if len(still_here) < len(members):
            logger.info('%s welcome: %d member(s) left before the flush — '
                        'dropped from the greeting', self.name,
                        len(members) - len(still_here))
        if not still_here:
            return
        members = still_here

        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error('%s welcome channel %s not found', self.name,
                         self.channel_id)
            return

        attachment = None
        if self.image_path:
            try:
                attachment = discord.File(self.image_path, filename='welcome.png')
            except OSError:
                logger.warning('%s welcome image %s unreadable — sending text '
                               'only', self.name, self.image_path)
        try:
            await channel.send(
                self.render(members),
                file=attachment,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False,
                    users=members[:self.max_mentions]),
            )
        except discord.HTTPException:
            logger.exception('Could not send the %s welcome message', self.name)
            return

        logger.info('%s-welcomed %d member(s): %s', self.name, len(members),
                    ', '.join(str(m) for m in members[:5]))


class WelcomeGreeter(commands.Cog):
    """Two-stage greeter: Micro Center on join, Costco on verify."""

    def __init__(self, bot):
        self.bot = bot
        master = _env_bool('WELCOME_ENABLED', False)
        max_mentions = int(_env('WELCOME_MAX_MENTIONS', '12'))
        verify_channel = _env_id('WELCOME_VERIFY_CHANNEL_ID') or _env_id('WELCOME_CHANNEL_ID')

        refs = {
            'rules': _env_id('WELCOME_RULES_CHANNEL_ID'),
            'roles': _env_id('WELCOME_ROLES_CHANNEL_ID'),
            'resources': _env_id('WELCOME_RESOURCE_CHANNEL_ID'),
            'wagon': _env_id('WELCOME_WAGON_CHANNEL_ID'),
            'general': _env_id('WELCOME_GENERAL_CHANNEL_ID') or verify_channel,
        }
        self.role_id = _env_id('WELCOME_ROLE_ID')

        self.join = _GreetStage(
            bot, name='join',
            enabled=master and _env_bool('WELCOME_JOIN_ENABLED', True),
            channel_id=_env_id('WELCOME_JOIN_CHANNEL_ID'),
            template=_env('WELCOME_JOIN_MESSAGE'),
            default_template=MICROCENTER_MESSAGE,
            image_path=_env('WELCOME_JOIN_IMAGE', MICROCENTER_IMAGE),
            cooldown=float(_env('WELCOME_JOIN_COOLDOWN_SECONDS', '900')),
            max_mentions=max_mentions,
            welcomed_file='welcomed_newbies.json',
            refs=refs,
        )
        self.verify = _GreetStage(
            bot, name='verify',
            enabled=master and _env_bool('WELCOME_VERIFY_ENABLED', True),
            channel_id=verify_channel,
            template=_env('WELCOME_VERIFY_MESSAGE'),
            default_template=COSTCO_MESSAGE,
            image_path=_env('WELCOME_VERIFY_IMAGE', COSTCO_IMAGE),
            cooldown=float(_env('WELCOME_VERIFY_COOLDOWN_SECONDS', '900')),
            max_mentions=max_mentions,
            welcomed_file='welcomed_users.json',   # keep the existing dedup file
            refs=refs,
            max_tenure_days=float(_env('WELCOME_MAX_TENURE_DAYS', '30')),
        )

        # Validation: a stage missing its channel (or the verify role) is a
        # misconfiguration, not a crash — turn just that stage off.
        if self.join.enabled and self.join.channel_id is None:
            logger.error('WELCOME_JOIN enabled but WELCOME_JOIN_CHANNEL_ID is '
                         'missing — join greeter stays off')
            self.join.enabled = False
        if self.verify.enabled and (self.role_id is None or self.verify.channel_id is None):
            logger.error('WELCOME_VERIFY enabled but WELCOME_ROLE_ID or its '
                         'channel is missing — verify greeter stays off')
            self.verify.enabled = False

        self.enabled = self.join.enabled or self.verify.enabled
        # The tick only CHECKS for window boundaries; it must run well inside
        # the smallest window so a flush lands promptly after :00/:15/:30/:45.
        live = [s.cooldown for s in (self.join, self.verify) if s.enabled]
        self._base_tick = min([60.0] + live)

    async def cog_load(self):
        if not self.enabled:
            return
        self.greet_tick.change_interval(seconds=self._base_tick)
        self.greet_tick.start()
        logger.info('Welcome greeter active: join=%s (-> %s, %.0fs windows, %d greeted), '
                    'verify=%s (role %s -> %s, %.0fs windows, %d greeted); '
                    'clock-aligned, base tick %.0fs',
                    self.join.enabled, self.join.channel_id, self.join.cooldown,
                    len(self.join._welcomed), self.verify.enabled, self.role_id,
                    self.verify.channel_id, self.verify.cooldown,
                    len(self.verify._welcomed), self._base_tick)

    async def cog_unload(self):
        self.greet_tick.cancel()

    # ------------------------------------------------------------- events

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self.join.enabled or member.bot:
            return
        if self.join.seen(member.id):
            return
        self.join.claim(member)
        logger.info('Join welcome queued for %s (%d pending)',
                    member, len(self.join._pending))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not self.verify.enabled or after.bot:
            return
        if self.role_id in {r.id for r in before.roles}:
            return
        if self.role_id not in {r.id for r in after.roles}:
            return
        if self.verify.seen(after.id):
            return

        # Tenure gate: the verify greeting is for ARRIVALS. A member who has
        # been here for months and only now picks up the reaction role — or an
        # existing member caught in a MEE6 bulk role re-sync — is not new.
        if self.verify.max_tenure_days > 0:
            joined = getattr(after, 'joined_at', None)
            if (joined is not None
                    and (discord.utils.utcnow() - joined).days > self.verify.max_tenure_days):
                self.verify.mark_only(after.id)
                logger.info('Verify welcome for %s skipped — joined %d days '
                            'ago, not a new arrival', after,
                            (discord.utils.utcnow() - joined).days)
                return

        self.verify.claim(after)
        logger.info('Verify welcome queued for %s (%d pending)',
                    after, len(self.verify._pending))

    @tasks.loop(seconds=60)
    async def greet_tick(self):
        """Each base tick, flush whichever stage has crossed into a new
        clock-aligned window with members waiting."""
        now = time.time()
        for stage in (self.join, self.verify):
            if stage.enabled and stage.due(now):
                try:
                    await stage._flush()
                except Exception:
                    logger.exception('%s welcome flush failed', stage.name)

    @greet_tick.before_loop
    async def before_greet_tick(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(WelcomeGreeter(bot))
    logger.info('WelcomeGreeter cog loaded')
