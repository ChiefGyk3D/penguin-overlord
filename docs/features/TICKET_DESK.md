# Ticket desk: replacing Ticket Tool

**Status: design note, nothing implemented. Requested by the operator on
2026-09-28.** Ordering and the reasons for it are in
[ROADMAP.md](../ROADMAP.md).

The server runs [Ticket Tool](https://tickettool.xyz) for support tickets.
It works most of the time and is annoying the rest of it: the panel is
theirs, the transcripts live on their site, the useful settings sit behind
a subscription, and when it is slow there is nothing to look at. The
question is what replaces it, and, since anything that replaces it runs on
the same homelab as the rest of the bot, what members do when that box is
dark.

## Build it as a cog, do not host someone else's bot

Three ways to get a self-hosted ticket system, considered and rejected in
favour of a cog:

| Option | Why not |
|---|---|
| Self-host [TicketsBot](https://github.com/TicketsBot) (the open-source Go bot behind ticketsbot.net) | A second Discord application with its own token, and a stack of services (gateway, worker, dashboard, Postgres, Redis) to run and back up. It is the best of the hosted ticket bots, but self-hosting it is a project on its own, and it shares nothing with this bot: no trust tiers, no moderation history, no audit trail, no metrics. |
| Self-host a modmail bot (the Python `modmail-dev/modmail` lineage) | A different model: members DM the bot, staff answer in a mirrored channel. Good for reports and appeals, wrong for "help me with my radio", and it needs MongoDB. The DM half is worth stealing later for appeals (below), not the whole bot. |
| Keep Ticket Tool, live with it | The operator's request is to stop. It stays installed as the break-glass fallback for one release, see below. |

A cog is the small option. Everything a ticket system needs is already
here: persistent components that survive restarts (the `DynamicItem`
pattern in `cogs/role_picker.py` and the moderation review buttons), the
SQLite database with WAL and a schema version, `utils/trust.py` for
account-age and tenure gates, the mod card and decisions channel for the
staff-only side of a report, `utils/metrics.py` for the Grafana panel, and
one deploy. It also lands on the community-bot side of the split the
roadmap's item 1 describes, which is where it belongs.

## What v1 does

**Panel.** One persistent message in `#support` (or wherever
`TICKETS_PANEL_CHANNEL_ID` points) with a select menu of ticket types.
Types come from a JSON file the way role panels do (`assets/tickets/
types.json`): key, label, description, which staff role gets pinged, which
channel the ticket lives in, whether the opener must be verified, and an
optional intake form. Shipped types:

| Type | Staff role | Intake form |
|---|---|---|
| Support | helpers | "What do you need help with?" |
| Report a member | moderators | "Who, where, what happened?" plus an optional message link |
| Appeal a timeout or warning | moderators | "Which action, and why should it be reconsidered?" |
| Partnership, press, other | operator | "Tell us about it" |

**A ticket is a private thread.** Ticket Tool creates a channel per
ticket under a category. Private threads do the same job with less
plumbing: no permission overwrites to compute, no category to fill, no
risk of hitting the 500-channel guild cap, and Discord archives them for
free. The bot creates the thread in the type's channel, adds the opener,
posts the intake answers and a control card, and mentions the staff role
so the ping brings them in. Nobody else sees it. The thread is named
`ticket-0042-username`; the number is the ticket row's id.

**Control card.** One message at the top of the thread with buttons:
**Claim** (assigns the ticket to the clicking staff member and says so in
the thread), **Add member** (modal asking for a user), **Close** (modal
for a reason, then confirm), and **Transcript** (staff only, sends the
current transcript to the ticket log channel). The card's custom_ids
encode the ticket id, so a restart never orphans a ticket.

**Close.** The thread is archived and locked, the row gets
`closed_at`, `closed_by`, and the reason, a transcript is rendered, and a
summary card (type, opener, claimed by, open time, message count, reason,
transcript attached) goes to `TICKETS_LOG_CHANNEL_ID`. The opener gets a
DM with the summary unless they have opted out; a failed DM is logged,
never retried. Tickets untouched for `TICKETS_IDLE_DAYS` (default 7) get
a warning ping at day 6 and auto-close at day 7 with reason `idle`.

**Transcripts.** Rendered twice: a self-contained HTML file for humans
(no external assets, so it opens offline and stays readable when Discord's
CDN links die) and a JSON file with the raw messages, attachments listed
by URL and size, and the ticket row. Both land in `data/tickets/<id>/` on
the data volume, so they ride the same backup as the database, and the
HTML is attached to the summary card. Attachments themselves are not
downloaded in v1; a `TICKETS_ARCHIVE_ATTACHMENTS` flag and a size cap can
come later.

**Limits.** One open ticket per member per type. Members in the `new`
trust tier (under 30 days) get one open ticket total. Opening is
rate-limited per member (three per hour), and staff can `/ticket block`
someone who abuses it; the block is a row, not a role, and it is logged.

**Staff commands** under one `/ticket` group, gated by the type's staff
role: `open @member <type>` (staff opens on someone's behalf), `claim`,
`close [reason]`, `add @member`, `remove @member`, `rename <title>`,
`list [open|claimed|mine]`, `block @member`, `unblock @member`, and
`stats` (open count by type, median time to first staff reply, median
time to close, per week). `/ticket panel post` and `/ticket panel refresh`
manage the panel like `/roles post` does. Every one of these lands in
`reference/COMMANDS.md` in the same PR.

**Report a message.** A message context-menu command (right-click,
Apps, "Report to moderators") opens a Report ticket with the message
link, author, channel, and a snapshot of the content already filled in.
The snapshot matters: reported messages get deleted by their authors. This
is the feature Ticket Tool never had and the one that makes the mod team
faster.

**Reports and appeals talk to moderation.** A Report ticket posts a mod
card in the decisions channel with the reported member's infraction
history, trust tier, and the ticket link; that card is where staff talk
about the reported member, never in the thread the reporter can read. An
Appeal ticket is linked to the infraction it appeals (`appeals
mod_infractions.id`), and closing it with **Upheld** or **Overturned**
writes the outcome back to the infraction, so the calibration dataset
learns from appeals too. The reporter's identity is visible to staff and
nobody else.

## What v1 does not do

- **No web dashboard.** Transcripts are files and Discord attachments.
  If a browser view is ever wanted, the static site the events spec
  already plans can render the JSON transcripts behind auth.
- **No DM-based tickets.** A banned member shares no server with the bot,
  so the bot cannot DM them and they cannot open a ticket: ban appeals
  need a door outside the guild. Options, in order of cheapness: a
  second, tiny "appeals" guild the bot also sits in; a form on the static
  site that posts to a webhook; the modmail model. Parked until phase 3
  enforcement produces bans the bot itself made.
- **No migration of old tickets.** Ticket Tool's transcripts stay on
  Ticket Tool's site. Closed tickets are closed. The cut-over is a new
  panel, not an import.
- **No AI in the loop.** Later candidates, all scheduled or opt-in, never
  on the open path: a gemma4 one-line summary on close for the log card,
  a first reply that points at the resources channel the way the newcomer
  helper does for Support tickets, and a triage hint on Report tickets
  from the moderation second stage. None of it changes who answers.

## Storage

Two tables in the existing database (schema version 4):

```
tickets: id, guild_id, type, opener_id, thread_id, channel_id,
         status (open | claimed | closed), claimed_by, opened_at,
         first_staff_reply_at, closed_at, closed_by, close_reason,
         appeals_infraction_id, transcript_path, message_count
ticket_blocks: guild_id, user_id, blocked_by, reason, created_at
```

`tickets.thread_id` is unique. Message content is not stored in the
table; the transcript files hold it, and the security event log
([SECURITY_EVENT_LOG.md](SECURITY_EVENT_LOG.md)) records the ticket
lifecycle (opened, claimed, member added, closed, blocked) as events with
the actor and the ticket id, which is how `/whois` and the SIEM see
tickets.

## Configuration

```env
TICKETS_ENABLED=false
TICKETS_PANEL_CHANNEL_ID=        # where the panel lives and Support threads open
TICKETS_LOG_CHANNEL_ID=          # summary cards and transcripts; staff only
TICKETS_IDLE_DAYS=7
TICKETS_TYPES_FILE=assets/tickets/types.json
```

Per-type staff roles and channels are in the types file, not env, because
there are four of them and they change. All of it goes through
`utils/config.py` like everything else.

## The fallback: what happens when the homelab is dark

The bot going down takes tickets with it, and it goes down more often than
Ticket Tool does: the homelab reboots, the ISP drops, the operator is
asleep. Three layers, cheapest first. Each one exists because the layer
above it can fail.

**Layer 0: words, no bot.** A pinned message in `#support`, maintained by
hand, that says what to do when the ticket button does not answer within
a minute: post in the public `#help` forum for anything that is not
private, and for anything that is, DM one of the moderators named in the
pin. It costs nothing and it is the only layer that works when everything
is broken. It goes up before the cog does.

**Layer 1: a deputy on someone else's infrastructure.** A second Discord
application ("deputy", a name for this note only) whose entire job is one
button. It has no gateway connection and no server: it is an HTTP
interactions endpoint on a free-tier edge worker (Cloudflare Workers is
the obvious one; anything that runs a request handler and a cron will
do). Discord signs every interaction, the worker verifies the signature,
and the button handler makes three REST calls: create a private thread in
`#support`, add the clicker, post "the main desk is offline, a moderator
will be with you" and mention the staff role. Stateless, so nothing to
back up.

The deputy only shows itself when needed. The main bot sends it a
heartbeat every minute (one authenticated HTTP request to the worker,
the same shape as any dead-man switch). The worker's cron runs each
minute: heartbeat older than five minutes and no deputy panel posted →
post the deputy panel in `#support` and ping the operator; heartbeat
fresh and a deputy panel exists → delete it. The member sees one working
button, whichever bot is behind it.

When the main bot returns it **adopts** the deputy's threads: any private
thread in `#support` whose name matches the deputy's pattern and has no
`tickets` row gets a row, a control card, and a log entry, so nothing
opened during the outage is lost or unclosable.

The same dead-man switch is the "bot offline for more than five minutes"
alert the roadmap's observability item wants, and it is the only version
of that alert that works when the homelab, Grafana included, is what went
down. Build it once, use it for both.

**Layer 2: Ticket Tool stays for one release.** Its panel comes down the
day the cog's goes up, but the bot stays in the server, with its
permissions reduced to the ticket category, for the release cycle after
launch. Re-posting its panel is a two-minute break-glass if layer 1 turns
out to have a bug on a bad night. It is removed once the deputy has
covered one real outage cleanly. Two ticket buttons in the same channel
is confusing, so it is never re-enabled without also removing the cog's
panel.

## Rollout

1. Layer 0 pin, and the `#help` forum if it does not exist.
2. Cog behind `TICKETS_ENABLED`, dry-run first: the panel posts, opening a
   ticket creates the thread and the row, and the log card says
   `dry-run` in its footer. One week with staff only.
3. Deputy worker and heartbeat. Prove it by stopping the container on
   purpose and opening a ticket through the deputy panel; confirm
   adoption on restart.
4. Ticket Tool's panel comes down; the cog's goes up; announcement in
   `#announcements` with the Layer 0 pin's text.
5. One release later, Ticket Tool leaves.

## Metrics

`penguin_tickets_opened_total{type}`, `penguin_tickets_closed_total{type,
reason}`, `penguin_tickets_open{type}` (gauge),
`penguin_tickets_first_reply_seconds{type}` (histogram),
`penguin_tickets_deputy_adopted_total`. The first-reply histogram is the
one that says whether the mod team is keeping up.
