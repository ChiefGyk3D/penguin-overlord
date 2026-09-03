#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One-time import of the old events/*.csv calendar into the events table.

    python scripts/import-events-csv.py --guild 123456789012345678 \
        --csv events/security_and_ham_events_2026_with_types.csv

Every row becomes an approved, annual, calendar-provenance event decided
by actor 0. Rows whose (guild, fingerprint) already exist are skipped, so
running it again is harmless. Uses the same database the bot does
(BOT_DATABASE_PATH, else DATA_DIR/penguin_overlord.db); stop the bot first
so the two do not share the file. Does not read .env and never talks to
Discord.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

from utils import database  # noqa: E402
from utils.events_logic import csv_row_to_event  # noqa: E402
from utils.events_store import EventsStore  # noqa: E402


async def import_csv(guild_id: int, csv_path: Path) -> tuple[int, int]:
    db = await database.get_database()
    store = EventsStore(db)
    inserted = skipped = 0
    with csv_path.open(newline='', encoding='utf-8') as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            try:
                event = csv_row_to_event(row, guild_id)
            except (KeyError, ValueError) as e:
                raise SystemExit(f'{csv_path.name} line {line}: {e}') from None
            if await store.find_fingerprint(guild_id, event['fingerprint']):
                skipped += 1
                continue
            await store.insert(event, actor_id=0, action='import')
            inserted += 1
    # One trail row for the run itself, under the reserved event id 0.
    await store.audit(0, 0, 'import', None,
                      {'file': csv_path.name, 'guild_id': guild_id, 'inserted': inserted, 'skipped': skipped})
    return inserted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--guild', type=int, required=True, help='guild id the events belong to')
    parser.add_argument('--csv', type=Path, required=True, help='path to the calendar CSV')
    args = parser.parse_args()
    if not args.csv.is_file():
        print(f'FAIL: {args.csv} is not a file', file=sys.stderr)
        return 1
    inserted, skipped = asyncio.run(_run(args.guild, args.csv))
    print(f'OK: inserted {inserted}, skipped {skipped} (already present)')
    return 0


async def _run(guild_id: int, csv_path: Path) -> tuple[int, int]:
    try:
        return await import_csv(guild_id, csv_path)
    finally:
        db = await database.get_database()
        await db.close()


if __name__ == '__main__':
    sys.exit(main())
