# Penguin Overlord on the suite board and on current GYST

> **2026-10-08:** Penguin Overlord moved to the Renegade-Penguin "Bots & socials" board
> (organization project 4), not the suite board. Where this plan says "the suite board", read the
> bots board; its `Area` field already has the `Penguin Overlord` option, so step 1 below is done.

**Status: plan, written 2026-10-07.** The CI half ships with this plan (the
pull request that adds this file); the board half waits on five settings
only the maintainer can make, listed below in order. The feature plan this
repository is working to is the roadmap in draft PR #223; this file does not
restate it, it says how that roadmap becomes cards on a board that is kept
current without anyone typing.

## Where it stood on 2026-10-07

**git-your-ship-together (GYST): adopted, behind.** This repository has
called GYST's shared workflows since 2026-09-21 (PR #180 onward) and is in
GYST's `baseline/repos.txt`, so the weekly audit already covers it. What was
behind:

| Caller | Pinned | Current GYST tag |
|---|---|---|
| `ci.yml`, `release.yml`, `verify.yml`, `dependabot-auto-merge.yml` | v1.6.1 (2026-10-02) | v1.14.0 (2026-10-06) |
| `security.yml` | v1.9.0 (2026-10-04) | v1.14.0 |

Not a fault: GYST cut eight releases in five days and Dependabot waits
seven days before proposing a tag, so the bumps were due around 2026-10-11.
Two of those releases matter here. v1.13.0 runs gitleaks as a pinned binary
and asked every `security.yml` caller to re-pin; v1.8.0 made Trivy a gate on
the release build. v1.14.0 is also the first tag whose `project-sync.yml`
takes the board App by Client ID with its own Doppler scope, which is what
the board half needs.

**Scrum Around and Find Out (SAFO): not yet.** SAFO is a design (spec
approved 2026-10-07) and its worked example, the Renegade-Penguin suite
board, listed Hammunition and GYST only. Penguin Overlord had no
`project-sync.yml` caller either, so no issue or pull request of this
repository was on any board. The SAFO spec is amended the same day to list
this repository (`default_area: Penguin Overlord`); until SAFO ships, the
GYST caller is the only path, and this plan sets it up.

**The feature plan exists but is unmerged.** Three drafts are open:

| PR | What | Since |
|---|---|---|
| #223 | The roadmap revision: ticket desk and security event log designs, the quality-of-life list, the reordered improvements | 2026-09-28 |
| #238 | One-file fix for the CodeQL finding in `ai/guardrails.py` (#237) | 2026-10-05 |
| #239 | Optional `num_ctx` and `keep_alive`, second-stage placement on its own Ollama host | 2026-10-07 |

## What this pull request changes

1. Every caller pinned to GYST v1.14.0
   (`a5b834a6e03e0bf7187eeebfa84685498d73b139`). Each input the callers pass
   was checked against that tag's workflow files; none was renamed or
   removed. `release.yml` now calls `container-release.yml`, the name GYST
   gives new callers; `python-docker-release.yml` is the same workflow under
   its old name.
2. `.github/workflows/project-sync.yml`, the v1.14.0 caller shape: issue
   events, `pull_request_target` with no checkout and no run step (the two
   zizmor ignore lines are GYST's, with the reason beside them), the weekly
   reconcile, Area `Penguin Overlord`, the App key from Doppler
   `projects`/`prd`.
3. `.github/workflows/README.md` describes six callers and the three
   repository variables.
4. What the first CI run of the bump found, fixed in the second commit:
   hadolint (a gate since the container workflow gained it) wanted the
   `HEALTHCHECK` command in exec form and apt versions pinned; the first is
   done, the second is ignored on the two `RUN` lines with the reason (a
   `pkg=version` pin breaks the build the day Debian's security archive
   drops that version, and the base is already pinned by digest). gitleaks
   8.30.1 over the full history reported two leaks: the initial commit's
   documentation placeholders, which `.gitleaks.toml` already allowlisted in
   one of their two shapes (base64) and not the other (plain digits). Both
   are listed now; measured locally, the scan reports no leaks and still
   catches GYST's planted canary key.

zizmor at the persona GYST's workflow lint runs (`regular`) reports no
findings on the six files; hadolint 2.15.1 and gitleaks 8.30.1, the versions
GYST pins, were run locally on the fixed files.

## What only the maintainer can do, in order

`project-sync.yml` is red on every run until all five exist. Merge this
pull request after them, or merge first and expect red runs until then;
nothing else in the pull request depends on them.

1. **The Area option.** Add `Penguin Overlord` to the suite board's `Area`
   field in the Projects UI. The sync script refuses, before any change, an
   option it cannot find, and neither it nor SAFO's `bootstrap` ever edits
   an existing single-select field's options through the API (that mutation
   regenerates every option id and wipes the field across the board).
2. **The App on this account.** The board App is installed on the
   Renegade-Penguin organization. An organization project can hold items
   from a personal-account repository, but the App's token can only add
   what the App can read: install it on the `ChiefGyk3D` account with
   access to this repository, Issues and Pull requests read.
3. **Two repository variables** (Settings, Secrets and variables, Actions,
   Variables): `PROJECTS_APP_CLIENT_ID` (the App's Client ID, from its
   settings page) and `PROJECTS_DOPPLER_IDENTITY_ID` (the identity that
   reads `projects`/`prd`, separate from `DOPPLER_IDENTITY_ID`).
