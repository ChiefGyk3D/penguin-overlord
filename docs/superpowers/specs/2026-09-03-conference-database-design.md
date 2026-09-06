# Con Recon: the events database, conferences and meetups with a mod queue

Status: **approved design, 2026-09-03; open questions decided (section 14); phase 1
implemented (PR #161).** Sub-project 2 of the events work in `docs/ROADMAP.md`;
sub-project 1 (the role picker, PR #153, multi-region since PR #159) is what this
feature tags. Retires `cogs/eventpinger.py` and the `events/` CSV.

Revision 2 (same day) folds in the operator's direction: region roles are a set per
member, discovery must find small local cons, DEF CON Groups as a seed, a later DEF
CON track, and a roadmap appendix (section 15).

Revision 3 (2026-09-05): the whole feature is branded **Con Recon** wherever a member
or moderator reads it (help page, embed author line, docs, `/events status`), while
the typed surface stays `/events` and the settings stay `EVENTS_*`; Hacker Tracker
joins the discovery sources (section 7) and every event that came from it links back
to its Hacker Tracker listing.

## 1. Goals and non-goals

Goals:

- One crowd-sourced list of cybersecurity, ham radio and FOSS events, US and Canada
  first, in the bot's SQLite database. Members submit; a moderator approves before
  anything is visible. Nothing reaches a public channel without a human decision.
- Every row records where it came from: a member, the old calendar CSV, an AI
  discovery job, or an annual rollover.
- Members list and filter by state or province, country, topic and window.
- Reminders are channel posts that mention the role picker roles (country, US state,
  Canadian province) plus a topic role. Never an individual member mention. The
  operator's words: "I don't want the general public seeing who is tagged plus that
  could be hundreds of people tagged."
- Scheduled Gemini jobs verify dates and discover new events, feeding the mod queue.
  gemma4 (local, via `ai/`) does cheap relevance and near-duplicate checks. The Gemini
  key pool is a shared module other features (quiz generation, image moderation) reuse.
- Preserve what the CSV cog offered: its 29 events, its 7/3/1-day reminder idea (never
  switched on, no channel was ever configured), and the four lookups (`!events`,
  `!allevents`, `!nextevent`, `!searchevent`).

Non-goals: DMs to members (the roadmap lists them "after channel posts prove out");
events outside the US and Canada (the schema allows any country, the region mapping
and discovery seeds do not); ticketing, RSVPs or Discord Scheduled Events objects;
recurrence beyond "every year"; a web UI or export feed.

## 2. Approaches

**(a) SQLite table, slash commands, scheduled poster, no AI.** `/events submit`
inserts a pending row; a card lands in the mod channel with approve/reject buttons; a
daily poster mentions roles at fixed windows. Discovery and date verification are
manual. Pro: smallest surface, no external quota, trivially clean provenance, one PR.
Con: the list rots. Estimated dates (13 of the 29 CSV rows) stay estimated until a
human rechecks the site, and growth depends on members remembering to submit.

**(b) Approach (a) plus Gemini verify and discover jobs behind the mod queue.** Same
tables, commands and poster. Verify rechecks approved events against their source page
and proposes edits; discovery parses a short list of index pages and queues
candidates. Both produce mod cards; neither writes to an approved row. Pro: the list
stays current and grows without member effort; the key pool, quota tracking and
redaction are needed by two other roadmap items anyway; the human gate is identical to
(a), so the added risk is mod attention, not public content. Con: a Gemini quota to
manage, an HTML fetch path that needs size caps, more cards to look at.

**(c) External source of truth (shared Google Calendar or iCal), bot as mirror.**
Moderators maintain a calendar; the bot pulls the ICS feed into SQLite and posts from
the mirror. Pro: a calendar UI for free, easy sharing outside Discord. Con: submission
and approval move outside Discord, so the bot cannot own the queue, the audit trail or
the provenance (an ICS row does not say who added it or from where); filters by state
need a location-field convention nobody enforces; two systems to keep in sync; one
Google account becomes the single point of failure.

**Recommendation: build (b)** in two phases that are each shippable: phase 1 is
exactly (a); phase 2 adds the key pool and the two Gemini jobs. Tables, enums and
commands below are designed for (b) from the start so phase 2 adds code, not
migrations. (c) is rejected because it moves the approval queue and the provenance out
of the bot, which are the two things the operator asked for.

## 3. Data model

Schema lives in `utils/database.py` `_SCHEMA` (the single migration authority) with
`SCHEMA_VERSION` bumped to 3. New tables arrive via `CREATE TABLE IF NOT EXISTS`, so
`_migrate` needs no ALTER for v3. Queries live in a new `utils/events_store.py` class
that borrows the connection from `get_database()`; `ModerationDatabase` is unchanged.
The `events` table:

| column | type | notes |
| --- | --- | --- |
| id, guild_id | INTEGER | PK; guild |
| title | TEXT NOT NULL | as displayed |
| fingerprint | TEXT NOT NULL | normalized title (lowercase, ASCII, punctuation, year and edition numbers stripped) plus start year: `bsides detroit:2026` |
| topic | TEXT NOT NULL | `cyber`, `ham`, `foss`, `other` |
| start_date, end_date | TEXT NOT NULL | ISO dates; end equals start for one-day events |
| start_time, timezone | TEXT | `HH:MM` or NULL for all-day; IANA name, default `EVENTS_TIMEZONE` |
| date_status | TEXT NOT NULL | `confirmed`, `estimated` |
| city, region_code, country_code | TEXT | city required; ISO 3166-2 (`US-MI`, `CA-ON`), NULL for online; ISO 3166-1 alpha-2, required |
| scope | TEXT NOT NULL | `regional` (default) or `national`; picks the geo role |
| url, notes | TEXT | event site; free text, 500 chars max |
| recurrence, parent_event_id | TEXT, INTEGER | `none` or `annual`; parent set on rollover rows |
| status | TEXT NOT NULL | `pending`, `approved`, `rejected`, `cancelled`, `retired` |
| provenance | TEXT NOT NULL | `member`, `calendar`, `ai`, `hackertracker`, `rollover` |
| submitted_by | INTEGER | user id; NULL unless provenance is `member` |
| source_url, source_note | TEXT | page extracted from; CSV `Source` column or discovery key |
| ai_relevance | TEXT | gemma4 advisory label: `relevant`, `unclear`, `off_topic`, NULL when AI is off |
| review_message_id | INTEGER | the mod card |
| decided_by, decided_at, reject_reason | INTEGER, TEXT, TEXT | moderator, UTC time and reason of the decision |
| last_verified_at | TEXT | set by the verify job when the source page agrees |
| created_at, updated_at | TEXT NOT NULL | UTC ISO |

Indexes: `(guild_id, status, start_date)` for list and poster; `UNIQUE (guild_id,
fingerprint)` for dedupe; `(review_message_id)` for buttons; `(status, created_at)`
for `/events pending`.

`rejected` rows stay 180 days so discovery cannot re-queue the fingerprint, then the
sweep deletes them; `cancelled` is public with a strike-through and sends one notice;
`retired` is the end state after the event ends, never shown. Supporting tables:

- `event_reminders (id, event_id, window TEXT, channel_id, message_id,
  roles_mentioned TEXT, posted_at)` with `UNIQUE (event_id, window)`. `window` is a
  configured day count as a string (`30`, `7`, `1`) or `changed` or `cancelled`. The
  unique key is the dedupe: a window posts once per event, ever, across restarts and
  date edits.
- `event_proposals (id, event_id, proposed_json, review_message_id, status, decided_by,
  decided_at, created_at)`: the verify job's suggested edits, `status` in `open`,
  `applied`, `ignored`.
- `event_audit (id, event_id, actor_id, action, before_json, after_json, created_at)`.
  `action` in `submit`, `import`, `discover`, `rollover`, `approve`, `reject`, `edit`,
  `cancel`, `retire`, `expire`, `verify_match`, `verify_propose`, `apply`, `ignore`.
  `actor_id` is a user id or 0 for the bot. Never purged.
- `event_discovery_runs (id, source_key, started_at, finished_at, key_id,
  fetched_bytes, candidates, queued, dup_skipped, offtopic_skipped, error)`.
- `ai_key_usage (key_id TEXT, day TEXT, requests, errors, cooldown_until TEXT,
  disabled INTEGER, PRIMARY KEY (key_id, day))`. `key_id` is the first 8 hex chars of
  SHA-256 of the key; the key itself is never stored. `day` is the date in
  `America/Los_Angeles`, where Google resets free-tier quota at midnight.

### Geography, recurrence, timezone

`assets/events/regions.json` maps region codes to picker role names (`"US-MI":
"Michigan"`, `"CA-ON": "Ontario"`) and country codes to `"United States"`, `"Canada"`.
A unit test asserts every role name in that file exists in exactly one panel under
`assets/role_panels/`. The events cog never creates roles; `/roles post` does. Topic
roles come from a new non-exclusive panel `assets/role_panels/event_topics.json` with
roles `Cybersecurity Events`, `Ham Radio Events`, `FOSS Events`; members opt in, and
topic `other` mentions no topic role.

A region role means "ping me for events here", not "I live here". Since PR #159 the
picker panels are non-exclusive: a member in Ohio who drives to GrrCON holds Ohio and
Michigan, and someone who flies to DEF CON, CCC or Cyber Week holds Nevada, Germany and
Israel too. There is no home role and the events system never needs one; a regional
event mentions its region role and reaches everyone who opted into that region. This
is also why regional events mention the region role only (section 14, question 3): the
member already chose the set of places they want to hear about.

`recurrence = annual` rows roll forward. On the day after `end_date` the nightly sweep
marks the row `retired` and inserts a copy with `provenance = rollover`,
`parent_event_id` set, `status = pending`, `date_status = estimated`, and dates shifted
to the same ordinal weekday next year (third Saturday of April stays the third
Saturday of April). The verify job then checks it against `url`; a mod approves it
like any other pending row. At most one rollover per parent.

Dates are calendar dates. "Days until" is `start_date` minus today's date in
`EVENTS_TIMEZONE` (default `America/New_York`, the operator's zone), so a reminder for
a Saturday event goes out the same Eastern morning whatever the event's own zone. When
`start_time` is set, posts render a Discord `<t:unix:F>` timestamp built from date, time
and the row's `timezone`, so each viewer sees local time.

## 4. Command tree

One `app_commands.Group` named `events` with no `default_permissions` (members need
it). Mod subcommands check `moderate_members` at runtime with
`app_commands.checks.has_permissions`, the same permission `/mod` requires. The CSV
cog's prefix forms are not carried over; `/roles` and `/mod` are slash-only and this
group follows them. Member subcommands (ephemeral unless noted):

| command | parameters | replaces |
| --- | --- | --- |
| `/events list` | `days` (default 30, max 365), `topic` choice, `region` autocomplete, `country` choice | `!events`, `!allevents`: public paginated embed, 5 per page, the old paginator's buttons |
| `/events next` | `topic` | `!nextevent` |
| `/events search` | `query` over title, city, region name | `!searchevent` |
| `/events submit` | `title`, `topic` choice, `start` (YYYY-MM-DD), `end` (optional), `city`, `region` autocomplete, `url`, `notes` (optional) | new |
| `/events mine` | none | new: the caller's submissions with status and reject reason |

Slash parameters rather than a modal because a discord.py 2.7 modal has no select:
`topic` needs choices and `region` needs autocomplete over `regions.json` plus
`Online` (stores `region_code = NULL`). A member may have at most
`EVENTS_MAX_PENDING_PER_MEMBER` open submissions. Moderator subcommands:

| command | parameters | effect |
| --- | --- | --- |
| `/events pending` | none | open cards oldest first with jump links, like `/mod pending`; reposts any card whose message is gone |
| `/events approve` | `id` | same as the card button |
| `/events reject` | `id`, `reason` | same as the card button |
| `/events edit` | `id`, then a modal (title, dates, location, url, notes) | any status; writes an audit row |
| `/events cancel` | `id`, `reason` | approved to cancelled; posts one notice |
| `/events status` | none | flags, dry-run, counts by status, next poster run, mention permission check, last five discovery runs, key pool summary |
| `/events discover` | `source` (optional) | run discovery now; needs a usable key but not `EVENTS_DISCOVERY_ENABLED`; once per hour |

## 5. Mod approval flow

1. A submission (member, discovery, rollover) inserts a `pending` row. Duplicate
   fingerprint: the member is told "That matches #12, BSides Detroit 2026 (approved)"
   with the existing row's status, and nothing is inserted; discovery counts it as
   `dup_skipped`.
2. If `AI_EVENTS_ENABLED`, gemma4 labels relevance and, for rows whose fingerprint is
   within edit distance 3 of an existing one, answers "same event?" The answers are
   advisory text on the card; they never block or auto-reject.
3. A card posts to `EVENTS_REVIEW_CHANNEL_ID` (default `MOD_ALERT_CHANNEL_ID`): title,
   topic, dates with status, city and region, url, a provenance line ("Submitted by
   @name", "Discovered from bsides.org", "Rolled over from #12"), AI labels, and the
   roles a reminder would mention. Buttons are `DynamicItem`s with `custom_id =
   event:<id>:<verb>` for `approve`, `reject`, `edit`, restart-safe like the
   moderation review buttons. Proposal cards use `eventprop:<id>:apply|ignore`.
4. Approve requires `moderate_members`. The first click decides (no vote threshold;
   events are not enforcement): the row goes to `approved`, `decided_by` and
   `decided_at` are set, an audit row is written, the card gets a resolution footer
   and loses its buttons. Reject opens a modal for the reason, then does the same with
   `rejected`. Edit opens the `/events edit` modal, saves, and re-renders the card
   still pending. A later click on a decided card gets "Already decided by @mod at
   time", ephemeral, as moderation does.
5. The submitter is not messaged; `/events mine` shows the outcome. Audit trail:
   `event_audit` rows plus the card's edit history in Discord. `/events edit` on an
   approved row writes an audit row and, if a dated reminder was already sent, posts
   one `changed` reminder (section 6).

## 6. Reminder scheduling

- One `tasks.loop` aligned to `EVENTS_POST_AT` (default `09:00`) in `EVENTS_TIMEZONE`,
  using the clock-aligned pattern of `welcome_greeter.py`; a restart never posts
  early. Per run: for every `approved` event whose `days_until` equals a value in
  `EVENTS_REMINDER_DAYS` (default `30,7,1`), post one reminder unless
  `event_reminders` already has `(event_id, window)`. Insert the row first; if the send
  fails, delete it so the next run retries. A missed window (bot down that morning) is
  skipped, not backfilled; nothing posts for an event that already started.
- Content: an embed like the old `nextevent` card (title, countdown, dates with the
  confirmed or estimated marker, location, link) with the role mentions in the message
  text above it. Roles: the topic role, plus the region role when `scope = regional`
  or the country role when `scope = national`; online events get the topic role only.
- Every send uses `AllowedMentions(everyone=False, users=False, roles=[resolved Role
  objects])`. `users=False` is the hard guarantee: a title containing `<@id>` cannot
  ping anyone. Picker roles are created non-mentionable, so the bot needs "Mention
  @everyone, @here and All Roles" in `EVENTS_CHANNEL_ID`; `/events status` says so
  when it is missing.
- Missing role: names resolve at post time from `regions.json`. If a role does not
  exist yet (panel not posted), the post still goes out with the plain name in text
  ("Michigan"), one WARNING per role per day is logged, and
  `penguin_events_role_missing_total` increments. Nothing is created.
- `changed` and `cancelled` windows post at most once each, immediately on the edit or
  cancel, and only if a dated reminder was already sent (otherwise nobody saw it).
- Weekly digest: Mondays at `EVENTS_POST_AT`, every approved event in the next 30 days
  grouped by topic, no role mentions; `EVENTS_DIGEST_ENABLED` controls it. Nightly
  sweep at 03:00 `EVENTS_TIMEZONE`: retire ended events, create rollovers, mark pending
  rows older than `EVENTS_PENDING_EXPIRE_DAYS` as `rejected` with reason `expired`,
  delete rejected rows older than 180 days.

## 7. AI jobs

**gemma4 (local, through `ai/manager.py`).** `events` joins `KNOWN_FEATURES`; config
is `AI_EVENTS_*` with the usual layering. Two prompts, both `raw=True` with a one-word
answer the cog parses: relevance (`relevant`, `unclear`, `off_topic`) and
near-duplicate (`same`, `different`). Both are advisory. If Ollama is down the labels
are NULL and the card says "AI unavailable". `events` joins `LOCAL_ONLY_FEATURES`
because the relevance prompt carries member text; discovery input is public web text
and goes to Gemini by design.

**Gemini (remote, through the key pool).** In both jobs the bot fetches the page with
`utils/http.py` (timeout 20 s, response cap `EVENTS_FETCH_MAX_BYTES`, HTML reduced to
visible text) and sends the text to Gemini with a fixed extraction prompt asking for a
JSON array of `{title, start, end, city, region, country, url, topic}`. Gemini never
fetches anything itself.

- Verify job, Sundays 03:00 `EVENTS_TIMEZONE`: every approved event with a `url`,
  starting within 120 days, whose `date_status` is `estimated` or whose
  `last_verified_at` is older than 60 days. If the extraction matches the row, set
  `last_verified_at` and write `verify_match` (not member-visible, no human needed).
  If it differs, insert an `event_proposals` row and post a card showing old and new
  values with Apply / Ignore buttons. Apply is the human decision: it edits the row,
  writes `apply`, and is the only job-driven path by which `date_status` becomes
  `confirmed`.
- Discovery job, Mondays 03:00 `EVENTS_TIMEZONE`: for each entry in
  `assets/events/discovery_sources.json` (`key`, `url`, `topic`, `countries`), extract
  candidates, drop any outside `countries`, drop any whose fingerprint exists in any
  status, label the rest with gemma4, and insert them as `pending`, `provenance = ai`,
  `source_url` set. At most `EVENTS_DISCOVERY_MAX_QUEUE` new cards per run; the rest
  wait a week. Nothing either job produces is visible to members until a moderator
  approves or applies it.

### Discovery sources: the small cons are the point

The operator's test case is not DEF CON, which everyone already knows about; it is
Hackers Teaching Hackers (Columbus), Queen City Con (Cincinnati, new) and GrrCON
(Grand Rapids): the cons a national aggregator lists late or never, and the ones a
local member would drive to. Three layers, cheapest first:

1. **Curated seed file `assets/events/known_events.json`**: `{title, url, topic,
   city, region, country, usual_month}` for every con the operator and the mods
   already know, starting with the three above and the 29 CSV rows' URLs. This is a
   verify-job input, not a discovery input: each entry's `url` is rechecked on the
   Sunday schedule so an announced date becomes a proposal card without anyone
   submitting it. Adding a con to the list is a one-line PR or, later, `/events seed`.
2. **Hacker Tracker** (hackertracker.app, by junctor, the DEF CON schedule app that now
   carries many BSides chapters, Ekoparty, 39C3, CactusCon, SaintCon and others).
   Organizers enter their own data through junctor's ConfMgr, so it is the one source
   whose rows are maintained by the con itself. Checked 2026-09-04: the app's Firestore
   project `junctor-hackertracker` answers an unauthenticated GET at
   `https://firestore.googleapis.com/v1/projects/junctor-hackertracker/databases/(default)/documents/conferences`
   with, per conference, `code`, `name`, `start_date` and `end_date` as `YYYY-MM-DD`,
   RFC3339 timestamps, an IANA `timezone`, `link` (the con's own site) and `hidden`.
   No model is needed; it is a JSON parse. Rules:
   - Poll it in the Monday discovery run before any page fetch. Skip `hidden` rows
     and anything already ended. Match existing rows first by the code stored in
     `source_note` (`ht:<code>`), then by fingerprint; a date change on a matched
     approved row becomes a proposal card exactly like the verify job's.
   - New rows insert as `pending`, `provenance = hackertracker`,
     `url = link` (falling back to the Hacker Tracker page when `link` is empty),
     `source_url = https://hackertracker.app/<code>`, `date_status = confirmed` (the
     organizer set the dates). The conference document has no city or country, so
     the card says "location: fill in" and a moderator adds it on Approve or Edit; the
     `locations` subcollection is tried first for a venue string when it is not empty.
   - Every card and public embed for a `hackertracker` row carries a second link,
     "On Hacker Tracker", to `source_url`. Members get the con's own site as the
     title link and the schedule app one line below. The deep links
     (`/<code>`, `/<code>/schedule`, `/<code>/content/<id>`) are a client-rendered
     app on GitHub Pages: fine for a human clicking from Discord, a 404 to a bare
     fetch, so the bot links to them and never fetches them.
   - The read is undocumented and the data carries no reuse licence (the code repos
     are MIT and GPL-3.0; the data has no stated terms). Treat it as a source that can
     vanish: cache the last good response in `DATA_DIR`, log one WARNING per run when
     it fails, never page or hammer it (one list call per week), and say hello in
     junctor's Discord (linked from `github.com/junctor/hackertracker-about`) before
     the job goes live. The repos are active (pushes in August 2026), and
     `hackertracker-export` plus `hackertracker-info` are the same data as static JSON
     for the DEF CON family only, a fallback if the Firestore read is ever closed.
   - It only knows cons that onboarded, which skews to the well-run ones. Hackers
     Teaching Hackers and Queen City Con still come from the seed file and infosecmap;
     Hacker Tracker is the layer that makes BSides Detroit and Burning River Cyber
     Con show up the week their organizers publish.
3. **Aggregator fetchers** in `discovery_sources.json`: infosecmap.com first (it lists
   regional US cons and BSides by state), then the bsides.org event index, the ARRL
   hamfest and convention search, the Linux Foundation events list, Meetup and
   Eventbrite category searches per seeded city. Each source records the parser it
   needs: most of these are structured pages or JSON endpoints that
   `utils/http.py` plus a few lines of parsing handle with no model at all. Gemini
   sees a page only when a source is marked `extract: llm`.
4. **Region sweeps** (phase 2b, after the first three prove out): for each region that
   has at least one opted-in member, one Gemini extraction over a search-results
   page for `"<region> cybersecurity conference <year>"`. Capped by
   `EVENTS_DISCOVERY_MAX_QUEUE`, and the reason the key pool exists.

**DEF CON Groups** get their own table later (section 15) rather than rows in
`events`; a group is a place, not a date. Seed: `github.com/DefconParrot/DefconGroups`
(checked 2026-09-03: hand-maintained markdown tables plus xlsx, about 293 groups,
DC614 Columbus, DC937 Dayton, DC216 Cleveland and DC330 Stark County present, last
push July 2025, no license). Every row carries a `forum.defcon.org/node/<id>` join
link, and that node id is the stable key for scraping `forum.defcon.org/social-groups`
without a model. Use the repo as a seed to verify against the forum, not as a
redistributed dataset, and keep only group name, city, website and forum link:
the point-of-contact emails in it are personal addresses and never enter the bot.
The official groups site misses groups (the operator's own local one), so the store
carries an operator overrides file and a periodic diff against the forum.

### Which model does what

Discovery is mostly a fetch-and-parse problem. The model's job is extraction over
text the bot already fetched (a page becomes `[{title, start, end, city, region,
country, url, topic}]`), which is a small, low-stakes task because every result lands
in the mod queue where a wrong extraction costs one click. Gemini Flash on the free
tier, twice a week, is enough for that, and the key pool keeps it inside quota.

What a stronger model would add is open-ended research ("a hamfest within 200 miles
of Detroit in October that none of the sources list") and adjudicating contradictory
dates. Neither belongs on a schedule. The extraction call sits behind one function,
`ai/extract.py: extract_events(text, source) -> list[dict]`, with the provider chosen
by config, so a Claude key can be added later as an on-demand `/events discover
--deep` a moderator triggers. If it is ever added: its own key, a spend cap in the
console, Doppler like every other secret, and that one call site as the only path
to it. Nothing in phase 1 or 2 depends on it.

**Key pool, `ai/keypool.py`.** Keys from `GEMINI_API_KEYS` (comma-separated) with
`GEMINI_API_KEY` appended if set, resolved through `utils/secrets.py` like the existing
key. `GeminiProvider` takes the pool; `AIManager` gains `generate_remote(feature, ...)`
for jobs that want Gemini directly rather than as a fallback. Per-key daily quota
`GEMINI_KEY_DAILY_QUOTA` (default 200 requests, under the free tier's 250 for the flash
models); usage persists in `ai_key_usage`, so a restart does not reset the count.
Rotation is round-robin over keys with quota left and no active cooldown. HTTP 429:
cooldown 60 s, doubling per consecutive hit, capped at 1 hour. HTTP 400, 401, 403:
`disabled` for the day, one ERROR log. With no usable key the call returns None and the
job stops early, logging how many items remain. Redaction: a `logging.Filter`
installed by `utils/logging_setup.py` replaces every configured key value with
`[GEMINI_KEY:<key_id>]` in every record; only `key_id` appears in metrics,
`ai_key_usage` and `/events status`.

## 8. Migration from the CSV

1. `scripts/import-events-csv.py --guild <id> --csv
   events/security_and_ham_events_2026_with_types.csv`, run once with the bot stopped.
   Each of the 29 rows becomes `status = approved`, `provenance = calendar`,
   `recurrence = annual`, `scope = national` for DEF CON and `regional` otherwise,
   `topic` from `Type` (Cybersecurity to `cyber`, Ham Radio to `ham`), `date_status`
   from `Date Status`, `source_note` from `Source`, `region_code` from the two-letter
   code (`MI` to `US-MI`; `ON` to `CA-ON` with `country_code = CA`), a missing end
   date copied from start, `decided_by = 0`, and an `import` audit row. Rows already
   in the past are imported too: the first sweep retires them and creates their 2027
   rollovers, which is how the list survives the year boundary. The script is
   idempotent (fingerprint unique) and prints what it inserted or skipped.
2. The same cutover PR deletes `cogs/eventpinger.py` and `events/`, replaces the Event
   Pinger page in `cogs/help_categorized.py` with an `/events` page, and updates the
   README section and `reference/COMMANDS.md`.

## 9. Configuration

| variable | default | meaning |
| --- | --- | --- |
| `EVENTS_ENABLED` | `false` | master switch: commands, poster, jobs |
| `EVENTS_DRY_RUN` | `true` | member-facing posts are logged, not sent; mod cards still post |
| `EVENTS_CHANNEL_ID` | unset (required when enabled) | reminders and digest |
| `EVENTS_REVIEW_CHANNEL_ID` | `MOD_ALERT_CHANNEL_ID` | mod cards |
| `EVENTS_TIMEZONE` | `America/New_York` | window math and schedules |
| `EVENTS_POST_AT` | `09:00` | daily poster and Monday digest time |
| `EVENTS_REMINDER_DAYS` | `30,7,1` | windows, days before start |
| `EVENTS_DIGEST_ENABLED` | `true` | Monday digest |
| `EVENTS_MAX_PENDING_PER_MEMBER` | `3` | open submissions per member |
| `EVENTS_PENDING_EXPIRE_DAYS` | `30` | pending rows auto-rejected after this |
| `EVENTS_DISCOVERY_ENABLED` | `false` | Monday discovery job |
| `EVENTS_VERIFY_ENABLED` | `false` | Sunday verify job |
| `EVENTS_DISCOVERY_MAX_QUEUE` | `10` | cards per discovery run |
| `EVENTS_FETCH_MAX_BYTES` | `524288` | page cap for both jobs |
| `AI_EVENTS_ENABLED` | `false` | gemma4 labels (needs `AI_ENABLED`) |
| `AI_EVENTS_MODEL` | `AI_DEFAULT_MODEL` | local model for labels |
| `GEMINI_API_KEYS` | unset | pool, comma-separated |
| `GEMINI_KEY_DAILY_QUOTA` | `200` | requests per key per Pacific day |

Both Gemini jobs require `EVENTS_ENABLED`, their own flag, and at least one usable
key; with no key the cog logs one WARNING at load and the job stays off.

## 10. Error handling

- Database error on a command: log with traceback, ephemeral "Could not save that;
  try again in a moment." Insert first, post second: on a card post failure
  `review_message_id` stays NULL and `/events pending` reposts it.
- `discord.Forbidden` on a reminder: log, `penguin_events_post_errors_total`
  increments, the `event_reminders` row is deleted, the run continues. A missing
  channel disables the poster until restart and shows in `/events status`. Invalid
  dates, end before start, start more than two years out, or a url without
  `http(s)://`: rejected at submit with the specific reason.
- Discovery: a fetch failure or non-JSON extraction records `error` on the run row and
  moves to the next source; a candidate missing `title` or `start` is dropped and
  counted. Every loop wraps per-event work in try/except so one bad row cannot stop the
  day's posts, matching the news schedulers.

## 11. Testing strategy

- Pure functions in `utils/events_logic.py` with no Discord or DB dependency:
  fingerprint, days-until with an injected `today`, window selection, rollover date
  shift, region-to-role resolution, mention text and `AllowedMentions` construction
  (asserts `users=False` always), CSV row mapping. The fake clock is a callable
  returning a fixed `datetime`, the greeter tests' pattern.
- Store tests on `aiosqlite` at a temp path via `BOT_DATABASE_PATH` (the
  `tmp_data_dir` fixture): fingerprint dedupe, one post per window under repeated runs
  and simulated restarts, an audit row per state change, key usage rollover at Pacific
  midnight.
- Golden files under `tests/data/events/`: the 29-row import result
  (`import_golden.json`); per discovery seed, a saved text extract, the recorded Gemini
  response and the expected candidates (`discovery_<key>_golden.json`), replayed
  through a fake provider. Regenerated on purpose only, diff reviewed, like
  `moderation_golden.json`.
- Cog tests with a fake bot: card render, button permission check, double-click
  handling, dry-run logging of what would post and to which roles, missing-role text.

## 12. Observability

Added to `utils/metrics.py` in the existing style. Counters:
`penguin_events_submissions_total{provenance}`,
`penguin_events_decisions_total{decision}` (`approve`, `reject`, `expire`, `apply`,
`ignore`), `penguin_events_reminders_total{window}`, `penguin_events_post_errors_total`,
`penguin_events_role_missing_total{role}`,
`penguin_events_discovery_candidates_total{outcome}` (`queued`, `dup`, `offtopic`,
`invalid`), `penguin_gemini_requests_total{key_id, outcome}` (`ok`, `rate_limited`,
`auth`, `error`). Gauges: `penguin_events_pending`, `penguin_gemini_quota_remaining{key_id}`.
INFO log lines for every post, decision and job run carry the event id and title; key
ids only, never keys.

## 13. Rollout

1. Phase 1 PR: schema v3, store, commands, cards, poster, digest, sweep, import
   script, cog deletion. Deploy with `EVENTS_ENABLED=true`, `EVENTS_DRY_RUN=true`, run
   the import, post `event_topics` with `/roles post`. Watch the dry-run log for a
   week: it prints each reminder it would have sent and the exact role names it
   resolved or failed to resolve. Then set `EVENTS_DRY_RUN=false` once the state and
   province panels are posted and the mention permission is granted.
2. Phase 2 PR: key pool, redaction filter, verify and discovery jobs, both default
   off. Enable verify first (it only proposes edits to rows that already exist), then
   discovery a week later. `/events discover` lets the operator run one source by hand
   before the schedule takes over.

## 14. Decisions (operator, 2026-09-03)

The five questions from revision 1, each closed on the recommendation:

1. Reminder windows: `30,7,1`. Conferences need travel lead time; `EVENTS_REMINDER_DAYS`
   changes it without code.
2. Who may submit: any member, at most 3 open submissions. The mod queue is the filter,
   and newcomers often join because of an event.
3. Geo mention for regional events: the region role only. Members now hold every
   region they want pings for (section 3), so a country mention on top would be the
   "hundreds of people" problem one level up.
4. Weekly Monday digest: on by default, no role mentions.
5. Discovery seeds: ship phase 2 with the sources in section 7, default off, turn
   discovery on after the verify job has run clean for a week. infosecmap and the
   curated small-con file come before the three national aggregators.

## 15. Later tracks (recorded so the phase 1 schema leaves room)

None of these is in phase 1 or 2. They are here because each one constrains a
decision above, and the operator has said where his head is going.

- **DEF CON track.** Starts a few months before the con: villages as they are
  announced, the speaker list, parties, a prep checklist. Shares the fetch-and-extract
  layer with discovery. Needs: an event to own many sub-items (a `event_items` table
  keyed by `event_id` with `kind` in `village`, `talk`, `party`, `task`), per-event
  sub-feeds and a thread or channel per con. `scope = national` and `parent_event_id`
  already give it a hook; nothing else in the phase 1 schema should assume one row is
  one post.
- **DEF CON Groups directory.** Own table (`dc_groups`: number, city, region_code,
  country_code, website, forum_node_id, source, overrides), seeded and scraped as in
  section 7. `/events groups <region>` answers "is there a DC group near me" and the
  regional reminder can add "your local group is DC614" when one exists.
- **Static search site.** A read-only export (JSON plus a small static site on
  Netlify or similar) rebuilt by a bot job whenever an approved row changes, so
  searching and browsing happen in a browser and the bot's list command can say
  "for anything more than the next 30 days, use the site". Low priority; the `events`
  table is the source of truth and the site is a mirror, never the other way round.
- **Panel consolidation.** US states and Canadian provinces into one panel: 3 plus 1
  menus fits the 5-per-panel cap. JSON merge plus a repost, no code. Not a priority.
- **Server onboarding.** The server is a click-to-verify setup from before Discord's
  native Onboarding (Community servers: welcome screen, questions that assign roles
  and reveal channels, rules acceptance before the first channel). Region and topic
  roles could be handed out there instead of, or as well as, the panels; the greeter
  already keys on the screening flip, so it keeps working either way. Design pass
  once the events system makes region roles matter to new members.
- **Bots still to replace.** LinkShield AI (link scanning) is next; the moderation
  pipeline already inspects message content, so this is likely a cog that expands
  and scores links rather than a new subsystem. A pass over top.gg's cybersecurity
  tag for what else the community leans on is queued behind it.
