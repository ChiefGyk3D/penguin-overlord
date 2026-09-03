# News System

Penguin Overlord aggregates 220+ public RSS, Atom and JSON feeds across 11
categories and posts them to per-category Discord channels. No feed needs an
API key. This is the canonical guide; the command table lives in
[COMMANDS.md](../reference/COMMANDS.md) and the timer install in
[SYSTEMD.md](../deployment/SYSTEMD.md).

Counts below were measured from the `*_SOURCES` dicts in the cogs on
2026-09-02. Feeds churn, so treat them as a snapshot and use
`/news list_sources <category>` for the live list.

## Architecture

Three pieces, one config file.

**`cogs/news_manager.py` is the configuration hub.** It owns
`data/news_config.json` (one entry per category: `enabled`, `channel_id`,
`interval_hours`, `minute_offset`, `sources`, `approved_roles`,
`concurrency_limit`, `use_etag_cache`) and the `/news` slash group. On load
it reads `NEWS_<CATEGORY>_CHANNEL_ID` from the secrets backend (Doppler, AWS,
Vault) and then the environment; an env value overrides whatever is in the
file, and on a fresh install a category is auto-enabled when its env var is
set.

**One cog per category does the fetching.** Each defines its source dict,
keeps its own state file, and exposes a manual-fetch slash command. Every cog
asks `NewsManager` for its channel, interval and disabled sources rather than
carrying its own copy.

**Two schedulers exist; run one.** Each cog starts an in-bot `@tasks.loop`
poster, and `install-systemd.sh` can also write one
`penguin-news-<category>.timer` per category that runs
`penguin-overlord/news_runner.py --category <category>` as a oneshot. Both
read the same `news_config.json`, but they keep separate dedupe state, so a
host that runs both posts every story twice. The `NEWS_AUTO_POST` gate
(`utils/news_dedupe.py`, default `true`) parks the in-bot loops; production
sets `NEWS_AUTO_POST=false` and lets the timers own posting. The `/news`
settings still drive what the timers post. `cve_enable` and `kev_enable`
are explicit admin actions and start their loops regardless of the gate.

KEV is the exception to "one timer per category": the installer never writes
`penguin-news-kev.*`; it writes `penguin-kev.{service,timer}` running
`kev_runner.py` instead. See SYSTEMD.md, "KEV is posted by one timer, not
two".

## Categories

| Category key | Cog | Sources | Representative feeds |
|---|---|---:|---|
| `cybersecurity` | `cybersecurity_news.py` | 115 | 404 Media, The Hacker News, BleepingComputer, Dark Reading, WeLiveSecurity, Malwarebytes Labs |
| `vendor_alerts` | `vendor_alerts.py` | 34 | Zscaler status (5 JSON feeds), Datadog regions, AWS, Azure, GCP, Cloudflare, Okta, GitHub, Atlassian products |
| `apple_google` | `apple_google_news.py` | 25 | 9to5Mac, MacRumors, AppleInsider, 9to5Google, Android Authority, Android Police |
| `tech` | `tech_news.py` | 17 | Ars Technica, The Verge, Phoronix, LWN.net, Hackaday, BBC Technology |
| `general_news` | `general_news.py` | 12 | NPR, PBS NewsHour Economy, Financial Times, NYT, Politico, five BBC feeds |
| `gaming` | `gaming_news.py` | 10 | IGN, Polygon, PC Gamer, Eurogamer, Rock Paper Shotgun, Kotaku |
| `cve` | `cve.py` | 6 | NVD (JSON API), Ubuntu Security Notices, CERT.PL, CERT-FR, Canadian Cyber Centre, JPCERT/CC |
| `us_legislation` | `us_legislation.py` | 4 | Congress.gov presented-to-President, House floor, Senate floor; GovInfo bills |
| `eu_legislation` | `eu_legislation.py` | 3 | EUR-Lex Parliament and Council legislation, Commission proposals, Official Journal |
| `kev` | `kev.py` | 2 | CISA KEV catalog (JSON), Exploit Database |
| `uk_legislation` | `uk_legislation.py` | 1 | UK Parliament, all bills |
| **Total** | | **229** | |

CVE and KEV are split on purpose. CVE is the general awareness firehose,
every 8 hours; KEV is the actively-exploited list, every 4 hours, and
deserves its own channel so it is not buried.

## `/news` commands

Every subcommand takes `category` as one of the 11 keys above. Permission
rules come from `news_manager.py`:

| Command | Who | Notes |
|---|---|---|
| `/news set_channel <category> <channel>` | Administrator, or an approved role for that category | Persists to `news_config.json`; an env var still wins on next load |
| `/news toggle_source <category> <source>` | Administrator, or an approved role | Source key from `list_sources`; default is enabled |
| `/news enable <category>` | Administrator only | Refuses until a channel is set |
| `/news disable <category>` | Administrator only | |
| `/news set_interval <category> <hours>` | Administrator only | Integer 1 to 24 |
| `/news add_role <category> <role>` | Administrator only | Grants set_channel and toggle_source |
| `/news remove_role <category> <role>` | Administrator only | |
| `/news status <category>` | everyone | Ephemeral: enabled, channel, interval, roles, disabled sources |
| `/news list_sources <category>` | everyone | Ephemeral: every source key with its on/off state. Known gap: the cog lookup table inside `news_manager.py` only resolves `cybersecurity`, `tech`, `gaming`, `apple_google`, `cve` and `general_news`; for the other five read the `*_SOURCES` dict in the cog until that is fixed |

Prefix fallbacks for when slash commands are not yet synced:
`!news_set_channel <category> <#channel>` (Manage Server plus the same
role check), `!news_enable` and `!news_disable` (Administrator), and
`!news_status [category]`.

