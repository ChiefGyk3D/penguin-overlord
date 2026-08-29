# Penguin Overlord — Project Assessment & AI Moderation Roadmap

**Date:** August 2026
**Scope:** Full codebase review (~21,300 lines of Python), CI/deployment review, review of the
existing AI work in PR #67 (`add-ollama-llm`), and a staged plan for: Ollama-powered Arch banter,
AI-assisted moderation (alerts first, actions later), multi-platform expansion (Matrix, Twitch,
Kick, YouTube), and Grafana/metrics integration.

> The bot is in production and working. Everything below is staged so that each phase ships from a
> test branch, is verifiable before merge, and degrades gracefully back to today's behavior.

> **Implementation status (this branch):** Phase 0 (foundations, P0/P1 fixes, pytest+CI), Phase 1
> (async `ai/` package + Ollama Arch roasts), Phase 2 (alert-first moderation with calibration
> loop), the Phase 3 enforcement machinery (present, default-off), and the Phase 5 core
> (Prometheus `/metrics` + real healthcheck) are implemented — see
> [docs/features/AI_MODERATION.md](features/AI_MODERATION.md) for the operator guide. Deferred:
> the `BaseNewsCog` refactor and data extraction (§2, kept to avoid churning working production
> cogs — the shared bugs were fixed in place instead), the news/CVE/legislation AI analyzers,
> Phase 4 multi-platform work, and Grafana dashboard JSON.

---

## 1. Executive summary

- **The bot works, but ~40% of the codebase is copy-paste debt.** Ten news-family cogs share
  ~1,500 duplicated lines with no base class, the HF-propagation physics exists in three diverging
  copies, and `techquote.py` is 94% embedded data. A `BaseNewsCog` refactor plus data extraction
  would remove roughly 5,000–6,000 lines without changing behavior.
- **The test suite is not a test suite.** All 23 files in `tests/` are print-only scripts with zero
  assertions, and CI cannot fail: every lint/security step is `continue-on-error` or `|| true`, and
  cog import failures are swallowed. This must be fixed *before* any AI/moderation work, because
  moderation is exactly the feature you cannot ship on vibes.
- **PR #67 already contains ~80% of the AI architecture you described** — an `ai/` package with
  Ollama + Gemini providers, per-feature model routing, guardrails, a request queue, an SQLite
  layer, AI Arch roasts, and an 893-line moderation cog. The architecture is good. It is **not
  mergeable as-is**: it has blocking I/O on the event loop, a missing `aiosqlite` dependency,
  unbounded per-message LLM calls, auto-delete/auto-timeout **on by default with no dry-run mode**,
  and zero tests. The plan below revives it in slices rather than rewriting.
- **A handful of real production bugs exist today** (P0 list in §3): a bot-freezing blocking HTTP
  loop in `cogs/xkcd.py`, news items silently lost on send failure in the legislation cogs, broken
  `start.sh`/`create-secrets.sh` quick-start paths, and no atomic writes or locking on any state
  file.
- **Recommendation on the "own project" question (§7):** build the moderation engine as a
  platform-agnostic core (its own package, eventually its own repo) with thin adapters. Penguin
  Overlord becomes the Discord adapter. Matrix/Twitch/Kick/YouTube become additional adapters later.
  Don't fork the code now — design the seam now, extract when the second platform lands.

---

## 2. Current state: architecture

### 2.1 News cogs — two copy-paste families, ~70% duplicated

There is no shared base class. Two lineages exist:

- **Family A** (`tech_news`, `gaming_news`, `apple_google_news`, `cybersecurity_news`): class bodies
  are exactly 213 lines each, ~93% identical (diffs are class name, state filename, interval,
  command name).
- **Family B** (`general_news`, `us/uk/eu_legislation`): ~92% identical to each other; adds
  `_ensure_session`, `_is_recent`, and a `posted_items` ring buffer.

