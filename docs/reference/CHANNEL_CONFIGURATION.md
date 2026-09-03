# Channel Configuration Reference

Every channel environment variable Penguin Overlord reads, what feeds it,
and the Discord command that sets the same thing at runtime.

Source counts were measured from the cogs on 2026-09-02. They drift as
feeds are added or retired; `/news list_sources <category>` is the live
answer.

## Quick Reference Table

| Environment Variable | Feature | Discord Command Alternative | Default | Sources |
|---------------------|---------|----------------------------|---------|--------:|
| `XKCD_POST_CHANNEL_ID` | XKCD Comics | `xkcd_set_channel #channel` | Disabled | 1 |
| `COMIC_POST_CHANNEL_ID` | Daily Tech Comics | `comic_set_channel #channel` | Disabled | 3 |
| `SOLAR_POST_CHANNEL_ID` | HAM Radio Solar/Propagation | `solar_set_channel #channel` | Disabled | NOAA SWPC |
| `NEWS_CYBERSECURITY_CHANNEL_ID` | Cybersecurity News | `/news set_channel cybersecurity #channel` | Disabled | 115 |
| `NEWS_VENDOR_ALERTS_CHANNEL_ID` | Vendor status and advisories | `/news set_channel vendor_alerts #channel` | Disabled | 34 |
| `NEWS_APPLE_GOOGLE_CHANNEL_ID` | Apple & Google News | `/news set_channel apple_google #channel` | Disabled | 25 |
| `NEWS_TECH_CHANNEL_ID` | Technology News | `/news set_channel tech #channel` | Disabled | 17 |
| `NEWS_GENERAL_NEWS_CHANNEL_ID` | General News Outlets | `/news set_channel general_news #channel` | Disabled | 12 |
| `NEWS_GAMING_CHANNEL_ID` | Gaming News | `/news set_channel gaming #channel` | Disabled | 10 |
| `NEWS_CVE_CHANNEL_ID` | CVE Vulnerabilities (General) | `/news set_channel cve #channel` | Disabled | 6 |
| `NEWS_US_LEGISLATION_CHANNEL_ID` | US Legislation | `/news set_channel us_legislation #channel` | Disabled | 4 |
| `NEWS_EU_LEGISLATION_CHANNEL_ID` | EU Legislation | `/news set_channel eu_legislation #channel` | Disabled | 3 |
| `NEWS_KEV_CHANNEL_ID` | KEV, Known Exploited (Critical) | `/news set_channel kev #channel` | Disabled | 2 |
| `NEWS_UK_LEGISLATION_CHANNEL_ID` | UK Legislation | `/news set_channel uk_legislation #channel` | Disabled | 1 |

**Total: 14 channel variables (3 background posters plus 11 news
categories); 229 news feeds plus XKCD, the three-comic rotation and NOAA.**

The legacy SecurityNews cog, its `SECNEWS_POST_CHANNEL_ID` variable and
`securitynews_state.json` no longer exist. Use
`NEWS_CYBERSECURITY_CHANNEL_ID`.

## Configuration Priority

For every channel variable:

1. **Environment variable** (`.env`, or Doppler / AWS / Vault via
   `utils/secrets.py`): highest priority, re-applied on every load.
2. **Discord command**: written to the feature's state file.
3. **Default**: no channel, auto-posting disabled.

Auto-posting is off until you enable it after setting a channel:
- XKCD: `xkcd_enable`
- Comics: `comic_enable`
- Solar: `solar_enable`
- News, any category: `/news enable <category>` (a news category whose env
  var is set is enabled automatically on a fresh install)

If systemd timers own posting (see [SYSTEMD.md](../deployment/SYSTEMD.md)),
also set `NEWS_AUTO_POST=false` so the bot's own loops stay parked.

## Detailed Configuration

### 🎨 Comics & Fun (2 channels)

#### XKCD_POST_CHANNEL_ID
- **Feature**: Posts each new XKCD as it appears
- **Update Frequency**: In-bot loop every 30 minutes
  (`XKCD_POLL_INTERVAL_MINUTES`), or `penguin-xkcd.timer` at :00 and :30
