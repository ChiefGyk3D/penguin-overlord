# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Community events: member submissions, moderator review, dated reminders.

Thin Discord layer. Decisions live in utils.events_logic, SQL in
utils.events_store, embeds in utils.events_cards. Spec:
docs/superpowers/specs/2026-09-03-conference-database-design.md.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import database
from utils import events_cards as cards
from utils.config import load_events_config
from utils.database import get_database
from utils.events_logic import (TOPIC_LABELS, TOPIC_ROLES, days_until, due_window, fingerprint, load_regions,
                                local_today, location_field, next_annual_dates, parse_dates_field,
                                parse_location_field, region_choices, resolve_place, role_names_for,
                                validate_submission)
from utils.events_store import EVENT_COLUMNS, EventsStore
from utils.metrics import (EVENTS_DECISIONS, EVENTS_PENDING, EVENTS_POST_ERRORS, EVENTS_REMINDERS,
                           EVENTS_ROLE_MISSING, EVENTS_SUBMISSIONS)

logger = logging.getLogger('penguin.events')

PAGE_SIZE = 5
LIST_DAYS = 365
NEXT_DAYS = 30
DISABLED_TEXT = 'Events are not enabled on this server.'
TOPIC_CHOICES = [app_commands.Choice(name=label, value=key) for key, label in TOPIC_LABELS.items()]
SWEEP_AT = (3, 0)
DIGEST_DAYS = 30
REJECTED_KEEP_DAYS = 180
MOD_ONLY_TEXT = 'Only moderators can do that.'
PROVENANCE_LINES = {
    'member': 'Submitted by <@{submitted_by}>',
    'calendar': 'Imported from the calendar',
    'rollover': 'Rolled over from #{parent_event_id}; dates are estimated until confirmed',
    'ai': 'Suggested by the discovery job',
}


class EventButton(discord.ui.DynamicItem[discord.ui.Button],
                  template=r'event:(?P<event_id>[0-9]+):(?P<verb>approve|reject|edit)'):
    """Persistent review button: the event id lives in the custom_id, so
    the card still works after a restart."""

    STYLES = {'approve': (discord.ButtonStyle.success, 'Approve'),
              'reject': (discord.ButtonStyle.danger, 'Reject'),
              'edit': (discord.ButtonStyle.secondary, 'Edit')}

    def __init__(self, event_id: int, verb: str):
        style, label = self.STYLES[verb]
        super().__init__(discord.ui.Button(style=style, label=label, custom_id=f'event:{event_id}:{verb}'))
        self.event_id = event_id
        self.verb = verb

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match['event_id']), match['verb'])

    async def callback(self, interaction: discord.Interaction):
        logger.info('Event button %s:%s clicked by %s', self.event_id, self.verb, interaction.user)
        cog = interaction.client.get_cog('Events')
        if cog is None or cog.store is None:
            await interaction.response.send_message(DISABLED_TEXT, ephemeral=True)
            return
        await cog.handle_button(interaction, self.event_id, self.verb)


