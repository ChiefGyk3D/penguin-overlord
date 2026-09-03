# Roadmap

The living list: what members and the operator have asked for, what is in
flight, and what the project needs structurally. Issues are the source of
truth for requests; this file is the ordering and the reasoning. Update it
when an issue opens, closes, or changes shape.

Last reviewed: 2026-09-02.

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
| Role picker: self-roles by country, US state, Canadian province | PR #153, `docs/features/ROLE_PICKER.md` | Built, awaiting merge + `/roles post` in the server. Sub-project 1 of the events work; covers the self-assign half of #26. |
| Events database: crowd-sourced conference list (cyber, ham, FOSS; US + Canada first) with mod approval queue, per-row provenance (member / calendar / AI), member filters by state, country and topic, reminders as channel posts tagging the picker roles (never individual mentions), Gemini for scheduled extraction and discovery, gemma4 for cheap relevance | Design in progress; spec to land in `docs/superpowers/specs/` | Sub-project 2. Retires `cogs/eventpinger.py` (CSV). |
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
3. **Events database** (above), then delete `eventpinger.py`.
4. **Typed config.** One module that validates every `*_ENABLED` and ID at
   startup, logs the effective config redacted, and fails on unknown keys.
   Kills the "set it in .env, forgot to recreate the container" class of
   bug, and is a prerequisite for ConfigMaps and Secrets on Kubernetes.
5. **Deploy script.** Verify the image revision matches the merge SHA,
   recreate, tail for the "active" log lines, roll back on a failed
   healthcheck. Replaces a hand-typed 400-character `docker run`.
6. **Chip the big files.** `techquote.py` (4.5k lines) and `radiohead.py`
   (2.6k) are mostly data tables inline in Python; move them to JSON.
   `ai_moderation.py` (1.2k): alert rendering and review UI into their own
   module, cog keeps listeners and commands.
7. **One mod card, one command tree.** Three card styles and two button
   vocabularies in the decisions channel today; a shared builder and a
   single `/mod` tree instead of `/mod` + `/profile` + whatever events adds.
8. **Observability someone reads.** Grafana panel: alerts/hour, second-stage
   latency, greeter batch size, feed errors; one alert rule for "bot
   offline > 5 min".
9. **Hygiene.** Dead branches, `dogatron/*` fate, permission rule for
   branch deletion, a committed `data/profile_blocklist.txt` example,
   docs audited against the code (done 2026-09-02; keep `reference/COMMANDS.md` current in the same PR as any command change).
10. **Image moderation.** Research item. The local box cannot run a vision
    model beside the guard and gemma4; Gemini free tier for low-volume image
    channels reuses the key-pool plumbing the events feature introduces.

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
Items 1 and 4 above are the prerequisites; nothing else here depends on
it.

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
