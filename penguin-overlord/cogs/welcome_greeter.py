# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Greet members in two stages — a big-box-store bit end to end.

New members arrive twice on this server. First they JOIN and land in
#welcome-newbies, where nothing else is visible yet — MEE6 posts the
instant hello there, so this bot deliberately does NOT. Then they VERIFY —
MEE6 grants a role from the #roles channel once they accept the terms — and
that role is what unlocks #general. This cog covers two moments MEE6
doesn't:

  Stage 1 — JOIN REMINDER → #welcome-newbies, the Micro Center greeter
                    penguin. "WELCOME TO MICRO CENTER, NERDS." Fires only
                    for members who joined a few minutes ago and STILL
                    haven't verified — a nudge with the checkout steps,
                    not a second hello. Verify (or leave) before the
                    reminder lands and it never mentions you.
  Stage 2 — VERIFY → #general, the Costco / Idiocracy penguin.
                    "WELCOME TO COSTCO. I LOVE YOU." A warm, silly intro to
                    the members who just earned their way in.

Both stages share the same batching engine (`_GreetStage`): members are
collected and flushed together at most once per stage per its window,
ALIGNED TO THE WALL CLOCK. The join reminder runs 900s windows (the quarter
hour: :00/:15/:30/:45); the verify intro runs 10800s windows (one GROUP
welcome every three hours), so a wave of arrivals is one message naming
several, and a quiet window is silence. The rendered message always fits
Discord's 2000-character limit; very large batches (a MEE6 bulk role
re-sync) mention the first few and count the rest.

Each member is greeted at most once per stage, persisted under `data/`
(join → `welcomed_newbies.json`, verify → `welcomed_users.json`), so role
churn or a re-join never produces a duplicate. The verify stage also gates
on tenure: a veteran who only now picks up the reaction role is not a new
arrival and is quietly marked instead of greeted.

A greeting is also cleaned up after the fact: when a member leaves or is
banned within WELCOME_RETRACT_WINDOW_SECONDS of being welcomed, the bot
edits them out of the greeting (or deletes it if they were the only one).
Discord clients render a departed user's mention as @unknown-user however
the message was sent, and a troll banned for their display name should not
keep a warm welcome on the wall either.

Every timer here is environment-tunable; nothing is hardcoded. Each stage
schedules one of two ways:
  - interval windows: WELCOME_<STAGE>_COOLDOWN_SECONDS, aligned to the wall
    clock (900 = the quarter hour, 10800 = every three hours), or
  - a daily send: WELCOME_<STAGE>_DAILY_AT=HH:MM in WELCOME_TIMEZONE (IANA
    name, e.g. America/New_York; DST handled) — one batch per day carrying
    everyone from the previous 24 hours. DAILY_AT wins when both are set.

