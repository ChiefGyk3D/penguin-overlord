# Channel Configuration Reference

Complete list of all channel environment variables used by Penguin Overlord bot.

## Quick Reference Table

| Environment Variable | Feature | Discord Command Alternative | Default | Sources |
|---------------------|---------|----------------------------|---------|---------|
| `XKCD_POST_CHANNEL_ID` | XKCD Comics | `!xkcd_set_channel #channel` | Disabled | 1 |
| `COMIC_POST_CHANNEL_ID` | Daily Tech Comics | `!comic_set_channel #channel` | Disabled | 5 |
| `SOLAR_POST_CHANNEL_ID` | HAM Radio Solar/Propagation | `!solar_set_channel #channel` | Disabled | 1 |
| `NEWS_CYBERSECURITY_CHANNEL_ID` | Cybersecurity News | `/news set_channel cybersecurity #channel` | Disabled | 18 |
| `NEWS_TECH_CHANNEL_ID` | Technology News | `/news set_channel tech #channel` | Disabled | 15 |
| `NEWS_GAMING_CHANNEL_ID` | Gaming News | `/news set_channel gaming #channel` | Disabled | 10 |
| `NEWS_APPLE_GOOGLE_CHANNEL_ID` | Apple & Google News | `/news set_channel apple_google #channel` | Disabled | 27 |
| `NEWS_CVE_CHANNEL_ID` | CVE Vulnerabilities (General) | `/news set_channel cve #channel` | Disabled | 2 |
| `NEWS_KEV_CHANNEL_ID` | KEV - Known Exploited (Critical) | `/news set_channel kev #channel` | Disabled | 1 |
| `NEWS_US_LEGISLATION_CHANNEL_ID` | US Legislation | `/news set_channel us_legislation #channel` | Disabled | 5 |
| `NEWS_EU_LEGISLATION_CHANNEL_ID` | EU Legislation | `/news set_channel eu_legislation #channel` | Disabled | 3 |
| `NEWS_UK_LEGISLATION_CHANNEL_ID` | UK Legislation | `/news set_channel uk_legislation #channel` | Disabled | 1 |
| `NEWS_GENERAL_NEWS_CHANNEL_ID` | General News Outlets | `/news set_channel general_news #channel` | Disabled | 12 |

**Total: 13 channel configurations, 113 total sources**

**Note**: Legacy SecurityNews system removed as of Nov 9, 2025. Use `NEWS_CYBERSECURITY_CHANNEL_ID` instead.

## Configuration Priority

For all channel configurations, the priority order is:

1. **Environment Variables** (.env file or Doppler) - Highest priority
2. **Discord Commands** (runtime configuration via bot commands)
3. **Default Values** (Disabled - no auto-posting)

**IMPORTANT**: As of November 9, 2025, ALL auto-posting features are **DISABLED by default**. 
You must explicitly enable them after setting channel IDs:
- XKCD: `!xkcd_enable`
- Comics: `!comic_enable`
- Solar: `!solar_enable`
- News (all categories): `/news enable <category>`

## Detailed Configuration

### 🎨 Comics & Fun (2 channels)

#### XKCD_POST_CHANNEL_ID
- **Feature**: Automated XKCD comic posting
- **Update Frequency**: Every 30 minutes (configurable via `XKCD_POLL_INTERVAL_MINUTES`)
- **Discord Commands**:
  - `!xkcd_set_channel #channel` - Set posting channel
  - `!xkcd_enable` - Enable auto-posting
  - `!xkcd_disable` - Disable auto-posting
  - `!xkcd_status` - View current configuration
- **State File**: `data/xkcd_state.json`
- **Cog**: `xkcd_poster.py`
- **Implementation**: Reads from env var on initialization

#### COMIC_POST_CHANNEL_ID
- **Feature**: Daily tech comics rotation
- **Update Frequency**: Daily at 9:00 AM UTC
- **Sources** (5):
  1. Joy of Tech
  2. TurnOff.us
  3. Geek and Poke
  4. CommitStrip
  5. Monkey User
- **Discord Commands**:
  - `!comic_set_channel #channel` - Set posting channel
  - `!comic_enable` - Enable daily comics
  - `!comic_disable` - Disable daily comics
  - `!comic_status` - View configuration
- **State File**: `data/comic_state.json`
- **Cog**: `comics.py`
- **Implementation**: Reads from env var on initialization

### 📻 HAM Radio (1 channel)

#### SOLAR_POST_CHANNEL_ID
- **Feature**: Solar weather and propagation reports
- **Update Frequency**: Every 12 hours
- **Data Source**: NOAA Space Weather Prediction Center
- **Discord Commands**:
  - `!solar_set_channel #channel` - Set posting channel
  - `!solar_enable` - Enable auto-posting
  - `!solar_disable` - Disable auto-posting
  - `!solar_status` - View configuration