- **Commands** (hybrid, slash or `!`): `xkcd_set_channel`, `xkcd_enable`,
  `xkcd_disable`, `xkcd_post_now`
- **State File**: `data/xkcd_state.json` (override with `XKCD_STATE_PATH`)
- **Code**: `cogs/xkcd_poster.py`, `xkcd_runner.py`

#### COMIC_POST_CHANNEL_ID
- **Feature**: One tech comic a day, rotating at random between three
  sources: XKCD, Joy of Tech, turnoff.us
- **Update Frequency**: In-bot loop every 24 hours, or `penguin-comics.timer`
  daily at 10:00 UTC
- **Commands** (hybrid): `comic_set_channel`, `comic_enable`,
  `comic_disable`; `daily_comic` forces a post now
- **State File**: `data/comic_state.json` (override with `COMIC_STATE_PATH`)
- **Code**: `cogs/comics.py`, `comics_runner.py`

### 📻 HAM Radio (1 channel)

#### SOLAR_POST_CHANNEL_ID
- **Feature**: Solar weather and HF propagation reports, with X-ray,
  D-RAP and aurora charts
- **Data Source**: NOAA Space Weather Prediction Center
- **Update Frequency**: In-bot loop every 12 hours, or `penguin-solar.timer`
  at :00 and :30
- **Commands** (hybrid): `solar_set_channel`, `solar_enable`,
  `solar_disable`, `solar_status`
- **State File**: `data/solar_state.json`
- **Code**: `cogs/radiohead.py` and `solar_runner.py` both read
  `SOLAR_POST_CHANNEL_ID` (the cog on load, the runner via
  `get_secret('SOLAR', 'POST_CHANNEL_ID')` with an env fallback)

### 📰 News System (11 channels)

Every category is configured the same way. The variable name is
`NEWS_<CATEGORY>_CHANNEL_ID` with the category key upper-cased; the same
value can be stored in the secrets backend as `<CATEGORY>_CHANNEL_ID` under
the `NEWS` prefix. `cogs/news_manager.py` resolves it in
`_get_channel_id_from_env()` and `news_runner.py` does the same for the
timers.

```
/news set_channel <category> #channel
/news enable <category>
/news status <category>
/news list_sources <category>
/news toggle_source <category> <source>
```

The per-category source lists are not repeated here. Run
`/news list_sources <category>` or read the `*_SOURCES` dict in the cog;
[NEWS_SYSTEM.md](../features/NEWS_SYSTEM.md) has representative feeds and
the schedule.

| Variable | Category key | Sources | Schedule | Example sources |
|---|---|---:|---|---|
| `NEWS_CYBERSECURITY_CHANNEL_ID` | `cybersecurity` | 115 | every 3 h | The Hacker News, BleepingComputer, Dark Reading |
| `NEWS_VENDOR_ALERTS_CHANNEL_ID` | `vendor_alerts` | 34 | every 30 min | AWS, Cloudflare, Okta status feeds |
| `NEWS_APPLE_GOOGLE_CHANNEL_ID` | `apple_google` | 25 | every 3 h | 9to5Mac, MacRumors, Android Police |
| `NEWS_TECH_CHANNEL_ID` | `tech` | 17 | every 4 h | Ars Technica, The Verge, Phoronix |
| `NEWS_GENERAL_NEWS_CHANNEL_ID` | `general_news` | 12 | every 2 h | NPR, Financial Times, BBC Top Stories |
| `NEWS_GAMING_CHANNEL_ID` | `gaming` | 10 | every 2 h | IGN, Polygon, PC Gamer |
| `NEWS_CVE_CHANNEL_ID` | `cve` | 6 | every 8 h | NVD, Ubuntu Security Notices, CERT-FR |
| `NEWS_US_LEGISLATION_CHANNEL_ID` | `us_legislation` | 4 | hourly | Congress.gov presented to President, House floor, GovInfo bills |
| `NEWS_EU_LEGISLATION_CHANNEL_ID` | `eu_legislation` | 3 | hourly | EUR-Lex Parliament and Council, Commission proposals, Official Journal |
| `NEWS_KEV_CHANNEL_ID` | `kev` | 2 | every 4 h | CISA KEV catalog, Exploit Database |
| `NEWS_UK_LEGISLATION_CHANNEL_ID` | `uk_legislation` | 1 | hourly | UK Parliament, all bills |

