# Security event log: the bot as a sensor

**Status: design note, nothing implemented. Requested by the operator on
2026-09-28.** Ordering is in [ROADMAP.md](../ROADMAP.md); the reading
side (Loki, Grafana, alert rules) is the roadmap's observability item and
is sketched at the end of this note.

Today the bot logs what it is doing (`reference/LOGGING.md`) and stores
what moderation decided (`mod_infractions`). It does not record what the
*server* is doing: who joined with a two-day-old account, who deleted
forty messages at 3am, which bot got Administrator last Tuesday, which
invite a wave of joins came through. Discord's own audit log has the
answers for 45 days, in a UI nobody reads, and only for the actions
Discord counts as auditable. The operator wants everything, kept, and
queryable: a SIEM of sorts. This note is the collection half of that.
The rule of thumb is: **collect broadly, store structured, keep content
for a bounded time, and make it easy to ship elsewhere.**

## Three readers

1. **Moderators, in Discord.** A `#mod-log` channel of embeds for the
   human-relevant subset (joins with account age, leaves, deleted and
   edited messages, role and nickname changes, timeouts, bans, tickets),
   and `/whois` and `/audit` commands that answer "what has this member
   done here" without leaving Discord.
2. **The operator, hunting.** Grafana Explore over Loki: every event,
   filterable by any field, next to the host's own journald, for as long
   as the retention says.
3. **Rules, nobody.** Alert rules that fire into a private
   `#security-alerts` channel when a pattern shows up: a raid, a mass
   delete, a permission escalation, a new webhook.

One stream feeds all three. Nothing is logged twice in two shapes.

## What is collected

Every family below becomes events with the same envelope (next section).
The rightmost column is what the bot needs that it does not have today.