Every cog re-implements the same fetch → dedup/state → channel resolution → embed pipeline, with
the embed built **twice per cog** (auto-poster + manual command). Meanwhile
`utils/news_fetcher.py` (`OptimizedNewsFetcher`: ETag/If-Modified-Since caching, concurrency
semaphore, GUID dedup, proper HTML stripping) is exactly the shared base that was needed — and **no
cog uses it**; only `news_runner.py` does. The runner also parses feeds with regex while the cogs
use ElementTree, so the same feed can behave differently in bot mode vs runner mode.

**Behavioral bug from the drift:** Family B marks items as posted *inside the fetcher, before the
send* (`us_legislation.py:231-234`; send happens at `:293`). If `channel.send()` raises, the item
is permanently marked posted and lost. Worse, the manual command (`us_legislation.py:313`) calls
the same fetcher, so a user running `/uslegislation` burns items out of the auto-poster's queue.
Family A does this correctly (save after successful send, `tech_news.py:292-294`). Same defect in
`general_news`, `uk_legislation`, `eu_legislation`.

### 2.2 God files

- `cogs/techquote.py` (4,565 lines): 4,274 lines are one `TECH_QUOTES` list literal (610 quotes).
  Belongs in `data/tech_quotes.json`. Five per-author commands are byte-identical modulo the author
  string — one parameterized `/quote author:` replaces them.
- `cogs/radiohead.py` (2,648 lines): ~770 lines of embedded reference tables, ~270 lines of
  propagation physics, and ~20 commands across six unrelated domains, including its own auto-poster
  with a third re-implementation of the channel-config pattern. Should become a `radio/` package.
- **The propagation physics is triplicated** in `radiohead.py:26-296`, `utils/solar_embed.py:27-155`,
  and `solar_runner.py:42-300`, and has already diverged (~220-line diff radiohead↔solar_runner) —
  `/propagation` and the cron solar report can give different band predictions from the same inputs.

### 2.3 Runners vs cogs — duplicated logic, shared state, no locking

`kev_runner.py`, `xkcd_runner.py`, `comics_runner.py`, `solar_runner.py` fully re-implement their
cog counterparts (~1,400 lines of shadow logic) and write **the same state files** the cogs use.
Nothing prevents deploying both; there is no file locking anywhere, so bot + runner co-deployment
races and can double-post. `news_runner.py` is the only well-behaved one (imports the cogs' source
tables, uses `OptimizedNewsFetcher`).

### 2.4 State persistence — no atomicity, three path schemes

- **Zero** uses of `os.replace`, temp-file writes, `fsync`, or `flock` in the repo. Every save is
  truncate-then-write on the live file; a crash mid-write corrupts it, and every `_load_state`
  swallows the error into `{}` — which means a **silent full re-post of every feed**.
- Path schemes: most cogs use relative `'data/...'` (CWD-dependent — correct under Docker by
  coincidence, writes into the repo tree under `start.sh`); `xkcd_poster`/`comics` use a correct
  env-aware resolution; `news_runner.py:61` hardcodes `/app/data`.
- **Precedence bug:** `xkcd_runner.py:52` / `comics_runner.py:53`:
  `os.getenv('DATA_DIR') or '/app/data' if os.path.exists('/app/data') else 'data'` — when
  `/app/data` doesn't exist, `DATA_DIR` is silently ignored (confirmed by execution).
- Runtime state is **git-tracked** (`penguin-overlord/data/*.json`, including live test residue in
  `test_cache.json`) despite `.gitignore` listing `data/` — the files were committed before the
  rule, so the ignore does nothing. `git pull` can clobber a deployment's dedup state.

### 2.5 Blocking calls on the event loop

- `cogs/xkcd.py:43` — synchronous `requests.get` called from async commands with no executor;
  `!xkcd_search` loops it up to **100 sequential blocking requests** (`xkcd.py:185`), stalling the
  entire bot (heartbeats included, risking gateway disconnect). `comics.py` already does the same
  job correctly with aiohttp.
- `utils/solar_embed.py:156-272` — matplotlib render (hundreds of ms) inside `async def` with no
  `asyncio.to_thread`, on every `/xray` and `/radio_maps`.
- ~20 truly bare `except:` clauses (catch `KeyboardInterrupt`/`SystemExit`), e.g.
  `general_news.py:158`, `radiohead.py:106`, `arch_banter.py:424`.

### 2.6 Dead code

