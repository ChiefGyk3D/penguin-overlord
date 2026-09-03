# Command reference

Every command the bot registers, grouped by feature. Generated from the
cogs on 2026-09-02; when you add or rename a command, update this file in
the same PR.

**How to read it**

- **Hybrid** commands work both ways: `/name` as a slash command and
  `!name` with the prefix.
- **Slash** commands are slash only. Group commands (`/mod`, `/news`,
  `/profile`, `/roles`) are slash only.
- **Prefix** commands are `!` only.
- *Who* is the default gate. Server admins can loosen or tighten any slash
  command's visibility under Server Settings > Integrations > Penguin
  Overlord.
- *Gate* is the `.env` flag the cog needs; without it the command is
  absent or answers "off".

Totals: 101 commands in 28 cogs (67 hybrid, 27 slash-only, 7 prefix-only).
Six more cogs have no commands and are listed at the end.

## Help and admin

| Command | Kind | Arguments | What it does | Who |
| --- | --- | --- | --- | --- |
| `help [command]` | hybrid | optional command name | Categorized help: a dropdown of nine pages (Overview, Comics & Fun, News & CVE, HAM Radio, Aviation, SIGINT, Events, Utilities, Admin). With a name, that command's help. | everyone |
| `!help_old [command]` | prefix | optional command name | The older paginated help. | everyone |
| `source_code` | hybrid | | Link to the bot's source. | everyone |
| `!sync` | prefix | | Re-sync slash commands with Discord. | bot owner |
| `!listcogs` | prefix | | List loaded cogs and their commands. | bot owner |

## Moderation: `/mod` (gate `MOD_ENABLED`)

Default visibility: Moderate Members. Every reply is ephemeral. Guide:
[AI_MODERATION.md](../features/AI_MODERATION.md).

| Command | Arguments | What it does |
| --- | --- | --- |
| `/mod status` | | Models, mode (dry-run or enforcing), watched channels, queue, endpoints (private hosts shown as RFC1918, never an IP). |
| `/mod stats [days]` | window, default 14 | Alert accuracy per category from moderator labels. |
| `/mod pending` | | Reviews nobody has decided yet, with jump links. Use it when a button click seemed to vanish. |
| `/mod benchmark` | | Run the golden corpus through the live analyzer and post the accuracy summary (a few minutes, one model call per example). |
| `/mod test <text>` | text | Analyze sample text and show the verdict. Nothing is stored. |
| `/mod purge_user <user>` | user | Delete everything stored about a user. |

Alert cards in the mod channel carry their own controls (Approve, Dismiss,
"Confirm as a different category" select, and Ban / Kick / Dismiss on
profile flags). Those are buttons, not commands, and they survive restarts.

## Profile screen: `/profile` (gate `PROFILE_SCREEN_ENABLED`)

Default visibility: Administrator. Ephemeral.

| Command | What it does |
| --- | --- |
| `/profile status` | Switches, model stage, open flags, keyword counts. |
| `/profile sync-automod` | Create or update the Discord AutoMod member-profile rule from the name term lists (the only thing that can see bios). Bot needs Manage Server. |

## Role picker: `/roles` (gate `ROLE_PICKER_ENABLED`)

Default visibility: Manage Roles. Ephemeral. Guide:
[ROLE_PICKER.md](../features/ROLE_PICKER.md).

| Command | Arguments | What it does |
| --- | --- | --- |
| `/roles list` | | Every panel the bot knows and how many of its roles exist yet. |
| `/roles post <panel> [channel]` | panel key (autocompletes: `country`, `us_states`, `ca_provinces`), channel default here | Create the panel's missing roles and post it with its dropdowns. |

Members use the dropdowns, not commands.

## News management: `/news`

No env gate. `set_channel`, `enable`, `disable`, `toggle_source` accept
Administrator or a role added with `add_role`; `set_interval`, `add_role`,
`remove_role` are Administrator only; `status` and `list_sources` are open.
Every subcommand takes a `category` from: `cybersecurity`, `tech`,
`gaming`, `apple_google`, `cve`, `kev`, `us_legislation`,
`eu_legislation`, `uk_legislation`, `general_news`, `vendor_alerts`.
Ephemeral. Guide: [NEWS_SYSTEM.md](../features/NEWS_SYSTEM.md).

