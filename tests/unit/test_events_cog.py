# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The events cog against a real store and a fake Discord.

Hermetic: no gateway, no .env. The bot object is a SimpleNamespace; the
interaction fakes record what was sent. Nothing here may call a bot
entrypoint or load dotenv.
"""

import types

import discord
import pytest

from cogs.events import DISABLED_TEXT, PAGE_SIZE, Events
from utils import database

GUILD = 1


@pytest.fixture
async def cog(tmp_data_dir, monkeypatch):
    monkeypatch.setenv('EVENTS_ENABLED', 'true')
    monkeypatch.setenv('EVENTS_DRY_RUN', 'false')
    monkeypatch.setenv('EVENTS_CHANNEL_ID', '5000')
    monkeypatch.setenv('EVENTS_REVIEW_CHANNEL_ID', '6000')
    monkeypatch.setenv('EVENTS_TIMEZONE', 'America/New_York')
    database.reset_database()
    bot = types.SimpleNamespace(added=[], config=None,
                                add_dynamic_items=lambda *items: bot.added.extend(items))
    c = Events(bot)
    # EVENTS_CHANNEL_ID/EVENTS_REVIEW_CHANNEL_ID go through the config
    # loader's Discord-snowflake check (17 to 20 digits), which the toy
    # ids 5000/6000 used throughout this file don't satisfy; set them on
    # the loaded config directly so the fixture's channel ids match the
    # FakeChannel ids the tests wire up.
    c.cfg = c.cfg.__class__(**{**c.cfg.__dict__, 'channel_id': 5000, 'review_channel_id': 6000})
    await c.attach()
    c.today = lambda: __import__('datetime').date(2026, 9, 3)      # frozen clock
    yield c
    await c.store.db.close()
    database.reset_database()


class FakeResponse:
    def __init__(self):
        self.sent = []

    def is_done(self):
        return bool(self.sent)

    async def send_message(self, content=None, *, embed=None, embeds=None, ephemeral=False,
                           allowed_mentions=None, view=None):
        self.sent.append(types.SimpleNamespace(content=content, embed=embed, embeds=embeds,
                                               ephemeral=ephemeral, allowed_mentions=allowed_mentions,
                                               view=view, modal=None))

    async def send_modal(self, modal):
        self.sent.append(types.SimpleNamespace(content=None, embed=None, ephemeral=True, modal=modal))

    async def defer(self, *, ephemeral=False, thinking=False):
        self.sent.append(types.SimpleNamespace(content=None, embed=None, deferred=True, ephemeral=ephemeral,
                                               modal=None))


class FakeFollowup:
    def __init__(self, response):
        self.response = response

    async def send(self, content=None, *, embed=None, ephemeral=False, allowed_mentions=None, view=None):
        await self.response.send_message(content, embed=embed, ephemeral=ephemeral,
                                         allowed_mentions=allowed_mentions, view=view)


class FakeMessage:
    def __init__(self, mid):
        self.id = mid
        self.edits = []

    async def edit(self, *, embed=None, view=None, content=None):
        self.edits.append(types.SimpleNamespace(embed=embed, view=view, content=content))


class FakeChannel:
    def __init__(self, cid, *, fail=False, guild_id=GUILD, perms=None):
        self.id = cid
        self.sent = []
        self.messages = {}
        self.fail = fail
        self._next = 1000
        self.perms = perms
        # run_poster and run_digest scope their rows to the channel's own
        # guild, so a real channel object always carries one.
        self.guild = types.SimpleNamespace(id=guild_id)

    def permissions_for(self, member):
        if self.perms is not None:
            return self.perms
        return discord.Permissions(mention_everyone=not self.fail, send_messages=True, embed_links=True)

    async def send(self, content=None, *, embed=None, view=None, allowed_mentions=None):
        if self.fail:
            raise discord.HTTPException(types.SimpleNamespace(status=500, reason='boom'), 'boom')
        self._next += 1
        self.sent.append(types.SimpleNamespace(content=content, embed=embed, view=view,
                                               allowed_mentions=allowed_mentions, id=self._next))
        self.messages[self._next] = FakeMessage(self._next)
        return self.messages[self._next]

    async def fetch_message(self, mid):
        if mid not in self.messages:
            raise discord.NotFound(types.SimpleNamespace(status=404, reason='gone'), 'gone')
        return self.messages[mid]


ROLE_NAMES = ('Cybersecurity Events', 'Ham Radio Events', 'FOSS Events', 'Michigan', 'Ohio', 'United States')


def make_guild(role_names=ROLE_NAMES, guild_id=GUILD):
    roles = [types.SimpleNamespace(name=n, id=i, mention=f'<@&{i}>') for i, n in enumerate(role_names, start=100)]
    return types.SimpleNamespace(id=guild_id, roles=roles, me=types.SimpleNamespace(id=1))


def wire(cog, *, guild=None, channels=None):
    """Give the cog's bot a guild and channels: the review channel (6000)
    and the events channel (5000) by default."""
    guild = guild or make_guild()
    channels = channels if channels is not None else {5000: FakeChannel(5000), 6000: FakeChannel(6000)}
    cog.bot.get_guild = lambda gid: guild if gid == guild.id else None
    cog.bot.get_channel = lambda cid: channels.get(cid)
    cog.bot.get_cog = lambda name: cog if name == 'Events' else None
    return guild, channels


def interaction(user_id=42, *, guild=None, guild_id=GUILD, mod=False, client=None):
    guild = guild or make_guild(guild_id=guild_id)
    user = types.SimpleNamespace(id=user_id, mention=f'<@{user_id}>', display_name=f'user{user_id}',
                                 guild_permissions=discord.Permissions(moderate_members=mod))
    response = FakeResponse()
    return types.SimpleNamespace(guild=guild, guild_id=guild.id, user=user, response=response,
                                 followup=FakeFollowup(response), client=client, channel=None, message=None)


def event(**over):
    base = dict(guild_id=GUILD, title='GrrCON', fingerprint='grrcon:2026', topic='cyber',
                start_date='2026-09-24', end_date='2026-09-25', start_time=None, timezone=None,
                date_status='confirmed', city='Grand Rapids', region_code='US-MI', country_code='US',
                scope='regional', url='https://grrcon.com', notes=None, recurrence='annual',
                parent_event_id=None, status='approved', provenance='calendar', submitted_by=None,
                source_url=None, source_note=None, decided_by=0)
    base.update(over)
    return base


async def seed(cog, n=7):
    ids = []
    for i in range(n):
        ids.append(await cog.store.insert(
            event(title=f'Con {i}', fingerprint=f'con {i}:2026', start_date=f'2026-10-{10 + i:02d}',
                  end_date=f'2026-10-{10 + i:02d}'), actor_id=0, action='import'))
    return ids


# -- disabled -----------------------------------------------------------------

async def test_disabled_cog_answers_every_command_with_one_line(tmp_data_dir, monkeypatch):
    monkeypatch.delenv('EVENTS_ENABLED', raising=False)
    c = Events(types.SimpleNamespace(config=None))
    await c.cog_load()                      # no store, no loops
    assert c.store is None
    i = interaction()
    await c.events_list.callback(c, i)
    assert i.response.sent[0].content == DISABLED_TEXT and i.response.sent[0].ephemeral


# -- list / next / search -----------------------------------------------------

async def test_list_pages_five_at_a_time(cog):
    await seed(cog)
    i = interaction()
    await cog.events_list.callback(cog, i)
    sent = i.response.sent[0]
    assert sent.ephemeral is False
    assert sent.embed.footer.text == 'Page 1 of 2'
    assert sent.embed.description.count('**Con') == PAGE_SIZE
    i = interaction()
    await cog.events_list.callback(cog, i, page=2)
    assert i.response.sent[0].embed.description.count('**Con') == 2


async def test_list_filters_by_topic_and_place(cog):
    await seed(cog, 2)
    await cog.store.insert(event(title='Hamfest', fingerprint='hamfest:2026', topic='ham',
                                 start_date='2026-10-01', end_date='2026-10-01',
                                 region_code='CA-ON', country_code='CA'), actor_id=0, action='import')
    i = interaction()
    await cog.events_list.callback(cog, i, topic='ham')
    assert 'Hamfest' in i.response.sent[0].embed.description
    assert 'Con 0' not in i.response.sent[0].embed.description
    i = interaction()
    await cog.events_list.callback(cog, i, where='CA')
    assert 'Hamfest' in i.response.sent[0].embed.description
    i = interaction()
    await cog.events_list.callback(cog, i, where='US-MI')
    assert 'Hamfest' not in i.response.sent[0].embed.description
    i = interaction()
    await cog.events_list.callback(cog, i, where='Narnia')
    assert 'Pick' in i.response.sent[0].content and i.response.sent[0].ephemeral


async def test_list_where_online_lists_only_events_with_no_place(cog):
    await cog.store.insert(event(title='InPersonCon', fingerprint='inpersoncon:2026',
                                 start_date='2026-09-24', end_date='2026-09-24'), actor_id=0, action='import')
    await cog.store.insert(event(title='VirtualCon', fingerprint='virtualcon:2026', city='Online',
                                 start_date='2026-09-25', end_date='2026-09-25', region_code=None,
                                 country_code=None), actor_id=0, action='import')
    i = interaction()
    await cog.events_list.callback(cog, i, where='Online')
    text = i.response.sent[0].embed.description
    assert 'VirtualCon' in text and 'InPersonCon' not in text


async def test_next_is_the_thirty_day_window(cog):
    await seed(cog, 2)                                     # Oct 10 and 11: beyond 30 days from Sep 3
    await cog.store.insert(event(title='Soon', fingerprint='soon:2026', start_date='2026-09-20',
                                 end_date='2026-09-20'), actor_id=0, action='import')
    i = interaction()
    await cog.events_next.callback(cog, i)
    text = i.response.sent[0].embed.description
    assert 'Soon' in text and 'Con 0' not in text


async def test_search_is_ephemeral_and_case_insensitive(cog):
    await seed(cog, 2)
    i = interaction()
    await cog.events_search.callback(cog, i, query='con 1')
    sent = i.response.sent[0]
    assert sent.ephemeral and 'Con 1' in sent.embed.description and 'Con 0' not in sent.embed.description


async def test_where_autocomplete_returns_choices(cog):
    choices = await cog._where_autocomplete(interaction(), 'mich')
    assert [(c.name, c.value) for c in choices] == [('Michigan (US-MI)', 'US-MI')]


# -- submit -------------------------------------------------------------------

async def test_submit_creates_pending_row_and_posts_a_card(cog):
    posted = []

    async def post_review_card(ev):
        posted.append(ev)
        return 777
    cog.post_review_card = post_review_card
    i = interaction(user_id=42)
    await cog.events_submit.callback(cog, i, title='Queen City Con', topic='cyber', start='2026-10-10',
                                     end='2026-10-11', city='Cincinnati', where='US-OH',
                                     url='https://queencitycon.org')
    sent = i.response.sent[-1]                              # sent[0] is the defer
    assert sent.ephemeral and '#1' in sent.content and 'review' in sent.content.lower()
    row = await cog.store.get(1)
    assert row['status'] == 'pending' and row['submitted_by'] == 42 and row['provenance'] == 'member'
    assert row['region_code'] == 'US-OH' and row['country_code'] == 'US' and row['scope'] == 'regional'
    assert row['review_message_id'] == 777
    assert posted[0]['id'] == 1


async def test_submit_defers_before_the_slow_work(cog):
    # post_review_card becomes a real HTTP round trip once Task 8 lands;
    # the interaction has to be acknowledged before that, not after.
    cog.post_review_card = lambda ev: _async(777)
    i = interaction(user_id=42)
    await cog.events_submit.callback(cog, i, title='Deferred Con', topic='cyber', start='2026-10-15',
                                     city='Detroit', where='US-MI')
    first = i.response.sent[0]
    assert getattr(first, 'deferred', False) is True and first.ephemeral is True
    thanks = i.response.sent[-1]
    assert thanks.ephemeral is True and '#1' in thanks.content and 'review' in thanks.content.lower()


async def test_submit_rejects_bad_input_with_the_reason(cog):
    i = interaction()
    await cog.events_submit.callback(cog, i, title='X', topic='cyber', start='next friday', city='Detroit',
                                     where='US-MI')
    sent = i.response.sent[0]
    assert sent.ephemeral and 'YYYY-MM-DD' in sent.content
    assert await cog.store.get(1) is None


async def test_submit_duplicate_names_the_existing_event(cog):
    # Not seed(): seed()'s synthetic fingerprints ('con 0:2026') keep the
    # bulk-listing fixtures from colliding but don't match what
    # validate_submission actually computes for 'Con 0' (fingerprint()
    # strips standalone digits, so it's 'con:2026'); this test needs the
    # real value to exercise duplicate detection.
    await cog.store.insert(event(title='Con 0', fingerprint='con:2026', start_date='2026-10-10',
                                 end_date='2026-10-10'), actor_id=0, action='import')
    i = interaction()
    await cog.events_submit.callback(cog, i, title='Con 0', topic='cyber', start='2026-10-12',
                                     city='Detroit', where='US-MI')
    sent = i.response.sent[-1]                               # sent[0] is the defer
    assert 'matches #1' in sent.content and 'Con 0' in sent.content and 'approved' in sent.content
    assert await cog.store.count_open_submissions(GUILD, 42) == 0


async def test_submit_caps_open_submissions(cog):
    # Named 'Pending Alpha/Beta/Gamma', not 'Pending 0/1/2': fingerprint()
    # strips standalone digits by design (edition numbers), so bare-digit
    # titles here would all fingerprint to 'pending:2026' and the second
    # and third submissions would be rejected as duplicates of the first
    # instead of accepted as separate pending rows.
    cog.post_review_card = lambda ev: _async(None)
    for n, word in enumerate(('Alpha', 'Beta', 'Gamma')):
        i = interaction()
        await cog.events_submit.callback(cog, i, title=f'Pending {word}', topic='cyber',
                                         start=f'2026-11-{10 + n}', city='Detroit', where='US-MI')
    i = interaction()
    await cog.events_submit.callback(cog, i, title='One more', topic='cyber', start='2026-11-20',
                                     city='Detroit', where='US-MI')
    assert 'already have 3' in i.response.sent[-1].content     # sent[0] is the defer
    assert await cog.store.count_open_submissions(GUILD, 42) == 3


async def test_submit_online_event_has_no_place(cog):
    cog.post_review_card = lambda ev: _async(None)
    i = interaction()
    await cog.events_submit.callback(cog, i, title='Virtual Con', topic='foss', start='2026-11-01',
                                     city='Online', where='online')
    row = await cog.store.get(1)
    assert row['region_code'] is None and row['country_code'] is None and row['city'] == 'Online'


async def test_mine_lists_the_callers_rows_only(cog):
    cog.post_review_card = lambda ev: _async(None)
    i = interaction(user_id=42)
    await cog.events_submit.callback(cog, i, title='Mine', topic='cyber', start='2026-11-01',
                                     city='Detroit', where='US-MI')
    i = interaction(user_id=43)
    await cog.events_submit.callback(cog, i, title='Theirs', topic='cyber', start='2026-11-02',
                                     city='Detroit', where='US-MI')
    i = interaction(user_id=42)
    await cog.events_mine.callback(cog, i)
    sent = i.response.sent[0]
    assert sent.ephemeral and 'Mine' in sent.content and 'Theirs' not in sent.content


def _async(value):
    async def coro():
        return value
    return coro()


# -- review cards and buttons -------------------------------------------------

from cogs.events import EditModal, EventButton, RejectModal, review_view  # noqa: E402


async def submit(cog, user_id=42, **over):
    """A member submission through the real command, with the card posted
    to the wired review channel."""
    fields = dict(title='Queen City Con', topic='cyber', start='2026-10-10', end='2026-10-11',
                  city='Cincinnati', where='US-OH', url='https://queencitycon.org')
    fields.update(over)
    i = interaction(user_id=user_id)
    await cog.events_submit.callback(cog, i, **fields)
    return i


async def test_submission_posts_a_card_with_three_buttons(cog):
    guild, channels = wire(cog)
    await submit(cog)
    card = channels[6000].sent[0]
    assert card.embed.title == 'Event #1: Queen City Con'
    assert 'Submitted by <@42>' in card.embed.description
    assert [b.custom_id for b in card.view.children] == ['event:1:approve', 'event:1:reject', 'event:1:edit']
    assert card.allowed_mentions.users is False
    assert (await cog.store.get(1))['review_message_id'] == card.id


async def test_card_posting_failure_does_not_lose_the_submission(cog):
    wire(cog, channels={5000: FakeChannel(5000), 6000: FakeChannel(6000, fail=True)})
    i = await submit(cog)
    assert 'review queue' in i.response.sent[-1].content      # sent[0] is the defer
    row = await cog.store.get(1)
    assert row['status'] == 'pending' and row['review_message_id'] is None


async def test_button_template_round_trips():
    button = EventButton(12, 'approve')
    assert button.custom_id == 'event:12:approve'
    match = EventButton.__discord_ui_compiled_template__.match('event:12:reject')
    rebuilt = await EventButton.from_custom_id(None, None, match)
    assert (rebuilt.event_id, rebuilt.verb) == (12, 'reject')
    assert len(review_view(12).children) == 3


async def test_non_moderator_click_is_refused(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=99, mod=False)
    await cog.handle_button(i, 1, 'approve')
    assert 'moderator' in i.response.sent[0].content.lower() and i.response.sent[0].ephemeral
    assert (await cog.store.get(1))['status'] == 'pending'


async def test_approve_click_decides_and_rewrites_the_card(cog):
    guild, channels = wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'approve')
    row = await cog.store.get(1)
    assert row['status'] == 'approved' and row['decided_by'] == 7
    edit = channels[6000].messages[channels[6000].sent[0].id].edits[-1]
    assert edit.view is None and 'Approved by <@7>' in edit.embed.footer.text
    assert 'approved' in i.response.sent[-1].content.lower()      # sent[0] is the defer


async def test_second_click_reports_who_decided(cog):
    wire(cog)
    await submit(cog)
    await cog.handle_button(interaction(user_id=7, mod=True), 1, 'approve')
    i = interaction(user_id=8, mod=True)
    await cog.handle_button(i, 1, 'reject')
    # sent[0] is the defer
    assert 'Already decided' in i.response.sent[-1].content and '<@7>' in i.response.sent[-1].content


async def test_reject_click_opens_a_modal_and_the_modal_decides(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'reject')
    modal = i.response.sent[0].modal
    assert isinstance(modal, RejectModal)
    modal.reason._value = 'Duplicate of the BSides listing'
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    row = await cog.store.get(1)
    assert row['status'] == 'rejected' and row['reject_reason'] == 'Duplicate of the BSides listing'


async def test_edit_click_opens_a_prefilled_modal(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'edit')
    modal = i.response.sent[0].modal
    assert isinstance(modal, EditModal)
    assert modal.title_field.default == 'Queen City Con'
    assert modal.dates.default == '2026-10-10 to 2026-10-11'
    assert modal.location.default == 'Cincinnati, US-OH'


async def test_edit_modal_applies_changes_and_keeps_status(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.title_field._value = 'Queen City Con 2026'
    modal.dates._value = '2026-10-10 to 2026-10-12'
    modal.location._value = 'Cincinnati, US-OH, national'
    modal.url._value = 'https://queencitycon.org'
    modal.notes._value = ''
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    row = await cog.store.get(1)
    assert row['title'] == 'Queen City Con 2026' and row['end_date'] == '2026-10-12'
    assert row['scope'] == 'national' and row['status'] == 'pending'
    assert 'updated' in j.response.sent[-1].content.lower()       # sent[0] is the defer


async def test_edit_modal_bad_dates_are_reported_not_saved(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.dates._value = 'October 10'
    modal.title_field._value = 'Queen City Con'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    assert 'YYYY-MM-DD' in j.response.sent[0].content
    assert (await cog.store.get(1))['end_date'] == '2026-10-11'


# -- authorization travels with the write --------------------------------------

async def test_reject_modal_submit_from_a_non_mod_writes_nothing(cog):
    # The modal was opened while its clicker was still a moderator; by the
    # time they submit it, the role could be gone. decide() must gate this
    # itself, not rely on the button click that opened the modal.
    wire(cog)
    await submit(cog)
    modal = RejectModal(cog, 1)
    modal.reason._value = 'Duplicate of the BSides listing'
    j = interaction(user_id=99, mod=False)
    await modal.on_submit(j)
    assert 'moderator' in j.response.sent[0].content.lower() and j.response.sent[0].ephemeral
    assert (await cog.store.get(1))['status'] == 'pending'


async def test_edit_modal_submit_from_a_non_mod_writes_nothing(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.title_field._value = 'Should not stick'
    modal.dates._value = '2026-10-10 to 2026-10-11'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    j = interaction(user_id=99, mod=False)
    await modal.on_submit(j)
    assert 'moderator' in j.response.sent[0].content.lower() and j.response.sent[0].ephemeral
    assert (await cog.store.get(1))['title'] == 'Queen City Con'


# -- stale cards self-heal -----------------------------------------------------

async def test_stale_card_click_repairs_the_card(cog):
    guild, channels = wire(cog)
    await submit(cog)
    await cog.handle_button(interaction(user_id=7, mod=True), 1, 'approve')
    message = channels[6000].messages[channels[6000].sent[0].id]
    message.edits.clear()                                    # the earlier refresh "was lost"
    i = interaction(user_id=8, mod=True)
    await cog.handle_button(i, 1, 'reject')
    assert message.edits and message.edits[-1].view is None
    # refresh_card is fetch_message + edit, the same Discord HTTP round
    # trip that has to happen after the interaction is acknowledged, not
    # before: the deferred entry must precede the reply here too.
    first = i.response.sent[0]
    assert getattr(first, 'deferred', False) is True and first.ephemeral is True
    assert 'Already decided' in i.response.sent[-1].content


async def test_decide_on_an_already_decided_event_still_repairs_the_card(cog):
    guild, channels = wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.events_reject.callback(cog, i, event_id=1, reason='dup')
    message = channels[6000].messages[channels[6000].sent[0].id]
    message.edits.clear()
    i = interaction(user_id=7, mod=True)
    await cog.events_approve.callback(cog, i, event_id=1)
    assert message.edits and message.edits[-1].view is None
    assert 'Already decided' in i.response.sent[-1].content      # sent[0] is the defer


# -- respond before Discord HTTP -----------------------------------------------

async def test_approve_defers_before_the_card_refresh(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'approve')
    first = i.response.sent[0]
    assert getattr(first, 'deferred', False) is True and first.ephemeral is True
    assert 'approved' in i.response.sent[-1].content.lower()


async def test_reject_modal_defers_before_the_confirmation(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.handle_button(i, 1, 'reject')
    modal = i.response.sent[0].modal
    modal.reason._value = 'Duplicate of the BSides listing'
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    first = j.response.sent[0]
    assert getattr(first, 'deferred', False) is True and first.ephemeral is True
    assert 'rejected' in j.response.sent[-1].content.lower()


async def test_edit_modal_defers_before_the_confirmation(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.title_field._value = 'Queen City Con'
    modal.dates._value = '2026-10-10 to 2026-10-11'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    first = j.response.sent[0]
    assert getattr(first, 'deferred', False) is True and first.ephemeral is True
    assert 'updated' in j.response.sent[-1].content.lower()


async def test_cancel_defers_before_the_confirmation(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    i = interaction(user_id=7, mod=True)
    await cog.events_cancel.callback(cog, i, event_id=eid, reason='venue lost')
    first = i.response.sent[0]
    assert getattr(first, 'deferred', False) is True and first.ephemeral is True
    assert 'cancelled' in i.response.sent[-1].content.lower()


# -- one-shot notices ---------------------------------------------------------

async def test_notify_posts_with_role_mentions_only(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    assert await cog.notify(await cog.store.get(eid), '7') is True
    post = channels[5000].sent[0]
    mentions = {r.name for r in post.allowed_mentions.roles}
    assert mentions == {'Cybersecurity Events', 'Michigan'}
    assert post.allowed_mentions.users is False and post.allowed_mentions.everyone is False
    assert post.content.startswith('<@&100> <@&103>')
    assert post.embed.title == 'GrrCON in 21 days'
    assert await cog.store.dated_reminder_sent(eid) is True
    assert await cog.notify(await cog.store.get(eid), '7') is False      # once ever


async def test_notify_names_missing_roles_in_plain_text(cog):
    guild, channels = wire(cog, guild=make_guild(('Cybersecurity Events',)))
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    post = channels[5000].sent[0]
    assert [r.name for r in post.allowed_mentions.roles] == ['Cybersecurity Events']
    assert 'Michigan' in post.content


async def test_notify_send_failure_releases_the_claim(cog):
    wire(cog, channels={5000: FakeChannel(5000, fail=True), 6000: FakeChannel(6000)})
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    assert await cog.notify(await cog.store.get(eid), '30') is False
    assert await cog.store.claim_reminder(eid, '30', 5000) is not None    # nothing left behind


async def test_notify_dry_run_logs_and_records_nothing(cog, caplog):
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'dry_run': True})
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    with caplog.at_level('INFO', logger='penguin.events'):
        assert await cog.notify(await cog.store.get(eid), '30') is True
    assert channels[5000].sent == []
    assert any('DRY RUN events reminder' in r.message for r in caplog.records)
    assert await cog.store.dated_reminder_sent(eid) is False


# -- mod commands -------------------------------------------------------------

def test_mod_commands_require_moderate_members(cog):
    for cmd in (cog.events_pending, cog.events_approve, cog.events_reject, cog.events_edit, cog.events_cancel):
        assert cmd.checks, cmd.name


async def test_pending_lists_and_reposts_lost_cards(cog):
    guild, channels = wire(cog)
    await submit(cog)
    await submit(cog, title='Second', start='2026-11-01', end=None)
    channels[6000].messages.clear()                        # both cards deleted by hand
    i = interaction(user_id=7, mod=True)
    await cog.events_pending.callback(cog, i, repost=True)
    text = i.response.sent[0].content
    assert '#1' in text and '#2' in text and i.response.sent[0].ephemeral
    assert len(channels[6000].sent) == 4                   # two originals, two reposts
    assert (await cog.store.get(1))['review_message_id'] == channels[6000].sent[2].id


async def test_approve_and_reject_commands(cog):
    wire(cog)
    await submit(cog)
    await submit(cog, title='Second', start='2026-11-01', end=None)
    i = interaction(user_id=7, mod=True)
    await cog.events_approve.callback(cog, i, event_id=1)
    assert (await cog.store.get(1))['status'] == 'approved'
    i = interaction(user_id=7, mod=True)
    await cog.events_reject.callback(cog, i, event_id=2, reason='not a real con')
    assert (await cog.store.get(2))['reject_reason'] == 'not a real con'
    i = interaction(user_id=7, mod=True)
    await cog.events_approve.callback(cog, i, event_id=2)
    assert 'Already decided' in i.response.sent[-1].content       # sent[0] is the defer


async def test_edit_command_opens_the_modal(cog):
    wire(cog)
    await submit(cog)
    i = interaction(user_id=7, mod=True)
    await cog.events_edit.callback(cog, i, event_id=1)
    assert isinstance(i.response.sent[0].modal, EditModal)


async def test_cancel_posts_a_notice_only_if_a_reminder_went_out(cog):
    guild, channels = wire(cog)
    a = await cog.store.insert(event(), actor_id=0, action='import')
    b = await cog.store.insert(event(title='Quiet', fingerprint='quiet:2026'), actor_id=0, action='import')
    await cog.notify(await cog.store.get(a), '30')
    i = interaction(user_id=7, mod=True)
    await cog.events_cancel.callback(cog, i, event_id=a, reason='venue lost')
    i = interaction(user_id=7, mod=True)
    await cog.events_cancel.callback(cog, i, event_id=b, reason='never announced')
    posts = channels[5000].sent
    assert len(posts) == 2                                 # the reminder, then one cancellation
    assert posts[1].embed.title == 'Cancelled: GrrCON'
    assert (await cog.store.get(b))['status'] == 'cancelled'


async def test_edit_of_an_announced_event_posts_a_change_notice(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'start_date': '2026-09-25', 'end_date': '2026-09-26'})
    posts = channels[5000].sent
    assert len(posts) == 2 and posts[1].embed.title.startswith('Updated: GrrCON')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'notes': 'parking is free'})
    assert len(channels[5000].sent) == 2                   # notes are not a schedule change


async def test_two_consecutive_schedule_changes_each_post_a_notice(cog):
    # The first change notice claims window 'changed:<start_date>'; a
    # second move to a different date must claim a different window, not
    # collide with the first on the UNIQUE(event_id, window) index.
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'start_date': '2026-09-25', 'end_date': '2026-09-26'})
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'start_date': '2026-10-02', 'end_date': '2026-10-03'})
    posts = channels[5000].sent
    assert len(posts) == 3                                 # reminder, then two change notices
    assert posts[1].embed.title.startswith('Updated: GrrCON')
    assert posts[2].embed.title.startswith('Updated: GrrCON')


# -- the loops ----------------------------------------------------------------

import asyncio  # noqa: E402
import datetime as dt  # noqa: E402

from discord.ext import commands  # noqa: E402


def _freeze(cog, y, m, d):
    cog.today = lambda: dt.date(y, m, d)


async def test_poster_fires_each_window_once(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')            # 2026-09-24
    _freeze(cog, 2026, 8, 25)                                                # 30 days out
    assert await cog.run_poster() == 1
    assert await cog.run_poster() == 0                                       # same day again: nothing
    _freeze(cog, 2026, 8, 26)
    assert await cog.run_poster() == 0                                       # 29 days: no window
    _freeze(cog, 2026, 9, 17)
    assert await cog.run_poster() == 1                                       # 7
    _freeze(cog, 2026, 9, 23)
    assert await cog.run_poster() == 1                                       # 1
    windows = [p.embed.title for p in channels[5000].sent]
    assert windows == ['GrrCON in 30 days', 'GrrCON in 7 days', 'GrrCON tomorrow']


async def test_poster_skips_pending_and_cancelled_rows(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(status='pending', submitted_by=42), actor_id=42, action='submit')
    await cog.store.insert(event(title='Gone', fingerprint='gone:2026', status='cancelled'),
                           actor_id=0, action='import')
    _freeze(cog, 2026, 8, 25)
    assert await cog.run_poster() == 0 and channels[5000].sent == []


async def test_poster_after_a_missed_day_does_not_backfill(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 8, 27)                                                # 28 days: the 30 was missed
    assert await cog.run_poster() == 0


async def test_monday_digest_goes_out_without_mentions(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 9, 7)                                                 # a Monday, 17 days out
    await cog.run_poster()
    digest = [p for p in channels[5000].sent if p.embed.title == 'Con Recon: this month']
    assert len(digest) == 1
    assert digest[0].allowed_mentions.roles == [] and digest[0].content is None
    assert 'GrrCON' in digest[0].embed.description


async def test_digest_respects_the_flag_and_the_weekday(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 9, 8)                                                 # Tuesday
    await cog.run_poster()
    assert channels[5000].sent == []
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'digest_enabled': False})
    _freeze(cog, 2026, 9, 7)
    await cog.run_poster()
    assert channels[5000].sent == []


async def test_sweep_retires_rolls_over_and_posts_a_card(cog):
    guild, channels = wire(cog)
    old = await cog.store.insert(event(start_date='2026-05-30', end_date='2026-05-30'),
                                 actor_id=0, action='import')
    once = await cog.store.insert(event(title='One off', fingerprint='one off:2026', recurrence='none',
                                        start_date='2026-06-01', end_date='2026-06-01'),
                                  actor_id=0, action='import')
    result = await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert result['retired'] == 2 and result['rolled'] == 1
    assert (await cog.store.get(old))['status'] == 'retired'
    assert (await cog.store.get(once))['status'] == 'retired'
    child = await cog.store.find_fingerprint(GUILD, 'grrcon:2027')
    assert child['start_date'] == '2027-05-29' and child['date_status'] == 'estimated'
    assert child['status'] == 'pending' and child['provenance'] == 'rollover'
    assert child['parent_event_id'] == old and child['submitted_by'] is None
    card = channels[6000].sent[0]
    assert f'Rolled over from #{old}' in card.embed.description
    assert child['review_message_id'] == card.id
    # a second sweep does not roll the same parent again
    again = await cog.run_sweep(today=dt.date(2026, 9, 4))
    assert again['rolled'] == 0


async def test_sweep_rollover_collision_is_skipped(cog):
    wire(cog)
    old = await cog.store.insert(event(start_date='2026-05-30', end_date='2026-05-30'),
                                 actor_id=0, action='import')
    await cog.store.insert(event(title='GrrCON', fingerprint='grrcon:2027', start_date='2027-05-29',
                                 end_date='2027-05-29'), actor_id=0, action='import')  # already listed
    result = await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert result['rolled'] == 0 and (await cog.store.get(old))['status'] == 'retired'


async def test_sweep_expires_stale_pending_and_purges_old_rejected(cog):
    guild, channels = wire(cog)
    await submit(cog)                                                        # pending, created now
    now = dt.datetime.now(dt.timezone.utc)
    result = await cog.run_sweep(today=dt.date(2026, 9, 3), now=now)
    assert result['expired'] == 0
    result = await cog.run_sweep(today=dt.date(2026, 9, 3), now=now + dt.timedelta(days=31))
    assert result['expired'] == 1
    row = await cog.store.get(1)
    assert row['status'] == 'rejected' and row['reject_reason'] == 'expired'
    edit = channels[6000].messages[channels[6000].sent[0].id].edits[-1]
    assert edit.view is None and 'the sweep' in edit.embed.footer.text
    result = await cog.run_sweep(today=dt.date(2026, 9, 3), now=now + dt.timedelta(days=31 + 181))
    assert result['purged'] == 1 and await cog.store.get(1) is None


async def test_status_reports_flags_counts_and_missing_roles(cog):
    guild, channels = wire(cog, guild=make_guild(('Cybersecurity Events', 'Michigan')))
    await cog.store.insert(event(), actor_id=0, action='import')
    await submit(cog)
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    text = i.response.sent[-1].content                     # sent[0] is the defer
    assert 'dry run: off' in text and 'approved: 1' in text and 'pending: 1' in text
    assert '09:00 America/New_York' in text and '30, 7, 1' in text
    # needed = 3 topic roles + 64 regions + 24 countries = 91; the guild has 2
    assert 'missing roles: 89' in text
    assert 'role mentions: allowed' in text
    assert i.response.sent[-1].ephemeral


async def test_status_flags_a_channel_where_the_bot_cannot_mention_roles(cog):
    guild, channels = wire(cog, channels={5000: FakeChannel(5000, fail=True), 6000: FakeChannel(6000)})
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    assert 'role mentions: BLOCKED' in i.response.sent[-1].content


async def test_enabled_cog_starts_and_stops_its_loops_on_a_real_bot(tmp_data_dir, monkeypatch):
    monkeypatch.setenv('EVENTS_ENABLED', 'true')
    monkeypatch.setenv('EVENTS_CHANNEL_ID', '5000')
    database.reset_database()
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.default())

    async def parked():
        await asyncio.Event().wait()
    bot.wait_until_ready = parked
    try:
        await bot.load_extension('cogs.events')
        c = bot.get_cog('Events')
        assert c.poster.is_running() and c.sweeper.is_running()
        assert c.poster.time[0].hour == 9 and c.sweeper.time[0].hour == 3
        await bot.unload_extension('cogs.events')
        assert not c.poster.is_running() and not c.sweeper.is_running()
        await c.store.db.close()
    finally:
        await bot.close()
        database.reset_database()


# -- review findings: digest dedupe, orphaned claims, pending gauge -----------

async def test_digest_posts_once_per_day_even_across_two_poster_runs(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    _freeze(cog, 2026, 9, 7)                                                 # a Monday
    await cog.run_poster()
    await cog.run_poster()
    digest = [p for p in channels[5000].sent if p.embed.title == 'Con Recon: this month']
    assert len(digest) == 1


async def test_digest_send_failure_releases_the_claim(cog, caplog):
    wire(cog, channels={5000: FakeChannel(5000, fail=True), 6000: FakeChannel(6000)})
    await cog.store.insert(event(), actor_id=0, action='import')
    with caplog.at_level('INFO', logger='penguin.events'):
        assert await cog.run_digest(dt.date(2026, 9, 7)) is False
    # the claim was released: the same day's window is still open for a retry
    assert await cog.store.claim_reminder(0, 'digest:2026-09-07', 5000) is not None


async def test_digest_already_posted_is_logged_and_not_reposted(cog, caplog):
    wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    assert await cog.run_digest(dt.date(2026, 9, 7)) is True
    with caplog.at_level('INFO', logger='penguin.events'):
        assert await cog.run_digest(dt.date(2026, 9, 7)) is False
    assert any('Events digest already posted for 2026-09-07' in r.message for r in caplog.records)


async def test_sweep_releases_orphaned_reminder_claims(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    rid = await cog.store.claim_reminder(eid, '30', 5000)    # simulates a crash between claim and send
    # The reaper only frees a claim older than six hours, so that it can
    # never delete one the poster is still using; age this one past that.
    await cog.store.db.conn.execute(
        "UPDATE event_reminders SET claimed_at = datetime('now', '-7 hours') WHERE id = ?", (rid,))
    await cog.store.db.conn.commit()
    result = await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert result['released_claims'] == 1
    # the window is claimable again, and notify can actually post it now
    assert await cog.notify(await cog.store.get(eid), '30') is True


async def test_sweep_leaves_a_posted_claim_alone(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    result = await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert result['released_claims'] == 0
    assert await cog.store.dated_reminder_sent(eid) is True


async def test_notify_non_http_exception_releases_the_claim_and_propagates(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')

    async def boom(*args, **kwargs):
        raise RuntimeError('boom')
    channels[5000].send = boom
    with pytest.raises(RuntimeError):
        await cog.notify(await cog.store.get(eid), '30')
    # released, not stuck: the window can be claimed (and retried) again
    assert await cog.store.claim_reminder(eid, '30', 5000) is not None


async def test_sweep_updates_the_pending_gauge_after_a_rollover(cog, monkeypatch):
    # Patch the name in run_sweep's own __globals__, not a freshly `import
    # cogs.events`: the real-bot loop test elsewhere in this file unloads
    # the extension, which discord.py evicts from sys.modules, so a plain
    # re-import there would bind a second, unrelated module object and the
    # patch would silently miss the class this cog's bound methods use.
    class FakeGauge:
        def __init__(self):
            self.value = None

        def set(self, value):
            self.value = value
    gauge = FakeGauge()
    monkeypatch.setitem(cog.run_sweep.__globals__, 'EVENTS_PENDING', gauge)
    wire(cog)
    await cog.store.insert(event(start_date='2026-05-30', end_date='2026-05-30'),
                           actor_id=0, action='import')
    await cog.run_sweep(today=dt.date(2026, 9, 3))
    assert gauge.value == await cog.store.pending_count(GUILD) == 1


# -- final review: fingerprint on edit, guild scope, unconfigured review channel


async def test_edit_recomputes_the_fingerprint_so_dedupe_still_catches_a_repeat(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.title_field._value = 'Queen City Con'
    modal.dates._value = '2027-01-15'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    await modal.on_submit(interaction(user_id=7, mod=True))
    assert (await cog.store.get(1))['fingerprint'] == 'queen city con:2027'
    # a member proposing the same event on its new date is now caught
    i = await submit(cog, user_id=43, title='Queen City Con', start='2027-01-15', end=None)
    assert 'That matches #1' in i.response.sent[-1].content
    assert await cog.store.counts(GUILD) == {'pending': 1}


async def test_a_colliding_edit_is_reported_and_changes_nothing(cog):
    wire(cog)
    await submit(cog)
    await submit(cog, title='Another Con', start='2026-11-01', end=None)
    modal = EditModal(cog, await cog.store.get(2))
    modal.title_field._value = 'Queen City Con'
    modal.dates._value = '2026-12-01'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    assert 'collides with #1' in j.response.sent[-1].content
    assert (await cog.store.get(2))['title'] == 'Another Con'
    assert (await cog.store.get(2))['start_date'] == '2026-11-01'
    assert (await cog.store.get(1))['title'] == 'Queen City Con'


async def test_an_edit_of_a_row_that_vanished_says_so(cog):
    wire(cog)
    await submit(cog)
    modal = EditModal(cog, await cog.store.get(1))
    modal.title_field._value = 'Queen City Con'
    modal.dates._value = '2026-10-10 to 2026-10-11'
    modal.location._value = 'Cincinnati, US-OH'
    modal.url._value = ''
    modal.notes._value = ''
    # The row is deleted between apply_edit's get and its update, so the
    # update writes nothing and returns None.
    cog.store.update = lambda *a, **k: _async(None)
    j = interaction(user_id=7, mod=True)
    await modal.on_submit(j)
    assert 'no longer exists' in j.response.sent[-1].content


async def test_status_defers_before_it_resolves_the_channel(cog):
    guild, channels = wire(cog)
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    assert getattr(i.response.sent[0], 'deferred', False) is True
    assert 'dry run: off' in i.response.sent[-1].content


async def test_status_names_an_unconfigured_review_channel(cog):
    guild, channels = wire(cog)
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'review_channel_id': None})
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    text = i.response.sent[-1].content
    assert 'review channel: not configured' in text and '<#None>' not in text


async def test_rollover_moves_a_year_in_the_title_to_the_new_one(cog):
    wire(cog)
    dated = await cog.store.insert(event(title='HamCation 2026', fingerprint='hamcation:2026',
                                         start_date='2026-02-13', end_date='2026-02-15'),
                                   actor_id=0, action='import')
    undated = await cog.store.insert(event(title='Dayton Hamvention', fingerprint='dayton hamvention:2026',
                                           start_date='2026-05-15', end_date='2026-05-17'),
                                     actor_id=0, action='import')
    await cog.run_sweep(today=dt.date(2026, 9, 3))
    child = await cog.store.find_fingerprint(GUILD, 'hamcation:2027')
    assert child['title'] == 'HamCation 2027' and child['parent_event_id'] == dated
    plain = await cog.store.find_fingerprint(GUILD, 'dayton hamvention:2027')
    assert plain['title'] == 'Dayton Hamvention' and plain['parent_event_id'] == undated


async def test_poster_skips_rows_from_another_guild(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(start_date='2026-10-03', end_date='2026-10-03'),
                           actor_id=0, action='import')
    await cog.store.insert(event(guild_id=2, title='Elsewhere', fingerprint='elsewhere:2026',
                                 start_date='2026-10-03', end_date='2026-10-03'),
                           actor_id=0, action='import')
    _freeze(cog, 2026, 9, 3)                                                 # 30 days out for both
    assert await cog.run_poster() == 1
    assert len(channels[5000].sent) == 1
    assert 'GrrCON' in channels[5000].sent[0].embed.title


async def test_digest_skips_rows_from_another_guild(cog):
    guild, channels = wire(cog)
    await cog.store.insert(event(), actor_id=0, action='import')
    await cog.store.insert(event(guild_id=2, title='Elsewhere', fingerprint='elsewhere:2026'),
                           actor_id=0, action='import')
    assert await cog.run_digest(dt.date(2026, 9, 3)) is True
    body = channels[5000].sent[0].embed.description
    assert 'GrrCON' in body and 'Elsewhere' not in body


async def test_dry_run_counts_missing_roles_so_the_rollout_can_watch_them(cog, monkeypatch):
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'dry_run': True})
    wire(cog, guild=make_guild(('Cybersecurity Events',)))                   # no Michigan role

    class FakeCounter:
        def __init__(self):
            self.counted = []
            self._label = None

        def labels(self, **kwargs):
            self._label = kwargs
            return self

        def inc(self):
            self.counted.append(self._label)
    counter = FakeCounter()
    monkeypatch.setitem(cog.notify.__func__.__globals__, 'EVENTS_ROLE_MISSING', counter)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    assert await cog.notify(await cog.store.get(eid), '30') is True
    assert counter.counted == [{'role': 'Michigan'}]


# -- phase 1.1: guild-only ------------------------------------------------------

def test_events_group_is_guild_only():
    # Every /events command reads or writes guild-scoped rows and calls
    # interaction.guild_id; in a DM that is None and the command would
    # quietly operate on a guild that does not exist.
    assert Events.events.guild_only is True


# -- phase 1.1: the disabled cog stays quiet ------------------------------------

DISABLED_CALLS = (
    ('events_list', (), {}),
    ('events_next', (), {}),
    ('events_search', ('grrcon',), {}),
    ('events_submit', ('GrrCON', 'cyber', '2026-09-24', 'Grand Rapids', 'US-MI'), {}),
    ('events_mine', (), {}),
    ('events_pending', (), {}),
    ('events_status', (), {}),
    ('events_approve', (), {'event_id': 1}),
    ('events_reject', (), {'event_id': 1, 'reason': 'no'}),
    ('events_edit', (), {'event_id': 1}),
    ('events_cancel', (), {'event_id': 1, 'reason': 'no'}),
)


@pytest.fixture
async def off_cog(tmp_data_dir, monkeypatch):
    """The cog as bot.py loads it with EVENTS_ENABLED unset: registered,
    no store, no loops. Registration is left alone on purpose; every other
    feature cog in cogs/ loads unconditionally and gates at runtime."""
    monkeypatch.delenv('EVENTS_ENABLED', raising=False)
    c = Events(types.SimpleNamespace(config=None))
    await c.cog_load()
    assert c.store is None
    return c


@pytest.mark.parametrize('name, args, kwargs', DISABLED_CALLS)
async def test_disabled_cog_refuses_every_command_ephemerally(off_cog, name, args, kwargs):
    i = interaction(mod=True)
    await getattr(off_cog, name).callback(off_cog, i, *args, **kwargs)
    assert [s.content for s in i.response.sent] == [DISABLED_TEXT]
    assert all(s.ephemeral for s in i.response.sent)


async def test_disabled_cog_refuses_a_review_button_ephemerally(off_cog):
    button = EventButton(1, 'approve')
    i = interaction(mod=True, client=types.SimpleNamespace(get_cog=lambda name: off_cog))
    await button.callback(i)
    assert i.response.sent[0].content == DISABLED_TEXT and i.response.sent[0].ephemeral


# -- phase 1.1: a venue move is a change worth announcing -----------------------

async def test_venue_only_edit_of_an_announced_event_posts_a_change_notice(cog):
    # The dedupe window used to be 'changed:<start_date>' alone, so moving
    # the venue without moving the date collided with the date change that
    # came before it and the notice was silently dropped.
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'start_date': '2026-09-25', 'end_date': '2026-09-26'})
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'city': 'Detroit'})                  # same date, new venue
    posts = channels[5000].sent
    assert len(posts) == 3                                 # reminder, date change, venue change
    assert posts[2].embed.title.startswith('Updated: GrrCON')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'region_code': 'US-OH', 'country_code': 'US'})
    assert len(channels[5000].sent) == 4                   # a region move is a change too


async def test_notes_or_url_only_edits_still_post_no_change_notice(cog):
    guild, channels = wire(cog)
    eid = await cog.store.insert(event(), actor_id=0, action='import')
    await cog.notify(await cog.store.get(eid), '30')
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'notes': 'parking is free'})
    i = interaction(user_id=7, mod=True)
    await cog.apply_edit(i, eid, {'url': 'https://grrcon.example'})
    assert len(channels[5000].sent) == 1                   # the reminder, nothing else


async def test_change_window_key_folds_case_and_whitespace(cog):
    # Re-typing the same city with different spacing is not a change, so
    # it must land on the window the first notice already claimed.
    a = cog._changed_window(event(start_date='2026-09-24', city='Grand Rapids', region_code='US-MI'))
    b = cog._changed_window(event(start_date='2026-09-24', city='  grand   rapids ', region_code='us-mi'))
    assert a == b == 'changed:2026-09-24:grand rapids|us-mi'
    assert cog._changed_window(event(start_date='2026-09-24', city='Detroit')) != a
    assert len(cog._changed_window(event(city='x' * 500))) <= 128


# -- phase 1.1: status checks the permissions that actually stop a post --------

async def test_status_reports_send_and_embed_permissions(cog):
    guild, channels = wire(cog)
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    text = i.response.sent[-1].content
    assert 'posting: allowed' in text and 'review posting: allowed' in text


async def test_status_names_the_missing_posting_permissions(cog):
    # mention_everyone alone was checked, so a bot that could not speak in
    # the events channel at all still reported a clean bill of health.
    guild, channels = wire(cog, channels={
        5000: FakeChannel(5000, perms=discord.Permissions(mention_everyone=True)),
        6000: FakeChannel(6000, perms=discord.Permissions(send_messages=True)),
    })
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    text = i.response.sent[-1].content
    assert 'posting: BLOCKED, grant Send Messages and Embed Links in the events channel' in text
    assert 'review posting: BLOCKED, grant Embed Links in the review channel' in text


async def test_status_says_nothing_about_a_review_channel_it_does_not_have(cog):
    guild, channels = wire(cog)
    cog.cfg = cog.cfg.__class__(**{**cog.cfg.__dict__, 'review_channel_id': None})
    i = interaction(user_id=7, mod=True, guild=guild)
    await cog.events_status.callback(cog, i)
    assert 'review posting' not in i.response.sent[-1].content