`social/discord.py` and `social/matrix.py` are vendored from Boon-Tube-Daemon, import
`boon_tube_daemon.utils.config` (doesn't exist here → `ModuleNotFoundError`), have zero importers,
and are synchronous `requests` code with stream-announcement semantics. The Matrix logic is a
useful *reference* for Phase 4 but is not functional. Delete from the tree (git history keeps it).

Also: `cogs/securitynews.py.deprecated` (delete; history keeps it) and
`penguin-overlord/snyk-code.sarif` (stale empty CI artifact, delete + gitignore `*.sarif`).

---

## 3. Current state: testing, CI, deployment, secrets

### 3.1 Tests

All 23 files in `tests/`: zero `pytest`/`unittest` imports, **zero assert statements**. They are
live-network feed pingers that print emoji status and exit 0. Several hardcode *copies* of the
cogs' feed dicts, so they test the copy, not the code. Two have broken `sys.path` inserts
(`test_secrets.py:16`, `test_comic_command.py:7`). `test_secrets.py:34,53-54` **prints prefixes and
suffixes of the live Discord token** — a leak vector if output is pasted into an issue. Cog logic
coverage is effectively zero.

### 3.2 CI cannot fail

`ci-tests.yml` runs no test files. Its cog import loop swallows failures
(`|| echo "⚠ Warning..."`, line 72), and ruff/bandit/safety are all `continue-on-error` (+
`|| true`). Other issues: `snyk-security.yml:54,60` redirects **stderr into the SARIF file**,
corrupting it whenever Snyk warns (then silently deletes it — likely why the empty SARIF got
committed); Trivy only scans on PRs, so published `latest` images are never image-scanned;
`trivy-action@master` is an unpinned mutable ref; `safety check` is the deprecated CLI.

### 3.3 Deployment & secrets

Good: non-root container (`USER penguin`), multi-stage build, hardened systemd units
(`NoNewPrivileges`, `ProtectSystem=strict`), no real secrets anywhere in the repo, `.env`
gitignored/dockerignored.

Broken/risky:

- `start.sh:65` runs `python test_secrets.py` from the repo root — file lives in `tests/`; with
  `set -e` the documented quick-start **aborts before the bot starts**.
- `scripts/create-secrets.sh:43` writes `DISCORD_TOKEN=` but the bot reads `DISCORD_BOT_TOKEN` —
  **the generated .env does not work**. Same wrong name in `install-systemd.sh:128`. Token also
  read with plain `read -p` (echoes) instead of `read -s`.
- The Docker/compose healthcheck is `python -c "import sys; sys.exit(0)"` — always passes, says
  nothing about gateway connectivity.
- `utils/secrets.py` and `utils/config.py` are two overlapping copies of the same layer, both
  carrying foreign defaults: Doppler project defaults to `'stream-daemon'`
  (`secrets.py:87,153`), config docstring/AWS/Vault defaults say `boon-tube`
  (`config.py:6,248,285`). A user setting `DOPPLER_TOKEN` without `DOPPLER_PROJECT` silently
  queries the wrong project.
- **No caching:** every `get_secret`/`get_config` call constructs a fresh Doppler SDK client and
  fetches *all* secrets — a full API round-trip per lookup.
- ~10 cogs call `ET.fromstring()` on untrusted remote feed bytes (e.g. `general_news.py:199`,
  `vendor_alerts.py:388`, `kev.py:138`) — stdlib XML is not hardened against entity-expansion DoS;
  use `defusedxml`. Bandit flags this (B314) but its findings are suppressed by CI.
- `requirements.txt`: exact pins (good), but `boto3`+`hvac`+`doppler-sdk` are unconditional hard
  deps imported at module top level in `secrets.py` (most deployments need one or none), and
  there's no dev/test requirements file at all.

### 3.4 P0/P1 bug list (pre-AI fixes)

| Pri | Issue | Where |
|-----|-------|-------|
| P0 | Blocking `requests.get` ×100 loop freezes bot | `cogs/xkcd.py:43,185` |
| P0 | Items marked posted before send; manual cmd steals auto-poster queue | `us_legislation.py:231-234,313` + general/uk/eu |
| P0 | `start.sh` aborts (wrong test path + `set -e`) | `start.sh:65` |
| P0 | Generated `.env` uses wrong var name (`DISCORD_TOKEN`) | `create-secrets.sh:43`, `install-systemd.sh:128` |
| P0 | CI cog-import failures swallowed → CI can't go red | `ci-tests.yml:72` |
| P1 | No atomic state writes; corrupt file → silent mass re-post | all cogs' `_save_state`/`_load_state` |
| P1 | `DATA_DIR` env var silently ignored (operator precedence) | `xkcd_runner.py:52`, `comics_runner.py:53` |
| P1 | Git-tracked runtime state under `penguin-overlord/data/` | `git rm --cached` + ship `*.example.json` |
| P1 | `defusedxml` for feed parsing | ~10 cogs |
| P1 | Doppler client rebuilt per lookup; foreign project-name defaults | `utils/secrets.py`, `utils/config.py` |
| P1 | matplotlib render on the event loop | `utils/solar_embed.py:156-272` |
| P1 | Token fragments printed by test script | `tests/test_secrets.py:34,53-54` |
| P2 | Dead `social/`, `.deprecated` cog, stale SARIF | delete |
| P2 | Fake healthcheck; Trivy not scanning published images; stderr-corrupted Snyk SARIF | Dockerfile/compose, workflows |

---

## 4. PR #67 (`add-ollama-llm`) — review verdict

**Keep the architecture, fix the blockers, split the rollout.** The layering is right:
`AIManager` → per-host `OllamaProvider` pool + `GeminiProvider` fallback → `RequestQueue` →
`Guardrails` → feature modules (`ArchRoaster`, `CVEAnalyzer`, `NewsAnalyzer`,
`LegislationAnalyzer`, `ModerationAnalyzer`) with injected generate callables (mockable,
provider-agnostic). Per-feature model/host/temperature routing supports a multi-GPU Ollama setup.
Everything degrades to `None` → pre-AI behavior. Secrets go through the existing pipeline.

### Merge blockers

1. **`aiosqlite` missing from `requirements.txt`** → the DB layer silently falls back to blocking
   `sqlite3` on the event loop, with a DB read on *every message* when moderation is on.
2. **Blocking connect inside async paths**: `ollama_provider.py:189-191` calls a synchronous,
   no-timeout `ollama.Client(host).list()` from `generate()`; `AIManager.initialize()` is sync and
   called from `setup_hook`/handlers. A firewalled/blackholed host freezes the whole bot for the OS
   TCP timeout, recurring every reconnect interval. **Fix: switch to `ollama.AsyncClient`** (kills
   the sync/thread bridge and the executor-leak-on-timeout problem at `ollama_provider.py:216-226`).
3. **Per-message LLM calls, unbounded queue**: `ai_moderation.py:270` fires on every guild message
   with no length floor, rate limit, or sampling, into a queue with no depth cap
   (`ai/queue.py`) — a 20 msg/min channel backlogs forever and enforcement goes stale.
4. **Dangerous defaults**: `MOD_AUTO_DELETE` and `MOD_AUTO_TIMEOUT` default `true`
   (`ai_moderation.py:178-179`) and **there is no dry-run mode**. Also `AI_ENABLED` defaults `true`
   and `cve.py:114` / `kev.py:72` / `us_legislation.py:115` call `get_ai_manager()` gated only on
   import success — first CVE post after deploy attempts an Ollama connection even if you never
   configured AI.
5. **Zero tests** for ~2,900 new lines, including the regex response parser
   (`moderation.py:313-364`) and the guardrail pipeline — exactly where silent misbehavior lives.

### Other significant findings

- `get_model_config()` returns shared dicts **by reference** and per-feature config mutates them in
  place (`ai/config.py:249,255,302-315`) — setting `AI_CVE_TEMPERATURE` changes other features
  sharing the model.
- **Gemini fallback defaults on for moderation** (`config.py:375`): if Ollama is down and a
  `GEMINI_API_KEY` exists, every scanned Discord message is silently shipped to Google. Must be
  off for moderation.
- Review buttons (`ReviewActionView`, `ai_moderation.py:135-165`) are not registered as persistent
  views and share a static `custom_id` → **after any restart, every Approve/Deny button is dead**;
  the approve handler also never defers, so kick/ban flows blow the 3-second interaction window.
- `hate_speech` is not special-cased: an 0.75-confidence hit with `ACTION: delete` is deleted with
  no human ever seeing it, while doxxing gets mandatory review. Given the whole point is
  protecting against hate speech, it should get **forced human review + evidence preservation**
  (see §6).
- Roast guardrails explicitly disable the profanity filter for roasting
  (`ai/guardrails.py:82-93`) and no slur/hate-term deny-list exists anywhere in the package — model
  output goes to a public channel with the target's @mention. Needs a hard deny-list applied to
  all features regardless of config.
- `docs/AI_LLM_INTEGRATION.md` describes moderation as "stub, not wired" while the same PR ships a
  cog that deletes messages; `.env.example` documents zero `MOD_*` variables and ships
  `AI_ENABLED=true` uncommented.
- Misc: unlocked singletons (`get_ai_manager`, `get_database`), no WAL/busy_timeout on SQLite, no
  schema migration path, `_context_buffer` never pruned, unrelated Solana/README commit in the
  branch.

---

## 5. Staged roadmap

Each phase is a separate test branch → PR → staging validation → production. Phases 1–3 are the
AI track; Phase 0 is a prerequisite for all of them.

### Phase 0 — Foundations (make the ground safe to build on)

*Branch theme: `fix/foundations-*`. No feature changes; production-safe; ship in small PRs.*

1. **Real test harness**: add `pytest` + `pytest-asyncio` + `dpytest`-style fakes (or plain
   mocks), `requirements-dev.txt`, `pyproject.toml` (ruff config included). Move the live-network
   feed pingers to `scripts/feed-check/` — they're useful triage tools, not tests.
2. **CI that can fail**: remove the `||` swallows in `ci-tests.yml`, make ruff + pytest required;
   keep bandit/safety advisory initially, ratchet later. Fix the Snyk stderr-into-SARIF bug, pin
   `trivy-action`, scan published images too.
3. **Fix P0 bugs** (§3.4): xkcd blocking loop → aiohttp; family-B mark-after-send; `start.sh`;
   `create-secrets.sh` var name; each with a regression test.
4. **State layer**: one `utils/state.py` — atomic writes (`tmp` + `os.replace`), single
   env-aware `DATA_DIR` resolution, and an `asyncio.Lock` per file. Untrack
   `penguin-overlord/data/*.json` (`git rm --cached`), ship `*.example.json`.
5. **Secrets layer**: merge `utils/secrets.py`/`utils/config.py` into one module with an in-process
   TTL cache, correct `penguin-overlord` defaults, lazy backend imports, and backends as optional
   extras.
6. **`defusedxml`** for all feed parsing; delete `social/`, `.deprecated` cog, stale SARIF.
7. **(parallel, ongoing) `BaseNewsCog` refactor**: fold the ten news cogs onto
   `utils/news_fetcher.py` + a base class; extract `TECH_QUOTES` and radiohead tables to JSON;
   dedupe the propagation physics into `utils/propagation.py`. This is the "optimize the mess"
   ask — do it incrementally, one cog family per PR, with before/after feed fixtures as tests.

**Exit criteria:** CI red on real failures; `pytest` suite exists and gates merges; state writes
atomic; quick-start scripts work.

### Phase 1 — LLM plumbing + Ollama Arch banter (low-stakes proving ground)

*Rebase/split from PR #67: land `ai/` infra + `arch_banter` only. Leave the moderation cog and the
cve/kev/legislation wiring for later slices.*

1. Port `ai/` package with the fixes from §4: **`ollama.AsyncClient`**, async `initialize()`,
   config deep-copy bug, bounded queue (depth cap + drop-and-log), locked singletons,
   `aiosqlite` in requirements, `AI_ENABLED` default **false**, per-feature enable flags gating
   every call site.
2. **Guardrails hardening**: hard slur/hate-term deny-list applied to *all* output regardless of
   per-feature config; profanity filter on (`severe`) for roasting; keep the prompt-injection
   sanitizer.
3. Arch banter: AI roast with fallback to the static list (PR #67's structure is right), SQLite
   leaderboard with completed migration (stop double-writing JSON).
4. Tests: unit tests for provider fallback chain, guardrail pipeline, and roast fallback; a
   recorded-response Ollama fake so CI needs no GPU.
5. Mirror your Stream-Daemon conventions (`LLM` config section names, reconnect/backoff,
   thinking-mode handling) so the three projects feel the same to operate — but async-native here.

**Exit criteria:** bot runs for a week with Ollama host down, up, and flapping, with zero user-visible
errors and zero event-loop stalls; roast output passes the deny-list in a red-team test set.

### Phase 2 — AI moderation, **alert-only** (the "first for alerting" milestone)

*This phase never touches a message or a member. It watches, scores, and reports.*

1. **Dry-run is the only mode**: `MOD_DRY_RUN` locked `true`; auto-action code paths compile but
   are unreachable. Every detection posts a rich alert to a private mod channel: message link,
   category, confidence, model, proposed action, user history summary.
2. **Scope controls**: `MOD_CHANNELS` **allowlist** (not ignore-list), per-user rate limit, minimum
   message length, and a token-bucket cap on LLM calls per minute. Start with one busy channel.
3. **Privacy stance**: Gemini fallback hard-disabled for moderation (local-only inference);
   retention policy + purge command for stored message excerpts; document what is stored.
4. **Hate-speech posture**: `hate_speech`, `doxxing`, `self_harm` always escalate to humans with
   evidence preserved (don't delete in dry-run anyway); prompt tuned with slur-evasion patterns
   (leet, spacing, homoglyphs) — regex pre-filters catch the cheap evasions before the LLM.
5. **User history & weights (your "context, not regex" ask)**: extend the PR #67 schema into a
   per-user behavior record — infractions with category/confidence/timestamp, moderator verdicts
   (confirmed/false-positive), join age, prior actions. Feed a compact history summary into the
   moderation prompt, and compute a trust score with time decay. Moderator verdicts on alerts are
   the labeled data that makes Phase 3 safe.
6. **Calibration loop**: log every (message, model verdict, human verdict) tuple; build a golden
   eval set from real traffic (including the antisemitic/anti-LGBTQ patterns you actually see —
   the generic model prompt will underfit these without examples); track
   precision/recall per category weekly. Add ✅/❌ reactions on alerts so mods label with one click.

**Exit criteria:** ≥2 weeks of shadow operation; precision on `hate_speech` alerts high enough
that mods trust the pings (target: >90% of alerts actionable); false-negative review of a sampled
week shows nothing egregious missed.

### Phase 3 — Graduated enforcement (opt-in actions)

1. Enable actions **per category, per action**, opt-in: start with delete-on-`doxxing`/PII
   (objective, low-regret), then timeout for repeat spam, and only then (if ever) hate-speech
   auto-timeout — with `hate_speech` still always paging humans. Kick/ban remain human-click-only.
2. Fix the review UX from PR #67: persistent views (`bot.add_view` + `pending_id` in `custom_id`),
   `interaction.response.defer()`, full audit trail in SQLite, appeal/undo command.
3. Thresholds come from Phase 2 calibration data, not the model's self-reported confidence alone
   (combine confidence, category, trust score, and repeat-window counts).
4. Kill switch: one command (`/mod panic`) that drops back to alert-only instantly.

### Phase 4 — Multi-platform: Matrix first, then streaming platforms

See §7 for the project-structure recommendation. Sequence:

1. **Extract the moderation core** (analyzer, guardrails, history/weights, policy engine) into a
   platform-agnostic package with a small interface: `ingest(Message) -> Verdict`,
   `Verdict -> [Alert|Action]`, where `Message`/`Action` are platform-neutral dataclasses.
2. **Matrix adapter**: use `matrix-nio` (async, E2E-capable) — not the vendored requests code.
   Alert-only first, same as Phase 2. Matrix moderation actions = redact event, kick, ban, mute
   via power levels. Consider [Draupnir/Mjolnir] interop for policy lists rather than reinventing
   ban-list sync.
3. **Twitch/Kick/YouTube adapters**: Twitch EventSub + chat over IRC/WebSocket; Kick's API;
   YouTube live chat polling. These are where "StreamElements is too rigid" gets solved: the same
   history/weights engine sees a user across platforms (identity linking table), and timeout/ban
   actions map per platform. Rate limits and TOS differ per platform — adapters own that.

### Phase 5 — Metrics & Grafana

1. `prometheus_client` in the bot: an HTTP `/metrics` endpoint (also becomes the **real Docker
   healthcheck** — expose gateway latency and last-heartbeat age). Counters/histograms for:
   messages scanned, LLM latency per model/host, queue depth, alerts by category, actions by type,
   false-positive rate (from mod verdicts), feed-poster successes/failures, Ollama up/down.
2. Grafana dashboards: moderation overview (alert volume, category mix, precision trend),
   LLM health (latency, fallbacks, reconnects), bot health (gateway, task loops, state writes).
3. Optional: Loki for structured moderation-event logs so you can grep history from Grafana;
   alerting rules (Ollama down > 5 min, alert spike = possible raid).

---

## 6. Testing strategy (the "comprehensive and robust" requirement)

- **Unit**: pure functions first — feed parsing against fixture XML (per source), state
  round-trips, dedup, propagation math, guardrail pipeline, moderation response parser, fallback
  chains. These are cheap and catch the drift bugs this review found.
- **LLM contract tests**: a fake Ollama server (recorded responses) in CI; schema-validate every
  prompt's expected output shape; adversarial cases (injection attempts, slur evasions, empty/
  malformed model output).
- **Moderation eval harness**: versioned golden set of labeled messages (grown from Phase 2 mod
  verdicts); CI job reports precision/recall per category on every prompt/model change — prompts
  become testable artifacts, not vibes.
- **Integration**: a staging Discord guild + staging bot token; smoke suite that boots the real
  bot, loads all cogs (import failures = red), and exercises one command per cog.
- **Shadow production**: Phase 2 *is* the integration test for moderation — dry-run against real
  traffic with human labels before any enforcement.
- **CI gating order**: ruff + pytest required now; bandit/dependency-review already exist —
  un-suppress them per §3.2; eval-harness regression gate once Phase 2 data exists.

---

## 7. Same project or separate? — Recommendation

**Design the seam now; extract the repo later.** Concretely:

- Phases 1–3 live in this repo as `penguin-overlord/ai/` + `moderation/` — fastest iteration,
  one deploy, your real server as the proving ground.
- The moderation core is written platform-agnostic from day one (no `discord.*` imports inside
  analyzer/policy/history code — the PR #67 layering already mostly respects this).
- When the Matrix adapter lands (Phase 4), promote the core + adapters to its own repo/package
  (working title: your call — it's a "moderation daemon" sibling to Stream-Daemon and
  Boon-Tube-Daemon). Penguin Overlord then pins it as a dependency and keeps only Discord glue.
- Why not a separate project now: you'd be maintaining two repos and a release cycle before the
  core is proven; Discord alerting will shake out the design cheaply.
- Why definitely separate later: Twitch/Kick/YouTube adapters have no business in a Discord bot's
  cog loader; the shared user-history/weights engine wants one home and one schema; and
  Grafana/Prometheus wiring belongs to the daemon, not to each bot.

---

## 8. Branch & PR mechanics

- Working branches off `main`, one phase-slice per PR, production deploys only from `main` after
  staging-guild validation. Keep PRs reviewable (<~500 lines of logic).
- **PR #67**: don't merge as-is; harvest it. Suggested split: (a) `ai/` infra + fixes,
  (b) arch-banter AI, (c) database layer, (d) moderation cog (alert-only rework),
  (e) cve/kev/legislation analyzers — each landing with tests. Drop the unrelated Solana/README
  commit into its own PR.
- Dependabot PR backlog (~15 open): merge the safe pins after Phase 0 CI actually gates them;
  note `discord.py 2.6.4 → 2.7.1` should be tested in staging (component/interaction changes).
