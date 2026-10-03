# Roadmap

The living list: what members and the operator have asked for, what is in
flight, and what the project needs structurally. Issues are the source of
truth for requests; this file is the ordering and the reasoning. Update it
when an issue opens, closes, or changes shape.

Last reviewed: 2026-09-28.

## How the order was chosen

1. Things members can see and use.
2. Things that turn already-built machinery into value (moderation is
   built and sitting in dry-run).
3. Structural work that has to land before the cloud move.
4. Afternoon jobs that slot in while a PR waits on review.

Costs matter: this is a sole-operator project on a home server with one
12B-class local model. Anything that needs a bigger model gets precomputed
on a schedule (Gemini free tier) and stored, never called per request.

## In flight

| What | Where | State |
| --- | --- | --- |
| Role picker: self-roles by country, US state, Canadian province; a member holds every region they want event pings for | PRs #153, #159, `docs/features/ROLE_PICKER.md` | Deployed and posted 2026-09-03. Sub-project 1 of the events work; covers the self-assign half of #26. |
| Con Recon (events database): crowd-sourced conference list (cyber, ham, FOSS; US + Canada first) with mod approval queue, per-row provenance (member / calendar / AI), member filters by state, country and topic, reminders as channel posts tagging the picker roles (never individual mentions), Gemini for scheduled extraction and discovery, gemma4 for cheap relevance | `docs/superpowers/specs/2026-09-03-conference-database-design.md` (approved, revision 3) | Sub-project 2. Phase 1 shipped (no AI): schema v3, /events, review cards, poster, digest, sweep, CSV import; eventpinger.py deleted. Phase 2a (Hacker Tracker discovery, no model) shipped; phase 2b adds the Gemini key pool, verify with proposal cards, and the aggregator fetchers. Later tracks (DEF CON track, DC Groups directory, static search site, onboarding, LinkShield replacement) are section 15 of the spec. |
| Profile screen: names screened at join and on change, greeter hold, mod card, AutoMod member-profile rule for bios | PRs #150, #152 | Deployed 2026-09-02. Watch the model-sourced flags for false positives. |

## Requested (open issues)

| Issue | Request | Plan |
| --- | --- | --- |
| #26 Reaction roles (high priority) | Replace MEE6 for self-roles, welcome/verify with anti-bot, stream and post alert roles | Self-roles: PR #153. Verify/anti-bot: the greeter already owns the post-verify welcome and the profile screen holds suspicious names; a bot-side verify gate (button + account-age check) is the next slice. Alert roles: see #25. Levelling is deliberately last (XP migration from MEE6 may not be possible; see `features/ROLE_MANAGEMENT_NOTES.md`). |
| #25 Roles to subscribe to high-priority alerts | Roles for CVE, KEV, breach, legislation alerts | A non-exclusive role-picker panel (`alerts.json`: CVE, KEV, Breaches, US Legislation, UK Legislation, EU Legislation), plus a `ping_role` per poster so the CVE/KEV/legislation cogs mention the role on high-severity posts only. Small once #153 lands. |
| #24 Have I Been Pwned and breach detections | Alert on new breaches in a dedicated channel | Half done without anyone noticing: the HIBP latest-breaches feed is already a source in `cogs/cybersecurity_news.py` (`haveibeenpwned`), mixed into the cyber news channel. Finishing it: route that source (plus HIBP's keyless `/api/v3/breaches` JSON for pwn counts and data classes) to its own channel with a richer embed, and ping the Breaches role from #25. Other sources to evaluate: Ransomware.live, DataBreaches.net RSS. |
| #14 Quiz bot (IT, cyber, maybe ham) | Community-suggested quiz feature; reference impl is MIT and vibe-coded | Do not fork. Write a small question-bank cog: JSON banks per topic, `/quiz start <topic>`, buttons for answers, per-channel cooldown, scoreboard in SQLite. Question generation is a good scheduled Gemini job (generate, mod reviews, bank grows), and the ham bank can seed from the public FCC question pools, which are public domain. |
| #49 BBC news duplication | Same story from multiple BBC feeds and repeats from one feed | Fixed on main (`utils/news_dedupe.py`: cross-feed title and URL dedupe, one scheduler per category) and deployed; verify in #news for a week and close. |

## Improvements the project needs (big to small)

1. **Decide what the bot is, then split along that line.** The news
   aggregator (14 systemd timers, 224 feeds) and the community bot
   (moderation, greeter, roasters, screener, roles, events) share an image
   and a `.env` but almost no code. Two packages, two entrypoints, two
   images before the cloud move, so the migration carries two small
   things instead of one tangle. This is the restructure pass.