def review_view(event_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for verb in ('approve', 'reject', 'edit'):
        view.add_item(EventButton(event_id, verb))
    return view


class RejectModal(discord.ui.Modal, title='Reject event'):
    reason = discord.ui.TextInput(label='Reason (the submitter sees this)', max_length=200)

    def __init__(self, cog, event_id: int):
        super().__init__()
        self.cog = cog
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.decide(interaction, self.event_id, 'rejected', reason=self.reason.value.strip())


class EditModal(discord.ui.Modal):
    """Moderator edit of any event, any status. Free-text fields that the
    logic module parses back; a parse failure is reported and nothing is
    saved."""

    def __init__(self, cog, event: dict):
        super().__init__(title=f"Edit event #{event['id']}")
        self.cog = cog
        self.event_id = event['id']
        dates = event['start_date'] if event['start_date'] == event['end_date'] \
            else f"{event['start_date']} to {event['end_date']}"
        self.title_field = discord.ui.TextInput(label='Title', default=event['title'], max_length=120)
        self.dates = discord.ui.TextInput(label='Dates: YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD',
                                          default=dates, max_length=24)
        self.location = discord.ui.TextInput(label='Location: City, US-MI[, national] or Online',
                                             default=location_field(event), max_length=80)
        self.url = discord.ui.TextInput(label='URL', default=event['url'] or '', required=False, max_length=300)
        self.notes = discord.ui.TextInput(label='Notes', style=discord.TextStyle.paragraph,
                                          default=event['notes'] or '', required=False, max_length=500)
        for item in (self.title_field, self.dates, self.location, self.url, self.notes):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            changes = self.cog.parse_edit(title=self.title_field.value, dates=self.dates.value,
                                          location=self.location.value, url=self.url.value,
                                          notes=self.notes.value)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await self.cog.apply_edit(interaction, self.event_id, changes)


class Events(commands.Cog):
    """Conference and meetup calendar with role-targeted reminders."""

    def __init__(self, bot):
        self.bot = bot
        config = getattr(bot, 'config', None)
        self.cfg = config.events if config is not None else load_events_config()
        self.store: Optional[EventsStore] = None
        self.regions = load_regions()
        self._warned_roles: dict = {}    # role name -> local date it was last warned about
        tz = ZoneInfo(self.cfg.timezone)
        self.poster = tasks.loop(time=datetime_time(*self.cfg.post_at, tzinfo=tz))(self._poster_tick)
        self.sweeper = tasks.loop(time=datetime_time(*SWEEP_AT, tzinfo=tz))(self._sweep_tick)
        self.poster.before_loop(self._wait_ready)
        self.sweeper.before_loop(self._wait_ready)

    # -- lifecycle ------------------------------------------------------------

    async def cog_load(self):
        if not self.cfg.enabled:
            logger.info('Events disabled (EVENTS_ENABLED=false)')
            return
        await self.attach()
        self.bot.add_dynamic_items(EventButton)
        self.poster.start()
        self.sweeper.start()
        logger.info('Events active: channel=%s review=%s dry_run=%s post_at=%02d:%02d %s reminders=%s',
                    self.cfg.channel_id, self.cfg.review_channel_id, self.cfg.dry_run,
                    *self.cfg.post_at, self.cfg.timezone, self.cfg.reminder_days)

    async def cog_unload(self):
        self.poster.cancel()
        self.sweeper.cancel()
        # Loop.cancel() only requests cancellation; the underlying task is
        # not actually done until the event loop gets a turn to process it,
        # so is_running() would still read True to a caller that checks
        # right after unload. Yield once so cog_unload really does leave
        # both loops stopped, not just asked to stop.
        await asyncio.sleep(0)

    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    async def _poster_tick(self):
        try:
            await self.run_poster()
        except Exception:
            logger.exception('Events poster failed')

    async def _sweep_tick(self):
        try:
            await self.run_sweep()
        except Exception:
            logger.exception('Events sweep failed')

    async def attach(self):
        """Open the store. Separate from cog_load so tests can attach
        without starting the clock loops."""
        self.store = EventsStore(await get_database())

    def today(self) -> date:
        return local_today(self.cfg.timezone)

    async def _refuse_if_off(self, interaction: discord.Interaction) -> bool:
        if self.store is None:
            await interaction.response.send_message(DISABLED_TEXT, ephemeral=True)
            return True
        return False

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

    # -- moderator surface -----------------------------------------------------

    async def _channel(self, channel_id: Optional[int]):
        if not channel_id:
            return None
        channel = self.bot.get_channel(channel_id)
        if channel is None and hasattr(self.bot, 'fetch_channel'):
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                channel = None
        return channel

    def _local(self, iso: Optional[str]) -> str:
        if not iso:
            return 'unknown time'
        stamp = datetime.fromisoformat(iso).astimezone(ZoneInfo(self.cfg.timezone))
        return stamp.strftime('%Y-%m-%d %H:%M ') + ('ET' if self.cfg.timezone == 'America/New_York'
                                                    else stamp.strftime('%Z'))

    def decided_line(self, event: dict) -> str:
        who = 'the sweep' if not event.get('decided_by') else f"<@{event['decided_by']}>"
        text = f"{event['status'].capitalize()} by {who} at {self._local(event.get('decided_at'))}"
        if event.get('reject_reason'):
            text += f": {event['reject_reason']}"
        return text

    def _card(self, event: dict) -> discord.Embed:
        line = PROVENANCE_LINES.get(event['provenance'], 'Unknown source').format(**event)
        decided = self.decided_line(event) if event['status'] != 'pending' else None
        return cards.review_card(event, self.regions, provenance_line=line, decided=decided)

    async def post_review_card(self, event: dict) -> Optional[int]:
        channel = await self._channel(self.cfg.review_channel_id)
        if channel is None:
            logger.warning('Event #%d: no review channel (%s); card not posted',
                           event['id'], self.cfg.review_channel_id)
            return None
        try:
            message = await channel.send(embed=self._card(event), view=review_view(event['id']),
                                         allowed_mentions=cards.allowed_mentions([]))
        except discord.HTTPException as e:
            logger.error('Event #%d: review card failed: %s', event['id'], e)
            return None
        return message.id

    async def refresh_card(self, event: dict) -> None:
        """Rewrite the card after a decision or edit; buttons come off once
        the row is no longer pending."""
        channel = await self._channel(self.cfg.review_channel_id)
        if channel is None or not event.get('review_message_id'):
            return
        try:
            message = await channel.fetch_message(event['review_message_id'])
            view = review_view(event['id']) if event['status'] == 'pending' else None
            await message.edit(embed=self._card(event), view=view)
        except discord.HTTPException as e:
            logger.warning('Event #%d: card refresh failed: %s', event['id'], e)

    @staticmethod
    def _is_mod(interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, 'guild_permissions', None)
        return bool(perms and perms.moderate_members)

    async def _reply(self, interaction: discord.Interaction, text: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    async def handle_button(self, interaction: discord.Interaction, event_id: int, verb: str) -> None:
        if not self._is_mod(interaction):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        event = await self.store.get(event_id)
        if event is None:
            await self._reply(interaction, f'Event #{event_id} no longer exists.')
            return
        if verb == 'edit':
            await interaction.response.send_modal(EditModal(self, event))
            return
        if event['status'] != 'pending':
            # refresh_card is Discord HTTP (fetch_message + edit); defer
            # first so it does not race the interaction's 3 second budget,
            # the same fix decide/apply_edit/events_cancel already needed.
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.refresh_card(event)    # an earlier refresh may have failed; this click repairs it
            await self._reply(interaction, f'Already decided. {self.decided_line(event)}')
            return
        if verb == 'approve':
            await self.decide(interaction, event_id, 'approved')
        else:
            await interaction.response.send_modal(RejectModal(self, event_id))

    async def decide(self, interaction: discord.Interaction, event_id: int, status: str,
                     reason: Optional[str] = None) -> None:
        # Authorization travels with the write: a button click is already
        # gated by handle_button, but a modal's on_submit reaches decide()
        # directly, possibly minutes after the mod role that opened it was
        # removed, so the check is repeated here.
        if not self._is_mod(interaction):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        # Defer before any Discord HTTP round trip (refresh_card below is a
        # fetch_message plus an edit): the initial response has a 3 second
        # budget, and a slow review channel must not cost the interaction.
        await interaction.response.defer(ephemeral=True, thinking=True)
        done = await self.store.decide(event_id, status=status, moderator_id=interaction.user.id, reason=reason)
        event = await self.store.get(event_id)
        if not done:
            if event is None:
                await self._reply(interaction, f'Event #{event_id} no longer exists.')
                return
            await self.refresh_card(event)    # an earlier refresh may have failed; this click repairs it
            await self._reply(interaction, f'Already decided. {self.decided_line(event)}')
            return
        EVENTS_DECISIONS.labels(decision=status).inc()
        EVENTS_PENDING.set(await self.store.pending_count(event['guild_id']))
        logger.info('Event #%d %s by %s%s', event_id, status, interaction.user.id,
                    f': {reason}' if reason else '')
        await self.refresh_card(event)
        await self._reply(interaction, f"#{event_id} {event['title']} {status}.")

    def parse_edit(self, *, title: str, dates: str, location: str, url: str, notes: str) -> dict:
        title = (title or '').strip()
        if not title:
            raise ValueError('A title is required.')
        start, end = parse_dates_field(dates)
        city, region_code, country_code, scope = parse_location_field(location, self.regions)
        url = (url or '').strip() or None
        if url and not url.lower().startswith(('http://', 'https://')):
            raise ValueError('The url must start with http:// or https://.')
        return {
            'title': title, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'city': city, 'region_code': region_code, 'country_code': country_code, 'scope': scope,
            'url': url, 'notes': (notes or '').strip() or None,
        }

    SCHEDULE_FIELDS = ('start_date', 'end_date', 'city', 'region_code', 'country_code')

    async def apply_edit(self, interaction: discord.Interaction, event_id: int, changes: dict) -> None:
        # Same two reasons as decide(): the write needs its own
        # authorization check (EditModal.on_submit reaches this directly),
        # and the refresh_card HTTP call below must not happen before the
        # interaction is acknowledged.
        if not self._is_mod(interaction):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        before = await self.store.get(event_id)
        if before is None:
            await self._reply(interaction, f'Event #{event_id} no longer exists.')
            return
        after = await self.store.update(event_id, changes, actor_id=interaction.user.id)
        await self.refresh_card(after)
        logger.info('Event #%d edited by %s: %s', event_id, interaction.user.id, sorted(changes))
        await self._reply(interaction, f"#{event_id} {after['title']} updated.")
        schedule_changed = any(before[k] != after[k] for k in self.SCHEDULE_FIELDS)
        if after['status'] == 'approved' and schedule_changed and await self.store.dated_reminder_sent(event_id):
            # Scoped to the new start date: a second schedule change claims
            # a different window, so it is not swallowed by the UNIQUE
            # index on the first 'changed' claim.
            await self.notify(after, f"changed:{after['start_date']}", changed=True)

    # -- posting ---------------------------------------------------------------

    def resolve_roles(self, guild, names: list) -> tuple[list, list]:
        """(roles found, names missing). Missing names are warned once per
        role per local day: the fix is a moderator creating the role, and
        the log should not scream every run."""
        by_name = {r.name: r for r in getattr(guild, 'roles', [])}
        roles, missing = [], []
        for name in names:
            if name in by_name:
                roles.append(by_name[name])
            else:
                missing.append(name)
                today = self.today()
                if self._warned_roles.get(name) != today:
                    self._warned_roles[name] = today
                    logger.warning('Events: role %r does not exist in guild %s; mentioning by name only',
                                   name, getattr(guild, 'id', None))
        return roles, missing

    async def notify(self, event: dict, window: str, *, changed: bool = False) -> bool:
        """Post one member-facing notice for (event, window), once ever.
        True when it went out (or was logged in dry run)."""
        days = days_until(event['start_date'], self.today())
        names = role_names_for(event, self.regions)
        guild = self.bot.get_guild(event['guild_id'])
        roles, missing = self.resolve_roles(guild, names)
        if self.cfg.dry_run:
            logger.info('DRY RUN events reminder: #%d %s window=%s roles=%s missing=%s',
                        event['id'], event['title'], window, [r.name for r in roles], missing)
            return True
        reminder_id = await self.store.claim_reminder(event['id'], window, self.cfg.channel_id)
        if reminder_id is None:
            return False
        channel = await self._channel(self.cfg.channel_id)
        if channel is None:
            await self.store.release_reminder(reminder_id)
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: channel %s not found; reminder #%d/%s not sent',
                         self.cfg.channel_id, event['id'], window)
            return False
        try:
            message = await channel.send(
                cards.reminder_text(event, [r.mention for r in roles], missing),
                embed=cards.reminder_embed(event, self.regions, days, changed=changed),
                allowed_mentions=cards.allowed_mentions(roles))
        except discord.HTTPException as e:
            await self.store.release_reminder(reminder_id)
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: reminder #%d/%s failed: %s', event['id'], window, e)
            return False
        except Exception:
            await self.store.release_reminder(reminder_id)
            raise
        await self.store.mark_reminder_sent(reminder_id, message.id, ', '.join(names))
        EVENTS_REMINDERS.labels(window=window).inc()
        for name in missing:
            EVENTS_ROLE_MISSING.labels(role=name).inc()
        logger.info('Events: reminder #%d/%s posted (%s)', event['id'], window, ', '.join(names) or 'no roles')
        return True

    # -- scheduled work ----------------------------------------------------------

    async def run_poster(self, today: Optional[date] = None) -> int:
        """Post every reminder whose window lands today. No backfill: a
        window missed while the bot was down stays missed, on purpose."""
        today = today or self.today()
        horizon = today + timedelta(days=max(self.cfg.reminder_days))
        posted = 0
        for event in await self.store.approved_between(today.isoformat(), horizon.isoformat()):
            window = due_window(days_until(event['start_date'], today), self.cfg.reminder_days)
            if window and await self.notify(event, window):
                posted += 1
        logger.info('Events poster: %d reminder(s) for %s', posted, today)
        if self.cfg.digest_enabled and today.weekday() == 0:
            await self.run_digest(today)
        return posted

    async def run_digest(self, today: Optional[date] = None) -> bool:
        today = today or self.today()
        rows = await self.store.approved_between(today.isoformat(),
                                                 (today + timedelta(days=DIGEST_DAYS)).isoformat())
        embed = cards.digest_embed(rows, self.regions, today=today.isoformat())
        if self.cfg.dry_run:
            logger.info('DRY RUN events digest: %d event(s)', len(rows))
            return True
        # event_id 0 is a sentinel: the digest is not about one event, and
        # PRAGMA foreign_keys is off, so the row is not checked against a
        # real events.id. This is the same claim/send/mark dance notify()
        # uses, keyed on the day so a second run this Monday cannot double-post.
        reminder_id = await self.store.claim_reminder(0, f'digest:{today.isoformat()}', self.cfg.channel_id)
        if reminder_id is None:
            logger.info('Events digest already posted for %s', today)
            return False
        channel = await self._channel(self.cfg.channel_id)
        if channel is None:
            await self.store.release_reminder(reminder_id)
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: channel %s not found; digest not sent', self.cfg.channel_id)
            return False
        try:
            message = await channel.send(embed=embed, allowed_mentions=cards.allowed_mentions([]))
        except discord.HTTPException as e:
            await self.store.release_reminder(reminder_id)
            EVENTS_POST_ERRORS.inc()
            logger.error('Events: digest failed: %s', e)
            return False
        await self.store.mark_reminder_sent(reminder_id, message.id, '')
        logger.info('Events digest posted: %d event(s)', len(rows))
        return True

    def _rollover_row(self, parent: dict) -> dict:
        start, end = next_annual_dates(date.fromisoformat(parent['start_date']),
                                       date.fromisoformat(parent['end_date']))
        child = {col: parent.get(col) for col in EVENT_COLUMNS}
        child.update({
            'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'fingerprint': fingerprint(parent['title'], start), 'date_status': 'estimated',
            'status': 'pending', 'provenance': 'rollover', 'parent_event_id': parent['id'],
            'submitted_by': None, 'review_message_id': None, 'decided_by': None, 'decided_at': None,
            'reject_reason': None, 'last_verified_at': None,
        })
        return child

    async def run_sweep(self, today: Optional[date] = None, now: Optional[datetime] = None) -> dict:
        """Nightly: reap crashed reminder claims, retire ended events, roll
        annual ones into next year's pending row, expire stale submissions,
        purge old rejections."""
        today = today or self.today()
        now = now or datetime.now(ZoneInfo('UTC'))
        released_claims = await self.store.release_unposted_claims()
        if released_claims:
            logger.info('Events sweep: released %d orphaned reminder claim(s)', released_claims)
        retired = await self.store.retire_ended(today.isoformat())
        guild_ids = {row['guild_id'] for row in retired}
        rolled = 0
        for row in retired:
            if row['recurrence'] != 'annual' or row['status'] != 'approved':
                continue
            if await self.store.has_rollover(row['id']):
                continue
            child = self._rollover_row(row)
            try:
                child_id = await self.store.insert(child, actor_id=0, action='rollover')
            except database.aiosqlite.IntegrityError:
                logger.info('Events: rollover of #%d skipped, %s already listed', row['id'], child['fingerprint'])
                continue
            EVENTS_SUBMISSIONS.labels(provenance='rollover').inc()
            event = await self.store.get(child_id)
            message_id = await self.post_review_card(event)
            if message_id:
                await self.store.set_review_message(child_id, message_id)
            rolled += 1
        expired_ids = await self.store.expire_pending(
            (now - timedelta(days=self.cfg.pending_expire_days)).isoformat())
        for event_id in expired_ids:
            EVENTS_DECISIONS.labels(decision='expired').inc()
            expired_row = await self.store.get(event_id)
            if expired_row:
                guild_ids.add(expired_row['guild_id'])
            await self.refresh_card(expired_row)
        purged = await self.store.purge_rejected((now - timedelta(days=REJECTED_KEEP_DAYS)).isoformat())
        for guild_id in guild_ids:
            EVENTS_PENDING.set(await self.store.pending_count(guild_id))
        result = {'retired': len(retired), 'rolled': rolled, 'expired': len(expired_ids), 'purged': purged,
                  'released_claims': released_claims}
        logger.info('Events sweep for %s: %s', today, result)
        return result

    # -- mod commands ----------------------------------------------------------

    @events.command(name='pending', description='Submissions waiting for review')
    @app_commands.describe(repost='Post review cards again for any whose card is gone')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_pending(self, interaction: discord.Interaction, repost: bool = False):
        if await self._refuse_if_off(interaction):
            return
        rows = await self.store.list_pending(interaction.guild_id)
        if not rows:
            await interaction.response.send_message('Nothing is waiting for review.', ephemeral=True)
            return
        lines = [f"#{r['id']} {r['title']} ({r['start_date']}) from <@{r['submitted_by']}>"
                 if r['submitted_by'] else f"#{r['id']} {r['title']} ({r['start_date']}), {r['provenance']}"
                 for r in rows]
        await interaction.response.send_message('\n'.join(lines), ephemeral=True,
                                                allowed_mentions=cards.allowed_mentions([]))
        if not repost:
            return
        channel = await self._channel(self.cfg.review_channel_id)
        reposted = 0
        for row in rows:
            present = False
            if channel is not None and row.get('review_message_id'):
                try:
                    await channel.fetch_message(row['review_message_id'])
                    present = True
                except discord.HTTPException:
                    present = False
            if present:
                continue
            message_id = await self.post_review_card(row)
            if message_id:
                await self.store.set_review_message(row['id'], message_id)
                reposted += 1
        await interaction.followup.send(f'Reposted {reposted} review card(s).', ephemeral=True)

    @events.command(name='status', description='Events system health')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_status(self, interaction: discord.Interaction):
        if await self._refuse_if_off(interaction):
            return
        counts = await self.store.counts(interaction.guild_id)
        needed = set(TOPIC_ROLES.values()) | set(self.regions.regions.values()) | set(self.regions.countries.values())
        have = {r.name for r in interaction.guild.roles}
        missing = sorted(needed - have)
        next_post = self.poster.next_iteration
        next_sweep = self.sweeper.next_iteration
        channel = await self._channel(self.cfg.channel_id)
        can_mention = bool(channel) and channel.permissions_for(interaction.guild.me).mention_everyone
        lines = [
            f"dry run: {'on' if self.cfg.dry_run else 'off'}; channel <#{self.cfg.channel_id}>; "
            f"review <#{self.cfg.review_channel_id}>",
            f"posts at {self.cfg.post_at[0]:02d}:{self.cfg.post_at[1]:02d} {self.cfg.timezone}; "
            f"reminders {', '.join(str(d) for d in self.cfg.reminder_days)} days out; "
            f"digest {'on' if self.cfg.digest_enabled else 'off'}",
            'counts: ' + (', '.join(f'{k}: {v}' for k, v in sorted(counts.items())) or 'no events yet'),
            f"next post: {self._local(next_post.isoformat()) if next_post else 'loop not running'}; "
            f"next sweep: {self._local(next_sweep.isoformat()) if next_sweep else 'loop not running'}",
            f"missing roles: {len(missing)}" + (f" ({', '.join(missing[:8])}{', ...' if len(missing) > 8 else ''})"
                                                 if missing else ''),
            'role mentions: ' + ('allowed' if can_mention else 'BLOCKED, grant Mention @everyone, @here and All Roles '
                                                              'in the events channel'),
        ]
        await interaction.response.send_message('\n'.join(lines), ephemeral=True)

    @events.command(name='approve', description='Approve a pending event by id')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_approve(self, interaction: discord.Interaction, event_id: int):
        if await self._refuse_if_off(interaction):
            return
        row = await self.store.get(event_id)
        if row is None or row['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(f'No event #{event_id} here.', ephemeral=True)
            return
        await self.decide(interaction, event_id, 'approved')

    @events.command(name='reject', description='Reject a pending event by id')
    @app_commands.describe(reason='The submitter sees this')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_reject(self, interaction: discord.Interaction, event_id: int,
                            reason: app_commands.Range[str, 1, 200]):
        if await self._refuse_if_off(interaction):
            return
        row = await self.store.get(event_id)
        if row is None or row['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(f'No event #{event_id} here.', ephemeral=True)
            return
        await self.decide(interaction, event_id, 'rejected', reason=reason.strip())

    @events.command(name='edit', description='Edit an event (any status)')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_edit(self, interaction: discord.Interaction, event_id: int):
        if await self._refuse_if_off(interaction):
            return
        event = await self.store.get(event_id)
        if event is None or event['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(f'No event #{event_id} here.', ephemeral=True)
            return
        await interaction.response.send_modal(EditModal(self, event))

    @events.command(name='cancel', description='Cancel an approved event')
    @app_commands.describe(reason='Shown in the cancellation notice')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def events_cancel(self, interaction: discord.Interaction, event_id: int,
                            reason: app_commands.Range[str, 1, 200]):
        if await self._refuse_if_off(interaction):
            return
        row = await self.store.get(event_id)
        if row is None or row['guild_id'] != interaction.guild_id:
            await interaction.response.send_message(f'No event #{event_id} here.', ephemeral=True)
            return
        # Nothing has been sent yet, so the gate above may still reply
        # directly; everything past this point does Discord HTTP
        # (refresh_card, notify), so acknowledge first.
        await interaction.response.defer(ephemeral=True, thinking=True)
        announced = await self.store.dated_reminder_sent(event_id)
        done = await self.store.cancel(event_id, moderator_id=interaction.user.id, reason=reason.strip())
        if not done:
            await self._reply(interaction,
                              f'#{event_id} is not an approved event, so there is nothing to cancel.')
            return
        event = await self.store.get(event_id)
        EVENTS_DECISIONS.labels(decision='cancelled').inc()
        await self.refresh_card(event)
        await self._reply(interaction, f"#{event_id} {event['title']} cancelled.")
        if announced:
            await self.notify(event, 'cancelled')

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await self._reply(interaction, MOD_ONLY_TEXT)
            return
        logger.exception('Events command failed: %s', error)
        try:
            await self._reply(interaction, 'That did not work; the error is in the log.')
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Events(bot))
