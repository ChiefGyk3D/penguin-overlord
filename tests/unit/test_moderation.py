# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the moderation analyzer, policy layer, and database."""

import pytest

from ai.features.moderation import (
    FORCED_REVIEW_CATEGORIES,
    ModerationAnalyzer,
    ModerationResult,
    decide,
    parse_moderation_response,
    pre_scan_pii,
)
from utils.database import ModerationDatabase


# -- response parsing -------------------------------------------------------

GOOD_RESPONSE = """SAFE: false
CATEGORY: harassment
CONFIDENCE: 0.82
REASON: sustained hostility toward a user
ACTION: delete
PII: none"""


def test_parse_good_response():
    r = parse_moderation_response(GOOD_RESPONSE)
    assert not r.is_safe
    assert r.category == 'harassment'
    assert r.confidence == pytest.approx(0.82)
    assert r.suggested_action == 'delete'
    assert r.pii_detected == []


def test_parse_safe_response():
    r = parse_moderation_response("SAFE: true\nCATEGORY: safe\nCONFIDENCE: 0.99\nREASON: fine\nACTION: none\nPII: none")
    assert r.is_safe


def test_parse_garbage_forces_review():
    r = parse_moderation_response("lol I am a model and I refuse the format")
    assert not r.is_safe
    assert r.category == 'unknown'
    assert r.suggested_action == 'review'
    assert r.confidence == 0.0


def test_parse_empty_forces_review():
    r = parse_moderation_response("")
    assert r.suggested_action == 'review'


def test_parse_unknown_category_and_mute_mapping():
    r = parse_moderation_response("SAFE: false\nCATEGORY: novel_badness\nCONFIDENCE: 0.7\nREASON: x\nACTION: mute\nPII: none")
    assert r.category == 'unknown'
    assert r.suggested_action == 'timeout'


def test_parse_pii_list():
    r = parse_moderation_response("SAFE: false\nCATEGORY: pii_exposure\nCONFIDENCE: 0.9\nREASON: x\nACTION: review\nPII: email, phone")
    assert r.pii_detected == ['email', 'phone']


def test_parse_confidence_clamped():
    r = parse_moderation_response("SAFE: false\nCATEGORY: spam\nCONFIDENCE: 47\nREASON: x\nACTION: delete\nPII: none")
    assert r.confidence == 1.0


# -- PII pre-scan -----------------------------------------------------------

def test_pii_prescan():
    assert 'email' in pre_scan_pii("mail me at someone@example.com thanks")
    assert 'ssn' in pre_scan_pii("my ssn is 123-45-6789")
    assert pre_scan_pii("just a normal message about penguins") == []


# -- policy layer -----------------------------------------------------------

def _result(category='spam', confidence=0.9, action='delete', safe=False, denylist=False):
    return ModerationResult(safe, category, confidence, 'r', action, [], denylist)


def test_safe_means_no_alert():
    d = decide(_result(category='safe', safe=True, action='none'),
               dry_run=True, min_confidence=0.75, auto_delete=True, auto_timeout=True)
    assert not d.alert


@pytest.mark.parametrize('category', sorted(FORCED_REVIEW_CATEGORIES))
def test_forced_review_categories_never_auto(category):
    # Even with dry-run OFF and every auto flag ON at max confidence
    d = decide(_result(category=category, confidence=0.99, action='delete'),
               dry_run=False, min_confidence=0.5, auto_delete=True, auto_timeout=True)
    assert d.alert and d.requires_human and d.auto_action == 'none'


def test_denylist_hit_forces_human():
    d = decide(_result(category='spam', denylist=True),
               dry_run=False, min_confidence=0.5, auto_delete=True, auto_timeout=True)
    assert d.requires_human


@pytest.mark.parametrize('action', ['kick', 'ban'])
def test_kick_ban_always_human(action):
    d = decide(_result(action=action, confidence=0.99),
               dry_run=False, min_confidence=0.5, auto_delete=True, auto_timeout=True)
    assert d.requires_human and d.auto_action == 'none'