There is no `/news test` command.

## Manual fetch commands

These post the latest items from one source into the current channel and
have no permission gate.

| Command | Source argument |
|---|---|
| `/cybersecurity <source>` | any key from `/news list_sources cybersecurity` |
| `/tech <source>` | tech key |
| `/gaming <source>` | gaming key |
| `/applegoogle <source>` | Apple/Google key |
| `/generalnews <source>` | `npr_news`, `pbs_economy`, `financial_times`, `pew_research`, `nyt_homepage`, `foreign_affairs`, `politico` (the BBC feeds post on the schedule only) |
| `/uslegislation <source>` | `presented_to_president`, `house_floor`, `senate_floor`, `govinfo_bills` |
| `/eulegislation <source>` | `eurlex_parliament_council`, `eurlex_proposals`, `eurlex_official_journal` |
| `/uklegislation <source>` | `all_bills` |

CVE and KEV are hybrid commands (slash or `!`): `/cve [source]` (usually
`nvd` or `ubuntu`; any `CVE_SOURCES` key is accepted) and `/kev`. Their
`*_set_channel` (Manage Server), `*_enable` / `*_disable` (bot owner) and
`*_status` companions are listed in COMMANDS.md. Vendor alerts has no manual
fetch command; it is schedule-only.

## Deduplication

Issue #49 traced duplicate posts to two causes, both handled in
`utils/news_dedupe.py`.

*Cross-feed syndication.* Publishers push one story into several feeds (BBC
Top Stories and BBC UK, for example). `normalize_link()` strips fragments,
tracking parameters (`utm_*`, `at_*`, `ns_*`, `cmp`, `ocid`, `ref`) and
trailing slashes, and `seen_in_any()` compares an item's link or GUID
against the union of every feed's seen-list, not just its own. The timer
path (`utils/news_fetcher.py`) applies this to all categories through its
per-category `feed_cache_<category>.json`; in the bot, `general_news.py`
uses it, while the other cogs still dedupe per feed (last link per source,
or the last 50 links per source for legislation). Matching is on URL or
GUID; titles are not compared.

*Two schedulers.* `autopost_enabled()` reads `NEWS_AUTO_POST` so a category
is posted by one scheduler with one state file, never both.

CVE and KEV additionally track posted IDs (last 1000 CVEs, last 500 KEVs);
vendor alerts keeps its last 500 item IDs.

## State files

All under the data directory resolved by `utils/state.py`: `DATA_DIR` if
set, else `/app/data` when it exists (the Docker volume), else the repo's
`data/`. `news_runner.py` writes its feed cache to `/app/data` directly.

| File | Owner |
|---|---|
| `news_config.json` | `news_manager.py` (all 11 categories) |
| `cybersecurity_news_state.json`, `tech_news_state.json`, `gaming_news_state.json`, `apple_google_news_state.json`, `general_news_state.json` | the matching news cog |
| `us_legislation_state.json`, `eu_legislation_state.json`, `uk_legislation_state.json` | legislation cogs |
| `vendor_alerts_state.json`, `cve_state.json`, `kev_state.json` | vendor, CVE and KEV cogs |
| `feed_cache_<category>.json` | `news_runner.py` (ETag, Last-Modified and seen GUIDs per timer category) |

`data/news_config.example.json` is a starting point for the config file.

## Environment variables

```bash
NEWS_CYBERSECURITY_CHANNEL_ID=
NEWS_VENDOR_ALERTS_CHANNEL_ID=
NEWS_APPLE_GOOGLE_CHANNEL_ID=
NEWS_TECH_CHANNEL_ID=
NEWS_GENERAL_NEWS_CHANNEL_ID=
NEWS_GAMING_CHANNEL_ID=
NEWS_CVE_CHANNEL_ID=
NEWS_US_LEGISLATION_CHANNEL_ID=
NEWS_EU_LEGISLATION_CHANNEL_ID=
NEWS_KEV_CHANNEL_ID=
NEWS_UK_LEGISLATION_CHANNEL_ID=

# false where systemd timers own posting; default true
NEWS_AUTO_POST=true
```

The variable name is derived as `NEWS_<CATEGORY>_CHANNEL_ID` with the
category key upper-cased, so the two-word keys keep their underscore
(`apple_google` becomes `NEWS_APPLE_GOOGLE_CHANNEL_ID`). Each may also live
in the secrets backend as `<CATEGORY>_CHANNEL_ID` under the `NEWS` prefix.
`kev_runner.py` reads the same `NEWS_KEV_CHANNEL_ID`; there is no separate
`KEV_CHANNEL_ID` alias.

## Setup

1. Set a channel per category you want, either in `.env` (or Doppler) or
   with `/news set_channel <category> #channel`.
2. `/news enable <category>` (env-configured categories are already enabled
   on a fresh install).
3. Optional: `/news add_role <category> @role` so a team can manage its own
   sources, then `/news list_sources` and `/news toggle_source` to prune.
4. If you deploy the systemd timers, set `NEWS_AUTO_POST=false` and restart
   the bot.

## Related

- [COMMANDS.md](../reference/COMMANDS.md): every command with arguments and gates
- [SYSTEMD.md](../deployment/SYSTEMD.md): timer schedules, KEV single-timer rule
- [NEWS_CATEGORIES_OVERVIEW.md](NEWS_CATEGORIES_OVERVIEW.md): one-page category and schedule table
- [CHANNEL_CONFIGURATION.md](../reference/CHANNEL_CONFIGURATION.md): every channel env var, news and otherwise
- `scripts/feed_audit.py`: classify every configured feed as OK, EMPTY, REDIRECTED, HTML, PARSE or FAIL