Configuration:
    WELCOME_ENABLED=false            master switch for both stages
    WELCOME_MAX_MENTIONS=12          mention this many; the rest are a count
    WELCOME_TIMEZONE=UTC             IANA timezone for the DAILY_AT schedules
    WELCOME_RETRACT_WINDOW_SECONDS=86400  edit a leaver out of a greeting
                                     this recent; older ones are history

  Shared channel references (used in message placeholders):
    WELCOME_RULES_CHANNEL_ID=        {rules}
    WELCOME_ROLES_CHANNEL_ID=        {roles}
    WELCOME_RESOURCE_CHANNEL_ID=     {resources}
    WELCOME_WAGON_CHANNEL_ID=        {wagon}   (the #welcome-wagon terms)
    WELCOME_GENERAL_CHANNEL_ID=      {general} (defaults to the verify channel)

  Stage 1 — join reminder (Micro Center → #welcome-newbies):
    WELCOME_JOIN_ENABLED=true        (within WELCOME_ENABLED)
    WELCOME_JOIN_CHANNEL_ID=         where newcomers first land
    WELCOME_JOIN_MESSAGE=            template: {users}{rules}{roles}{wagon}{general}
    WELCOME_JOIN_COOLDOWN_SECONDS=900  window length; flushes align to
                                     wall-clock multiples (900 = the quarter hour)
    WELCOME_JOIN_REMIND_AFTER_SECONDS=300  wait this long after a join;
                                     members who verified (gained
                                     WELCOME_ROLE_ID) or left by then are
                                     silently skipped. With membership
                                     screening on, "join" means clicking
                                     through the rules screen (when MEE6
                                     says hello), not the gateway join.
    WELCOME_JOIN_DAILY_AT=           HH:MM in WELCOME_TIMEZONE for one
                                     reminder batch per day (optional)
    WELCOME_JOIN_IMAGE=              attached image ('' = none)

  Stage 2 — verify (Costco → #general):
    WELCOME_VERIFY_ENABLED=true      (within WELCOME_ENABLED)
    WELCOME_ROLE_ID=                 the role whose grant means "verified"
    WELCOME_VERIFY_CHANNEL_ID=       where to greet (defaults to WELCOME_CHANNEL_ID)
    WELCOME_VERIFY_MESSAGE=          template: {users}{roles}
    WELCOME_VERIFY_COOLDOWN_SECONDS=10800  interval-window length (unused
                                     when DAILY_AT is set)
    WELCOME_VERIFY_DAILY_AT=         HH:MM in WELCOME_TIMEZONE for one group
                                     welcome per day (e.g. 09:00)
    WELCOME_VERIFY_IMAGE=            attached image ('' = none)
    WELCOME_MAX_TENURE_DAYS=30       only greet members who JOINED this
                                     recently (0 disables the gate)
"""

import json
import logging
import time
from pathlib import Path

import discord
from discord.ext import commands, tasks

from utils.config import section_config
from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)


def _timezone(name: str):
    """The ZoneInfo for a config timezone name; UTC when it will not load.

    load_config() already rejects an unknown name at startup, so this only
    catches a lenient environment load in tests and tooling.
    """
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(name or 'UTC')
    except Exception:
        logger.warning('%r is not a known IANA timezone, using UTC', name)
        return ZoneInfo('UTC')

_ASSETS = Path(__file__).resolve().parent.parent / 'assets'
MICROCENTER_IMAGE = str(_ASSETS / 'tux-micro-center.png')
COSTCO_IMAGE = str(_ASSETS / 'tux-costco-i-love-you.png')

# Stage 1: the Micro Center greeter, a REMINDER for members who joined a
# few minutes ago and still haven't verified. MEE6 already said hello; this
# one's job is to make the checkout steps impossible to miss.
# The operator's copy. House style: no em dashes, ever.
MICROCENTER_MESSAGE = (
    "🐧 **WELCOME TO MICRO CENTER, NERDS.** 🐧\n"
    "Hey {users}, welcome to **Renegade Penguin**! 🎉\n\n"
    "Please grab a cart, abandon all expectations of leaving with only the "
    "thing you came for, and follow the blue-vest penguin instructions "
    "below:\n\n"
    "**1️⃣ READ THE TERMS & VERIFY**\n"
    "Head to {wagon} and give everything a read. Then visit {roles} and "
    "click the ✅ verification reaction role to agree.\n\n"
    "**2️⃣ CONFIGURE YOUR ALERTS**\n"
    "While you're in {roles}, grab whatever notification roles you want for "
    "Twitch, TikTok, YouTube, and the other assorted chaos.\n\n"
    "**3️⃣ KNOW THE RULES**\n"
    "{rules} contains the rules that keep this particular electronics aisle "
    "from becoming a complete dumpster fire.\n\n"
    "🔓 Once you verify, {general} and the rest of the server unlock.\n\n"
    "Need help? Open a ticket in discord-support and a vest wearing penguin "
    "will eventually emerge from behind a shelf of Raspberry Pis to assist "
    "you.\n\n"
    "Please enjoy your stay, resist the impulse-buy aisle, and remember: "
    "you came here for one thing. You will leave with seventeen.\n\n"
    "🐧 **Happy Hacking!**"
)

# Stage 2: the Costco / Idiocracy penguin, shown when they verify into
# #general. Batches everyone who verified in the window into one group
# welcome. The operator's copy. House style: no em dashes, ever.
COSTCO_MESSAGE = (
    "📣 **WELCOME TO COSTCO. I LOVE YOU.** 📣\n\n"
    "The doors just slid open, the receipt checker gave a vague nod, and "
    "{users} strolled in, officially verified and loose in the warehouse. 🎉\n\n"
    "🥤 Remember to hydrate. Drink your **Brawndo**. It's got electrolytes. "
    "It's what plants crave. Water? Like from the toilet?\n\n"
    "Now that you're in:\n"
    "🐧 Introduce yourself to the other warehouse creatures\n"
    "🎭 Grab any roles you missed in {roles}\n"
    "🛒 Wander the aisles, make questionable decisions, and make yourself "
    "at home\n\n"
    "Your membership has been approved. Your hot dog remains $1.50.\n\n"
    "Welcome to Costco. I love you. ❤️🐧\n"
    "-# If you don't get the joke, watch Idiocracy."
)


class _GreetStage:
    """One batched greeting flow. Collects members, flushes them together at
    most once per window, greets each at most once ever (persisted).

    Windows come in two flavors:
    - interval: `cooldown` seconds, ALIGNED TO THE WALL CLOCK (900 → on the
      quarter hour).
    - daily: `daily_at=(hour, minute)` in `tz` — one window per day rolling
      over at that local time, so a 09:00 America/New_York stage greets
      everyone from the previous 24 hours at 9AM Eastern, DST included.
    """

    def __init__(self, bot, *, name, enabled, channel_id, template,
                 default_template, image_path, cooldown, max_mentions,
                 welcomed_file, refs, max_tenure_days=0.0, min_wait=0.0,
                 skip_role_id=None, daily_at=None, tz=None,
                 retract_window=86400.0):
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
        self.min_wait = min_wait             # seconds before a member is ripe
        self.skip_role_id = skip_role_id     # holders are dropped at flush
        self.daily_at = daily_at             # (hour, minute) local, or None
        self.tz = tz
        self._welcomed = self._load()
        self._pending: list = []             # [(member, ready_at wall time)]
        # Greetings we posted recently: [(message, [members], sent_at)].
        # Kept so a member who LEAVES right after being welcomed (drive-by,
        # or banned for the name they showed up with) can be edited out —
        # Discord clients render a departed user's mention as @unknown-user
        # no matter how the message was sent, so the fix is after the fact.
        self._posted: list = []
        self.retract_window = retract_window # seconds a greeting stays editable
        # Member ids parked by the profile screener (a flagged display
        # name): they stay pending, unmentioned, until a moderator decides.
        self.held: set = set()
        # The window we last flushed in (or booted in): members go out at
        # the first tick after the boundary FOLLOWING their ready time, so
        # greetings land ON the boundary — :00/:15/:30/:45 for a 900s
        # interval, 9AM local for a daily stage — never mid-window,
        # including right after a boot.
        self._last_period = self._period(time.time())

    def _period(self, now: float) -> int:
        """Monotonic window counter: increments exactly at each boundary."""
        if self.daily_at is None:
            return int(now // self.cooldown)
        from datetime import datetime
        local = datetime.fromtimestamp(now, self.tz)
        period = local.toordinal()
        if (local.hour, local.minute) < self.daily_at:
            period -= 1                      # today's window hasn't opened yet
        return period

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
                or any(m.id == member_id for m, _ in self._pending))

    def claim(self, member):
        """Mark greeted and queue — claimed immediately so whatever happens
        to the send, nobody is greeted twice. The member becomes ripe for
        flushing `min_wait` seconds from now (0 = ripe immediately)."""
        self._welcomed.add(member.id)
        self._save()
        self._pending.append((member, time.time() + self.min_wait))

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

    @staticmethod
    async def _resolve(m):
        """The member's CURRENT guild object (fresh roles), the queued
        object when the guild can't say either way, or None when the API
        definitively reports they left. A stale cache or flaky API must
        never cost a real member their greeting."""
        guild = getattr(m, 'guild', None)
        if guild is None:
            return m
        get_member = getattr(guild, 'get_member', None)
        if callable(get_member):
            fresh = get_member(m.id)
            if fresh is not None:
                return fresh
        else:
            return m
        fetch = getattr(guild, 'fetch_member', None)
        if not callable(fetch):
            return m
        try:
            return await fetch(m.id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return m                 # can't tell — greet rather than ghost

    def due(self, now: float) -> bool:
        """A member is waiting whose ready time fell in an EARLIER window,
        and this window hasn't flushed yet — greetings land ON the boundary,
        at most one per window, never before a member's `min_wait` has
        run."""
        if not self._pending:
            return False
        period = self._period(now)
        if period <= self._last_period:
            return False
        return any(self._period(ready) < period for _, ready in self._pending)

    async def _flush(self, now: float = None):
        """Send one message for every ripe pending member; unripe members
        stay queued for a later window."""
        if now is None:
            now = time.time()
        ripe = [(m, r) for m, r in self._pending
                if r <= now and m.id not in self.held]
        if not ripe:
            return
        self._pending = [(m, r) for m, r in self._pending
                         if r > now or m.id in self.held]
        self._last_period = self._period(now)
        members = [m for m, _ in ripe]

        # Between queueing and the flush people move: drive-by joiners LEAVE
        # (a departed member renders as @unknown-user — say nothing to them)
        # and, for a reminder stage, some VERIFY (skip_role_id) — the whole
        # point is to only nudge those who still need it.
        keep = []
        left = verified = 0
        for m in members:
            fresh = await self._resolve(m)
            if fresh is None or getattr(fresh, 'pending', False):
                # gone, or still on the membership screening rules page:
                # either way they cannot read the greeting
                left += 1
                continue
            if self.skip_role_id is not None and any(
                    r.id == self.skip_role_id
                    for r in getattr(fresh, 'roles', [])):
                verified += 1
                continue
            keep.append(fresh)
        if left or verified:
            logger.info('%s welcome: dropped %d departed-or-unscreened and %d '
                        'already-verified member(s) before the flush', self.name,
                        left, verified)
        if not keep:
            return
        members = keep

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
            posted = await channel.send(
                self.render(members),
                file=attachment,
                allowed_mentions=self._mentions(members),
            )
        except discord.HTTPException:
            logger.exception('Could not send the %s welcome message', self.name)
            return

        logger.info('%s-welcomed %d member(s): %s', self.name, len(members),
                    ', '.join(str(m) for m in members[:5]))
        if posted is not None:
            self._posted.append((posted, list(members), now))
            self._posted = self._posted[-200:]

    def _mentions(self, members: list) -> discord.AllowedMentions:
        return discord.AllowedMentions(everyone=False, roles=False,
                                       users=members[:self.max_mentions])

    # ------------------------------------------------------------ retract

    async def retract(self, member_id: int, now: float = None):
        """Edit a recently posted greeting so it no longer names a member
        who has since left; delete it when they were the only one. Older
        greetings are history and stay as they are."""
        if now is None:
            now = time.time()
        self._posted = [(msg, ms, at) for msg, ms, at in self._posted
                        if now - at <= self.retract_window]
        kept = []
        for msg, members, at in self._posted:
            if all(m.id != member_id for m in members):
                kept.append((msg, members, at))
                continue
            remaining = [m for m in members if m.id != member_id]
            try:
                if remaining:
                    await msg.edit(content=self.render(remaining),
                                   allowed_mentions=self._mentions(remaining))
                    kept.append((msg, remaining, at))
                else:
                    await msg.delete()
            except discord.HTTPException:
                logger.warning('Could not retract member %s from a %s '
                               'greeting (harmless)', member_id, self.name)
                kept.append((msg, remaining, at))
            else:
                logger.info('%s welcome: member %s left, greeting %s',
                            self.name, member_id,
                            'edited' if remaining else 'removed')
        self._posted = kept


class WelcomeGreeter(commands.Cog):
    """Two-stage greeter: Micro Center verify-reminder after join, Costco
    intro on verify."""

    def __init__(self, bot):
        self.bot = bot
        settings = section_config(bot, 'greeter')
        master = settings.enabled
        max_mentions = settings.max_mentions
        verify_channel = settings.verify_channel_id or settings.channel_id

        refs = {
            'rules': settings.rules_channel_id,
            'roles': settings.roles_channel_id,
            'resources': settings.resource_channel_id,
            'wagon': settings.wagon_channel_id,
            'general': settings.general_channel_id or verify_channel,
        }
        self.role_id = settings.role_id
        tz = _timezone(settings.timezone)
        retract_window = settings.retract_window_seconds

        self.join = _GreetStage(
            bot, name='join',
            enabled=master and settings.join_enabled,
            channel_id=settings.join_channel_id,
            template=settings.join_message,
            default_template=MICROCENTER_MESSAGE,
            image_path=settings.join_image or MICROCENTER_IMAGE,
            cooldown=settings.join_cooldown_seconds,
            max_mentions=max_mentions,
            welcomed_file='welcomed_newbies.json',
            refs=refs,
            # The join stage is a verification REMINDER: MEE6 posts the
            # instant hello, so wait a few minutes and only nudge members
            # who still haven't picked up the verify role by then.
            min_wait=settings.join_remind_after_seconds,
            skip_role_id=self.role_id,
            daily_at=settings.join_daily_at,
            tz=tz,
            retract_window=retract_window,
        )
        self.verify = _GreetStage(
            bot, name='verify',
            enabled=master and settings.verify_enabled,
            channel_id=verify_channel,
            template=settings.verify_message,
            default_template=COSTCO_MESSAGE,
            image_path=settings.verify_image or COSTCO_IMAGE,
            # One GROUP welcome per three hours: everyone who verified in
            # the window gets introduced together at the aligned boundary.
            cooldown=settings.verify_cooldown_seconds,
            max_mentions=max_mentions,
            welcomed_file='welcomed_users.json',   # keep the existing dedup file
            refs=refs,
            max_tenure_days=settings.max_tenure_days,
            daily_at=settings.verify_daily_at,
            tz=tz,
            retract_window=retract_window,
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

        def schedule(stage):
            if stage.daily_at is not None:
                return 'daily at %02d:%02d %s' % (*stage.daily_at, stage.tz)
            return '%.0fs windows' % stage.cooldown

        logger.info('Welcome greeter active: join=%s (-> %s, %s, %d greeted), '
                    'verify=%s (role %s -> %s, %s, %d greeted); '
                    'clock-aligned, base tick %.0fs',
                    self.join.enabled, self.join.channel_id,
                    schedule(self.join), len(self.join._welcomed),
                    self.verify.enabled, self.role_id, self.verify.channel_id,
                    schedule(self.verify), len(self.verify._welcomed),
                    self._base_tick)

    async def cog_unload(self):
        self.greet_tick.cancel()

    # ------------------------------------------------------------- events

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # With membership screening on, this fires the instant someone clicks
        # Join, while they are still on the rules screen and can see no
        # channel. MEE6 greets when they click through; anchor the reminder
        # on that same moment (the pending flip, below) or a slow reader
        # gets our reminder before the hello.
        if getattr(member, 'pending', False):
            logger.info('Join welcome for %s deferred: still behind the '
                        'membership screening gate', member)
            return
        self._queue_join(member)

    def _queue_join(self, member: discord.Member):
        if not self.join.enabled or member.bot:
            return
        if self.join.seen(member.id):
            return
        self.join.claim(member)
        logger.info('Join welcome queued for %s (%d pending)',
                    member, len(self.join._pending))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        if (getattr(before, 'pending', False)
                and not getattr(after, 'pending', False)):
            self._queue_join(after)
        if not self.verify.enabled:
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

    # ------------------------------------------------------------- holds

    def hold(self, member_id: int):
        """Park a member (flagged profile): no stage greets them until
        `release`. Called by the profile screener."""
        for stage in (self.join, self.verify):
            stage.held.add(member_id)

    def release(self, member_id: int):
        for stage in (self.join, self.verify):
            stage.held.discard(member_id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Leaving (or being banned) shortly after a welcome pulls the
        member back out of it; a ban also fires this event."""
        for stage in (self.join, self.verify):
            stage.held.discard(member.id)
            stage._pending = [(m, r) for m, r in stage._pending
                              if m.id != member.id]
            if stage.enabled:
                try:
                    await stage.retract(member.id)
                except Exception:
                    logger.exception('%s welcome retraction failed', stage.name)

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
