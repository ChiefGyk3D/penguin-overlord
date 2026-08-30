#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Replay moderator-labeled alerts through the CURRENT decision pipeline.

`fp_report.py` replays historical excerpts through the regex layers only.
This replays them through everything the cog does — analyzer, dog-whistle
watchlist adjudication, reclaimed-language and address adjudication, and
`decide()` — so a labeled corpus answers the only question that matters
after a filter change: *would we still get this one wrong?*

Usage (needs network reach to the Ollama host):

    # on the bot host
    python scripts/eval-moderation/replay_labeled.py --db data/penguin_overlord.db \\
        --host http://192.168.214.10:11434

    # or from a workstation, against a dumped table
    python scripts/eval-moderation/replay_labeled.py --json infractions.json \\
        --host http://192.168.214.10:11434

Scoring is against the moderator's label:
    false_positive -> the pipeline should now return NO alert
    confirmed      -> the pipeline should still alert
Unlabeled rows are replayed too and reported separately, since a changed
verdict on an unlabeled row is where new regressions hide.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

from ai.features.moderation import (  # noqa: E402
    ModerationAnalyzer, ModerationResult, decide, pre_scan_pii,
)
from ai.guardrails import (  # noqa: E402
    find_blocked_terms, find_dogwhistles, find_injection_markers,
)
from ai.providers import OllamaProvider  # noqa: E402


def load_rows(args):
    if args.json:
        return json.loads(Path(args.json).read_text())
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(
        'SELECT id, username, category, confidence, excerpt, human_verdict '
        'FROM mod_infractions ORDER BY id')]


