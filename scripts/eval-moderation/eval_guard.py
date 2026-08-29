# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Benchmark a moderation model against the Vicomtech hate-speech dataset.

Routes every sample through the bot's REAL ModerationAnalyzer (guard-bare
vs template-wrapped prompt shape, parser, deny-list merge), so the numbers
reflect what the AIModeration cog would actually decide.

Usage:
    git clone https://github.com/Vicomtech/hate-speech-dataset.git /tmp/hsd
    python scripts/eval-moderation/eval_guard.py \
        --dataset /tmp/hsd --host http://192.168.1.50:11434 \
        --model llama-guard3:8b --n 75

Baselines (stock llama-guard3:8b, n=75/class, seed 42):
    2026-08-28 contaminated wrapper prompt: recall 70.7%, FP rate 21.3%
    2026-08-29 guard-native bare prompt:    recall 58.7%, FP rate 10.7%
(the deny-list still catches slur-bearing hate at 100% regardless; the
recall gap is slur-free coded hate — the fine-tune's target)
See docs/features/MODERATION_FINETUNE_PLAN.md for the fine-tune this
benchmark gates.
"""

import argparse
import asyncio
import csv
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

import os  # noqa: E402

from ai.features.moderation import ModerationAnalyzer  # noqa: E402
from ai.providers import OllamaProvider  # noqa: E402


def load_samples(dataset: Path, n_per_class: int, seed: int):
    rows = list(csv.DictReader(open(dataset / 'annotations_metadata.csv')))
    by_label = {'hate': [], 'noHate': []}
    for r in rows:
        if r['label'] in by_label:
            path = dataset / 'all_files' / f"{r['file_id']}.txt"
            if path.exists():
                text = path.read_text(errors='replace').strip()
                if 15 <= len(text) <= 600:
                    by_label[r['label']].append(text)
    rng = random.Random(seed)
    return (rng.sample(by_label['hate'], n_per_class),
            rng.sample(by_label['noHate'], n_per_class))


async def classify(analyzer, sem, text):
    """Route through the REAL analyzer so prompt shape (guard-bare vs
    template-wrapped), parser, and deny-list merge all match the bot."""
    async with sem:
        try:
            return await analyzer.analyze(text, 'evaluser')
        except Exception as e:
            print('ERR', type(e).__name__, e, file=sys.stderr)
            return None


def stats(results):
    done = [r for r in results if r is not None]
    unsafe = [r for r in done if not r.is_safe]
    cats = {}
    for r in unsafe:
        cats[r.category] = cats.get(r.category, 0) + 1
    return len(done), len(unsafe), cats


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', type=Path, required=True,
                    help='path to a clone of Vicomtech/hate-speech-dataset')
    ap.add_argument('--host', default='http://localhost:11434')
    ap.add_argument('--model', default='llama-guard3:8b')
    ap.add_argument('--n', type=int, default=75, help='samples per class')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--concurrency', type=int, default=2)
    args = ap.parse_args()

    os.environ['AI_MODERATION_MODEL'] = args.model
    hate, no_hate = load_samples(args.dataset, args.n, args.seed)

    provider = OllamaProvider(args.host)

    class EvalManager:
        async def generate(self, feature, prompt, system_prompt=None,
                           raw=False, **kw):
            return await provider.generate(
                model=args.model, prompt=prompt, system_prompt=system_prompt,
                temperature=0.0, max_tokens=256, timeout=90,
            )

    analyzer = ModerationAnalyzer(EvalManager())
    sem = asyncio.Semaphore(args.concurrency)

    hate_results = await asyncio.gather(
        *(classify(analyzer, sem, t) for t in hate))
    nohate_results = await asyncio.gather(
        *(classify(analyzer, sem, t) for t in no_hate))

    h_done, h_unsafe, h_cats = stats(hate_results)
    n_done, n_unsafe, n_cats = stats(nohate_results)

    print(f"model={args.model} n={args.n}/class seed={args.seed}")
    print(f"HATE   : {h_unsafe}/{h_done} flagged unsafe "
          f"(recall {h_unsafe / max(h_done, 1):.1%})  categories={h_cats}")
    print(f"NOHATE : {n_unsafe}/{n_done} flagged unsafe "
          f"(false-positive rate {n_unsafe / max(n_done, 1):.1%})  categories={n_cats}")


if __name__ == '__main__':
    asyncio.run(main())
