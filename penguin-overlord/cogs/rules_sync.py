# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Keep a copy of the server's #rules and let moderation read it.

The moderation model judges messages against generic policy. The server
has its own written rules, sitting in a channel the bot can read — so the
bot reads them: on startup and once a day, the rules channel's messages
are fetched and cached to `data/server_rules.json`, and
`moderation_system_prompt()` appends them (capped) to what the model sees.
When the text changes, a note is posted to the mod alert channel, so a
rules edit is a visible event rather than something moderation silently
starts enforcing.

Configuration:
    MOD_RULES_CHANNEL_ID=      the #rules channel to learn from
    MOD_RULES_SYNC_HOURS=24    refresh cadence
"""

import json
import logging
import re

import discord
from discord.ext import commands, tasks

from utils.config import section_config
from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)

RULES_FILE = 'server_rules.json'
# Cap what reaches the prompt: rules channels accumulate banners and edits,
# and the model needs the substance, not the formatting history.
MAX_RULES_CHARS = 1800


def load_cached_rules() -> str:
    """The cached rules text, or '' — used by the moderation prompt."""
    try:
        path = resolve_data_dir() / RULES_FILE
        data = json.loads(path.read_text(encoding='utf-8'))
        return data.get('text', '')
    except (OSError, ValueError):
        return ''


class RulesSync(commands.Cog):
    """Reads #rules on startup and daily; caches for the moderation prompt."""

    def __init__(self, bot):
        self.bot = bot
        moderation = section_config(bot, 'moderation')
        self.rules_channel_id = moderation.rules_channel_id
        self.sync_hours = moderation.rules_sync_hours
        self.alert_channel_id = moderation.alert_channel_id

    async def cog_load(self):
        if self.rules_channel_id is None:
            return
        self.sync_rules.change_interval(hours=self.sync_hours)
        self.sync_rules.start()
        logger.info('Rules sync active: channel %s, every %.0fh',
                    self.rules_channel_id, self.sync_hours)

    async def cog_unload(self):
        self.sync_rules.cancel()

    @tasks.loop(hours=24)
    async def sync_rules(self):
        try:
            await self._sync_once()
        except Exception:
            logger.exception('Rules sync failed')

    @sync_rules.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    async def _sync_once(self):
        channel = self.bot.get_channel(self.rules_channel_id)
        if channel is None:
            logger.error('Rules channel %s not found', self.rules_channel_id)
            return

        parts = []
        # oldest first, so rule 1 comes before rule 12
        async for message in channel.history(limit=50, oldest_first=True):
            text = (message.content or '').strip()
            for embed in message.embeds:
                for piece in (embed.title, embed.description):
                    if piece:
                        text = f'{text}\n{piece}'.strip()
            if text:
                parts.append(text)
        raw = '\n\n'.join(parts)
        # collapse decoration: mentions become names, emoji/dividers go
        cleaned = re.sub(r'<a?:\w+:\d+>', '', raw)
        cleaned = re.sub(r'^[-=_*#~ ]{4,}$', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()[:MAX_RULES_CHARS]

        if not cleaned:
            logger.warning('Rules channel %s yielded no text', self.rules_channel_id)
            return

        path = resolve_data_dir() / RULES_FILE
        previous = load_cached_rules()
        if cleaned == previous:
            logger.info('Rules unchanged (%d chars)', len(cleaned))
            return

        path.write_text(json.dumps({
            'text': cleaned,
            'channel_id': self.rules_channel_id,
            'synced_at': discord.utils.utcnow().isoformat(),
        }, indent=1), encoding='utf-8')
        logger.info('Rules %s: %d chars cached from #%s',
                    'updated' if previous else 'learned',
                    len(cleaned), getattr(channel, 'name', channel.id))

        # A rules change alters what moderation enforces — say so where the
        # moderators live, not just in a log.
        if previous and self.alert_channel_id:
            mod_channel = self.bot.get_channel(self.alert_channel_id)
            if mod_channel is not None:
                try:
                    await mod_channel.send(
                        f'📜 The rules in <#{self.rules_channel_id}> changed — '
                        f'the moderation model now sees the updated text.')
                except discord.HTTPException:
                    logger.warning('Could not announce the rules change')


async def setup(bot):
    await bot.add_cog(RulesSync(bot))
    logger.info('RulesSync cog loaded')