- **State File**: `data/solar_state.json`
- **Cog**: `radiohead.py`
- **Implementation**: ⚠️ **NEEDS IMPLEMENTATION** - Currently only supports Discord command

### 🔐 ~~Legacy Security News~~ (REMOVED)

**As of November 9, 2025**, the legacy SecurityNews system has been removed and replaced by the modern News System.

**Migration**:
- Old: `SECNEWS_POST_CHANNEL_ID` / `!secnews_*` commands
- New: `NEWS_CYBERSECURITY_CHANNEL_ID` / `/news` commands

The new cybersecurity news category provides better:
- Source curation (18 high-quality sources)
- Per-source control
- Unified management interface
- Better performance and reliability

### 📰 News System (8 channels, 90 sources)

All news categories use the same command structure:
```
/news set_channel <category> #channel
/news enable <category>
/news disable <category>
/news status
/news toggle_source <category> <source>
```

#### NEWS_CYBERSECURITY_CHANNEL_ID
- **Category**: Cybersecurity
- **Sources** (18):
  1. Krebs on Security
  2. Dark Reading
  3. Schneier on Security
  4. Troy Hunt (Have I Been Pwned)
  5. Graham Cluley
  6. The Hacker News
  7. SecurityWeek
  8. Threatpost
  9. Bleeping Computer
  10. CyberScoop
  11. Infosecurity Magazine
  12. Naked Security (Sophos)
  13. Security Affairs
  14. The Security Ledger
  15. SANS Internet Storm Center
  16. Talos Intelligence
  17. Malwarebytes Labs
  18. Kaspersky Securelist
- **Update Frequency**: Every 3 hours
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `news_manager.py`
- **Implementation**: ✅ Full env var support via `_get_channel_id_from_env()`

#### NEWS_TECH_CHANNEL_ID
- **Category**: Technology
- **Sources** (15):
  1. Ars Technica
  2. The Verge
  3. TechCrunch
  4. Wired
  5. Engadget
  6. ZDNet
  7. CNET
  8. The Register
  9. Tom's Hardware
  10. AnandTech
  11. Slashdot
  12. Hacker News (YCombinator)
  13. MIT Technology Review
  14. VentureBeat
  15. TechRadar
- **Update Frequency**: Every 3 hours
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `news_manager.py`
- **Implementation**: ✅ Full env var support

#### NEWS_GAMING_CHANNEL_ID
- **Category**: Gaming
- **Sources** (10):
  1. IGN
  2. Kotaku
  3. PC Gamer
  4. Polygon
  5. Rock Paper Shotgun
  6. Eurogamer
  7. GameSpot
  8. Destructoid
  9. Giant Bomb
  10. Game Informer
- **Update Frequency**: Every 3 hours
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `news_manager.py`
- **Implementation**: ✅ Full env var support

#### NEWS_APPLE_GOOGLE_CHANNEL_ID
- **Category**: Apple & Google
- **Sources** (27):
  - **Apple** (14): 9to5Mac, MacRumors, AppleInsider, iMore, MacWorld, etc.
  - **Google** (13): 9to5Google, Android Police, Android Central, Android Authority, etc.
- **Update Frequency**: Every 3 hours
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `apple_google_news.py` (dedicated cog)
- **Implementation**: ✅ Full env var support

#### NEWS_CVE_CHANNEL_ID
- **Category**: CVE Vulnerabilities (General Awareness)
- **Sources** (2):
  1. NVD Recent CVEs (National Vulnerability Database)
  2. Ubuntu Security Notices
- **Update Frequency**: Every 8 hours (general awareness, not urgent)
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `cve.py` (dedicated cog)
- **Implementation**: ✅ Full env var support
- **Note**: For actively exploited vulnerabilities, see NEWS_KEV_CHANNEL_ID

#### NEWS_KEV_CHANNEL_ID
- **Category**: KEV - Known Exploited Vulnerabilities (HIGH PRIORITY)
- **Sources** (1):
  1. CISA Known Exploited Vulnerabilities Catalog
- **Update Frequency**: Every 4 hours (actively exploited, requires immediate attention)
- **Priority Level**: 🔴 CRITICAL - These vulnerabilities are being actively exploited in the wild
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `kev.py` (dedicated cog)
- **Implementation**: ✅ Full env var support
- **Recommendation**: Set up a separate high-priority channel for KEV alerts to prevent them from being lost in general CVE noise

