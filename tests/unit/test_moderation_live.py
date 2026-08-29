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
import os

import pytest

from ai.features.moderation import ModerationAnalyzer, benchmark_golden
from ai.providers import OllamaProvider

pytestmark = pytest.mark.network

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
    summary = await benchmark_golden(analyzer)

    print(f"\n=== Live golden set — model {MODEL} @ {OLLAMA_HOST} ===")
    print(f"overall accuracy:          {summary['accuracy']:.0%}  ({summary['total']} cases)")
    print(f"hate recall (all):         {summary['hate_recall']:.0%}")
    print(f"hate recall (model-only):  {summary['model_recall']:.0%}")
    print(f"clean false-positive rate: {summary['clean_fp_rate']:.0%}")
    print("\nMisses and false positives:")
    for r in summary['misses']:
        print(f"  MISSED HATE  {r['text'][:70]!r}  ({r['note']})")
    for r in summary['false_positives']:
        print(f"  FALSE POS    {r['category']:<14} conf={r['confidence']:.2f}  "
              f"{r['text'][:60]!r}  ({r['note']})")

    # Slur-bearing hate is deny-list-backed: must be 100% regardless of model.
    regex_tier = [r for r in summary['rows'] if r['label'] == 'hate' and r['regex_tier']]
    assert all(r['flagged'] for r in regex_tier), 'deny-list-backed hate missed'

    # Loose smoke bounds for the stochastic model — the table above is the
    # real deliverable; tighten these as the model/fine-tune improves.
    assert summary['model_recall'] >= 0.5, f"model-tier recall collapsed: {summary['model_recall']:.0%}"
    assert summary['clean_fp_rate'] <= 0.5, f"clean FP rate exploded: {summary['clean_fp_rate']:.0%}"
