# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deterministic golden-set gate for the moderation pipeline (runs in CI).

The corpus in tests/data/moderation_golden.json holds labeled hate-speech
and known-clean messages. This tier checks the parts that must behave
identically on every run, no model involved:

- every slur-bearing hate example (regex_must_catch) is caught by the
  deny-list alone, and flows end-to-end (analyzer with the model DOWN)
  into a hate_speech alert with forced human review;
- NO clean example ever trips the deny-list or the PII pre-scan — the
  identity-affirmation lines ("I'm Jewish and bi ...") are the ones a
  naive filter gets wrong, and they are hard failures here.

The live-model tier for the same corpus is tests/unit/test_moderation_live.py
(marked 'network'; run it on the bot host against real Ollama).
"""

import json
from pathlib import Path

import pytest

from ai.features.moderation import ModerationAnalyzer, decide, pre_scan_pii
from ai.guardrails import find_blocked_terms

GOLDEN_PATH = Path(__file__).resolve().parents[1] / 'data' / 'moderation_golden.json'
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding='utf-8'))

HATE = GOLDEN['hate']
CLEAN = GOLDEN['clean']
REGEX_HATE = [case for case in HATE if case['regex_must_catch']]


def _case_id(case):
    return case['note'][:40].replace(' ', '-')


class ModelDownManager:
    async def generate(self, **kwargs):
        return None


@pytest.mark.parametrize('case', REGEX_HATE, ids=_case_id)
def test_denylist_catches_known_hate(case):
    assert find_blocked_terms(case['text'], extra_terms=()) != [], (
        f"deny-list missed known hate speech: {case['text']!r} ({case['note']})"
    )


@pytest.mark.parametrize('case', CLEAN, ids=_case_id)
def test_denylist_never_flags_clean(case):
    hits = find_blocked_terms(case['text'], extra_terms=())
    assert hits == [], (
        f"deny-list false positive on clean message: {case['text']!r} "
        f"hit {hits} ({case['note']})"
    )


@pytest.mark.parametrize('case', CLEAN, ids=_case_id)
def test_pii_never_flags_clean(case):
    pii = pre_scan_pii(case['text'])
    assert pii == [], (
        f"PII false positive on clean message: {case['text']!r} "
        f"hit {pii} ({case['note']})"
    )


@pytest.mark.parametrize('case', REGEX_HATE, ids=_case_id)
async def test_slur_hate_alerts_even_with_model_down(case):
    """End to end through the analyzer + policy with Ollama unavailable:
    slur-bearing hate must still produce a forced-human-review alert."""
    analyzer = ModerationAnalyzer(ModelDownManager())
    result = await analyzer.analyze(case['text'], 'someone')
    assert not result.is_safe
    assert result.category == 'hate_speech'
    decision = decide(result, dry_run=True, min_confidence=0.75,
                      auto_delete=False, auto_timeout=False)
    assert decision.alert and decision.requires_human


async def test_clean_messages_silent_with_model_down():
    analyzer = ModerationAnalyzer(ModelDownManager())
    for case in CLEAN:
        result = await analyzer.analyze(case['text'], 'someone')
        assert result.is_safe, (
            f"clean message alerted with model down: {case['text']!r} "
            f"-> {result.category} ({case['note']})"
        )


def test_corpus_shape():
    """Guard the corpus itself: labels present, no duplicates."""
    texts = [c['text'] for c in HATE] + [c['text'] for c in CLEAN]
    assert len(texts) == len(set(texts)), "duplicate texts in golden corpus"
    assert len(REGEX_HATE) >= 12, "slur-bearing tier shrank unexpectedly"
    assert len(HATE) - len(REGEX_HATE) >= 6, "model-tier hate examples shrank"
    assert len(CLEAN) >= 20, "clean tier shrank unexpectedly"