def test_dry_run_blocks_all_auto_actions():
    d = decide(_result(action='delete', confidence=0.99),
               dry_run=True, min_confidence=0.5, auto_delete=True, auto_timeout=True)
    assert d.alert and not d.requires_human and d.auto_action == 'none'


def test_auto_action_needs_flag_and_confidence():
    kwargs = dict(dry_run=False, min_confidence=0.75, auto_delete=False, auto_timeout=False)
    assert decide(_result(action='delete', confidence=0.9), **kwargs).auto_action == 'none'

    kwargs['auto_delete'] = True
    assert decide(_result(action='delete', confidence=0.9), **kwargs).auto_action == 'delete'
    assert decide(_result(action='delete', confidence=0.5), **kwargs).auto_action == 'none'


# -- analyzer fallback ------------------------------------------------------

class StubManager:
    def __init__(self, response):
        self._response = response

    async def generate(self, **kwargs):
        return self._response


async def test_analyzer_denylist_works_without_model():
    analyzer = ModerationAnalyzer(StubManager(None))
    result = await analyzer.analyze("you people are all k1kes", "someone")
    assert not result.is_safe
    assert result.category == 'hate_speech'
    assert result.denylist_hit


async def test_analyzer_model_unavailable_clean_message():
    analyzer = ModerationAnalyzer(StubManager(None))
    result = await analyzer.analyze("I love penguins", "someone")
    assert result.is_safe


async def test_analyzer_denylist_overrides_model_safe_verdict():
    analyzer = ModerationAnalyzer(StubManager(
        "SAFE: true\nCATEGORY: safe\nCONFIDENCE: 0.9\nREASON: fine\nACTION: none\nPII: none"))
    result = await analyzer.analyze("subtle slur: f4ggot", "someone")
    assert not result.is_safe
    assert result.category == 'hate_speech'
    assert result.confidence >= 0.95


# -- database ---------------------------------------------------------------

@pytest.fixture
async def db(tmp_path):
    database = ModerationDatabase(path=str(tmp_path / "mod.db"))
    await database.connect()
    yield database
    await database.close()


async def test_infraction_roundtrip(db):
    iid = await db.add_infraction(
        guild_id=1, channel_id=2, message_id=3, user_id=4, username='u',
        category='hate_speech', confidence=0.9, proposed_action='review',
        excerpt='x' * 500,
    )
    assert iid > 0
    count = await db.get_user_infraction_count(1, 4)
    assert count == 1
    history = await db.get_user_history(1, 4)
    assert history[0]['category'] == 'hate_speech'
    # excerpt is capped at 300 chars
    stats = await db.calibration_stats(1)
    assert stats['hate_speech']['total'] == 1


async def test_false_positive_label_reduces_count(db):
    iid = await db.add_infraction(
        guild_id=1, channel_id=2, message_id=3, user_id=4, username='u',
        category='spam', confidence=0.8, proposed_action='delete',
    )
    assert await db.get_user_infraction_count(1, 4) == 1
    await db.set_human_verdict(iid, 'false_positive', moderator_id=99)
    assert await db.get_user_infraction_count(1, 4) == 0


async def test_pending_action_single_decision(db):
    iid = await db.add_infraction(
        guild_id=1, channel_id=2, message_id=3, user_id=4, username='u',
        category='harassment', confidence=0.9, proposed_action='timeout',
    )
    pid = await db.add_pending_action(iid, 'timeout')
    await db.set_review_message(pid, 777)

    found = await db.find_infraction_by_alert(777)
    assert found and found['id'] == iid

    assert await db.resolve_pending_action(pid, 'approved', moderator_id=99) is True
    # Second moderator loses the race
    assert await db.resolve_pending_action(pid, 'denied', moderator_id=100) is False
    pending = await db.get_pending_action(pid)
    assert pending['status'] == 'approved' and pending['decided_by'] == 99


async def test_purge_user_and_retention(db):
    await db.add_infraction(
        guild_id=1, channel_id=2, message_id=3, user_id=4, username='u',
        category='spam', confidence=0.8, proposed_action='delete',
    )
    assert await db.purge_user(1, 4) == 1
    assert await db.get_user_infraction_count(1, 4) == 0
    assert await db.purge_older_than(30) == 0