#### NEWS_US_LEGISLATION_CHANNEL_ID
- **Category**: US Legislation
- **Sources** (5 government sources):
  1. GovInfo Congressional Record
  2. GovInfo House Bills
  3. GovInfo Senate Bills
  4. Congressional Research Service Reports
  5. Library of Congress Thomas Feed
- **Update Frequency**: Every hour (legislation is time-sensitive)
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `us_legislation.py` (dedicated cog)
- **Implementation**: ✅ Full env var support
- **Note**: Uses public RSS feeds, NO API key required

#### NEWS_EU_LEGISLATION_CHANNEL_ID
- **Category**: EU Legislation
- **Sources** (3 official EU sources):
  1. EUR-Lex Latest Documents
  2. EU Publications Office
  3. European Commission Press Releases
- **Update Frequency**: Every hour
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `eu_legislation.py` (dedicated cog)
- **Implementation**: ✅ Full env var support

#### NEWS_UK_LEGISLATION_CHANNEL_ID
- **Category**: UK Legislation
- **Sources** (1 comprehensive source):
  1. UK Parliament - All Bills (includes both public and private bills)
- **Update Frequency**: Every hour (at :15 past each hour)
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `uk_legislation.py` (dedicated cog)
- **Implementation**: ✅ Full env var support
- **Note**: Uses public RSS feed from bills.parliament.uk, NO API key required. Single feed provides complete coverage of all UK Parliament legislative activity.

#### NEWS_GENERAL_NEWS_CHANNEL_ID
- **Category**: General News
- **Sources** (12 major outlets):
  1. NPR News
  2. PBS NewsHour
  3. Financial Times (corrected URL: `https://www.ft.com/news-feed?format=rss`)
  4. Pew Research Center
  5. New York Times
  6. Foreign Affairs
  7. Politico
  8. BBC News - Health
  9. BBC News - UK
  10. BBC News - World
  11. BBC News - Top Stories
  12. BBC News - Politics
- **Update Frequency**: Every 2 hours
- **Config File**: `penguin-overlord/data/news_config.json`
- **Cog**: `general_news.py` (dedicated cog)
- **Implementation**: ✅ Full env var support
- **Note**: Created Nov 9, 2025 to separate general news from government legislation

## .env Configuration Examples

### Basic Setup (All Features)
```bash
# Comics & Fun
XKCD_POST_CHANNEL_ID=123456789012345678
XKCD_POLL_INTERVAL_MINUTES=30
COMIC_POST_CHANNEL_ID=234567890123456789

# HAM Radio
SOLAR_POST_CHANNEL_ID=345678901234567890

# Legacy Security (deprecated)
SECNEWS_POST_CHANNEL_ID=456789012345678901

# News System (9 categories)
NEWS_CYBERSECURITY_CHANNEL_ID=567890123456789012
NEWS_TECH_CHANNEL_ID=678901234567890123
NEWS_GAMING_CHANNEL_ID=789012345678901234
NEWS_APPLE_GOOGLE_CHANNEL_ID=890123456789012345
NEWS_CVE_CHANNEL_ID=901234567890123456
NEWS_US_LEGISLATION_CHANNEL_ID=012345678901234567
NEWS_EU_LEGISLATION_CHANNEL_ID=123456789012345670
NEWS_UK_LEGISLATION_CHANNEL_ID=234567890123456701
NEWS_GENERAL_NEWS_CHANNEL_ID=345678901234567012
```

### Minimal Setup (Just Security & Tech)
```bash
NEWS_CYBERSECURITY_CHANNEL_ID=567890123456789012
NEWS_TECH_CHANNEL_ID=678901234567890123
NEWS_CVE_CHANNEL_ID=901234567890123456
```

Then enable them:
```bash
/news enable cybersecurity
/news enable tech
/news enable cve
```

### Doppler Configuration
```bash
# All channel IDs can be stored in Doppler
doppler secrets set XKCD_POST_CHANNEL_ID="123456789012345678"
doppler secrets set COMIC_POST_CHANNEL_ID="234567890123456789"
doppler secrets set NEWS_CYBERSECURITY_CHANNEL_ID="567890123456789012"
# ... etc for all channels
```

## Getting Channel IDs

1. Enable **Developer Mode** in Discord:
   - Settings → Advanced → Developer Mode (toggle ON)

2. Get a channel ID:
   - Right-click any channel
   - Select "Copy Channel ID"
   - Paste into .env file (no quotes needed)

## Implementation Status

### ✅ Fully Implemented (Env Var + Discord Command)
- `XKCD_POST_CHANNEL_ID` - xkcd_poster.py (defaults to disabled)
- `COMIC_POST_CHANNEL_ID` - comics.py (defaults to disabled)
- `NEWS_*_CHANNEL_ID` (all 8) - news_manager.py + category cogs (defaults to disabled)

