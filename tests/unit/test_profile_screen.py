# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Profile screener: usernames and display names get the same look messages
do, and a flag holds the welcome and alerts the mod channel."""

import types

import pytest

from cogs import profile_screen as ps
from cogs.profile_screen import ProfileScreen

ALERTS = 555
OWNER_ID = 7


def _member(user_id=42, name='cooluser', global_name=None, nick=None,
            bot=False, guild=None):
    m = types.SimpleNamespace(
        id=user_id, name=name, global_name=global_name, nick=nick, bot=bot,
        display_name=nick or global_name or name, mention=f'<@{user_id}>',
        guild=guild or _guild(),
        created_at=None, joined_at=None,
        banned=[], kicked=[],
    )
    m.__str__ = lambda self: self.name

    async def ban(reason=None, **kw):
        m.banned.append(reason)

    async def kick(reason=None):
        m.kicked.append(reason)
    m.ban = ban
    m.kick = kick
    return m


def _guild():
    return types.SimpleNamespace(
        id=1, owner=types.SimpleNamespace(id=OWNER_ID, name='chiefgyk3d',
                                          display_name='ChiefGyk3D'))


class _Analyzer:
    """Stand-in second stage: answers what it is told to, records the ask."""

    def __init__(self, verdict='clean'):
        self.verdict = verdict
        self.calls = []

    async def adjudicate_custom(self, system_prompt, content, username, *,
                                allowed, kind='custom', context_messages=None,
                                note=None):
        self.calls.append((content, kind))
        return self.verdict


class _Channel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append((content, kw))
        return types.SimpleNamespace(id=900 + len(self.sent), edit=self._edit)

    async def _edit(self, **kw):
        pass


class _Greeter:
    def __init__(self):
        self.held = []
        self.released = []

    def hold(self, uid):
        self.held.append(uid)

    def release(self, uid):
        self.released.append(uid)


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setenv('PROFILE_SCREEN_ENABLED', 'true')
    monkeypatch.setenv('MOD_ALERT_CHANNEL_ID', str(ALERTS))
    monkeypatch.setenv('MOD_PING_ROLE_ID', '777')
    monkeypatch.delenv('PROFILE_SCREEN_PROTECTED_NAMES', raising=False)
    channel = _Channel()
    greeter = _Greeter()
    bot = types.SimpleNamespace(
        get_channel=lambda cid: channel if cid == ALERTS else None,
        get_cog=lambda name: greeter if name == 'WelcomeGreeter' else None,
    )
    c = ProfileScreen(bot)
    c.analyzer = _Analyzer()
    c.channel = channel
    c.greeter = greeter
    return c


# -- the pure term screen ----------------------------------------------------

def test_slur_in_username_is_flagged_by_denylist():
    v = ps.screen_terms(['n1gg4_king'])
    assert v is not None
    assert v.category == 'hate_speech' and v.source == 'denylist'


def test_hitler_display_name_is_flagged():
    v = ps.screen_terms(['me_killed_him_97629', 'Aydolf hitler'])
    assert v is not None and v.category == 'hate_speech'
    assert 'hitler' in v.reason


def test_staff_impersonation_is_flagged():
    v = ps.screen_terms(['Discord Moderator'])
    assert v is not None and v.category == 'impersonation'


def test_owner_impersonation_is_flagged():
    v = ps.screen_terms(['ChiefGyk3D_'], protected=('chiefgyk3d',))
    assert v is not None and v.category == 'impersonation'


def test_ordinary_names_pass_the_term_screen():
    for name in ('hidadiya', 'thesaltynewfie', 'admiral_ackbar', 'Nazim',
                 'Adolfo', 'kkkaty'):
        assert ps.screen_terms([name]) is None, name


# -- the model second look -----------------------------------------------------

async def test_clean_name_asks_the_model_and_stays_quiet(cog):
    verdict = await cog.screen(_member(name='cooluser'))
    assert verdict is None
    assert len(cog.analyzer.calls) == 1
    content, kind = cog.analyzer.calls[0]
    assert 'cooluser' in content and kind == 'profile'


async def test_model_verdict_hateful_flags(cog):
    cog.analyzer = _Analyzer('hateful')
    # A name the term screen cannot catch (no listed term), so the model
    # is the only stage that can flag it.
    verdict = await cog.screen(_member(name='gas_chamber_enjoyer'))
    assert verdict is not None
    assert verdict.category == 'hate_speech' and verdict.source == 'model'


async def test_model_uncertain_is_not_a_flag(cog):
    cog.analyzer = _Analyzer('uncertain')
    assert await cog.screen(_member(name='whatever')) is None


async def test_term_hit_skips_the_model(cog):
    verdict = await cog.screen(_member(name='Aydolf hitler'))
    assert verdict is not None and verdict.source == 'denylist'
    assert cog.analyzer.calls == []


async def test_all_names_are_screened(cog):
    m = _member(name='fine', global_name='also fine', nick='heil hitler')
    verdict = await cog.screen(m)
    assert verdict is not None and 'hitler' in verdict.reason


# -- the cog: alert + hold -----------------------------------------------------

async def test_join_with_a_flagged_name_alerts_and_holds(cog):
    m = _member(user_id=42, name='Aydolf hitler')
    await cog.on_member_join(m)

    assert cog.greeter.held == [42]
    assert len(cog.channel.sent) == 1
    content, kw = cog.channel.sent[0]
    assert content == '<@&777>'
    embed = kw['embed']
    assert 'Profile' in embed.title
    assert '<@42>' in embed.description and 'hitler' in embed.description
    labels = [item.label for item in kw['view'].children]
    assert labels == ['Ban', 'Kick', 'Dismiss']


async def test_clean_join_is_silent(cog):
    await cog.on_member_join(_member(name='cooluser'))
    assert cog.channel.sent == [] and cog.greeter.held == []


async def test_bots_are_ignored(cog):
    await cog.on_member_join(_member(name='hitler bot', bot=True))
    assert cog.channel.sent == []


async def test_nickname_change_is_rescreened(cog):
    before = _member(user_id=43, name='fine')
    after = _member(user_id=43, name='fine', nick='Aydolf hitler')
    await cog.on_member_update(before, after)
    assert len(cog.channel.sent) == 1 and cog.greeter.held == [43]


async def test_unrelated_member_update_is_not_rescreened(cog):
    cog.analyzer = _Analyzer('hateful')
    before = _member(user_id=44, name='fine')
    after = _member(user_id=44, name='fine')
    await cog.on_member_update(before, after)
    assert cog.channel.sent == [] and cog.analyzer.calls == []


async def test_same_member_is_not_alerted_twice_for_the_same_names(cog):
    m = _member(user_id=45, name='Aydolf hitler')
    await cog.on_member_join(m)
    await cog.on_member_update(m, m)
    await cog.on_member_join(m)
    assert len(cog.channel.sent) == 1


async def test_dismiss_releases_the_hold(cog):
    m = _member(user_id=46, name='Aydolf hitler')
    await cog.on_member_join(m)
    outcome = await cog.resolve(m.guild, 46, 'dismiss', moderator='mod')
    assert cog.greeter.released == [46]
    assert 'dismiss' in outcome


async def test_ban_bans_and_says_so(cog):
    m = _member(user_id=47, name='Aydolf hitler')
    m.guild.fetch_member = _fetcher(m)
    m.guild.get_member = lambda uid: m if uid == 47 else None
    await cog.on_member_join(m)
    outcome = await cog.resolve(m.guild, 47, 'ban', moderator='mod')
    assert m.banned and 'ban' in outcome


async def test_kick_after_they_already_left_is_reported(cog):
    m = _member(user_id=48, name='Aydolf hitler')
    m.guild.get_member = lambda uid: None
    m.guild.fetch_member = _fetcher(None)
    await cog.on_member_join(m)
    outcome = await cog.resolve(m.guild, 48, 'kick', moderator='mod')
    assert 'already' in outcome


def _fetcher(member):
    async def fetch_member(uid):
        if member is None:
            import discord
            raise discord.NotFound(
                types.SimpleNamespace(status=404, reason='nf'), 'Unknown')
        return member
    return fetch_member


# -- AutoMod sync (bios are only reachable through Discord's own rule) ------

def test_automod_keywords_cover_the_denylist_and_name_terms():
    words = ps.automod_keywords()
    assert 'hitler' in words and 'kike' in words
    assert len(words) <= 1000 and all(len(w) <= 60 for w in words)
    assert len(set(words)) == len(words)
