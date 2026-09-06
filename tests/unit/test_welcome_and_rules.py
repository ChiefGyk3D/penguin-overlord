# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the two-stage welcome greeter and rules sync.

Stage 1 (join → #welcome-newbies, Micro Center) and stage 2 (verify → #general,
Costco) share the same batching engine, so the batching/limit/dedup tests run
against the verify stage and the join-specific tests confirm the second stage
fires on member-join into its own channel.
"""

import json
import types

import pytest

from cogs.welcome_greeter import WelcomeGreeter
from tests.conftest import bot_with_config

GENERAL = 1016382144882409594
NEWBIES = 1018571050860167198
WAGON = 1258442017847902294
RULES = 1018640640814366802
RESOURCES = 1275242331632566323
ROLES_CH = 1258855607281127424
ACCESS_ROLE = 1018571935640199219
# A path that does not exist: discord.File raises, the greeter warns and
# sends text only, and no test ever opens a real asset.
NO_IMAGE = '/nonexistent/welcome-image.png'


class _Message:
    """What a fake channel hands back from send(): remembers edits and
    deletes so retraction tests can see what happened to the greeting."""
    _next_id = 1000

    def __init__(self, text, kw, fail=None):
        _Message._next_id += 1
        self.id = _Message._next_id
        self.content = text
        self.kwargs = kw
        self.edits = []
        self.deleted = False
        self._fail = fail

    async def edit(self, **kw):
        if self._fail:
            raise self._fail
        self.content = kw.get('content', self.content)
        self.edits.append(kw)

    async def delete(self):
        if self._fail:
            raise self._fail
        self.deleted = True


class _Channel:
    def __init__(self, cid, sink, fail=None):
        self.id = cid
        self._sink = sink
        self.messages = []
        self._fail = fail

    async def send(self, text, **kw):
        self._sink.append((self.id, text, kw))
        msg = _Message(text, kw, fail=self._fail)
        self.messages.append(msg)
        return msg


@pytest.fixture
def greeter(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_VERIFY_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_JOIN_CHANNEL_ID', str(NEWBIES))
    monkeypatch.setenv('WELCOME_RULES_CHANNEL_ID', str(RULES))
    monkeypatch.setenv('WELCOME_RESOURCE_CHANNEL_ID', str(RESOURCES))
    monkeypatch.setenv('WELCOME_ROLES_CHANNEL_ID', str(ROLES_CH))
    monkeypatch.setenv('WELCOME_WAGON_CHANNEL_ID', str(WAGON))
    # No file IO in tests. An empty value is "unset" to the typed config,
    # which then falls back to the shipped image, so point somewhere absent.
    monkeypatch.setenv('WELCOME_JOIN_IMAGE', NO_IMAGE)
    monkeypatch.setenv('WELCOME_VERIFY_IMAGE', NO_IMAGE)
    # Batching-engine tests exercise the shared machinery without the join
    # stage's reminder delay; the reminder-specific tests set their own.
    monkeypatch.setenv('WELCOME_JOIN_REMIND_AFTER_SECONDS', '0')
    monkeypatch.delenv('WELCOME_JOIN_MESSAGE', raising=False)
    monkeypatch.delenv('WELCOME_VERIFY_MESSAGE', raising=False)

    sent = []
    channels = {GENERAL: _Channel(GENERAL, sent), NEWBIES: _Channel(NEWBIES, sent)}
    cog = WelcomeGreeter(bot=types.SimpleNamespace(
        get_channel=lambda cid: channels.get(cid)))
    cog.sent = sent
    return cog


def member(user_id=42, roles=(), bot=False, pending=False):
    m = types.SimpleNamespace(
        id=user_id, bot=bot, mention=f'<@{user_id}>', pending=pending,
        roles=[types.SimpleNamespace(id=r) for r in roles],
    )
    m.__str__ = lambda self: f'user{user_id}'
    return m


def queue(stage, *members, ready_at=0.0):
    """Put members straight into a stage's pending list, already ripe."""
    stage._pending.extend((m, ready_at) for m in members)


async def gains_role(cog, user_id=42):
    await cog.on_member_update(member(user_id, roles=()),
                               member(user_id, roles=(ACCESS_ROLE,)))


def _in(sent, channel_id):
    return [(t, kw) for (cid, t, kw) in sent if cid == channel_id]


