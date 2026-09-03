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
    await c.attach()
    c.today = lambda: __import__('datetime').date(2026, 9, 3)      # frozen clock
    yield c
    await c.store.db.close()
    database.reset_database()


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, *, embed=None, embeds=None, ephemeral=False,
                           allowed_mentions=None, view=None):
        self.sent.append(types.SimpleNamespace(content=content, embed=embed, embeds=embeds,
                                               ephemeral=ephemeral, allowed_mentions=allowed_mentions,
                                               view=view))

    async def defer(self, *, ephemeral=False, thinking=False):
        self.sent.append(types.SimpleNamespace(content=None, embed=None, deferred=True, ephemeral=ephemeral))


def interaction(user_id=42, *, roles=(), guild_id=GUILD, mod=False):
    guild = types.SimpleNamespace(id=guild_id, roles=[types.SimpleNamespace(name=n, id=i, mention=f'<@&{i}>')
                                                     for i, n in enumerate(roles, start=100)],
                                  me=types.SimpleNamespace(id=1), get_channel=lambda cid: None)
    user = types.SimpleNamespace(id=user_id, mention=f'<@{user_id}>', display_name=f'user{user_id}',
                                 guild_permissions=discord.Permissions(moderate_members=mod))
    return types.SimpleNamespace(guild=guild, guild_id=guild_id, user=user, response=FakeResponse(),
                                 followup=None, client=None, channel=None, message=None)


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
    sent = i.response.sent[0]
    assert sent.ephemeral and '#1' in sent.content and 'review' in sent.content.lower()
    row = await cog.store.get(1)
    assert row['status'] == 'pending' and row['submitted_by'] == 42 and row['provenance'] == 'member'
    assert row['region_code'] == 'US-OH' and row['country_code'] == 'US' and row['scope'] == 'regional'
    assert row['review_message_id'] == 777
    assert posted[0]['id'] == 1


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
    sent = i.response.sent[0]
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
    assert 'already have 3' in i.response.sent[0].content
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