Notes:
- CVE is general awareness; KEV is the actively-exploited list. Give KEV its
  own channel so it is not buried in CVE volume.
- `kev_runner.py` reads `NEWS_KEV_CHANNEL_ID` as well; there is no separate
  `KEV_CHANNEL_ID`.
- GovInfo bills is high volume. `/news toggle_source us_legislation
  govinfo_bills` if it is too noisy.
- Vendor alerts has no manual fetch command; the rest have `/cybersecurity`,
  `/tech`, `/gaming`, `/applegoogle`, `/generalnews`, `/uslegislation`,
  `/eulegislation`, `/uklegislation`, `/cve`, `/kev`.

## .env Configuration Examples

### Basic Setup (All Features)
```bash
# Comics & Fun
XKCD_POST_CHANNEL_ID=123456789012345678
XKCD_POLL_INTERVAL_MINUTES=30
COMIC_POST_CHANNEL_ID=234567890123456789

# HAM Radio
SOLAR_POST_CHANNEL_ID=345678901234567890

# News System (11 categories)
NEWS_CYBERSECURITY_CHANNEL_ID=567890123456789012
NEWS_VENDOR_ALERTS_CHANNEL_ID=456789012345678901
NEWS_APPLE_GOOGLE_CHANNEL_ID=890123456789012345
NEWS_TECH_CHANNEL_ID=678901234567890123
NEWS_GENERAL_NEWS_CHANNEL_ID=345678901234567012
NEWS_GAMING_CHANNEL_ID=789012345678901234
NEWS_CVE_CHANNEL_ID=901234567890123456
NEWS_US_LEGISLATION_CHANNEL_ID=012345678901234567
NEWS_EU_LEGISLATION_CHANNEL_ID=123456789012345670
NEWS_KEV_CHANNEL_ID=234567890123456789
NEWS_UK_LEGISLATION_CHANNEL_ID=234567890123456701

# Only when systemd timers own posting
NEWS_AUTO_POST=false
```

### Minimal Setup (Just Security & Tech)
```bash
NEWS_CYBERSECURITY_CHANNEL_ID=567890123456789012
NEWS_TECH_CHANNEL_ID=678901234567890123
NEWS_CVE_CHANNEL_ID=901234567890123456
NEWS_KEV_CHANNEL_ID=234567890123456789
```

Then confirm they are on (env-configured categories enable themselves on
first load; run these if you are adding to an existing config):
```bash
/news enable cybersecurity
/news enable tech
/news enable cve
/news enable kev
```

### Doppler Configuration
```bash
doppler secrets set XKCD_POST_CHANNEL_ID="123456789012345678"
doppler secrets set COMIC_POST_CHANNEL_ID="234567890123456789"
doppler secrets set NEWS_CYBERSECURITY_CHANNEL_ID="567890123456789012"
# ... and so on for each variable above
```

## Getting Channel IDs

1. Enable **Developer Mode** in Discord: Settings, Advanced, Developer Mode.
2. Right-click any channel, select "Copy Channel ID", paste into `.env`
   (no quotes needed).

## Implementation Status

All 14 variables are read from the environment and can also be set by a
Discord command:

- `XKCD_POST_CHANNEL_ID`: `cogs/xkcd_poster.py`, `xkcd_runner.py`
- `COMIC_POST_CHANNEL_ID`: `cogs/comics.py`, `comics_runner.py`
- `SOLAR_POST_CHANNEL_ID`: `cogs/radiohead.py`, `solar_runner.py`
- `NEWS_*_CHANNEL_ID` (11): `cogs/news_manager.py` for the bot,
  `news_runner.py` and `kev_runner.py` for the timers