# -- stage 2: verify -> #general (Costco), the shared batching engine --------

async def test_verified_arrivals_wait_for_the_tick_and_come_out_together(greeter):
    # 2 verify in a window -> one message naming two; next window 5 -> one
    # message naming five; a quiet window -> silence.
    await gains_role(greeter, 1)
    await gains_role(greeter, 2)
    assert greeter.sent == []            # nothing until the tick

    await greeter.verify._flush()
    out = _in(greeter.sent, GENERAL)
    assert len(out) == 1
    text, kwargs = out[0]
    assert '<@1>' in text and '<@2>' in text
    assert 'COSTCO' in text and f'<#{ROLES_CH}>' in text
    assert kwargs['allowed_mentions'].everyone is False

    for uid in range(10, 15):
        await gains_role(greeter, uid)
    await greeter.verify._flush()
    out = _in(greeter.sent, GENERAL)
    assert len(out) == 2
    text, _ = out[1]
    assert all(f'<@{uid}>' in text for uid in range(10, 15))

    await greeter.verify._flush()        # quiet window: silence
    assert len(_in(greeter.sent, GENERAL)) == 2


async def test_batch_always_fits_discord_message_limit(greeter):
    greeter.verify.max_mentions = 200    # deliberately misconfigured high
    # real Discord snowflakes are 18-19 digits — short test ids would let
    # 150 mentions fit and prove nothing
    queue(greeter.verify, *[member(10**18 + i) for i in range(150)])
    await greeter.verify._flush()
    text, _ = _in(greeter.sent, GENERAL)[0]
    assert len(text) <= 2000
    assert 'more new friends' in text


async def test_nobody_is_ever_greeted_twice(greeter):
    await gains_role(greeter)
    await gains_role(greeter)            # role churn / MEE6 hiccup
    await greeter.verify._flush()
    assert len(_in(greeter.sent, GENERAL)) == 1
    # and it survives a restart
    fresh = WelcomeGreeter(bot=greeter.bot)
    assert 42 in fresh.verify._welcomed


async def test_huge_batches_mention_a_few_and_count_the_rest(greeter):
    greeter.verify.max_mentions = 3
    members = [member(i) for i in range(100, 120)]
    queue(greeter.verify, *members)
    await greeter.verify._flush()
    text, kwargs = _in(greeter.sent, GENERAL)[0]
    assert '<@100>' in text and '<@102>' in text and '<@103>' not in text
    assert 'and 17 more new friends' in text
    assert len(kwargs['allowed_mentions'].users) == 3


async def test_unrelated_changes_and_bots_are_ignored(greeter):
    await greeter.on_member_update(member(roles=(1,)), member(roles=(1, 2)))
    robot_before = member(roles=(), bot=True)
    robot_after = member(roles=(ACCESS_ROLE,), bot=True)
    await greeter.on_member_update(robot_before, robot_after)
    assert greeter.sent == []


async def test_longtime_members_gaining_the_role_are_not_greeted(greeter):
    # "Don't want to annoy people already here": someone with two years of
    # tenure clicking the reaction role today is not a new arrival, and a
    # MEE6 bulk role re-sync is not a wave of newcomers.
    from datetime import datetime, timedelta, timezone
    veteran_before = member(77, roles=())
    veteran_after = member(77, roles=(ACCESS_ROLE,))
    for m in (veteran_before, veteran_after):
        m.joined_at = datetime.now(timezone.utc) - timedelta(days=700)
    await greeter.on_member_update(veteran_before, veteran_after)

    assert greeter.sent == []
    assert 77 in greeter.verify._welcomed   # and can never be pinged later


async def test_recent_joiners_still_get_the_welcome(greeter):
    from datetime import datetime, timedelta, timezone
    fresh_before = member(88, roles=())
    fresh_after = member(88, roles=(ACCESS_ROLE,))
    for m in (fresh_before, fresh_after):
        m.joined_at = datetime.now(timezone.utc) - timedelta(days=2)
    await greeter.on_member_update(fresh_before, fresh_after)
    await greeter.verify._flush()
    assert len(_in(greeter.sent, GENERAL)) == 1