| Command | Extra arguments | What it does |
| --- | --- | --- |
| `/news set_channel <category> <channel>` | channel | Where the category posts. |
| `/news enable <category>` | | Turn auto-posting on. |
| `/news disable <category>` | | Turn auto-posting off. |
| `/news set_interval <category> <hours>` | 1 to 24 | Posting interval. |
| `/news toggle_source <category> <source>` | source key | Enable or disable one feed. |
| `/news add_role <category> <role>` | role | Let a role manage that category. |
| `/news remove_role <category> <role>` | role | Revoke it. |
| `/news status <category>` | | Channel, interval, enabled state, sources. |
| `/news list_sources <category>` | | Every feed key in the category. |
| `!news_set_channel <category> <#channel>` | | Prefix equivalent (Manage Server). |
| `!news_enable <category>` / `!news_disable <category>` | | Prefix equivalents (Administrator). |
| `!news_status [category]` | | Prefix equivalent. |

On the production box the in-bot loops are off (`NEWS_AUTO_POST=false`)
and systemd timers run `news_runner.py` instead; the `/news` settings still
drive what the timers post.

## Fetch news on demand (slash, no gate)

Each posts the latest items from one source into the current channel.

| Command | Source argument |
| --- | --- |
| `/cybersecurity <source>` | any key from `/news list_sources cybersecurity` |
| `/tech <source>` | tech source key |
| `/gaming <source>` | gaming source key |
| `/applegoogle <source>` | Apple/Google source key |
| `/generalnews <source>` | `npr_news`, `pbs_economy`, `financial_times`, `pew_research`, `nyt_homepage`, `foreign_affairs`, `politico` (the BBC feeds post on the timer only) |
| `/uslegislation <source>` | `presented_to_president`, `house_floor`, `senate_floor`, `govinfo_bills` |
| `/eulegislation <source>` | `eurlex_parliament_council`, `eurlex_proposals`, `eurlex_official_journal` |
| `/uklegislation <source>` | `all_bills` |

## Vulnerabilities: CVE and KEV (hybrid)

| Command | Arguments | What it does | Who |
| --- | --- | --- | --- |
| `cve [source]` | `nvd`, `ubuntu`, `cert_pl`, `cert_fr`, `cert_ca`, `jpcert` (free text, any key) | Recent CVEs. | everyone |
| `cve_status` | | Auto-poster state. | everyone |
| `cve_set_channel [channel]` | channel | Where auto CVE alerts go. | Manage Server |
| `cve_enable` / `cve_disable` | | Auto CVE alerts on/off. | bot owner |
| `kev` | | CISA Known Exploited Vulnerabilities, latest additions. | everyone |
| `kev_status` | | Auto-poster state. | everyone |
| `kev_set_channel [channel]` | channel | Where auto KEV alerts go. | Manage Server |
| `kev_enable` / `kev_disable` | | Auto KEV alerts on/off. | bot owner |

## HAM radio and propagation (hybrid)

Guide: [RADIOHEAD_HAM_RADIO.md](../features/RADIOHEAD_HAM_RADIO.md).

| Command | Arguments | What it does |
| --- | --- | --- |
| `solar` | | Full solar weather report and band-by-band predictions (physics based: MUF, D-layer absorption, gray line, K-index). |
| `propagation` | | Same report as `solar`. |
| `xray [period]` | default `6h` | GOES X-ray flux chart. |
| `drap` | | D-region absorption prediction map. |
| `aurora` | | Auroral oval and forecast. |
| `radio_maps` | | All the propagation maps in one post. |
| `bandplan [band]` | e.g. `20m` | ARRL band plan. |
| `frequency [service]` | band or service | Frequency lookup for ham bands and common services. |
| `ham_class [class]` | Technician, General, Extra | Privileges and power limits. |
| `hamradio` | | Trivia and facts. |
| `contests [days]` | default 7 | Upcoming contests. |
| `grid <coords or two grids>` | `lat,lon` or `FN31 EM79` | Coordinates to Maidenhead, or distance between two grids. |
| `satellite [grid]` | your grid | Amateur satellite pass predictions. |
| `repeater <location>` | city, state or grid | Repeater directory lookup. |
| `solar_status` | | Auto-poster state. |
| `solar_set_channel [channel]` | channel | Where the automated report posts (Manage Server). |
| `solar_enable` / `solar_disable` | | Automated report on/off (bot owner). |