2. **Take moderation out of dry-run.** Guard + second stage, deny-list,
   watchlist, trust tiers, profiles, calibration, replay tooling: all
   built, 98% on the golden set. Blocked on moderator labels and the
   operator's sign-off on the escalation ladder in
   `features/PHASE3_ENFORCEMENT_SPEC.md`. Timeouts and warnings first;
   kick and ban stay human-only.
3. **Ticket desk: replace Ticket Tool.** A cog, not a second hosted bot:
   a panel of ticket types, a private thread per ticket, claim/close
   cards, HTML and JSON transcripts on the data volume, a "Report to
   moderators" message context menu that opens a pre-filled report, and
   reports and appeals wired to the mod card and the infraction rows.
   Because it runs on the homelab, the fallback is part of the design,
   in three layers: a pinned no-bot fallback in `#support`; a stateless
   "deputy" button on a free edge worker that only appears while the
   bot's heartbeat is stale, whose threads the bot adopts when it
   returns; and Ticket Tool left installed, panel-less, for one release.
   The heartbeat is also the "bot offline" alert item 10 wants, and the
   only version of it that survives the homelab going dark. Design:
   `features/TICKET_DESK.md`. Member-visible and retires a paid hosted
   tool, so it ranks right behind moderation.
4. **Con Recon phase 2b** (Gemini verify and aggregator discovery; phases 1 and 2a shipped).
5. **Security event log.** The bot as a sensor. Mirror Discord's audit
   log (45 days there, forever here, and it records what the *other*
   bots do), membership with account age and invite used, messages
   (metadata always, content on edits and deletes for 90 days), voice,
   channels, roles, webhooks, invites, AutoMod, and every command,
   button, moderation decision and ticket the bot handles itself: one
   JSON Lines stream with a stable, ECS-shaped schema to a rotated file,
   a SQLite table, and optionally stdout. The human half is a `#mod-log`
   channel and `/whois`; the rules half is five in-bot detections (raid,
   mass delete, permission escalation, new webhook, first-message link)
   with `/lockdown`. Design, retention and privacy:
   `features/SECURITY_EVENT_LOG.md`. Lands before item 10 because item
   10 is what reads it.
6. **Typed config.** One module that validates every `*_ENABLED` and ID at
   startup, logs the effective config redacted, and fails on unknown keys.
   Kills the "set it in .env, forgot to recreate the container" class of
   bug, and is a prerequisite for ConfigMaps and Secrets on Kubernetes.
   (done 2026-09-06; every cog including events, the `ai/` package and the
   utils read `utils/config.py`.)
7. **Deploy script.** Verify the image revision matches the merge SHA,
   recreate, tail for the "active" log lines, roll back on a failed
   healthcheck. Replaces a hand-typed 400-character `docker run`. Grows a
   nightly off-box backup (SQLite `.backup`, `data/tickets`,
   `data/security`) with a documented restore, since items 3 and 5 make
   the volume worth losing sleep over.
8. **Chip the big files.** `techquote.py` (4.5k lines) and `radiohead.py`
   (2.6k) are mostly data tables inline in Python; move them to JSON.
   `ai_moderation.py` (1.2k): alert rendering and review UI into their own
   module, cog keeps listeners and commands.
9. **One mod card, one command tree.** Three card styles and two button
   vocabularies in the decisions channel today; a shared builder and a
   single `/mod` tree instead of `/mod` + `/profile` + whatever events
   adds. The ticket desk's report card and `/whois` use the same builder,
   so this lands before or with item 3's report path.
10. **Observability someone reads, which is the SIEM.** Grafana with
    Prometheus (there) plus Loki (new), collected by Grafana Alloy on the
    host: the item 5 stream and the host's journald in one Explore view,
    alert rules to a Discord contact point in `#security-alerts`, the
    item 3 heartbeat for "bot offline > 5 min". Panels: alerts/hour,
    second-stage latency, greeter batch size, feed errors, tickets open
    and time to first reply, security events by kind. Wazuh only if the
    Grafana rules stop being enough; the event schema is chosen so that
    move is a config change.
11. **Hygiene.** Dead branches, `dogatron/*` fate, permission rule for
    branch deletion, a committed `data/profile_blocklist.txt` example,
    docs audited against the code (done 2026-09-02; keep `reference/COMMANDS.md` current in the same PR as any command change).
12. **Image moderation.** Research item. The local box cannot run a vision
    model beside the guard and gemma4; Gemini free tier for low-volume image
    channels reuses the key-pool plumbing the events feature introduces.

## Quality of life (afternoon jobs, in rough order)

Small things members or moderators would notice the same day. Each is a
PR or less, and each slots in while something bigger waits on review.
Most of them are the first consumers of items 3 and 5 above.

