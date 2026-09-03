# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Community events: member submissions, moderator review, dated reminders.

Thin Discord layer. Decisions live in utils.events_logic, SQL in
utils.events_store, embeds in utils.events_cards. Spec:
docs/superpowers/specs/2026-09-03-conference-database-design.md.
"""

import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import events_cards as cards
from utils.config import load_events_config
from utils.database import get_database
from utils.events_logic import (TOPIC_LABELS, load_regions, local_today, region_choices,
                                resolve_place, validate_submission)
from utils.events_store import EventsStore
from utils.metrics import EVENTS_PENDING, EVENTS_SUBMISSIONS

logger = logging.getLogger('penguin.events')

PAGE_SIZE = 5
LIST_DAYS = 365
NEXT_DAYS = 30
DISABLED_TEXT = 'Events are not enabled on this server.'
TOPIC_CHOICES = [app_commands.Choice(name=label, value=key) for key, label in TOPIC_LABELS.items()]


class Events(commands.Cog):
    """Conference and meetup calendar with role-targeted reminders."""

    def __init__(self, bot):
        self.bot = bot
        config = getattr(bot, 'config', None)
        self.cfg = config.events if config is not None else load_events_config()
        self.store: Optional[EventsStore] = None
        self.regions = load_regions()

    # -- lifecycle ------------------------------------------------------------

    async def cog_load(self):
        if not self.cfg.enabled:
            logger.info('Events disabled (EVENTS_ENABLED=false)')
            return
        await self.attach()
        logger.info('Events active: channel=%s review=%s dry_run=%s post_at=%02d:%02d %s reminders=%s',
                    self.cfg.channel_id, self.cfg.review_channel_id, self.cfg.dry_run,
                    *self.cfg.post_at, self.cfg.timezone, self.cfg.reminder_days)

    async def attach(self):
        """Open the store. Separate from cog_load so tests can attach
        without starting the clock loops."""
        self.store = EventsStore(await get_database())

    def today(self) -> datetime.date:
        return local_today(self.cfg.timezone)

    async def _refuse_if_off(self, interaction: discord.Interaction) -> bool:
        if self.store is None:
            await interaction.response.send_message(DISABLED_TEXT, ephemeral=True)
            return True
        return False

    async def post_review_card(self, event: dict) -> Optional[int]:
        """Post the moderator card for a new submission; returns the message
        id. Filled in by the moderation task; until then nothing is posted."""
        return None

    # -- autocomplete ---------------------------------------------------------

    async def _where_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=label, value=value)
                for label, value in region_choices(self.regions, current)]

    # -- member commands ------------------------------------------------------

    events = app_commands.Group(name='events', description='Community events calendar')

    @events.command(name='list', description='Upcoming events, soonest first')
    @app_commands.describe(topic='Only this topic', where='Only this state, province or country',
                           page='Page number')
    @app_commands.choices(topic=TOPIC_CHOICES)
    @app_commands.autocomplete(where=_where_autocomplete)
    async def events_list(self, interaction: discord.Interaction, topic: Optional[str] = None,
                          where: Optional[str] = None, page: app_commands.Range[int, 1, 50] = 1):
        if await self._refuse_if_off(interaction):
            return
        region_code = country_code = None
        online = bool(where) and where.strip().lower() == 'online'
        if where and not online:
            try:
                region_code, country_code, _ = resolve_place(where, False, self.regions)
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return
            if region_code:
                country_code = None                      # filter on the region alone
        today = self.today().isoformat()
        rows = await self.store.list_upcoming(interaction.guild_id, today=today, days=LIST_DAYS,
                                              topic=topic, region_code=region_code, country_code=country_code,
                                              online=online)
        pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        chunk = rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
        heading = 'Upcoming events'
        if topic:
            heading += f': {TOPIC_LABELS[topic]}'
        if where:
            heading += f' in {self.regions.name(region_code or country_code) or "Online"}'
        embed = cards.list_embed(chunk, self.regions, today=today, page=page, pages=pages, heading=heading)
        await interaction.response.send_message(embed=embed, allowed_mentions=cards.allowed_mentions([]))

    @events.command(name='next', description=f'Everything in the next {NEXT_DAYS} days')
    async def events_next(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        today = self.today().isoformat()
        rows = await self.store.list_upcoming(interaction.guild_id, today=today, days=NEXT_DAYS)
        embed = cards.list_embed(rows[:10], self.regions, today=today, page=1, pages=1,
                                 heading=f'Next {NEXT_DAYS} days')
        await interaction.response.send_message(embed=embed, allowed_mentions=cards.allowed_mentions([]))

    @events.command(name='search', description='Find an event by name or city')
    @app_commands.describe(query='Part of the name or city')
    async def events_search(self, interaction: discord.Interaction, query: app_commands.Range[str, 2, 80]):
        if await self._refuse_if_off(interaction):
            return
        today = self.today().isoformat()
        rows = await self.store.search(interaction.guild_id, query, today=today)
        embed = cards.list_embed(rows, self.regions, today=today, page=1, pages=1,
                                 heading=f'Events matching "{query}"')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @events.command(name='submit', description='Suggest an event for the calendar')
    @app_commands.describe(title='Event name', topic='What kind of event', start='Start date, YYYY-MM-DD',
                           end='End date, YYYY-MM-DD (blank for one day)',
                           city='City, or Online', where='State, province or country (start typing)',
                           url='Event website', notes='Anything else, up to 500 characters',
                           national='Notify the whole country, not just the state or province')
    @app_commands.choices(topic=TOPIC_CHOICES)
    @app_commands.autocomplete(where=_where_autocomplete)
    async def events_submit(self, interaction: discord.Interaction, title: str, topic: str, start: str,
                            city: str, where: str, end: Optional[str] = None, url: Optional[str] = None,
                            notes: Optional[str] = None, national: bool = False):
        if await self._refuse_if_off(interaction):
            return
        guild_id, user = interaction.guild_id, interaction.user
        clean, problem = validate_submission(title=title, topic=topic, start=start, end=end, city=city,
                                             url=url, notes=notes, today=self.today())
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        try:
            region_code, country_code, scope = resolve_place(where, national, self.regions)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        # The sync validation is done; everything from here does I/O
        # (post_review_card becomes a real HTTP call once Task 8 lands), so
        # acknowledge the interaction now rather than risk the 3 second
        # token expiring after the row is already inserted.
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = await self.store.find_fingerprint(guild_id, clean['fingerprint'])
        if existing:
            await interaction.followup.send(
                f"That matches #{existing['id']}, {existing['title']} ({existing['status']}). "
                'If the details changed, ask a moderator to edit it.', ephemeral=True)
            return
        open_count = await self.store.count_open_submissions(guild_id, user.id)
        if open_count >= self.cfg.max_pending_per_member:
            await interaction.followup.send(
                f'You already have {open_count} submissions waiting for review. '
                'Once a moderator handles those you can add more.', ephemeral=True)
            return
        row = {
            **clean, 'guild_id': guild_id, 'start_time': None, 'timezone': None,
            'date_status': 'confirmed', 'region_code': region_code, 'country_code': country_code,
            'scope': scope, 'recurrence': 'none', 'parent_event_id': None, 'status': 'pending',
            'provenance': 'member', 'submitted_by': user.id, 'source_url': None, 'source_note': None,
        }
        event_id = await self.store.insert(row, actor_id=user.id, action='submit')
        EVENTS_SUBMISSIONS.labels(provenance='member').inc()
        EVENTS_PENDING.set(await self.store.pending_count(guild_id))
        event = await self.store.get(event_id)
        message_id = await self.post_review_card(event)
        if message_id:
            await self.store.set_review_message(event_id, message_id)
        logger.info('Event #%d submitted by %s: %s (%s)', event_id, user.id, clean['title'], clean['start_date'])
        await interaction.followup.send(
            f"Thanks. #{event_id} {clean['title']} is in the review queue; a moderator will look at it. "
            'You can check on it with /events mine.', ephemeral=True)

    @events.command(name='mine', description='Your submissions and what happened to them')
    async def events_mine(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        rows = await self.store.mine(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(cards.mine_lines(rows), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Events(bot))
