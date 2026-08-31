# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Greet members when they unlock the server.

On this server, MEE6 grants a role from the #roles channel and that role is
what makes #general visible — so 'joined the guild' is not the moment a
member actually arrives. This cog greets on the moment that matters: the
first time a member GAINS the configured role.

Each member is greeted at most once, ever, persisted to
`data/welcomed_users.json` — a role removed and re-added (moderation,
MEE6 hiccups, self-role churn) must not produce a second welcome. Greets
are also rate-limited so a migration or a MEE6 bulk-sync cannot flood the
channel: past the per-minute cap, members are silently skipped (they were
almost certainly not new arrivals).

Configuration:
    WELCOME_ENABLED=false        master switch
    WELCOME_ROLE_ID=             the role whose grant means "they're in"
    WELCOME_CHANNEL_ID=          where to greet (e.g. #general)
    WELCOME_MESSAGE=             template: {user} {rules} {resources} {roles}
    WELCOME_RULES_CHANNEL_ID=    referenced by {rules}
    WELCOME_RESOURCE_CHANNEL_ID= referenced by {resources}
    WELCOME_ROLES_CHANNEL_ID=    referenced by {roles}
    WELCOME_MAX_PER_MINUTE=5     flood guard for bulk role syncs
"""

import json
import logging
import os
import time

import discord
from discord.ext import commands

from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)

WELCOMED_FILE = 'welcomed_users.json'

DEFAULT_MESSAGE = (
    "Welcome to the server, {user}! 🐧 Please give {rules} a read, and "
    "{resources} is the best place to start learning. Enjoy!"
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
    """One welcome per member, on the role grant that unlocks the server."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = _env_bool('WELCOME_ENABLED', False)
        self.role_id = _env_id('WELCOME_ROLE_ID')
        self.channel_id = _env_id('WELCOME_CHANNEL_ID')
        self.rules_channel_id = _env_id('WELCOME_RULES_CHANNEL_ID')
        self.resource_channel_id = _env_id('WELCOME_RESOURCE_CHANNEL_ID')
        self.roles_channel_id = _env_id('WELCOME_ROLES_CHANNEL_ID')
        self.template = _env('WELCOME_MESSAGE', DEFAULT_MESSAGE)
        self.max_per_minute = int(_env('WELCOME_MAX_PER_MINUTE', '5'))

        self._welcomed = self._load_welcomed()
        self._recent = []          # monotonic timestamps of recent greets

        if not self.enabled:
            return
        if self.role_id is None or self.channel_id is None:
            logger.error('WELCOME_ENABLED=true but WELCOME_ROLE_ID or '
                         'WELCOME_CHANNEL_ID is missing — greeter stays off')
            self.enabled = False

    async def cog_load(self):
        if self.enabled:
            logger.info('Welcome greeter active: role %s -> channel %s '
                        '(%d member(s) already greeted)',
                        self.role_id, self.channel_id, len(self._welcomed))

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

    def render(self, member) -> str:
        def mention(channel_id, fallback):
            return f'<#{channel_id}>' if channel_id else fallback

        values = {
            'user': member.mention,
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
        before_roles = {r.id for r in before.roles}
        if self.role_id in before_roles:
            return
        if self.role_id not in {r.id for r in after.roles}:
            return
        if after.id in self._welcomed:
            return

        # Flood guard: a MEE6 bulk sync re-granting roles to hundreds of
        # existing members must not narrate itself in #general.
        now = time.monotonic()
        self._recent = [t for t in self._recent if now - t < 60]
        if len(self._recent) >= self.max_per_minute:
            logger.warning('Welcome for %s skipped — %d greets in the last '
                           'minute looks like a bulk role sync, not arrivals',
                           after, len(self._recent))
            self._welcomed.add(after.id)   # never greet them later either
            self._save_welcomed()
            return

        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error('Welcome channel %s not found', self.channel_id)
            return
        try:
            await channel.send(
                self.render(after),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, users=[after]),
            )
        except discord.HTTPException:
            logger.exception('Could not send the welcome message')
            return

        self._recent.append(now)
        self._welcomed.add(after.id)
        self._save_welcomed()
        logger.info('Welcomed %s after they gained the access role', after)


async def setup(bot):
    await bot.add_cog(WelcomeGreeter(bot))
    logger.info('WelcomeGreeter cog loaded')
