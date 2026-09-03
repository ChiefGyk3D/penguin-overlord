# Phase 3 Enforcement Spec: Escalation, Notes, Persistent Log

Status: **specified 2026-08-29, not yet implemented.** Requirements set by
the server owner during the dry-run phase. Implementation is gated on the
calibration data showing the precision to justify any automation
(see AI_MODERATION.md "Graduating to enforcement").

## Hard floor (already enforced in code, stays forever)

- **Bans and kicks are human decisions. Always.** The policy layer
  hard-codes kick/ban as human-only in every configuration; Phase 3 does
  not change this.
- hate_speech / doxxing / self_harm / violence always page a human.
- `MOD_DRY_RUN=true` remains the instant kill switch.

## Escalation ladder (admin-configurable)

The AI's maximum autonomous action is configured by the admin per
category, bounded by the hard floor above (so: nothing, alert, or mute,
never ban):

1. **First offense** → alert/review only (default for everything).
2. **Repeat pattern** within the decay window → escalate per config:
   alert → mute → ban *proposal* (Approve/Dismiss buttons, human clicks).
3. Confidence thresholds per rung (`MOD_MIN_CONFIDENCE` today; per-action
   floors in Phase 3).

Mute mechanism to decide at implementation: Discord native timeout
(built-in expiry, used by current auto_timeout plumbing) vs assigning the
dedicated mute role `1019362425860014190` (survives rejoin, needs channel
permission overrides + expiry bookkeeping). Default proposal: native
timeout for short mutes, mute role for longer ones.

## Offense decay vs the permanent log

Two clocks, deliberately separate:

- **Punishment stacking decays.** Offenses stop counting toward
  escalation after `MOD_OFFENSE_DECAY`: allowed values 1, 3, 7, 14, 30
  days, 3, 6, 12 months, never. **Default: 30 days.** A user who was
  muted once in January is back to first-offense treatment in March.
- **The log is forever.** Infraction records (user, category, verdict,
  action taken, timestamps, mod notes) are never auto-deleted, pattern
  recognition needs history. Privacy floor preserved: message *excerpts*
  still purge after `MOD_RETENTION_DAYS` (90 default) and `/mod
  purge_user` still deletes stored *content*, the metadata skeleton
  (that an infraction happened, category, verdict) remains.

## Moderator notes

- `/mod note user:<user> text:...`: attach a note to a user's record
  (visible in alert embeds' prior-flags section and a `/mod history`
  view). Notes are part of the permanent log.
- Alert embeds for repeat offenders surface recent notes alongside prior
  flags.

## Trust-tier interaction

Tiers (shipped in Phase 2.5) modulate the ladder: e.g. new users can be
configured to escalate faster; trusted/creator tiers escalate only via
human decision. Exempt roles (mods `1018563764662046750`, stream mods
`1036071759339855902` when testing ends, bots `1018599520633880647`)
never enter the ladder.

## Server role map (for .env, recorded 2026-08-29)

| Role | ID | Mapping |
|---|---|---|
| Moderators | 1018563764662046750 | ping role; exempt after test phase |
| Stream Mods | 1036071759339855902 | trusted (exempt after test phase) |
| Content Creators | 1019354784920248431 | creator tier |
| New Users | 1018571935640199219 | informational; tenure computes 'new' |
| Leveled-up users | 1018625552837513286 | future MOD_MEMBER_ROLES option |
| Highest non-mod level | 1018625656055136347 | trusted tier |
| Bots (owner-run) | 1018599520633880647 | exempt (MOD_IGNORED_ROLES) |
| Mute role (planned) | 1019362425860014190 | Phase 3 mute mechanism |

Open questions for implementation time: mute mechanism choice (above);
whether role-based member/veteran mapping should supplement tenure
(MOD_MEMBER_ROLES / MOD_VETERAN_ROLES); per-category ladder overrides.
