# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Greet members when they unlock the server — Walmart-greeter edition.

On this server, MEE6 grants a role from the #roles channel and that role is
what makes #general visible — so 'joined the guild' is not the moment a
member actually arrives. This cog greets on the moment that matters: the
first time a member GAINS the configured role.

Greets are BATCHED, at most one message per WELCOME_COOLDOWN_SECONDS
(default 60): the first arrival in a quiet minute is greeted immediately,
and everyone else who gains the role before the cooldown expires is
collected and tagged together in the next message. A rush of joins gets
one friendly message naming all of them, not a wall of bot posts.

Each member is greeted at most once, ever, persisted to
`data/welcomed_users.json` — a role removed and re-added (moderation,
MEE6 hiccups, self-role churn) must not produce a second welcome. Very
large batches (a MEE6 bulk role sync re-granting hundreds of existing
members) mention the first few and count the rest.

The message ships with the server's Walmart-greeter Tux
(`assets/welcome_tux.png`) and signs off with the house "Happy Hacking".

Configuration:
    WELCOME_ENABLED=false        master switch
    WELCOME_ROLE_ID=             the role whose grant means "they're in"
    WELCOME_CHANNEL_ID=          where to greet (e.g. #general)
    WELCOME_MESSAGE=             template: {users} {rules} {resources} {roles}
    WELCOME_RULES_CHANNEL_ID=    referenced by {rules}
    WELCOME_RESOURCE_CHANNEL_ID= referenced by {resources}
    WELCOME_ROLES_CHANNEL_ID=    referenced by {roles}
    WELCOME_COOLDOWN_SECONDS=60  at most one greeting message per this
    WELCOME_MAX_MENTIONS=12      mention this many; the rest become a count
    WELCOME_IMAGE=               override the attached image path ('' = none)
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import discord
from discord.ext import commands

from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)

WELCOMED_FILE = 'welcomed_users.json'
DEFAULT_IMAGE = str(Path(__file__).resolve().parent.parent / 'assets' / 'welcome_tux.png')

DEFAULT_MESSAGE = (
    "🛒 Welcome to the server, {users}! I'm the greeter penguin — "
    "how can I help?\n"
    "Carts are to your left, the rules are in {rules} (please read before "
    "operating heavy machinery), and today's rollback special is free "
    "knowledge in {resources} — aisle 7, next to the soldering irons.\n"
    "Grab your name tag in {roles} and holler if you can't find anything. "
    "Happy Hacking! 🐧"
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


class WelcomeGreeter(commands.Cog):
    """One batched welcome per cooldown window; each member greeted once ever."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = _env_bool('WELCOME_ENABLED', False)
        self.role_id = _env_id('WELCOME_ROLE_ID')
        self.channel_id = _env_id('WELCOME_CHANNEL_ID')
        self.rules_channel_id = _env_id('WELCOME_RULES_CHANNEL_ID')
        self.resource_channel_id = _env_id('WELCOME_RESOURCE_CHANNEL_ID')
        self.roles_channel_id = _env_id('WELCOME_ROLES_CHANNEL_ID')
        self.template = _env('WELCOME_MESSAGE', DEFAULT_MESSAGE)
        self.cooldown = float(_env('WELCOME_COOLDOWN_SECONDS', '60'))
        self.max_mentions = int(_env('WELCOME_MAX_MENTIONS', '12'))
        self.image_path = _env('WELCOME_IMAGE', DEFAULT_IMAGE)

        self._welcomed = self._load_welcomed()
        self._pending: list = []       # members waiting for the next batch
        self._last_greet: float = None  # monotonic; None = never
        self._flush_task = None

        if not self.enabled:
            return
        if self.role_id is None or self.channel_id is None:
            logger.error('WELCOME_ENABLED=true but WELCOME_ROLE_ID or '
                         'WELCOME_CHANNEL_ID is missing — greeter stays off')
            self.enabled = False

    async def cog_load(self):
        if self.enabled:
            logger.info('Welcome greeter active: role %s -> channel %s, one '
                        'message per %.0fs (%d member(s) already greeted)',
                        self.role_id, self.channel_id, self.cooldown,
                        len(self._welcomed))

    async def cog_unload(self):
        if self._flush_task is not None:
            self._flush_task.cancel()

    # ------------------------------------------------------------ storage

    def _load_welcomed(self) -> set:
        try:
            path = resolve_data_dir() / WELCOMED_FILE
            return set(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            return set()

    def _save_welcomed(self):
        try:
            path = resolve_data_dir() / WELCOMED_FILE
            path.write_text(json.dumps(sorted(self._welcomed)), encoding='utf-8')
        except OSError:
            logger.exception('Could not persist the welcomed-users list')

    # ------------------------------------------------------------- render

    def render(self, members: list) -> str:
        def mention(channel_id, fallback):
            return f'<#{channel_id}>' if channel_id else fallback

        named = members[:self.max_mentions]
        users = ', '.join(m.mention for m in named)
        overflow = len(members) - len(named)
        if overflow > 0:
            users += f' (and {overflow} more new friends)'

        values = {
            'users': users,
            'user': users,   # older templates used the singular
            'rules': mention(self.rules_channel_id, 'the rules channel'),
            'resources': mention(self.resource_channel_id, 'the resources channel'),
            'roles': mention(self.roles_channel_id, 'the roles channel'),
        }
        try:
            return self.template.format(**values)
        except (KeyError, IndexError):
            logger.warning('WELCOME_MESSAGE has an unknown placeholder; using the default')
            return DEFAULT_MESSAGE.format(**values)

    # ------------------------------------------------------------- events

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not self.enabled or after.bot:
            return
        if self.role_id in {r.id for r in before.roles}:
            return
        if self.role_id not in {r.id for r in after.roles}:
            return
        if after.id in self._welcomed or any(m.id == after.id for m in self._pending):
            return

        # Claim the member immediately: whatever happens to the batch send,
        # nobody is ever greeted twice.
        self._welcomed.add(after.id)
        self._save_welcomed()
        self._pending.append(after)

        now = time.monotonic()
        if self._last_greet is None or now - self._last_greet >= self.cooldown:
            await self._flush()
        elif self._flush_task is None or self._flush_task.done():
            # More arrivals inside the window join this batch; the flush
            # fires when the cooldown expires and tags everyone at once.
            delay = self.cooldown - (now - self._last_greet)
            self._flush_task = asyncio.get_running_loop().create_task(
                self._flush_later(delay))
            logger.info('Welcome for %s batched (+%d pending, flush in %.0fs)',
                        after, len(self._pending), delay)

    async def _flush_later(self, delay: float):
        try:
            await asyncio.sleep(delay)
            await self._flush()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception('Batched welcome flush failed')

    async def _flush(self):
        if not self._pending:
            return
        members, self._pending = self._pending, []

        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error('Welcome channel %s not found', self.channel_id)
            return

        attachment = None
        if self.image_path:
            try:
                attachment = discord.File(self.image_path,
                                          filename='welcome.png')
            except OSError:
                logger.warning('Welcome image %s unreadable — sending text only',
                               self.image_path)
        try:
            await channel.send(
                self.render(members),
                file=attachment,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False,
                    users=members[:self.max_mentions]),
            )
        except discord.HTTPException:
            logger.exception('Could not send the welcome message')
            return

        self._last_greet = time.monotonic()
        logger.info('Welcomed %d member(s): %s', len(members),
                    ', '.join(str(m) for m in members[:5]))


async def setup(bot):
    await bot.add_cog(WelcomeGreeter(bot))
    logger.info('WelcomeGreeter cog loaded')
