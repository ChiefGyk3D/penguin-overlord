# How this project is planned

The work is planned the way a small team plans software: a written backlog, a size on every item, two-week sprints, a review at the end of each, and a definition of done. The plan lives in GitHub, next to the code.

- **The board:** the [Penguin Overlord project](https://github.com/users/ChiefGyk3D/projects/5) (Sprint board, Sprint plan, Roadmap, Backlog and Agents at work views).
- **The backlog:** this repository's [issues](https://github.com/ChiefGyk3D/penguin-overlord/issues), grouped into epics.
- **The ordering and the reasoning:** [docs/ROADMAP.md](../ROADMAP.md). The board holds sizes, sprints and status; the roadmap says why things are in that order.
- **The board as code:** `board.yaml` in the repository root. [Scrum Around and Find Out](https://github.com/ChiefGyk3D/scrum-around-and-find-out) (SAFO) creates and checks the board from it.

## The shape of the plan

| Level | What it is | Where |
|---|---|---|
| Epic | One theme, labelled `epic`, with sub-issues. Its start and target dates draw its bar on the Roadmap view | Issue |
| Issue | One piece of work with a reason, a "done when" list and the gate it waits on | Sub-issue of an epic |
| Sprint | A two-week slice, Tuesday to Monday | Board field |

The ten epics are: ship what is built, community features, ticket desk, security and mod tooling, Con Recon, news and alert hygiene, structure and platform, observability, cloud, and process.

Parked ideas (the eraser bot, multi-platform moderation, social-graph memory, DM reminders, international events, ban appeals) stay in the roadmap and have no issue until one is real.

## Sprints and what "scheduled" means

Sprint 1 starts on Tuesday 2026-11-03; eight are defined, through 2027-02-22. Anything with a sprint is scheduled. Anything without one is backlog: wanted, ordered by priority, not promised. The cloud move is deliberately unscheduled until the bot/news split is done and the provider is decided.

## Capacity

The maintainer has a day job, works on this in evenings and at weekends, and runs other projects. The sprint load counts the maintainer's own hours: the items whose Agent is **You**. Penguin Overlord shares his time with other boards, so keep it to about 3 to 7 hours in a sprint. Agent items are limited by agent budgets and review time, with at most three in flight, each on its own branch and worktree. Sizes: **S** about 2 hours, **M** about 5, **L** about 12, **XL** about 30. An XL is split before it is scheduled.

Costs matter here too: this is a sole-operator project. Anything that needs a bigger model is precomputed on a schedule (Gemini free tier) and stored, never called per request.

## The flow of an issue

| Status | Meaning |
|---|---|
| Backlog | Not scheduled |
| Next | Scheduled for a sprint |
| In progress | Being worked, or a draft pull request is open |
| In review | A pull request is open and checks and reviews are running |
| Blocked | Needs the maintainer or an answer from outside |
| Done | Closed or merged, with the date in **Done on** |

The board is a user-owned project, so no App can write it. It is kept current by `safo --board board.yaml reconcile`, run weekly from a systemd user timer on the maintainer's login (`examples/systemd` in SAFO). Sprint, size, area, priority and agent are set by hand when an issue is planned.

## Definition of ready

An issue goes into a sprint when it has a reason, a "done when" checklist, a size, an owner (the maintainer or an agent) and its gate named. An issue that cannot say what done looks like is a question, not a task.

## Definition of done

1. Checks are green, including the `CI green` gate and the secret scan.
2. Tests exist for what changed, and a test that should fail without the change was shown to fail.
3. `docs/reference/COMMANDS.md` and the roadmap say what is now true, in the same pull request.
4. Security-relevant changes (moderation, the event log, tickets, anything handling tokens) get a Codex adversarial review before merge, even when CI and the Sonnet review are green.
5. A change that touches the live bot says how it is deployed and how it rolls back.
