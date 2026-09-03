# Events calendar

Crowd-sourced conferences, hamfests and meetups with a moderator approval
queue. Phase 1 of `docs/superpowers/specs/2026-09-03-conference-database-design.md`:
no AI, no external lookups. Members propose, moderators approve, the bot
reminds the roles that opted in.

## How it works

- **Submit.** `/events submit` takes a title, topic (cyber, ham, foss,
  other), start date, city, a place from the autocomplete list (state,
  province, country, or Online), and optionally an end date, URL, notes
  and a `national` flag for the DEF CON tier. Duplicates are caught by a
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
| `EVENTS_DRY_RUN` | `true` | Log what would be posted; send nothing, record nothing. |
| `EVENTS_CHANNEL_ID` | | Reminder and digest channel. Required when enabled. |
| `EVENTS_REVIEW_CHANNEL_ID` | `MOD_ALERT_CHANNEL_ID` | Where review cards go. |
| `EVENTS_TIMEZONE` | `America/New_York` | Local time for posts, sweeps and countdowns. |
| `EVENTS_POST_AT` | `09:00` | Daily poster and Monday digest time. |
| `EVENTS_REMINDER_DAYS` | `30,7,1` | Days-out windows. |
| `EVENTS_DIGEST_ENABLED` | `true` | Monday digest on or off. |
| `EVENTS_MAX_PENDING_PER_MEMBER` | `3` | Open submissions per member. |
| `EVENTS_PENDING_EXPIRE_DAYS` | `30` | Untouched pending rows expire after this. |

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
imports as approved annual events. Run it once with the bot stopped, against
the same data volume:

```bash
docker run --rm -e DATA_DIR=/app/data -v penguin-data:/app/data \
  ghcr.io/chiefgyk3d/penguin-overlord:latest \
  python scripts/import-events-csv.py --guild <guild id> \
    --csv events/security_and_ham_events_2026_with_types.csv
```

It prints `OK: inserted 29, skipped 0 (already present)`; a second run
skips all 29. Rows
whose dates have already passed retire on the first sweep and come back
as pending 2027 rows for moderators to confirm, so expect a batch of
review cards the morning after the first night.

## Rollout

1. Deploy with `EVENTS_ENABLED=true` and `EVENTS_DRY_RUN=true`, set
   `EVENTS_CHANNEL_ID`, drop the old `events/` bind mount from the service.
2. Run the import, post `event_topics`, grant the mention permission.
3. Watch the dry-run log (`DRY RUN events reminder: ...`) until the role
   names it resolves look right, then set `EVENTS_DRY_RUN=false`.

## Metrics

`penguin_events_submissions_total{provenance}`,
`penguin_events_decisions_total{decision}`,
`penguin_events_reminders_total{window}`, `penguin_events_post_errors_total`,
`penguin_events_role_missing_total{role}`, gauge `penguin_events_pending`.