### Implementation Pattern

The background posters follow the pattern in `xkcd_poster.py`:

```python
import os

env_chan = os.getenv('YOUR_CHANNEL_ID_VAR_NAME')
if env_chan and env_chan.isdigit():
    self.state['channel_id'] = int(env_chan)
    logger.info(f"Using channel from env: {env_chan}")
```

News categories go through `utils/secrets.get_secret('NEWS', ...)` first so
Doppler, AWS and Vault work without code changes.

## Verification Commands

```bash
# Solar
solar_status

# CVE and KEV auto-posters
cve_status
kev_status

# Any news category
/news status <category>
!news_status              # all categories, prefix form
```

XKCD and comics have no status command; read `xkcd_state.json` and
`comic_state.json`, or run `xkcd_post_now` / `daily_comic` to test the
channel.

## State Files

Channel settings persist in JSON under the data directory
(`DATA_DIR` if set, else `/app/data` when present, else `data/`):

```
data/
├── xkcd_state.json                  # XKCD channel, enabled, last comic
├── comic_state.json                 # comic channel, enabled, posted URLs
├── solar_state.json                 # solar channel, enabled, last post
├── news_config.json                 # all 11 news categories
├── cybersecurity_news_state.json
├── tech_news_state.json
├── gaming_news_state.json
├── apple_google_news_state.json
├── general_news_state.json
├── us_legislation_state.json
├── eu_legislation_state.json
├── uk_legislation_state.json
├── vendor_alerts_state.json
├── cve_state.json
├── kev_state.json
└── feed_cache_<category>.json       # news_runner.py ETag and seen-GUID cache
```

Each stores at minimum `channel_id` (integer or null) and `enabled`
(boolean), plus whatever the feature needs to avoid reposting.

## Migration Notes

### From Discord Commands to Env Vars

1. Note the channel from `solar_status`, `cve_status`, `kev_status` or
   `/news status <category>` (for XKCD and comics, read the state file).
2. Add the value to `.env` or Doppler.
3. Restart the bot; the env value now overrides the state file on every load.

## Troubleshooting

### Channel ID Not Working

1. **Numeric only**: `XKCD_POST_CHANNEL_ID=123456789012345678`. Quotes are
   tolerated but not needed.
2. **Bot permissions**: Send Messages and Embed Links in the target channel.
3. **Is `.env` loaded?** `python3 -c "import os; print(os.getenv('XKCD_POST_CHANNEL_ID'))"`
   from the same shell the bot uses.
4. **Logs**: `journalctl -u penguin-overlord -f | grep -i channel`

### Priority Conflicts

If both an env var and a Discord command have set a channel, the env var
wins by design. The command's value is stored but overridden on the next
load. Remove the env var to use the command's value.

### State File Issues

To reset a feature, stop the bot, delete its state file, and start again;
the file is recreated with defaults. Or edit the JSON and set
`"channel_id": null`.

## See Also

- `.env.example`: template configuration file
- [NEWS_SYSTEM.md](../features/NEWS_SYSTEM.md): architecture, dedupe, state files
- [NEWS_CATEGORIES_OVERVIEW.md](../features/NEWS_CATEGORIES_OVERVIEW.md): category and schedule table
- [RSS_FEEDS.md](RSS_FEEDS.md): feed access, health checks, adding feeds
- [COMMANDS.md](COMMANDS.md): every command and its permission gate
- [SYSTEMD.md](../deployment/SYSTEMD.md): timers and `NEWS_AUTO_POST`
- [HOUSEKEEPING_NOVEMBER_2025.md](../archive/HOUSEKEEPING_NOVEMBER_2025.md): archived history of the November 2025 channel changes

---

**Last Updated**: 2026-09-02
**Total Channel Variables**: 14 (3 background posters, 11 news categories)
**Default Behaviour**: all auto-posting disabled until a channel is set and the feature is enabled
