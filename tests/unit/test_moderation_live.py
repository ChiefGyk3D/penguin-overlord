# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Live-model golden-set benchmark (marked 'network' — never runs in CI).

Run on the bot host against the real Ollama moderation model:

    OLLAMA_HOST=http://192.168.1.50:11434 AI_MODERATION_MODEL=llama-guard3:8b \
        python -m pytest tests/unit/test_moderation_live.py -m network -s

Feeds the same golden corpus as the deterministic tier through the REAL
analyzer path (prompt shape, parser, deny-list merge) and reports recall
on the hate set and false positives on the clean set. Hard assertions are
deliberately loose smoke bounds — a stochastic model shouldn't produce a
flaky red — but the printed table is the real product: run it before and
after a model/prompt change and compare.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

from ai.features.moderation import ModerationAnalyzer
from ai.providers import OllamaProvider

pytestmark = pytest.mark.network

GOLDEN_PATH = Path(__file__).resolve().parents[1] / 'data' / 'moderation_golden.json'
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding='utf-8'))

OLLAMA_HOST = os.getenv('OLLAMA_HOST', '')
MODEL = (os.getenv('AI_MODERATION_MODEL')
         or os.getenv('AI_DEFAULT_MODEL')
         or 'llama-guard3:8b')

needs_ollama = pytest.mark.skipif(
    not OLLAMA_HOST, reason='set OLLAMA_HOST (and optionally AI_MODERATION_MODEL) to run'
)


class LiveOllamaManager:
    """Minimal AIManager stand-in: routes analyzer calls straight to Ollama."""

    def __init__(self):
        host = OLLAMA_HOST if '://' in OLLAMA_HOST else f'http://{OLLAMA_HOST}:11434'
        self._provider = OllamaProvider(host)
        self._lock = asyncio.Semaphore(2)

    async def generate(self, feature, prompt, system_prompt=None, raw=False, **kwargs):
        async with self._lock:
            return await self._provider.generate(
                model=MODEL, prompt=prompt, system_prompt=system_prompt,
                temperature=0.0, max_tokens=256, timeout=60,
            )


@needs_ollama
async def test_golden_set_against_live_model():
    analyzer = ModerationAnalyzer(LiveOllamaManager())

    rows = []
    for label, cases in (('hate', GOLDEN['hate']), ('clean', GOLDEN['clean'])):
        for case in cases:
            result = await analyzer.analyze(case['text'], 'goldenset')
            flagged = not result.is_safe
            rows.append({
                'label': label,
                'regex_tier': case.get('regex_must_catch', False),
                'flagged': flagged,
                'category': result.category,
                'confidence': result.confidence,
                'text': case['text'],
                'note': case['note'],
            })

    hate_rows = [r for r in rows if r['label'] == 'hate']
    model_tier = [r for r in hate_rows if not r['regex_tier']]
    clean_rows = [r for r in rows if r['label'] == 'clean']

    hate_recall = sum(r['flagged'] for r in hate_rows) / len(hate_rows)
    model_recall = (sum(r['flagged'] for r in model_tier) / len(model_tier)) if model_tier else 1.0
    clean_fp = sum(r['flagged'] for r in clean_rows) / len(clean_rows)

    print(f"\n=== Live golden set — model {MODEL} @ {OLLAMA_HOST} ===")
    print(f"hate recall (all):        {hate_recall:.0%}  ({len(hate_rows)} cases)")
    print(f"hate recall (model-only): {model_recall:.0%}  ({len(model_tier)} slur-free cases)")
    print(f"clean false-positive rate:{clean_fp:.0%}  ({len(clean_rows)} cases)")
    print("\nMisses and false positives:")
    for r in hate_rows:
        if not r['flagged']:
            print(f"  MISSED HATE  {r['text'][:70]!r}  ({r['note']})")
    for r in clean_rows:
        if r['flagged']:
            print(f"  FALSE POS    {r['category']:<14} conf={r['confidence']:.2f}  "
                  f"{r['text'][:60]!r}  ({r['note']})")

    # Slur-bearing hate is deny-list-backed: must be 100% regardless of model.
    regex_tier = [r for r in hate_rows if r['regex_tier']]
    assert all(r['flagged'] for r in regex_tier), 'deny-list-backed hate missed'

    # Loose smoke bounds for the stochastic model — the table above is the
    # real deliverable; tighten these as the model/fine-tune improves.
    assert model_recall >= 0.5, f'model-tier hate recall collapsed: {model_recall:.0%}'
    assert clean_fp <= 0.5, f'clean false-positive rate exploded: {clean_fp:.0%}'