### ⚠️ Needs Implementation (Discord Command Only)
- `SOLAR_POST_CHANNEL_ID` - radiohead.py (needs env var support added, defaults to disabled)

### 🗑️ Removed/Deprecated
- ~~`SECNEWS_POST_CHANNEL_ID`~~ - Removed Nov 9, 2025. Use `NEWS_CYBERSECURITY_CHANNEL_ID` instead.

### Implementation Pattern

To add env var support to a cog, use this pattern (from xkcd_poster.py):

```python
import os

# In __init__ or setup method:
env_chan = os.getenv('YOUR_CHANNEL_ID_VAR_NAME')
if env_chan and env_chan.isdigit():
    self.state['channel_id'] = int(env_chan)
    logger.info(f"Using channel from env: {env_chan}")
```

## Verification Commands

Test that channels are configured correctly:

```bash
# XKCD
!xkcd_status

# Comics
!comic_status

# Solar
!solar_status

# Security News (legacy)
!secnews_status

# News System (all categories)
/news status
```

## State Files

Channel configurations are persisted in JSON state files:

```
penguin-overlord/data/
├── xkcd_state.json           # XKCD channel + last_posted + enabled
├── comic_state.json          # Comic channel + enabled
├── solar_state.json          # Solar channel + enabled
├── securitynews_state.json   # SecurityNews channel + enabled
├── cve_state.json           # CVE tracking state
└── news_config.json         # All 8 news categories
```

State files store:
- `channel_id`: Discord channel ID (integer or null)
- `enabled`: Auto-posting enabled/disabled (boolean)
- `last_posted`: Last post timestamp (varies by feature)

## Migration Notes

### From Discord Commands to Env Vars

If you've been using Discord commands to configure channels:

1. Check current configuration:
   ```
   !xkcd_status
   !comic_status
   !solar_status
   /news status
   ```

2. Note the channel IDs from the output

3. Add to `.env`:
   ```bash
   XKCD_POST_CHANNEL_ID=<noted_channel_id>
   # ... etc
   ```

4. Restart bot - env vars will override state files

### From Legacy SecurityNews to News System

The old `securitynews.py` system (25 sources) is being replaced by `news_manager.py`:

```bash
# Old (deprecated)
SECNEWS_POST_CHANNEL_ID=123456789012345678

# New (recommended)
NEWS_CYBERSECURITY_CHANNEL_ID=123456789012345678
```

Both can coexist, but the new system has:
- More sources (18 curated sources vs 25 mixed quality)
- Better categorization
- Per-source enable/disable
- Consistent management interface

## Troubleshooting

### Channel ID Not Working

1. **Verify Channel ID is numeric**:
   ```bash
   # Good
   XKCD_POST_CHANNEL_ID=123456789012345678
   
   # Bad (quotes not needed, but won't break it)
   XKCD_POST_CHANNEL_ID="123456789012345678"
   ```

2. **Check bot has permissions**:
   - Bot must have "Send Messages" permission in target channel
   - Bot must have "Embed Links" permission (for rich embeds)
   - Check Discord → Server Settings → Roles → @Penguin Overlord

3. **Verify .env is loaded**:
   ```python
   # In Python
   import os
   print(os.getenv('XKCD_POST_CHANNEL_ID'))
   ```

4. **Check logs**:
   ```bash
   journalctl -u penguin-overlord -f | grep -i "channel"
   ```

### Priority Conflicts

If env var and Discord command are both set:
- **Env var wins** - This is by design
- Discord command values are stored but ignored
- Remove from .env to use Discord command value

### State File Issues

State files can get out of sync. To reset:

```bash
cd /home/chiefgyk3d/src/penguin-overlord/penguin-overlord/data
rm xkcd_state.json  # Will be recreated with defaults
# Or manually edit:
nano xkcd_state.json
# Set "channel_id": null to clear
```

## See Also

- `.env.example` - Template configuration file
- `docs/HOUSEKEEPING_NOVEMBER_2025.md` - Recent channel config improvements
- `docs/RSS_FEEDS_AND_API_KEYS.md` - Detailed feed information
- `docs/NEWS_CATEGORIES_OVERVIEW.md` - News system overview
- `penguin-overlord/cogs/help_categorized.py` - Help system with all commands

---

**Last Updated**: November 9, 2025  
**Total Channels**: 11 (removed legacy SecurityNews)  
**Total Sources**: 92 (90 news + 1 XKCD + 1 solar)  
**Default Behavior**: All auto-posting DISABLED by default (must explicitly enable)