async def test_unknown_join_date_is_treated_as_new(greeter):
    # joined_at can be None on uncached members; a missing date must not
    # silently disable the feature for them.
    await gains_role(greeter, 99)       # helper members carry no joined_at
    await greeter.verify._flush()
    assert len(_in(greeter.sent, GENERAL)) == 1


def test_custom_verify_template_and_fallback(greeter):
    greeter.verify.template = 'yo {users}, tags in {roles}'
    assert greeter.verify.render([member()]) == f'yo <@42>, tags in <#{ROLES_CH}>'
    greeter.verify.template = 'broken {nope}'
    # falls back to the Costco default, which references {roles}
    assert f'<#{ROLES_CH}>' in greeter.verify.render([member()])


# -- stage 1: join -> #welcome-newbies (Micro Center) ------------------------

async def test_join_greets_into_the_newbies_channel(greeter):
    await greeter.on_member_join(member(5))
    await greeter.on_member_join(member(6))
    assert greeter.sent == []            # batched until the tick

    await greeter.join._flush()
    out = _in(greeter.sent, NEWBIES)
    assert len(out) == 1
    text, kwargs = out[0]
    assert '<@5>' in text and '<@6>' in text
    assert 'MICRO CENTER' in text and 'Happy Hacking' in text
    # verify steps must be unmissable: wagon + roles + rules + general refs
    assert f'<#{WAGON}>' in text and f'<#{ROLES_CH}>' in text
    assert f'<#{RULES}>' in text and f'<#{GENERAL}>' in text
    assert kwargs['allowed_mentions'].everyone is False


async def test_join_and_verify_use_separate_dedup(greeter):
    # A member greeted at join must still get the verify greeting later.
    await greeter.on_member_join(member(7))
    await greeter.join._flush()
    assert len(_in(greeter.sent, NEWBIES)) == 1

    await gains_role(greeter, 7)
    await greeter.verify._flush()
    assert len(_in(greeter.sent, GENERAL)) == 1


async def test_join_ignores_bots_and_never_double_greets(greeter):
    await greeter.on_member_join(member(8, bot=True))
    await greeter.on_member_join(member(9))
    await greeter.on_member_join(member(9))      # duplicate join event
    await greeter.join._flush()
    out = _in(greeter.sent, NEWBIES)
    assert len(out) == 1
    text, _ = out[0]
    assert '<@9>' in text and '<@8>' not in text
    fresh = WelcomeGreeter(bot=greeter.bot)
    assert 9 in fresh.join._welcomed and 8 not in fresh.join._welcomed