## Aviation and SIGINT (hybrid, everyone)

| Command | Arguments | What it does |
| --- | --- | --- |
| `squawk [code]` | transponder code | What a squawk code means. |
| `aircraft` | | Aircraft type information. |
| `avfreq` | | Aviation frequencies. |
| `avfact` | | Aviation trivia. |
| `frequency_log` | | Interesting frequencies to monitor. |
| `sdrtool` | | SDR decoder tools and software. |
| `sigintfact` | | SIGINT facts and tips. |

## Comics (hybrid)

| Command | Arguments | What it does | Who |
| --- | --- | --- | --- |
| `comic [source]` | `xkcd`, `joyoftech`, `turnoff`, `random` (default) | A tech comic. | everyone |
| `comic_trivia <number>` | XKCD number | Explain an XKCD. | everyone |
| `xkcd [number]` | blank for latest | An XKCD comic. | everyone |
| `xkcd_random` / `xkcd_latest` | | Random or latest XKCD. | everyone |
| `xkcd_search <keyword>` | keyword | Search XKCD titles. | everyone |
| `daily_comic` | | Post today's comic now. | owner or Manage Server |
| `comic_set_channel <channel>` | channel | Daily comic channel. | owner or Manage Server |
| `comic_enable` / `comic_disable` | | Daily comic on/off. | bot owner |
| `xkcd_post_now` | | Post the latest XKCD now. | owner or Manage Server |
| `xkcd_set_channel <channel>` | channel | Automated XKCD channel. | owner or Manage Server |
| `xkcd_enable` / `xkcd_disable` | | Automated XKCD on/off. | bot owner |

On the production box comics and XKCD post from systemd timers
(`comics_runner.py`, `xkcd_runner.py`); the in-bot posters are off.

## Quotes (hybrid, everyone)

`techquote` (random), `quote_linus`, `quote_stallman`, `quote_hopper`,
`quote_shevinsky`, `quote_may`, `quote_list` (all authors).

## Events (hybrid, everyone)

CSV-backed for now; the events database in
[ROADMAP.md](../ROADMAP.md) replaces these.

| Command | Arguments | What it does |
| --- | --- | --- |
| `events [days] [type]` | default 30 days; type filter | Upcoming cyber and ham events. |
| `allevents [type]` | type filter | Everything upcoming, paginated. |
| `nextevent` | | The next event. |
| `searchevent <query>` | name or location | Search the list. |

## Fun and utilities (hybrid, everyone)

| Command | What it does |
| --- | --- |
| `fortune` | A cyber fortune cookie. |
| `manpage` | A random Linux command with its man page summary. |
| `patchgremlin` | A chaotic reminder to update. |
| `arch_banter_stats` | How often the Arch roaster has fired (gate `ARCH_BANTER_LLM` for the AI version). |
| `arch_leaderboard` | The Arch user hall of shame. |

## Cogs with no commands

These run on listeners or timers and are driven entirely by `.env`.

| Cog | What it does | Gate |
| --- | --- | --- |
| `welcome_greeter` | Verify reminder in #welcome-newbies a few minutes after the member clears membership screening (the moment MEE6 says hello); one daily group welcome in #general for the newly verified; edits leavers back out of recent greetings. | `WELCOME_ENABLED`, `WELCOME_JOIN_ENABLED`, `WELCOME_VERIFY_ENABLED` |
| `newcomer_helper` | Points brand-new members at the resources channel when they ask where to start. | `HELPER_ENABLED` |
| `skid_detector` | The script-kiddie alarm: roasts the energy, then corrects course. | `SKID_DETECTOR_ENABLED` (default on), `SKID_DETECTOR_LLM` |
| `arch_banter` | Roasts Arch and NixOS mentions (listener side; the two stats commands are above). | `ARCH_BANTER_LLM` |
| `rules_sync` | Reads #rules daily into the moderation prompt; announces changes in the mod channel. | `MOD_RULES_CHANNEL_ID` |
| `vendor_alerts` | Polls vendor status and security advisory feeds every 30 minutes. | `NEWS_AUTO_POST`, configured via `/news ... vendor_alerts` |
| `metrics` | Prometheus exporter and gateway heartbeat. | `METRICS_ENABLED` |