| Family | Events | Fields beyond the envelope | Needs |
|---|---|---|---|
| **Audit log mirror** | Every entry Discord writes: ban, unban, kick, timeout, member role update, role/channel/permission create/update/delete, webhook create/update/delete, integration and bot add/remove, invite create/delete, emoji/sticker changes, AutoMod rule changes, guild settings changes, message pin/unpin, bulk delete | `actor` (who did it, humans and other bots alike), `target`, `changes` (before/after per key, as Discord reports them), `reason` | **View Audit Log** permission; `on_audit_log_entry_create` (discord.py 2.2+) |
| **Membership** | join, leave, update, ban, unban | On join: `account.created_at`, `account.age_days`, `account.flags`, `invite.code` and `invite.inviter` (by diffing the guild's invite uses at join time), `member.pending` (onboarding); on update: `roles.added`, `roles.removed`, `nick.before/after`, `timeout.until` | **Manage Guild** for the invite diff; members intent (on) |
| **Messages** | create, edit, delete, bulk delete | Always: `channel`, `message.id`, `author`, `length`, `attachments[]` (name, size, type, no bytes), `links[]` (domains only in `create`, full URLs in `delete`), `mentions.count`, `mentions.everyone`, `reply_to`, `is_thread`. On **edit**: `content.before`, `content.after`. On **delete**: `content` (from the message cache; `content_available=false` when the cache missed). On **create**: content only when `SECLOG_CONTENT=create` (default is `edits_and_deletes`, see privacy) | message content intent (on); bigger message cache (`max_messages=10000`, memory is cheap here) |
| **Voice** | join, leave, move, mute/deafen changes, stream/camera on/off | `channel.before`, `channel.after` | nothing |
| **Structure** | channel, thread, role, emoji, sticker, webhook, invite, scheduled event: create, update, delete | `changes` from the gateway event where the audit mirror is late or absent | nothing |
| **AutoMod** | rule triggered, message blocked, member timed out by AutoMod | `rule`, `matched_keyword`, `action` | auto-moderation intents (in `Intents.default()`) |
| **Bot: interactions** | Every slash command, prefix command, context menu, button and select | `command`, `args` (redacted per command), `outcome` (ok, denied, error, cooldown), `latency_ms`, `error_id` | already in the bot; one `on_interaction` listener and a `before_invoke` hook |
| **Bot: decisions** | Moderation scan, alert, second-stage adjudication, moderator vote, enforcement action; profile screen hold; greeter batch; role picker change; ticket opened/claimed/closed/blocked; events review decision | `infraction_id`, `ticket_id`, `category`, `confidence`, `action` | already in the bot; each cog calls `emit()` where it already logs |
| **Bot: lifecycle** | start (effective config, redacted), cog load/unload, gateway connect/disconnect/resume, HTTP 429 with the route, unhandled error (traceback stored once, referenced by `error_id`), shutdown | | already in the bot |

**Deliberately not collected.** Presence and status changes (needs the
presence intent, is pure noise, and is the creepiest thing a bot can
log). Typing. Reactions by default (`SECLOG_REACTIONS=true` turns them
on; they matter for reaction-spam only). DMs (the bot does not read
them). Voice audio, obviously. Message content in any channel listed in
`SECLOG_CONTENT_EXCLUDE_CHANNELS`, and in ticket threads, whose
transcripts already exist and have their own retention.

## Event shape

JSON Lines, one object per line, flat keys with dots, names borrowed from
the Elastic Common Schema where one exists so a future Elastic, OpenSearch
or Wazuh reader needs no mapping. Snowflakes are strings: they exceed
2^53 and JavaScript-based readers will round them otherwise.

```json
{"@timestamp":"2026-09-28T14:03:11.482Z","event.kind":"message","event.action":"delete",
 "event.id":"01J9...","guild.id":"123","channel.id":"456","channel.name":"general",
 "message.id":"789","user.id":"1011","user.name":"someone","user.trust_tier":"new",
 "actor.id":"1213","actor.name":"a_moderator","actor.type":"member",
 "content":"the deleted text","content_available":true,"length":16,
 "attachments":[],"links":["example.com"],"via":"audit_log","schema":1}
```

- `event.kind` is the family (`audit`, `member`, `message`, `voice`,
  `structure`, `automod`, `interaction`, `decision`, `lifecycle`);
  `event.action` is the verb. Both are closed lists in
  `utils/security_log.py`, so a typo is a test failure, not a new bucket.
- `actor` is who caused it, `user` is who it happened to. For a
  self-delete they are the same; for a mod delete they differ, and that
  is the difference the audit mirror exists to record. When the gateway
  event does not say who did it, `actor` is filled from the matching
  audit-log entry when one arrives within a few seconds, and `via` says
  which.
- `schema` is bumped when a field changes meaning; readers filter on it.
- Secrets never enter an event: `args` go through the same redaction the
  config banner uses, and the emitter refuses any value that matches the
  gitleaks patterns in `.gitleaks.toml`.

## Sinks

The emitter (`utils/security_log.py`, `emit(kind, action, **fields)`)
writes each event to every enabled sink in order, and a sink that fails
never blocks the others or the gateway event that produced it.

| Sink | What it is for | Default |
|---|---|---|
| **File** `data/security/events-YYYY-MM-DD.jsonl`, gzipped after the day ends | The record. On the data volume, in the backup, readable with `jq` when everything else is down. This is also what a collector tails. | on |
| **SQLite** `security_events` (id, ts, kind, action, guild, channel, user, actor, message, `data` JSON) with indexes on (user, ts), (actor, ts), (channel, ts), (kind, action, ts) | `/whois`, `/audit`, in-bot detections, and retention enforcement. Content lives in `data` and is the part retention strips. | on |
| **stdout** as a JSON line prefixed `SECLOG ` on its own logger | So `docker logs` carries it and a Docker-log-reading collector works with no volume mount. Off by default because it doubles the container's log volume. | off |
| **`#mod-log`** embeds for the human subset (member, message delete/edit, audit, automod, ticket) | Readers 1. Rate-limited and batched (one embed per event, ten per message at most) so a purge does not get the bot rate-limited. | on when `SECLOG_MODLOG_CHANNEL_ID` is set |
| **`#security-alerts`** | Only the in-bot detections below post here directly; Grafana's alerts post here through a webhook. | on when set |

## Retention

Three clocks, because content, metadata and the audit mirror have
different reasons to exist. A nightly job enforces them in SQLite and
deletes aged files.

| What | Default | Why |
|---|---|---|
| Message content (`content`, `content.before/after`) | 90 days (`SECLOG_CONTENT_DAYS`) | Long enough to investigate a report or an appeal; the same window `MOD_RETENTION_DAYS` uses for excerpts. |
| Event metadata (everything else) | 365 days (`SECLOG_META_DAYS`) | A year of "who was here and what did they do" for trust and patterns. |
| Audit log mirror | forever (`SECLOG_AUDIT_DAYS=0`) | Discord's is 45 days. Permission and bot changes are the events you want in two years. Tiny volume. |
| Files on disk | 400 days, gzipped after day one | Matches the metadata clock with slack; Loki has its own retention. |

`/seclog forget @user` strips content fields for one member (metadata
stays, so a ban evader's pattern still does), for the day someone
exercises a deletion request.

## Privacy, and saying so

Storing message content is allowed for a bot's own functionality under
Discord's developer terms and must be disclosed. This is one guild, run
by its operator, so the disclosure is a paragraph in `#rules` (the rules
sync already pulls that channel into the moderation prompt, so the
moderation model sees the same text members do): what is recorded, for
how long, who can read it (moderators and the operator), and that
deleted messages are kept for 90 days for moderation. Members who do not
want that can leave; a server with an AI moderator already asked them to
accept more than this.

Access follows the data: `data/` is the operator's volume, `#mod-log` is
staff-only, and the Loki behind Grafana is on the homelab network behind
Twingate. Encryption at rest is the volume's job, not the bot's.

## Sizing

| | Estimate |
|---|---|
| Events per day, a busy day | ~20,000 (messages dominate) |
| Bytes per event, JSONL | ~400 uncompressed, ~60 gzipped |
| Disk per year, files | ~3 GB raw, ~0.5 GB gzipped |
| SQLite after a year | ~2 GB with content, ~0.7 GB after the content clock |
| Loki, 1 year | under 1 GB |

Nothing here needs more than the existing volume and a `docker volume`
with room to breathe.

## Configuration

```env
SECLOG_ENABLED=false
SECLOG_CONTENT=edits_and_deletes        # none | edits_and_deletes | create
SECLOG_CONTENT_EXCLUDE_CHANNELS=        # comma-separated channel IDs
SECLOG_REACTIONS=false
SECLOG_STDOUT=false
SECLOG_MODLOG_CHANNEL_ID=
SECLOG_ALERTS_CHANNEL_ID=
SECLOG_CONTENT_DAYS=90
SECLOG_META_DAYS=365
SECLOG_AUDIT_DAYS=0
```

All through `utils/config.py`; the startup banner lists the effective
sinks and clocks the same way it lists log sinks today.

## In-Discord queries

- `/whois @member`: account age, join date and invite, roles, trust tier,
  infractions (open and total), tickets, last 10 security events, and
  the count of deleted messages in 30 days. One card, the thing a
  moderator opens first.
- `/audit user @member [days]`, `/audit channel #channel [days]`,
  `/audit actor @member [days]`: paged lists of events; `actor` answers
  "what has this moderator (or bot) done".
- `/seclog export @member|#channel <days>`: the matching JSONL as an
  attachment, for a report to Discord Trust & Safety or to law
  enforcement, which is a thing that happens to communities.
- `/seclog stats`: events per kind per day, sink health, clocks.

## Detections

Two tiers. **In-bot** rules run on the event stream as it happens,
because they need to act in seconds; they post to `#security-alerts` and
can take one pre-agreed action. **Grafana** rules run over Loki on a
schedule and only notify; they are cheaper to write and to change.

In-bot, from day one:

1. **Raid**: more than N joins in M minutes (default 10 in 5) with a
   median account age under 7 days → alert, and, if `SECLOG_RAID_LOCKDOWN`
   is on, pause invites and raise the verification level to highest until
   a moderator runs `/lockdown off` (which is itself a logged action).
2. **Mass delete**: one actor deletes more than N messages in a minute
   outside a `/purge` the bot ran itself → alert.
3. **Escalation**: any role gains Administrator, Manage Guild, Manage
   Roles, Manage Webhooks, or Ban Members; any member is given such a
   role; any bot is added → alert, always, no threshold.
4. **New webhook or integration** → alert. Webhooks are how servers get
   spammed from outside.
5. **First message is a link** from a `new`-tier account, to a domain not
   seen in the guild before → alert (the moderation pipeline already sees
   the message; this is the cheap check for when it is not running).

Grafana, once Loki exists: joins per hour vs baseline, deletes per user
per day, commands by non-staff that were denied, interactions error rate,
429s per route, moderation alerts per category per day against the
14-day average, tickets opened per hour, gateway resumes per day. Each
one is a Loki query, a threshold, and the Discord contact point.

## Shipping it: the SIEM half

The file sink is the interface. What reads it is a deployment choice,
and the choice for the first year is **Grafana + Loki**, collected by
**Grafana Alloy**:

- Grafana is already the roadmap's observability target and already has
  the Prometheus metrics; Loki is one more container beside it, and the
  same Explore view shows a `penguin_mod_alerts_total` spike next to the
  events that caused it.
- Alloy on the host tails `data/security/*.jsonl` (labels: `guild`,
  `event.kind`, `event.action`; everything else stays in the JSON and is
  queried with `| json`) **and** the host's journald (sshd, docker, the
  inference server), so the bot's view of Discord sits next to the host's
  view of itself. That is the "SIEM of sorts": one place, one query
  language, one alerting path.
- Grafana alerting has a native Discord contact point, so rule → webhook →
  `#security-alerts` needs no glue.

**Wazuh** is the actual SIEM answer (a rule engine, agents with file
integrity monitoring on every host, compliance dashboards) and it costs
an OpenSearch cluster and several gigabytes of RAM that the homelab
would rather give to models. The event schema is chosen so the move is
cheap when it is wanted: the Wazuh agent's logcollector reads the JSONL
with `log_format json`, and ECS names map onto its decoders. Same for
OpenSearch or Elastic directly. Decide when the Grafana rules stop being
enough, not before.

## Implementation shape

- `utils/security_log.py`: schema constants, `emit()`, redaction, the
  file and SQLite and stdout sinks, the retention job. No Discord
  imports, so it is unit-testable and the runners can use it.
- `cogs/security_log.py`: the gateway listeners (audit, member, message,
  voice, structure, automod), the audit-log correlation that fills in
  `actor`, the `#mod-log` embeds, the in-bot detections, and the
  `/whois`, `/audit`, `/seclog`, `/lockdown` commands.
- Every existing cog: replace the `logger.info('Review button ... clicked')`
  style lines that are really events with an `emit()` call that also
  logs, so the text log keeps working and the event exists.
- `utils/database.py`: schema version bump, `security_events` table and
  indexes, retention queries.
- Phases: (1) emitter, file and SQLite sinks, audit mirror, membership
  and message families; (2) `#mod-log` and `/whois`; (3) interactions and
  decisions from the existing cogs, `/audit`, `/seclog`; (4) in-bot
  detections and `/lockdown`; (5) Alloy, Loki, dashboards and Grafana
  rules, documented in `deployment/`.

## Metrics

`penguin_seclog_events_total{kind,action}`,
`penguin_seclog_sink_errors_total{sink}`,
`penguin_seclog_detections_total{rule}`, `penguin_seclog_content_rows`
(gauge, what the content clock will eventually delete), and
`penguin_seclog_lag_seconds` (audit-log correlation delay). A sink error
counter that moves is the first thing the Grafana panel should shout
about, because a silent sensor is worse than none.