async def scan(analyzer, content, username, tier, args):
    """Mirror of AIModeration._scan_message, minus Discord plumbing.

    Kept deliberately in the same order as the cog so a divergence here is
    a bug in one of the two, not an artifact of the harness.
    """
    pii = pre_scan_pii(content)
    denylist_hits = find_blocked_terms(content)
    dogwhistle_hits = find_dogwhistles(content)
    injection_markers = find_injection_markers(content)

    def leniency_allowed(result):
        if injection_markers:
            return False
        return (result is None or result.denylist_hit
                or result.confidence < args.leniency_max_confidence)

    has_letters = any(ch.isalpha() for ch in content)
    run_llm = ((len(content) >= args.min_length and has_letters)
               or bool(pii) or bool(denylist_hits) or bool(dogwhistle_hits))

    result = None
    if run_llm:
        result = await analyzer.analyze(content, username)

    if dogwhistle_hits and not (result is not None and result.denylist_hit):
        verdict = await analyzer.adjudicate(
            'dogwhistle', content, username, note=', '.join(dogwhistle_hits))
        if verdict == 'hateful':
            result = ModerationResult(False, 'hate_speech', 0.9,
                                      'coded hate signal', 'review', pii)
        elif verdict == 'uncertain' and (result is None or result.is_safe):
            result = ModerationResult(False, 'evasion', 0.5,
                                      'possible coded signal', 'review', pii)
        elif (verdict in ('benign', 'mention') and result is not None
              and not result.is_safe
              and result.category in ('hate_speech', 'harassment')
              and leniency_allowed(result)):
            result = ModerationResult(True, 'safe', 0.8,
                                      f'watchlist context check: {verdict}',
                                      'none', pii)

    if result is None or result.is_safe:
        if pii:
            result = ModerationResult(False, 'pii_exposure', 0.9,
                                      f"regex detected: {', '.join(pii)}",
                                      'review', pii)
        else:
            return None, 'safe'
    elif pii and not result.pii_detected:
        result.pii_detected = pii

    model_hate = (not result.denylist_hit
                  and result.category in ('hate_speech', 'harassment'))
    if (result.denylist_hit or model_hate) and tier in args.reclaimed_tiers:
        verdict = await analyzer.adjudicate('reclaimed_slur', content, username)
        if verdict == 'banter' and leniency_allowed(result):
            return None, 'in-group banter'

    address_driven = ('address' in result.pii_detected
                      or (result.category == 'doxxing' and not result.denylist_hit))
    if address_driven:
        verdict = await analyzer.adjudicate('address', content, username)
        if verdict == 'public':
            result.pii_detected = [p for p in result.pii_detected if p != 'address']
            if result.category == 'doxxing':
                return None, 'public address'
            if not result.pii_detected and result.category in ('pii_exposure', 'safe'):
                return None, 'public address'

    decision = decide(result, dry_run=True, min_confidence=args.min_confidence,
                      auto_delete=False, auto_timeout=False,
                      alert_min_confidence=args.alert_min_confidence)
    if not decision.alert:
        return None, f'below alert threshold ({result.category})'
    return result, result.category


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', default='data/penguin_overlord.db')
    ap.add_argument('--json', help='dumped mod_infractions rows instead of a DB')
    ap.add_argument('--host', default='http://localhost:11434')
    ap.add_argument('--model', default=os.getenv('AI_MODERATION_MODEL', 'llama-guard3:8b'))
    ap.add_argument('--second-model', default=os.getenv('AI_MODERATION_SECOND_MODEL', 'gemma4:12b'))
    ap.add_argument('--tier', default='member', help='trust tier to replay as')
    ap.add_argument('--reclaimed-tiers', default='member,veteran,trusted,creator')
    ap.add_argument('--min-length', type=int, default=10)
    ap.add_argument('--min-confidence', type=float, default=0.7)
    ap.add_argument('--alert-min-confidence', type=float, default=0.5)
    ap.add_argument('--leniency-max-confidence', type=float, default=0.95,
                    help='above this, a context check may not clear a model verdict')
    ap.add_argument('--only', help='replay a single row id, or "labeled"')
    args = ap.parse_args()
    args.reclaimed_tiers = set(args.reclaimed_tiers.split(','))

    os.environ['AI_MODERATION_MODEL'] = args.model
    os.environ['AI_MODERATION_SECOND_MODEL'] = args.second_model
    provider = OllamaProvider(args.host)

    class EvalManager:
        async def generate(self, feature, prompt, system_prompt=None,
                           raw=False, model=None, **kw):
            return await provider.generate(
                model=model or args.model, prompt=prompt,
                system_prompt=system_prompt, temperature=0.0,
                max_tokens=256, timeout=120,
            )

    analyzer = ModerationAnalyzer(EvalManager())

    rows = load_rows(args)
    if args.only == 'labeled':
        rows = [r for r in rows if r['human_verdict']]
    elif args.only:
        rows = [r for r in rows if str(r['id']) == args.only]

    fixed = still_wrong = held = lost = 0
    changed_unlabeled = []
    for row in rows:
        content = row['excerpt'] or ''
        # Alerts store the model's rendered verdict above the message on
        # some older rows; the message itself is what a rescan would see.
        result, why = await scan(analyzer, content, row['username'] or 'user',
                                 args.tier, args)
        alerted = result is not None
        label = row['human_verdict']
        if label == 'false_positive':
            mark = 'FIXED  ' if not alerted else 'STILL-FP'
            fixed += not alerted
            still_wrong += alerted
        elif label == 'confirmed':
            mark = 'HELD   ' if alerted else 'LOST   '
            held += alerted
            lost += not alerted
        else:
            mark = 'alert  ' if alerted else 'clear  '
            changed_unlabeled.append((row['id'], alerted, row['category'], why))
        first_line = ' '.join(content.split())[:88]
        print(f"[{mark}] #{row['id']:>3} was={row['category']:<14} "
              f"now={why:<28} {first_line}")

    print(f"\nlabeled false positives : {fixed} now clear, {still_wrong} still alerting")
    print(f"labeled confirmed       : {held} still caught, {lost} lost")
    flipped = [c for c in changed_unlabeled if not c[1]]
    print(f"unlabeled rows          : {len(changed_unlabeled)} replayed, "
          f"{len(flipped)} now clear")


if __name__ == '__main__':
    asyncio.run(main())
