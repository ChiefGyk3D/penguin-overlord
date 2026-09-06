# Con Recon

Con Recon is the community conference calendar, driven by the `/events`
commands and the `EVENTS_*` settings (there is no `CON_RECON_*` variable;
the code and config keep the original `events` name). Crowd-sourced
conferences, hamfests and meetups with a moderator approval queue. Phase 1
of `docs/superpowers/specs/2026-09-03-conference-database-design.md`: no
AI, no external lookups. Members propose, moderators approve, the bot
reminds the roles that opted in.

## How it works

- **Submit.** `/events submit` takes a title, topic (cyber, ham, foss,
  other), start date, city, a place from the autocomplete list (state,
  province, country, or Online), and optionally an end date, URL, notes
  and a `national` flag for the DEF CON tier. The title is capped at 120
  characters, the city at 80 and the notes at 500. Duplicates are caught by a
  fingerprint of the normalised title plus start date. A member can have
  three submissions open at once.
- **Review.** Every submission posts a card to the review channel
  (`EVENTS_REVIEW_CHANNEL_ID`, falling back to `MOD_ALERT_CHANNEL_ID`)
  with Approve, Reject and Edit buttons. Reject asks for a reason, which
  goes into the audit trail and is shown to the submitter under
  `/events mine`. Pending cards untouched for `EVENTS_PENDING_EXPIRE_DAYS`
  expire on their own.
- **Remind.** Each day at `EVENTS_POST_AT` (default 09:00 in
  `EVENTS_TIMEZONE`) the poster sends one message per approved event whose
  start is exactly 30, 7 or 1 days away (`EVENTS_REMINDER_DAYS`). The
  message tags the topic role plus the region and country roles the role
  picker defines, and nothing else: no `@everyone`, no individual mentions.
  Missing roles are logged once a day and counted in
  `penguin_events_role_missing_total`. A reminder that failed to send is
  retried the next day; one that was sent is never sent again.
- **Digest.** Mondays at the same time, a list of the next 30 days with no
  mentions at all (`EVENTS_DIGEST_ENABLED`).
- **Sweep.** 03:00 local nightly: ended events retire; annual ones that
  ended come back as a pending row one year later, marked estimated, for a
  moderator to confirm or reject. Expired and old rejected rows are pruned.
- **Cancel or reschedule.** `/events cancel` and the Edit button post one
  notice to the channel if the event had already been announced.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `EVENTS_ENABLED` | `false` | Load the cog and its loops. |
| `EVENTS_DRY_RUN` | `true` | Member-facing posts (reminders, digest) are logged instead of sent. Moderator review cards still post and the nightly sweep still runs. |
| `EVENTS_CHANNEL_ID` | | Reminder and digest channel. Required when enabled. |
| `EVENTS_REVIEW_CHANNEL_ID` | `MOD_ALERT_CHANNEL_ID` | Where review cards go. |
| `EVENTS_TIMEZONE` | `America/New_York` | Local time for posts, sweeps and countdowns. |
| `EVENTS_POST_AT` | `09:00` | Daily poster and Monday digest time. Keep it after 03:00 local, when the nightly sweep runs, so a claim orphaned by a crash is released before the next post. |
| `EVENTS_REMINDER_DAYS` | `30,7,1` | Days-out windows. |
| `EVENTS_DIGEST_ENABLED` | `true` | Monday digest on or off. |
| `EVENTS_MAX_PENDING_PER_MEMBER` | `3` | Open submissions per member. |
| `EVENTS_PENDING_EXPIRE_DAYS` | `30` | Untouched pending rows expire after this. |
| `EVENTS_DISCOVERY_ENABLED` | `false` | Monday Hacker Tracker read; new cons land in the review queue with a "Location TBD" city for a moderator to fill in. |

The bot needs **Mention @everyone, @here and All Roles** in the events
channel or the role tags render as plain text.

## Roles

Reminders resolve role names from `assets/events/regions.json` (regions and
countries, the same names the role picker provisions) and the topic panel
`assets/role_panels/event_topics.json`. Post the topic panel with
`/roles post event_topics`. `/events status` lists every role the guild
is missing.

## One-time import

The old CSV calendar (`events/security_and_ham_events_2026_with_types.csv`)
imports as approved annual events. Run it once with the bot stopped.

**Use the same `-v` and the same `--env-file` your bot service uses.**
Otherwise the rows land in a database the bot never opens: the script still
prints `inserted 29`, the calendar stays empty, and a second run prints
`skipped 29`, which reads like confirmation that the data is there.