4. **The Doppler identity's subjects**, on the `gha-projects` service
   account's identity, in both forms GitHub issues:
   `repo:ChiefGyk3D/penguin-overlord:ref:refs/heads/main`,
   `repo:ChiefGyk3D/penguin-overlord:pull_request`, and the two
   `repo:ChiefGyk3D@<owner-id>/penguin-overlord@<repo-id>:...` forms. The
   audience is `https://github.com/ChiefGyk3D`. The `:pull_request` subject
   is acceptable on this scope and nowhere else because the config holds
   only the App key; the reasoning is in the GYST README under "The
   project-sync Doppler scope".
5. **One manual run.** `workflow_dispatch` the Project sync workflow once.
   The reconcile adds every open issue and pull request; check the board's
   Area filter shows them.

## Triage the scanner issues before the first reconcile

The reconcile adds every open issue. On 2026-10-07 that is 36, and 31 of
them are CodeQL findings filed by the security scan on 2026-09-28 and
2026-10-05, several in duplicate pairs. Left alone, the board's first view
of this repository is 31 scanner cards and five requests. Close or fix them
first, by group:

| Finding | Where | Count | Disposition |
|---|---|---|---|
| Clear-text logging of a secret | `utils/secrets.py` (two sites, filed twice), `scripts/feed-check/test_secrets.py` | 5 | Labelled false-positive; close with the reason, or add the CodeQL suppression so they stop being refiled |
| Implicit string concatenation in a list | `cogs/skid_detector.py` | 9 | One fix: the missing commas, or explicit `+`, in one list literal |
| Use of `exit` or `quit` | `scripts/feed-check/*` | 5 | `sys.exit`, one pass over the scripts |
| Overlapping or overly large character range in `_EMOJI_RE` | `ai/guardrails.py` | 2 | PR #238 |
| Unreachable statement | `xkcd_runner.py`, `comics_runner.py` | 2 | Delete the dead line |
| File not closed | `tests/unit/test_news_state.py`, `scripts/eval-moderation/eval_guard.py` | 2 | `with open(...)` |
| Comparison of identical expressions | `solar_runner.py`, `cogs/metrics.py` | 2 | Labelled false-positive (NaN checks); close with the reason |
| Surplus named argument to `str.format`, multiple definition | `cogs/newcomer_helper.py`, `utils/database.py` | 2 | Fix |

The five requests (#14 quiz, #24 breaches, #25 alert roles, #26 reaction
roles, #49 BBC duplication) are the real backlog; #49 is fixed on main and
waiting on a week of `#news` to close.

## The roadmap becomes cards

Issues are the source of truth for the board (SAFO's rule, and this
roadmap's own first paragraph). The roadmap in PR #223 names work that has
no issue, so it is invisible to a board. Merge order for the drafts: #223
(documentation only), #238 (one file), #239 (feature, 975 tests pass).
Then open one issue per item below, each linking the roadmap line and the
design note, so the sprint views mean something:

| Issue to open | Roadmap item | Design |
|---|---|---|
| Split the news aggregator from the community bot | Improvements 1 | the cloud section |
| Moderation out of dry-run: timeouts and warnings | Improvements 2 | `features/PHASE3_ENFORCEMENT_SPEC.md` |
| Ticket desk v1: panel, private threads, control card, transcripts | Improvements 3 | `features/TICKET_DESK.md` |
| Ticket desk fallback: heartbeat, deputy worker, no-bot pin | Improvements 3 | same |
| Con Recon phase 2b: Gemini verify and aggregator discovery | Improvements 4 | the events spec, section 10 |
| Security event log: stream, sinks, `#mod-log` | Improvements 5 | `features/SECURITY_EVENT_LOG.md` |
| Deploy script with rollback and nightly off-box backup | Improvements 7 | |
| Chip the big files into JSON and modules | Improvements 8 | |
| One mod card builder, one `/mod` tree | Improvements 9 | |
| Loki, Alloy and the alert rules | Improvements 10 | the event log note, last section |
| Quality of life 1 to 9, one issue each (`/whois`, report context menu, verify gate, raid guard and `/lockdown`, `/purge`, go-live alerts, `/status`, sticky guides, temp voice) | Quality of life | |
| The docs-audit bug list as one issue with a checklist | Small bugs | |

Existing issues stay as they are: #26 is the parent of the verify gate and
go-live alerts, #25 of the alert-role panel, #24 of the breach channel.

## A first sprint, as a proposal

The suite board's iterations run fourteen days from 2026-10-06. Nothing
below is decided; it is what fits the roadmap's own ordering (members
first, then built machinery, then structure) in one sprint of evenings:

1. Merge the three drafts and triage the scanner issues (above).
2. Complete the five maintainer steps; the board shows this repository.
3. `/whois` (quality of life 1) and the "Report to moderators" context menu
   (2): both are member-visible, both are the first consumers of the mod
   card builder, and both ship before the ticket desk they later feed.
4. Open the issues in the table; set Sprint on the three or four that are
   next, leave the rest in Backlog with their Area.

Ticket desk v1 and the security event log are each a sprint on their own
and come after; their designs are written and waiting on the merge of #223.

## What SAFO changes later

When SAFO's Action ships, GYST's `project-sync.yml` becomes a thin wrapper
around it and `reconcile` walks every repository in `board.yaml` from one
place, so this repository's caller shrinks to its event half or goes away.
The Area, the App installation and the Doppler subjects stay as set here;
nothing in this plan is undone by that move.