async def test_greetings_fire_on_aligned_windows(greeter):
    # Join reminders run 900s windows (the quarter hour); verify intros run
    # 10800s windows (one GROUP welcome every three hours). A member queued
    # mid-window goes out at the boundary, not seconds after arriving.
    assert greeter.join.cooldown == 900
    assert greeter.verify.cooldown == 10800
    for stage in (greeter.join, greeter.verify):
        window = int(stage.cooldown)
        boundary = 1_800_000_000 - (1_800_000_000 % window)
        stage._pending = [(member(1), boundary + 60)]
        stage._last_period = int((boundary + 60) // window)     # queued early
        assert stage.due(boundary + 120) is False               # same window
        assert stage.due(boundary + window - 1) is False        # still waiting
        assert stage.due(boundary + window + 1) is True         # boundary crossed


async def test_flush_pins_the_stage_to_the_current_window(greeter):
    # After a flush, nothing more goes out until the NEXT quarter hour even
    # if new members arrive immediately.
    queue(greeter.verify, member(3))
    await greeter.verify._flush()
    import time as _time
    now = _time.time()
    queue(greeter.verify, member(4), ready_at=_time.time())
    assert greeter.verify.due(now) is False              # same window as the flush
    assert greeter.verify.due(now + greeter.verify.cooldown) is True  # next window


def _not_found():
    import discord
    return discord.NotFound(types.SimpleNamespace(status=404, reason='Not Found'),
                            'Unknown Member')


def _guild(present_ids, api_error=False):
    """Fake guild: empty cache, so presence is decided by fetch_member —
    the API either confirms, 404s, or (api_error) fails inconclusively."""
    async def fetch_member(uid):
        if api_error:
            import discord
            raise discord.HTTPException(
                types.SimpleNamespace(status=500, reason='oops'), 'boom')
        if uid in present_ids:
            return member(uid)
        raise _not_found()
    return types.SimpleNamespace(get_member=lambda uid: None,
                                 fetch_member=fetch_member)


async def test_departed_members_are_not_greeted(greeter):
    # Drive-by joins: someone who joined and LEFT before the window boundary
    # renders as @unknown-user — drop them from the greeting instead. The
    # cache misses both; the API confirms one and 404s the other.
    here = member(31)
    gone = member(32)
    guild = _guild(present_ids={31})
    here.guild = guild
    gone.guild = guild
    queue(greeter.join, here, gone)
    await greeter.join._flush()
    out = _in(greeter.sent, NEWBIES)
    assert len(out) == 1
    text, _ = out[0]
    assert '<@31>' in text and '<@32>' not in text


async def test_all_departed_means_silence(greeter):
    gone = member(33)
    gone.guild = _guild(present_ids=set())
    queue(greeter.join, gone)
    await greeter.join._flush()
    assert greeter.sent == []
    # and the ghost stays marked so a rejoin isn't double-greeted... they
    # were claimed at join time; the flush must not resurrect the pending.
    assert greeter.join._pending == []


# -- retraction: a greeted member who then leaves (or is banned) is edited
#    out of the greeting so no client ever renders @unknown-user, and a
#    banned troll's name does not linger in a warm welcome -----------------

def _newbies_channel(greeter):
    return greeter.bot.get_channel(NEWBIES)


async def test_leaver_is_edited_out_of_a_recent_greeting(greeter):
    queue(greeter.join, member(31), member(32))
    await greeter.join._flush()
    posted = _newbies_channel(greeter).messages[0]
    assert '<@32>' in posted.content

    await greeter.on_member_remove(member(32))

    assert posted.deleted is False
    assert '<@31>' in posted.content and '<@32>' not in posted.content
    users = posted.edits[-1]['allowed_mentions'].users
    assert [u.id for u in users] == [31]


async def test_sole_leaver_deletes_the_greeting(greeter):
    queue(greeter.join, member(33))
    await greeter.join._flush()
    posted = _newbies_channel(greeter).messages[0]

    await greeter.on_member_remove(member(33))

    assert posted.deleted is True


async def test_leaver_is_retracted_from_both_stages(greeter):
    queue(greeter.join, member(34))
    await greeter.join._flush()
    queue(greeter.verify, member(34), member(35))
    await greeter.verify._flush()

    await greeter.on_member_remove(member(34))

    assert _newbies_channel(greeter).messages[0].deleted is True
    costco = greeter.bot.get_channel(GENERAL).messages[0]
    assert '<@34>' not in costco.content and '<@35>' in costco.content


async def test_old_greetings_are_left_alone(greeter):
    import time as _time
    queue(greeter.join, member(36))
    await greeter.join._flush()
    posted = _newbies_channel(greeter).messages[0]

    # Someone who leaves days after being welcomed is history, not a ghost.
    later = _time.time() + greeter.join.retract_window + 1
    await greeter.join.retract(36, now=later)

    assert posted.deleted is False and posted.edits == []


async def test_leaver_who_was_never_greeted_is_a_no_op(greeter):
    queue(greeter.join, member(37))
    await greeter.join._flush()
    await greeter.on_member_remove(member(99))
    posted = _newbies_channel(greeter).messages[0]
    assert posted.deleted is False and posted.edits == []


# -- hold: the profile screener can park a member (a flagged display name)
#    so no stage greets them until a moderator dismisses the flag ----------

async def test_held_member_is_not_greeted_until_released(greeter):
    queue(greeter.join, member(51), member(52))
    greeter.hold(52)
    await greeter.join._flush()
    text, _ = _in(greeter.sent, NEWBIES)[0]
    assert '<@51>' in text and '<@52>' not in text

    greeter.release(52)
    await greeter.join._flush()
    text, _ = _in(greeter.sent, NEWBIES)[1]
    assert '<@52>' in text


async def test_hold_applies_to_both_stages(greeter):
    greeter.hold(53)
    queue(greeter.join, member(53))
    queue(greeter.verify, member(53))
    await greeter.join._flush()
    await greeter.verify._flush()
    assert greeter.sent == []


async def test_held_member_who_leaves_is_forgotten(greeter):
    # Banned while on hold: nothing to greet, nothing left waiting.
    greeter.hold(54)
    queue(greeter.join, member(54))
    await greeter.on_member_remove(member(54))
    assert greeter.join._pending == []
    assert 54 not in greeter.join.held


async def test_retraction_api_failure_is_harmless(monkeypatch, tmp_path):
    import discord
    boom = discord.HTTPException(
        types.SimpleNamespace(status=500, reason='oops'), 'boom')
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_VERIFY_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_JOIN_CHANNEL_ID', str(NEWBIES))
    monkeypatch.setenv('WELCOME_JOIN_IMAGE', NO_IMAGE)
    monkeypatch.setenv('WELCOME_VERIFY_IMAGE', NO_IMAGE)
    monkeypatch.setenv('WELCOME_JOIN_REMIND_AFTER_SECONDS', '0')
    sent = []
    channels = {NEWBIES: _Channel(NEWBIES, sent, fail=boom)}
    cog = WelcomeGreeter(bot=types.SimpleNamespace(
        get_channel=lambda cid: channels.get(cid)))
    queue(cog.join, member(38))
    await cog.join._flush()

    await cog.on_member_remove(member(38))      # must not raise


async def test_daily_costco_fires_at_nine_eastern(monkeypatch, tmp_path):
    # One group welcome per day at 09:00 America/New_York: everyone who
    # verified in the previous 24 hours goes out together, DST handled.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_VERIFY_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_JOIN_CHANNEL_ID', str(NEWBIES))
    monkeypatch.setenv('WELCOME_VERIFY_IMAGE', NO_IMAGE)
    monkeypatch.setenv('WELCOME_VERIFY_DAILY_AT', '09:00')
    monkeypatch.setenv('WELCOME_TIMEZONE', 'America/New_York')
    sent = []
    channels = {GENERAL: _Channel(GENERAL, sent)}
    cog = WelcomeGreeter(bot=types.SimpleNamespace(
        get_channel=lambda cid: channels.get(cid)))
    stage = cog.verify
    assert stage.daily_at == (9, 0)

    ny = ZoneInfo('America/New_York')
    def at(h, mi, day=2):
        return datetime(2026, 9, day, h, mi, tzinfo=ny).timestamp()

    # Verified 3PM yesterday and 8AM today: both waiting at 8:59...
    stage._pending = [(member(51), at(15, 0, day=1)), (member(52), at(8, 0))]
    stage._last_period = stage._period(at(8, 59))
    assert stage.due(at(8, 59)) is False
    # ...and both flushed together just after 9AM Eastern.
    assert stage.due(at(9, 1)) is True
    await stage._flush(now=at(9, 1))
    assert len(sent) == 1
    text = sent[0][1]
    assert '<@51>' in text and '<@52>' in text

    # Verified at 9:05? Waits for TOMORROW's 9AM, not a minute sooner.
    stage._pending = [(member(53), at(9, 5))]
    assert stage.due(at(23, 59)) is False
    assert stage.due(at(9, 1, day=3)) is True


def test_bad_daily_at_falls_back_to_interval_windows(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_VERIFY_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_JOIN_CHANNEL_ID', str(NEWBIES))
    monkeypatch.setenv('WELCOME_VERIFY_DAILY_AT', 'nine-ish')
    monkeypatch.setenv('WELCOME_TIMEZONE', 'Mars/Olympus_Mons')
    cog = WelcomeGreeter(bot=types.SimpleNamespace())
    assert cog.verify.daily_at is None            # malformed time ignored
    assert str(cog.verify.tz) == 'UTC'            # unknown tz falls back
    assert cog.verify.cooldown == 10800           # interval mode still works


async def test_join_reminder_waits_its_few_minutes(monkeypatch, tmp_path):
    # MEE6 posts the instant hello; the Micro Center penguin is a REMINDER.
    # A fresh joiner must not be flushed before REMIND_AFTER has elapsed.
    import time as _time
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_VERIFY_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_JOIN_CHANNEL_ID', str(NEWBIES))
    monkeypatch.setenv('WELCOME_JOIN_IMAGE', NO_IMAGE)
    monkeypatch.setenv('WELCOME_JOIN_REMIND_AFTER_SECONDS', '300')
    sent = []
    channels = {NEWBIES: _Channel(NEWBIES, sent)}
    cog = WelcomeGreeter(bot=types.SimpleNamespace(
        get_channel=lambda cid: channels.get(cid)))

    await cog.on_member_join(member(41))
    now = _time.time()
    await cog.join._flush(now=now)               # too early — not ripe
    assert sent == []
    assert len(cog.join._pending) == 1           # still queued, not lost

    await cog.join._flush(now=now + 301)         # wait elapsed
    assert len(sent) == 1
    assert '<@41>' in sent[0][1]


async def test_members_who_verified_get_no_reminder(greeter):
    # The whole point: verify before the reminder lands and the Micro
    # Center penguin never mentions you.
    slow = member(43)
    quick = member(44)
    fresh_quick = member(44, roles=(ACCESS_ROLE,))     # verified meanwhile
    lookup = {43: member(43), 44: fresh_quick}
    guild = types.SimpleNamespace(get_member=lambda uid: lookup.get(uid))
    slow.guild = guild
    quick.guild = guild
    queue(greeter.join, slow, quick)
    await greeter.join._flush()
    out = _in(greeter.sent, NEWBIES)
    assert len(out) == 1
    text, _ = out[0]
    assert '<@43>' in text and '<@44>' not in text


async def test_everyone_verified_means_no_reminder_at_all(greeter):
    quick = member(45)
    quick.guild = types.SimpleNamespace(
        get_member=lambda uid: member(45, roles=(ACCESS_ROLE,)))
    queue(greeter.join, quick)
    await greeter.join._flush()
    assert greeter.sent == []


async def test_cache_miss_with_api_trouble_still_greets(greeter):
    # A stale cache plus a flaky API must never cost a real member their
    # welcome — inconclusive means greet.
    maybe = member(35)
    maybe.guild = _guild(present_ids=set(), api_error=True)
    queue(greeter.join, maybe)
    await greeter.join._flush()
    out = _in(greeter.sent, NEWBIES)
    assert len(out) == 1 and '<@35>' in out[0][0]


async def test_fresh_batch_waits_for_the_next_boundary(greeter):
    # Live bug: after a quiet window, _last_period was stale and the first
    # arrival of a new window flushed at the very next 60s tick (17:31:51,
    # 18:06:47 in the logs) instead of on the quarter hour. A batch must
    # wait for the first boundary AFTER it started queueing.
    import time as _time
    greeter.join.claim(member(34))            # queued NOW, mid-window
    now = _time.time()
    assert greeter.join.due(now) is False     # same window as the queue
    next_boundary = (int(now // 900) + 1) * 900
    assert greeter.join.due(next_boundary + 1) is True


async def test_boot_does_not_flush_mid_window(monkeypatch, tmp_path):
    # A fresh boot must wait for the next clock boundary, not greet whoever
    # queues within seconds of startup.
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.setenv('WELCOME_ROLE_ID', str(ACCESS_ROLE))
    monkeypatch.setenv('WELCOME_VERIFY_CHANNEL_ID', str(GENERAL))
    monkeypatch.setenv('WELCOME_JOIN_CHANNEL_ID', str(NEWBIES))
    cog = WelcomeGreeter(bot=types.SimpleNamespace())
    import time as _time
    now = _time.time()
    cog.join._pending = [(member(5), _time.time())]
    assert cog.join.due(now) is False                    # booted this window
    next_boundary = (int(now // 900) + 1) * 900
    assert cog.join.due(next_boundary + 1) is True


async def test_disabled_without_channels(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'true')
    monkeypatch.delenv('WELCOME_ROLE_ID', raising=False)
    monkeypatch.delenv('WELCOME_CHANNEL_ID', raising=False)
    monkeypatch.delenv('WELCOME_VERIFY_CHANNEL_ID', raising=False)
    monkeypatch.delenv('WELCOME_JOIN_CHANNEL_ID', raising=False)
    cog = WelcomeGreeter(bot=types.SimpleNamespace())
    assert cog.enabled is False


def test_greeter_settings_come_from_the_bots_typed_config(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('WELCOME_ENABLED', 'false')          # env says off
    monkeypatch.setenv('WELCOME_MAX_MENTIONS', '3')
    bot = bot_with_config(
        DATA_DIR=str(tmp_path), WELCOME_ENABLED='true',
        WELCOME_MAX_MENTIONS='9', WELCOME_ROLE_ID=str(ACCESS_ROLE),
        WELCOME_VERIFY_CHANNEL_ID=str(GENERAL), WELCOME_JOIN_CHANNEL_ID=str(NEWBIES),
        WELCOME_TIMEZONE='Europe/Berlin', WELCOME_VERIFY_COOLDOWN_SECONDS='11',
    )
    bot.get_channel = lambda cid: None
    cog = WelcomeGreeter(bot=bot)
    assert cog.enabled is True
    assert cog.verify.max_mentions == 9 and cog.join.max_mentions == 9
    assert cog.role_id == ACCESS_ROLE
    assert cog.verify.channel_id == GENERAL
    assert cog.join.channel_id == NEWBIES
    assert str(cog.verify.tz) == 'Europe/Berlin'
    assert cog.verify.cooldown == 11.0


# -- rules sync --------------------------------------------------------------

def test_rules_sync_settings_come_from_the_bots_typed_config(monkeypatch):
    from cogs.rules_sync import RulesSync
    monkeypatch.setenv('MOD_RULES_CHANNEL_ID', '999999999999999999')
    bot = bot_with_config(MOD_RULES_CHANNEL_ID=str(RULES),
                          MOD_RULES_SYNC_HOURS='6',
                          MOD_ALERT_CHANNEL_ID=str(GENERAL))
    cog = RulesSync(bot=bot)
    assert cog.rules_channel_id == RULES
    assert cog.sync_hours == 6.0
    assert cog.alert_channel_id == GENERAL


def test_rules_sync_without_a_channel_stays_idle():
    from cogs.rules_sync import RulesSync
    cog = RulesSync(bot=bot_with_config())
    assert cog.rules_channel_id is None and cog.alert_channel_id is None


# -- rules cache -> moderation prompt ----------------------------------------

def test_cached_rules_reach_the_moderation_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    (tmp_path / 'server_rules.json').write_text(json.dumps({
        'text': 'Rule 1: Be excellent to each other.\nRule 2: No doxxing.',
        'channel_id': RULES, 'synced_at': 'x',
    }))
    import ai.features.moderation as mod
    monkeypatch.setattr(mod, '_RULES_CACHE', None)
    prompt = mod.moderation_system_prompt()
    assert "THIS SERVER'S OWN RULES" in prompt
    assert 'Be excellent to each other' in prompt
    # rules come before the generic instructions
    assert prompt.index('OWN RULES') < prompt.index('content moderation assistant')


def test_missing_rules_cache_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    import ai.features.moderation as mod
    monkeypatch.setattr(mod, '_RULES_CACHE', None)
    assert "OWN RULES" not in mod.moderation_system_prompt()


# -- Discord membership screening: on_member_join fires the instant someone
#    clicks Join, while they are still on the rules screen and can see no
#    channel. MEE6 greets when they click through (pending True -> False).
#    Anchor the reminder there too, or a slow reader gets our reminder
#    BEFORE the hello (seen live: reminder 11:15:03Z, MEE6 11:15:47Z) -------

async def test_join_reminder_waits_for_the_screening_gate(greeter):
    gated = member(61, pending=True)
    await greeter.on_member_join(gated)
    assert greeter.join._pending == []            # not even queued yet

    await greeter.on_member_update(member(61, pending=True),
                                   member(61, pending=False))
    assert [m.id for m, _ in greeter.join._pending] == [61]

    # the flip is not a second join: no double claim
    await greeter.on_member_update(member(61, pending=True),
                                   member(61, pending=False))
    assert len(greeter.join._pending) == 1


async def test_servers_without_screening_queue_on_join(greeter):
    await greeter.on_member_join(member(62, pending=False))
    assert [m.id for m, _ in greeter.join._pending] == [62]


async def test_members_still_on_the_rules_screen_are_not_pinged(greeter):
    # Queued somehow but never clicked through by flush time: they cannot
    # read the channel, so a mention is noise for everyone else.
    stuck = member(63)
    lookup = {63: member(63, pending=True)}
    stuck.guild = types.SimpleNamespace(get_member=lambda uid: lookup.get(uid))
    queue(greeter.join, stuck)
    await greeter.join._flush()
    assert greeter.sent == []