1. **`/whois @member`**: account age, join date and invite used, roles,
   trust tier, infractions, tickets, recent security events, one card.
   The first thing a moderator wants and the first thing item 5 pays for.
2. **"Report to moderators" context menu**: shippable before the ticket
   desk as a mod card with a content snapshot; becomes a ticket type once
   item 3 lands.
3. **Verify gate**: button plus account-age check, holding suspicious
   joins for the profile screen. The next slice of #26.
4. **Raid guard and `/lockdown`**: join-rate and account-age detection
   from item 5's stream; lockdown pauses invites and raises the
   verification level until a moderator lifts it. Auto-lift after an hour.
5. **`/purge`** with count, member and contains filters, that captures
   content to the security log before deleting and posts one summary
   embed to `#mod-log`, so a purge is never a mystery in the audit log.
6. **Go-live alerts**: Twitch, Kick and YouTube pollers that ping an
   alert role, on the #25 role plumbing. The stream-alert half of
   leaving MEE6. Polling first; EventSub webhooks could live on the
   deputy worker later.
7. **`/status`**: effective feature flags, last run of each poster and
   timer, gateway latency, database size, open tickets, pending mod
   actions, sink health. Cheap now that config is typed.
8. **Sticky channel guides**: the bot keeps a short "how to ask" message
   at the bottom of the busy help channels, re-posting when it scrolls
   off. Replaces a pin nobody reads.
9. **Temp voice channels**: join-to-create, deleted when empty.
   Member-visible, small, and a common ask on servers this size.

## Small bugs the docs audit turned up (2026-09-02)

Found while checking the docs against the code. None block anything; each
is an afternoon or less. The EU/UK manual-fetch choice mismatch found in
the same pass was fixed in the audit PR itself.

- `/news list_sources` KeyErrors on `kev`, `uk_legislation` and
  `vendor_alerts` and reports "cog not loaded" for US and EU legislation:
  the `cog_name_map` in `news_manager.py` is missing three entries and has
  two stale class names.
- The prefix `!news_*` fallbacks omit `kev` and `vendor_alerts`, list
  `uk_legislation` twice, and look up a cog by `f"{category}_news"` which
  matches nothing.
- `data/news_config.example.json` has no `vendor_alerts` entry, and
  `/news set_interval` only accepts whole hours so the 30-minute
  vendor_alerts cadence cannot be set from Discord.
- `/generalnews` offers 7 of 12 sources (the 5 BBC feeds are timer-only).
- `scripts/install-systemd.sh`: `$IS_DOCKER` and `$SERVICE_EXISTS` are never
  assigned, so the `data/` prep and the "rebuild image?" prompt never run;
  `usermod -aG docker` runs without sudo and aborts under `set -e`; the
  end-of-run summary quotes the wrong KEV and solar cadences; choosing
  timers does not set `NEWS_AUTO_POST=false`, so in-bot loops and timers
  double-post until `.env` is edited by hand.
- `news_runner.py` hardcodes `/app/data` for its feed cache, so venv-mode
  timers fail at `mkdir` unless the path is pre-created.
- `scripts/feed-check/*` compute `project_root` as if they still lived in
  `tests/`, so their cog imports fail; `scripts/preview-timers.sh` and
  `scripts/demo-install-flow.sh` hardcode a home directory path.

## Cloud (not scheduled)

Hybrid: OpenTofu with Spacelift-managed state, a resilient Kubernetes
cluster, Twingate for access to cloud and homelab, cloud workloads still
reaching the local AI server for inference. AWS vs DigitalOcean undecided.
Items 1 and 6 above are the prerequisites; nothing else here depends on
it. Item 3's deputy worker and item 10's Loki are the first pieces that
live off the homelab on purpose.

## Parked ideas

- Eraser bot (delete-all-messages requests): separate one-shot container,
  manifest then execute, must also purge bot-side rows and alert embeds.
- Moderation across Matrix, Twitch, Kick, YouTube Live: the moderation
  core is written platform-agnostic on purpose; adapters when a second
  platform is real.
- Group-dynamics / social-graph memory: structured DB, not chat-history
  stuffing.
- DMs to opted-in members for event reminders (after channel posts prove
  out).
- International events once US + Canada is clean.
- Ban appeals from outside the guild: a banned member shares no server
  with the bot, so appeals need a door elsewhere (a tiny appeals guild,
  a form on the static site, or the modmail model). Waits for phase 3
  enforcement to produce bans the bot made.
- Starboard, birthday roles, levelling: community asks that MEE6 covers
  today; levelling is deliberately last (`features/ROLE_MANAGEMENT_NOTES.md`).
