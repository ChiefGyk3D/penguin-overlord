# Role and engagement management: what is left after the role picker

**Status: self-assign roles shipped as the [role picker](ROLE_PICKER.md). Autorole, levelling, and reconciliation are still notes only.**

The server currently runs MEE6 for roles and engagement, and it hiccups ,
occasional gaps where a role is not applied, or a level-up goes missing.
The question is whether Penguin Overlord should take some or all of that
over, given it already has the pieces: a database, trust tiers, a metrics
endpoint, and a deployment the operator controls.

Nothing here is scheduled. This file exists so the idea is written down
with its trade-offs instead of being rediscovered later.

## What MEE6 is doing today

Worth confirming against the live server before building anything, but
broadly:

- **Autorole on join**: new members get a baseline role.
- **Reaction / self-assign roles**: pronouns, interests, ping opt-ins. Replaced by the role picker's dropdown panels; alert opt-ins are issue #25.
- **Levelling**: XP per message, level-up announcements, role rewards at
  thresholds.
- **Some moderation**: superseded by this bot's moderation cog.

## What taking it over would need

| Piece | Notes |
|---|---|
| Autorole | `on_member_join` plus a reconciliation pass, because the failure mode that matters is the join event being *missed*. A periodic sweep that finds members lacking the baseline role is the part MEE6 apparently lacks. |
| Self-assign roles | Done: `cogs/role_picker.py`, persistent `DynamicItem` selects with custom_id-encoded state, panels in JSON. |
| Levelling | XP table in the existing SQLite database, per-message with an anti-spam cooldown. Needs a migration path: **exporting existing XP from MEE6 is the hard part**, and starting everyone from zero would be unpopular. Worth checking what their export offers before committing. |
| Level rewards | Role grants at thresholds; must be idempotent and reconcilable for the same reason autorole is. |
| Permissions | The bot needs Manage Roles and a role positioned above everything it grants. Worth auditing what that widens. |

## Why it might be worth it

- One bot, one config, one log to read when something does not happen.
- The gaps are reconcilable: a sweep that compares intended state against
  actual state and fixes drift is straightforward here and is exactly what
  a hosted bot tends not to offer.
- Trust tiers already exist and are shared (`utils/trust.py`): tenure and
  role classes are computed once for moderation and the newcomer helper,
  and levelling would be a third consumer.

## Why it might not

- Role management is a **destructive** capability. Moderation here is
  deliberately alert-first and dry-run by default; granting Manage Roles is
  a different risk posture and deserves its own opt-in flags, its own audit
  log, and probably its own dry-run mode first.
- XP migration may simply not be possible cleanly, and a reset annoys
  everyone who earned a level.
- MEE6 working 95% of the time may beat a self-hosted replacement working
  99% of the time but going down when the homelab does. The bot already
  shares that fate for moderation, but roles failing closed is more
  visible to ordinary members.

## Suggested first step, when it comes up

Not a rewrite. Add a **reconciliation-only** mode: the bot watches, reports
what MEE6 *should* have done and did not: members missing the baseline
role, level rewards not applied: and posts that to the mod channel without
touching anything. That measures the size of the actual problem before
anyone commits to owning the whole feature, and mirrors how moderation was
introduced here (watch and report, earn trust, then enforce).