On the systemd deployment (what `scripts/install-systemd.sh` generates, and
the production path), the bot's unit runs
`--env-file /path/to/penguin-overlord/.env -v /path/to/penguin-overlord/data:/app/data`,
so the import is:

```bash
docker run --rm --env-file /path/to/penguin-overlord/.env \
  -v /path/to/penguin-overlord/data:/app/data \
  ghcr.io/chiefgyk3d/penguin-overlord:latest \
  python scripts/import-events-csv.py --guild <guild id> \
    --csv events/security_and_ham_events_2026_with_types.csv
```

On the docker-compose deployment the data lives in the named volume
`penguin-data` instead, so swap the mount for `-v penguin-data:/app/data`
and keep `--env-file .env`. The `--env-file` matters on its own: a
`BOT_DATABASE_PATH` set in `.env` wins over `DATA_DIR`, so leaving it out
can aim the import at a third location.

The script prints the database it opened before its result:

```
Database: /app/data/penguin_overlord.db
OK: inserted 29, skipped 0 (already present)
```

That path must match the bot's own startup line,
`Moderation database ready: <path>`. If the two differ, the import went
somewhere the bot will not read. A second run skips all 29. Rows whose
dates have already passed retire on the first sweep and come back as
pending rows for the next year, marked estimated, for moderators to
confirm, so expect a batch of review cards the morning after the first
night. A year in the title is rolled forward with the dates
(`HamCation 2026` becomes `HamCation 2027`); the URL is not, so check it
while approving.

## Rollout

1. Deploy with `EVENTS_ENABLED=true` and `EVENTS_DRY_RUN=true`, set
   `EVENTS_CHANNEL_ID` and `EVENTS_REVIEW_CHANNEL_ID` (it falls back to
   `MOD_ALERT_CHANNEL_ID`; with neither set, submissions are stored but no
   review card ever posts, and the startup log says so), drop the old
   `events/` bind mount from the service.
2. Run the import, post `event_topics`, grant the mention permission.
3. Watch the dry-run log (`DRY RUN events reminder: ...`) until the role
   names it resolves look right, then set `EVENTS_DRY_RUN=false`.
4. When you are ready for discovery: say hello in junctor's Discord, set
   `EVENTS_DISCOVERY_ENABLED=true`, run `/events discover` once, and work
   the review queue; every discovered row needs its location set before
   Approve accepts it.

## Metrics

`penguin_events_submissions_total{provenance}`,
`penguin_events_decisions_total{decision}`,
`penguin_events_reminders_total{window}`, `penguin_events_post_errors_total`,
`penguin_events_role_missing_total{role}`,
`penguin_events_discovery_total{source,outcome}`, gauge
`penguin_events_pending` (submissions awaiting review across every guild,
no label).

## Discovery: Hacker Tracker

Con Recon's first discovery source is Hacker Tracker (hackertracker.app),
junctor's open-source schedule app, used by DEF CON and a growing list of
chapters and independent cons. Organizers enter their own dates through
junctor's ConfMgr, so a row from it is not a guess: it is the con's own
claim about itself.

Discovery runs on Mondays inside the nightly sweep, gated by
`EVENTS_DISCOVERY_ENABLED` (default off). A moderator can also run
`/events discover` for an immediate check without waiting for Monday.

A discovered row lands as `pending` with provenance `hackertracker`. The
review card shows a "Location TBD" city, the con's own site as the title
link, and a second link, "On Hacker Tracker", to
`https://hackertracker.app/<CODE>`. Approve refuses the row until the
location is filled in through Edit (`/events edit <id>` or the card's Edit
button); a moderator has to give it a city before it can go live.

If an approved row's organizer changes the dates on Hacker Tracker, the
review channel gets a "Hacker Tracker disagrees on #<id>: <title>" notice.
It repeats only when the organizer's dates change again, not on every
sweep that finds the same mismatch.

The Hacker Tracker read caches to `hackertracker_conferences.json` in
`DATA_DIR`. If a fetch fails, the bot falls back to the last good copy and
logs one WARNING; the sweep does not fail because of it.

**Etiquette, read before you turn this on.** The Hacker Tracker read is an
undocumented endpoint with no stated data licence. Be a good citizen of
it: the sweep makes one list call a week, `/events discover` adds one per
run (so use it when you need it, not on a timer), and say hello in
junctor's Discord (linked from `github.com/junctor/hackertracker-about`)
before you flip `EVENTS_DISCOVERY_ENABLED` on for the first time.
