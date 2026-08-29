#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Summarize moderator-labeled false positives from the bot's database.

Run on the machine that hosts the bot (reads the SQLite DB directly):

    python scripts/eval-moderation/fp_report.py [--db data/penguin_overlord.db] [--days 14]

Shows per-category alert/label counts and the most recent false-positive
rows with the model's stated reason, so FP sources are visible instead of
anecdotal. Also replays each FP excerpt through the CURRENT deny-list and
PII regexes — after a filter fix, this shows which historical FPs would
still fire today.
"""

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

from ai.features.moderation import pre_scan_pii  # noqa: E402
from ai.guardrails import find_blocked_terms  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/penguin_overlord.db')
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--limit', type=int, default=25, help='FP rows to show')
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Database not found: {args.db} (run this on the bot host, or pass --db)")
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT category, confidence, excerpt, human_verdict, created_at
           FROM mod_infractions
           WHERE created_at >= datetime('now', ?)
           ORDER BY id DESC""",
        (f'-{args.days} days',),
    ).fetchall()

    if not rows:
        print(f"No alerts recorded in the last {args.days} days.")
        return 0

    print(f"=== Alerts, last {args.days} days: {len(rows)} total ===\n")
    by_cat = Counter()
    fp_by_cat = Counter()
    confirmed_by_cat = Counter()
    for row in rows:
        by_cat[row['category']] += 1
        if row['human_verdict'] == 'false_positive':
            fp_by_cat[row['category']] += 1
        elif row['human_verdict'] == 'confirmed':
            confirmed_by_cat[row['category']] += 1

    print(f"{'category':<20}{'alerts':>8}{'✅':>6}{'❌':>6}{'unlabeled':>11}{'precision':>11}")
    for cat, total in by_cat.most_common():
        fp = fp_by_cat[cat]
        ok = confirmed_by_cat[cat]
        labeled = fp + ok
        precision = f"{ok / labeled:.0%}" if labeled else "n/a"
        print(f"{cat:<20}{total:>8}{ok:>6}{fp:>6}{total - labeled:>11}{precision:>11}")

    fps = [r for r in rows if r['human_verdict'] == 'false_positive']
    print(f"\n=== Most recent false positives ({min(len(fps), args.limit)} of {len(fps)}) ===\n")
    still_firing = 0
    for row in fps[:args.limit]:
        excerpt = (row['excerpt'] or '').replace('\n', ' ')
        deny_now = find_blocked_terms(excerpt)
        pii_now = pre_scan_pii(excerpt)
        refires = bool(deny_now or pii_now)
        still_firing += refires
        marker = '⚠ STILL FIRES' if refires else '  fixed/model'
        print(f"[{marker}] {row['created_at'][:16]} {row['category']:<15} conf={row['confidence']:.2f}")
        print(f"    {excerpt[:120]}")
        if deny_now:
            print(f"    current deny-list hit: {deny_now}")
        if pii_now:
            print(f"    current PII hit: {pii_now}")
    print(f"\nOf the shown FPs, {still_firing} would still trigger the current regex filters;")
    print("the rest were either model verdicts (tune/ignore the category, raise")
    print("MOD_ALERT_MIN_CONFIDENCE, or wait for the fine-tune) or are fixed by filter changes.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
