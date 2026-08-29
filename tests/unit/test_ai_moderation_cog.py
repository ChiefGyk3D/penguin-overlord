# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the AIModeration cog's scan flow and alert posting."""

import types

import pytest

from ai.features.moderation import ModerationResult
from cogs.ai_moderation import AIModeration

ALERT_CHANNEL = 1543050172425048194
WATCHED_CHANNEL = 1016382144882409594
PING_ROLE = 1018563764662046750


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setenv('MOD_ENABLED', 'true')
    monkeypatch.setenv('MOD_ALERT_CHANNEL_ID', str(ALERT_CHANNEL))
    monkeypatch.setenv('MOD_CHANNELS', str(WATCHED_CHANNEL))
    monkeypatch.delenv('MOD_PING_ROLE_ID', raising=False)
    return AIModeration(bot=types.SimpleNamespace())


def make_message(content='hello there friends'):
    author = types.SimpleNamespace(
        id=111, bot=False, display_name='someone', mention='<@111>',
        roles=[],
    )
    author.__str__ = lambda self: 'someone#0'
    channel = types.SimpleNamespace(
        id=WATCHED_CHANNEL, name='general', mention='<#chan>',
    )
    return types.SimpleNamespace(
        id=999, content=content, author=author, channel=channel,
        guild=types.SimpleNamespace(id=42), jump_url='https://x/1',
    )


class RecordingAnalyzer:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def analyze(self, content, username, **kw):
        self.calls.append(content)
        return self.result


class FakeDB:
    async def get_user_infraction_count(self, guild_id, user_id):
        return 0


# -- scan flow ---------------------------------------------------------------

async def test_safe_message_produces_no_alert(cog):
    cog.analyzer = RecordingAnalyzer(
        ModerationResult(True, 'safe', 0.9, 'guard model verdict: safe', 'none'))
    cog.db = FakeDB()
    detections = []

    async def record(*a):
        detections.append(a)
    cog._handle_detection = record

    await cog._scan_message(make_message('just a normal sentence here'), 'just a normal sentence here')
    assert cog.analyzer.calls, 'LLM should have been consulted'
    assert detections == []


async def test_unsafe_message_reaches_detection(cog):
    cog.analyzer = RecordingAnalyzer(
        ModerationResult(False, 'hate_speech', 0.85, 'guard model verdict: unsafe (S10)', 'review'))
    cog.db = FakeDB()
    detections = []

    async def record(message, content, result, decision):
        detections.append((result, decision))
    cog._handle_detection = record

    await cog._scan_message(make_message('some scanned message text'), 'some scanned message text')
    assert len(detections) == 1
    result, decision = detections[0]
    assert result.category == 'hate_speech'
    assert decision.alert and decision.requires_human


async def test_short_message_skips_llm_but_regex_pii_still_alerts(cog):
    cog.analyzer = RecordingAnalyzer(
        ModerationResult(True, 'safe', 0.9, 'x', 'none'))
    cog.db = FakeDB()
    detections = []

    async def record(message, content, result, decision):
        detections.append(result)
    cog._handle_detection = record

    # Below MOD_MIN_MESSAGE_LENGTH default (6) and no regex hit: nothing at all
    await cog._scan_message(make_message('ok'), 'ok')
    assert cog.analyzer.calls == [] and detections == []

    # Short but contains an SSN: regex forces the scan and the alert
    ssn = '1 123-45-6789'
    await cog._scan_message(make_message(ssn), ssn)
    assert len(detections) == 1
    assert detections[0].category == 'pii_exposure'
    assert 'ssn' in detections[0].pii_detected


async def test_user_cooldown_skips_llm(cog):
    cog.analyzer = RecordingAnalyzer(
        ModerationResult(True, 'safe', 0.9, 'x', 'none'))
    cog.db = FakeDB()

    async def record(*a):
        pass
    cog._handle_detection = record

    await cog._scan_message(make_message('first message goes to the model'),
                            'first message goes to the model')
    await cog._scan_message(make_message('second message within cooldown'),
                            'second message within cooldown')
    assert len(cog.analyzer.calls) == 1


# -- alert posting -----------------------------------------------------------

class FakeAlertChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, embed=None, view=None, allowed_mentions=None):
        self.sent.append({'content': content, 'embed': embed,
                          'allowed_mentions': allowed_mentions})
        return types.SimpleNamespace(id=555, add_reaction=self._noop)

    async def _noop(self, *_):
        return None


class FakeHistoryDB(FakeDB):
    async def get_user_history(self, guild_id, user_id, limit=4):
        return []


def make_decision():
    from ai.features.moderation import ModerationDecision
    return ModerationDecision(True, False, 'none', 'dry-run: alert only')


async def test_post_alert_pings_role_when_configured(cog):
    cog.ping_role_id = PING_ROLE
    cog.db = FakeHistoryDB()
    channel = FakeAlertChannel()
    cog.bot = types.SimpleNamespace(get_channel=lambda cid: channel)

    result = ModerationResult(False, 'pii_exposure', 0.9, 'regex detected: ssn', 'review', ['ssn'])
    await cog._post_alert(make_message(), 'text', result, make_decision(), 7, 'none')

    assert len(channel.sent) == 1
    sent = channel.sent[0]
    assert sent['content'] == f'<@&{PING_ROLE}>'
    assert sent['allowed_mentions'] is not None
    assert [r.id for r in sent['allowed_mentions'].roles] == [PING_ROLE]
    assert not sent['allowed_mentions'].everyone
    assert sent['embed'].title == '🚨 Pii Exposure'


async def test_post_alert_silent_without_ping_role(cog):
    assert cog.ping_role_id is None
    cog.db = FakeHistoryDB()
    channel = FakeAlertChannel()
    cog.bot = types.SimpleNamespace(get_channel=lambda cid: channel)

    result = ModerationResult(False, 'spam', 0.8, 'x', 'review')
    await cog._post_alert(make_message(), 'text', result, make_decision(), 8, 'none')

    assert channel.sent[0]['content'] is None
    assert channel.sent[0]['allowed_mentions'] is None
