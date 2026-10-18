# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the random warehouse PA chime."""

from cogs.pa_announcer import PAAnnouncer
from tests.conftest import bot_with_config
from utils.pa_announcements import PA_ANNOUNCEMENTS

CHANNEL = 1016382144882409594


class _Channel:
    def __init__(self):
        self.sent = []

    async def send(self, text, **kw):
        self.sent.append((text, kw))


def make(**env):
    bot = bot_with_config(**env)
    bot.channel = _Channel()
    bot.get_channel = lambda cid: bot.channel if cid == CHANNEL else None
    return bot


def test_announcements_are_unique_and_use_no_em_dashes():
    assert len(PA_ANNOUNCEMENTS) == len(set(PA_ANNOUNCEMENTS))
    assert len(PA_ANNOUNCEMENTS) >= 200
    assert not any('—' in line for line in PA_ANNOUNCEMENTS)
    assert all(len(line) < 500 for line in PA_ANNOUNCEMENTS)


def test_off_by_default():
    assert PAAnnouncer(make()).enabled is False


def test_enabled_without_a_channel_stays_off():
    assert PAAnnouncer(make(PA_ENABLED='true')).enabled is False


def test_channel_falls_back_to_the_greeter_channel():
    cog = PAAnnouncer(make(PA_ENABLED='true',
                           WELCOME_GENERAL_CHANNEL_ID=str(CHANNEL)))
    assert cog.enabled and cog.channel_id == CHANNEL


def test_bag_plays_every_line_before_repeating():
    cog = PAAnnouncer(make())
    seen = [cog.next_announcement() for _ in PA_ANNOUNCEMENTS]
    assert sorted(seen) == sorted(PA_ANNOUNCEMENTS)
    assert cog.next_announcement() in PA_ANNOUNCEMENTS


def test_intervals_are_clamped_and_ordered():
    cog = PAAnnouncer(make(PA_MIN_INTERVAL_SECONDS='10',
                           PA_MAX_INTERVAL_SECONDS='5'))
    assert cog.min_interval == 60.0 and cog.max_interval == 60.0


def test_schedule_lands_inside_the_window():
    cog = PAAnnouncer(make(PA_MIN_INTERVAL_SECONDS='100',
                           PA_MAX_INTERVAL_SECONDS='200'))
    for _ in range(50):
        cog._schedule(1000.0)
        assert 1100.0 <= cog._next_at <= 1200.0


async def test_announce_posts_one_line_without_pings_and_reschedules():
    bot = make(PA_ENABLED='true', PA_CHANNEL_ID=str(CHANNEL))
    cog = PAAnnouncer(bot)
    await cog._announce(now=1000.0)
    (text, kw), = bot.channel.sent
    assert text.startswith('📢 *') and text.endswith('*')
    assert text[3:-1] in PA_ANNOUNCEMENTS
    assert kw['allowed_mentions'].users is False
    assert cog._next_at >= 1000.0 + cog.min_interval


async def test_missing_channel_is_not_fatal():
    bot = make(PA_ENABLED='true', PA_CHANNEL_ID='1234567890123456789')
    await PAAnnouncer(bot)._announce()
