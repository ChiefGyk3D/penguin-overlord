# News Categories Overview

One page: the 11 categories, how many feeds each carries, when each runs,
and the commands and env vars that drive them. The full guide is
[NEWS_SYSTEM.md](NEWS_SYSTEM.md).

Source counts were measured from the cogs' `*_SOURCES` dicts on 2026-09-02
(229 in total; the prose elsewhere says "220+" because feeds churn). The
live list for any category is `/news list_sources <category>`.

## Categories and schedule

Schedules are the `OnCalendar` values `scripts/install-systemd.sh` writes
for the `penguin-news-<category>.timer` units. KEV runs from the background
`penguin-kev.timer` (`kev_runner.py`) rather than a news timer.

| Category key | Sources | Schedule | Timer unit |
|---|---:|---|---|
| `cybersecurity` | 115 | every 3 h at :01 | `penguin-news-cybersecurity` |
| `vendor_alerts` | 34 | every 30 min at :25 and :55 | `penguin-news-vendor_alerts` |
| `apple_google` | 25 | every 3 h at :45 | `penguin-news-apple_google` |
| `tech` | 17 | every 4 h at :30 | `penguin-news-tech` |
| `general_news` | 12 | every 2 h at :20 | `penguin-news-general_news` |
| `gaming` | 10 | every 2 h at :15 | `penguin-news-gaming` |
| `cve` | 6 | every 8 h at :00 | `penguin-news-cve` |
| `us_legislation` | 4 | hourly at :05 | `penguin-news-us_legislation` |
| `eu_legislation` | 3 | hourly at :10 | `penguin-news-eu_legislation` |
| `kev` | 2 | every 4 h at :00 | `penguin-kev` (background timer) |
| `uk_legislation` | 1 | hourly at :15 | `penguin-news-uk_legislation` |
| **Total** | **229** | | |

Minute offsets are staggered so no two categories fetch in the same minute.
When the bot runs its own loops instead (`NEWS_AUTO_POST=true`, the
default), `interval_hours` and `minute_offset` in `news_config.json` play
the same role.

## Commands

Manual fetch, no permission gate, posts into the current channel:

```
/cybersecurity <source>
/tech <source>
/gaming <source>
/applegoogle <source>
/generalnews <source>
/uslegislation <source>
/eulegislation <source>
/uklegislation <source>
/cve [nvd|ubuntu]        # hybrid: also !cve
/kev                     # hybrid: also !kev
```

Vendor alerts is schedule-only; it has no manual fetch command.

Configuration (`/news` group; `enable`, `disable`, `set_interval`,
`add_role`, `remove_role` are Administrator only; `set_channel` and
`toggle_source` also accept approved roles; `status` and `list_sources` are
open to everyone):

```
/news set_channel <category> #channel
/news enable <category>
/news disable <category>
/news set_interval <category> <hours>
/news toggle_source <category> <source>
/news add_role <category> @role
/news remove_role <category> @role
/news status <category>
/news list_sources <category>
```

Prefix fallbacks: `!news_set_channel`, `!news_enable`, `!news_disable`,
`!news_status`.

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

NEWS_AUTO_POST=false   # when systemd timers own posting
```

A category whose env var is set is enabled automatically on a fresh
install. The same values can live in Doppler, AWS or Vault under the `NEWS`
prefix.

## Behaviour common to every category

- Public RSS, Atom or JSON feeds only; no API keys.
- A failed feed logs a warning and the run continues.
- The legislation and general news cogs drop items older than 7 days; the
  timer path relies on the seen-GUID cache instead.
- Dedupe is by normalized URL or GUID across feeds (see NEWS_SYSTEM.md,
  "Deduplication"); titles are not compared.
- ETag and Last-Modified caching on the timer path, with a per-category
  concurrency limit.

## Related

- [NEWS_SYSTEM.md](NEWS_SYSTEM.md): architecture, dedupe, state files
- [COMMANDS.md](../reference/COMMANDS.md): every command and its gate
- [SYSTEMD.md](../deployment/SYSTEMD.md): installing and operating the timers
- [CHANNEL_CONFIGURATION.md](../reference/CHANNEL_CONFIGURATION.md): all channel env vars
