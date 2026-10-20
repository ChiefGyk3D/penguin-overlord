# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measure how repetitive the Arch and NixOS roasts are.

Generates N roasts per distro through the bot's REAL ArchRoaster and AI
manager (rotation, ring buffer, duplicate guard and all), then reports per
distro: distinct-roast ratio, mean pairwise Jaccard, the top repeated
3-grams, angle and format usage, em dash and emoji-count violations, and
how many roasts needed a retry or failed. Code does every count; the model
only writes the roasts.

This calls the configured Ollama through the real manager, so it runs ONLY
when a human passes --live. Without it the script refuses and exits 2. The
manager reads AI_* / OLLAMA_* from the environment like the bot does.

Usage:
    python scripts/eval-roasts/eval_roasts.py --live --n 40 \
        --out /tmp/roast-report.json
    # try a drafted data file set without touching the install:
    python scripts/eval-roasts/eval_roasts.py --live --n 40 \
        --data-dir ./draft-roast-data --out /tmp/roast-report-draft.json

Compare two reports (before/after a data change) on distinct_ratio and
mean_pairwise_jaccard. See docs/features/ROAST_DATA.md.
"""

import argparse
import asyncio
import json
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

from ai.features import roast_text
from ai.features.arch_roaster import ArchRoaster, RoastSettings
from ai.features.roast_loader import load_roast_data

DISTROS = ('arch', 'nix')
TOP_NGRAMS = 10

# Neutral trigger messages (inputs, not jokes). Override with --messages.
DEFAULT_MESSAGES = {
    'arch': ['i use arch btw', 'just installed arch and the wifi works', 'pacman -Syu again today'],
    'nix': ['rewrote my flake.nix again', 'finally installed NixOS on the laptop', 'home-manager switch worked'],
}


@dataclass
class Record:
    distro: str
    text: Optional[str]
    angles: list = field(default_factory=list)
    format: str = ''
    attempts: int = 1
    reasons: list = field(default_factory=list)


# -- metrics -----------------------------------------------------------------

def _normal(text: str) -> str:
    return ' '.join(roast_text.token_list(text))


def _distro_metrics(records: list) -> dict:
    texts = [r.text for r in records if r.text]
    token_sets = [roast_text.tokens(t) for t in texts]
    pairs = list(combinations(token_sets, 2))
    mean_jaccard = (sum(roast_text.jaccard(a, b) for a, b in pairs) / len(pairs)) if pairs else 0.0

    distinct = len({_normal(t) for t in texts})
    grams = Counter()
    for t in texts:
        grams.update(set(roast_text.ngrams(roast_text.token_list(t), 3)))
    repeated = sorted(((g, c) for g, c in grams.items() if c >= 2), key=lambda gc: (-gc[1], gc[0]))

    emoji_counts = Counter(roast_text.count_emoji(t) for t in texts)
    return {
        'requested': len(records),
        'generated': len(texts),
        'failed': len(records) - len(texts),
        'retries': sum(max(r.attempts - 1, 0) for r in records),
        'rejections': dict(Counter(reason for r in records for reason in r.reasons)),
        'distinct': distinct,
        'distinct_ratio': (distinct / len(texts)) if texts else 0.0,
        'mean_pairwise_jaccard': mean_jaccard,
        'top_3grams': [[' '.join(g), c] for g, c in repeated[:TOP_NGRAMS]],
        'angle_usage': dict(Counter(a for r in records if r.text for a in r.angles)),
        'format_usage': dict(Counter(r.format for r in records if r.text)),
        'em_dash_violations': sum(roast_text.EM_DASH in t for t in texts),
        'emoji_violations': sum(roast_text.count_emoji(t) != 1 for t in texts),
        'emoji_histogram': {str(k): v for k, v in sorted(emoji_counts.items())},
    }


def compute_metrics(records: list) -> dict:
    """Per-distro metrics for a list of Record."""
    by_distro = {}
    for r in records:
        by_distro.setdefault(r.distro, []).append(r)
    return {distro: _distro_metrics(rs) for distro, rs in by_distro.items()}


# -- run loop ------------------------------------------------------------------

async def run_eval(generate, distros, n: int, messages: dict) -> list:
    """Call *generate(distro, message, username)* n times per distro, in order.

    Sequential on purpose: the roaster's rotation and ring state depend on call
    order, and the bot serialises generation through one queue anyway.
    """
    records = []
    for distro in distros:
        pool = messages[distro] if isinstance(messages, dict) else list(messages)
        for i in range(n):
            records.append(await generate(distro, pool[i % len(pool)], f'evaluser{i % 5}'))
    return records


def make_generator(manager, settings: RoastSettings, rng: random.Random, data_dir: Optional[str]):
    """An async generate(distro, message, username) -> Record over real ArchRoasters."""
    roasters = {}

    async def generate(distro, message, username):
        if distro not in roasters:
            roasters[distro] = ArchRoaster(
                manager, distro=distro, data=load_roast_data(distro, data_dir),
                settings=settings, rng=rng)
        result = await roasters[distro].generate(message, username)
        return Record(distro, result.text, result.angles, result.format,
                      result.attempts, result.reasons)

    return generate


def write_report(path, records: list, meta: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'meta': meta,
        'metrics': compute_metrics(records),
        'roasts': [asdict(r) for r in records],
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def print_summary(metrics: dict) -> None:
    for distro, m in metrics.items():
        print(f"{distro}: generated {m['generated']}/{m['requested']} (failed {m['failed']}, retries {m['retries']})")
        print(f"  distinct ratio        {m['distinct_ratio']:.3f}")
        print(f"  mean pairwise jaccard {m['mean_pairwise_jaccard']:.3f}")
        print(f"  em dash violations    {m['em_dash_violations']}")
        print(f"  emoji violations      {m['emoji_violations']}  histogram {m['emoji_histogram']}")
        print(f"  formats               {m['format_usage']}")
        for gram, count in m['top_3grams'][:5]:
            print(f"  repeated 3-gram x{count}: {gram}")


# -- CLI ---------------------------------------------------------------------------

def _messages(path: Optional[str]) -> dict:
    if not path:
        return DEFAULT_MESSAGES
    lines = [ln.strip() for ln in Path(path).read_text(encoding='utf-8').splitlines() if ln.strip()]
    if not lines:
        raise SystemExit(f'{path}: no messages')
    return {d: lines for d in DISTROS}


async def _live(args) -> list:
    from ai.manager import get_ai_manager
    from utils.config import load_section

    manager = await get_ai_manager(load_section('ai'))
    settings = RoastSettings.from_banter(load_section('banter'))
    generate = make_generator(manager, settings, random.Random(args.seed), args.data_dir)
    return await run_eval(generate, args.distros, args.n, _messages(args.messages))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--live', action='store_true',
                    help='REQUIRED to run: calls the real AI manager (Ollama) for every roast')
    ap.add_argument('--out', type=Path, required=True, help='path of the JSON report to write')
    ap.add_argument('--n', type=int, default=30, help='roasts per distro')
    ap.add_argument('--distros', nargs='+', choices=DISTROS, default=list(DISTROS))
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--data-dir', default=None, help='roast data override directory to evaluate')
    ap.add_argument('--messages', default=None, help='file of trigger messages, one per line')
    args = ap.parse_args(argv)

    if not args.live:
        print('refusing to run: this calls the real AI manager. Pass --live to confirm.', file=sys.stderr)
        return 2
    if args.n < 1:
        print('--n must be at least 1', file=sys.stderr)
        return 2

    records = asyncio.run(_live(args))
    meta = {'n': args.n, 'distros': args.distros, 'seed': args.seed,
            'data_dir_override': bool(args.data_dir)}
    write_report(args.out, records, meta)
    print_summary(compute_metrics(records))
    print(f'report written to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
