# Legislation Tracking System

> ARCHIVED: historical document. Commands, counts, and paths in here may no longer match the code; the current docs are indexed in [docs/README.md](../README.md).

## Overview

Added two new legislation tracking cogs for monitoring US and EU legislative activity, running hourly to catch new bills, laws, and policy updates.

## Categories Added

### 1. US Legislation & Political News (`us_legislation`)
**Sources** (11 total):

**Government Feeds:**
- ✍️ Congress.gov - Bills Presented to President
- 🏛️ Congress.gov - House Floor Today
- 🏛️ Congress.gov - Senate Floor Today
- 📋 Congress.gov - Most Viewed Bills
- 📜 GovInfo - Bills & Statutes (high volume)

**News Media:**
- 📻 NPR News
- � PBS NewsHour - Economy
- 📊 Pew Research Center
- 📰 New York Times - Homepage
- 🌍 Foreign Affairs
- 🏛️ Politico

**Update Frequency**: Hourly at :05 minutes
**Channel**: `/news set_channel us_legislation #us-legislation`
**API Keys**: None required! All feeds are public RSS

### 2. EU Legislation (`eu_legislation`)
**Sources** (3 total):
- 🇪🇺 EUR-Lex Legislation - Official EU legal database
- 🏛️ European Parliament News - Parliament activities and agendas
- 📰 Council of the EU Press Releases - Council decisions and press

**Update Frequency**: Hourly at :10 minutes
**Channel**: `/news set_channel eu_legislation #eu-legislation`
**API Keys**: None required! All feeds are public RSS

## Discord Commands

### Manual Fetching

```
# US Legislation & News
/uslegislation presented_to_president  - Bills awaiting presidential signature
/uslegislation house_floor            - House floor activity today
/uslegislation senate_floor           - Senate floor activity today
/uslegislation most_viewed_bills      - Trending legislation
/uslegislation govinfo_bills          - Official government publications
/uslegislation npr_news               - NPR general news
/uslegislation pbs_economy            - PBS NewsHour economy coverage
/uslegislation pew_research           - Pew Research Center reports
/uslegislation nyt_homepage           - New York Times news
/uslegislation foreign_affairs        - Foreign Affairs analysis
/uslegislation politico               - Politico political coverage

# EU Legislation
/eulegislation eurlex            - Fetch EUR-Lex legislation
/eulegislation europarl_news     - Fetch European Parliament news
/eulegislation council_press     - Fetch Council press releases
```

### Configuration (via /news commands)

```
# Set channels
/news set_channel us_legislation #us-legislation
/news set_channel eu_legislation #eu-legislation

# Enable auto-posting
/news enable us_legislation
/news enable eu_legislation

# Toggle specific sources
/news toggle_source us_legislation congress_bills
/news toggle_source eu_legislation eurlex

# View status
/news status us_legislation
/news status eu_legislation

# List all sources
/news list_sources us_legislation
/news list_sources eu_legislation
```

## Schedule

| Category        | Frequency | Offset | Example Times          |
|-----------------|-----------|--------|------------------------|
| US Legislation  | 1 hour    | :05    | 00:05, 01:05, 02:05... |
| EU Legislation  | 1 hour    | :10    | 00:10, 01:10, 02:10... |

*Offset ensures legislation checks don't overlap with news checks*

## Systemd Timer Deployment

If using optimized mode, add to `scripts/install-systemd.sh` or run manually:

```bash
# Create US Legislation timer
cat > /etc/systemd/system/penguin-legislation-us.service << EOF
[Unit]
Description=Penguin Bot US Legislation Fetcher
After=network.target

[Service]
Type=oneshot
User=penguin
WorkingDirectory=/opt/penguin-overlord/penguin-overlord
ExecStart=/usr/bin/python3 /opt/penguin-overlord/scripts/news_runner.py --category us_legislation
MemoryMax=256M
CPUQuota=50%
EOF

cat > /etc/systemd/system/penguin-legislation-us.timer << EOF
[Unit]
Description=US Legislation Hourly Check
Requires=penguin-legislation-us.service

[Timer]
OnCalendar=*-*-* *:05:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Create EU Legislation timer
cat > /etc/systemd/system/penguin-legislation-eu.service << EOF
[Unit]
Description=Penguin Bot EU Legislation Fetcher
After=network.target

[Service]
Type=oneshot
User=penguin
WorkingDirectory=/opt/penguin-overlord/penguin-overlord
ExecStart=/usr/bin/python3 /opt/penguin-overlord/scripts/news_runner.py --category eu_legislation
MemoryMax=256M
CPUQuota=50%
EOF

cat > /etc/systemd/system/penguin-legislation-eu.timer << EOF
[Unit]
Description=EU Legislation Hourly Check
Requires=penguin-legislation-eu.service

[Timer]
OnCalendar=*-*-* *:10:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable --now penguin-legislation-us.timer
systemctl enable --now penguin-legislation-eu.timer
```

## Files Created

1. **penguin-overlord/cogs/us_legislation.py** (254 lines)
   - USLegislation cog
   - 3 sources (Congress, GovInfo, States Newsroom)
   - `/uslegislation` command
   - Hourly auto-poster task

2. **penguin-overlord/cogs/eu_legislation.py** (254 lines)
   - EULegislation cog
   - 3 sources (EUR-Lex, Parliament, Council)
   - `/eulegislation` command
   - Hourly auto-poster task

## Integration

- ✅ Integrated with NewsManager for configuration
- ✅ Uses same state file pattern (JSON)
- ✅ Link-based deduplication (last 50 per source)
- ✅ Compatible with OptimizedNewsFetcher (when implemented)
- ✅ Works with systemd timers or in-bot tasks

## Testing

Both cogs loaded successfully:
```
✅ EU Legislation cog loaded
✅ US Legislation cog loaded
```

Total cogs now: **23 cogs** (21 existing + 2 legislation)

## Source Count Update

- **Previous**: 73 news sources across 5 categories
- **New**: 73 news + 6 legislation = **79 sources** across **7 categories**

Categories:
1. Cybersecurity (18 sources)
2. Tech (15 sources)
3. Gaming (10 sources)
4. Apple/Google (27 sources)
5. CVE (3 sources)
6. **US Legislation (3 sources)** ✨ NEW
7. **EU Legislation (3 sources)** ✨ NEW

## RSS Feed URLs

### US Sources
- Congress.gov: https://www.congress.gov/rss/most-viewed-bills.xml
  - Alternative: https://www.congress.gov/rss/bills.xml
- GovInfo: https://www.govinfo.gov/feeds/bills.xml
- States Newsroom: https://statesnewsroom.com/feed/dc-bureau

### EU Sources
- EUR-Lex: https://eur-lex.europa.eu/EN/display-feed.html?category=legislation
- European Parliament: https://www.europarl.europa.eu/rss/at-your-service/en/stay-informed.xml
- Council of EU: https://www.consilium.europa.eu/en/about-site/rss/press-releases.xml

## Usage Example

1. **Setup channels in Discord:**
   ```
   /news set_channel us_legislation #us-legislation
   /news set_channel eu_legislation #eu-legislation
   ```

2. **Enable auto-posting:**
   ```
   /news enable us_legislation
   /news enable eu_legislation
   ```

3. **Manual test:**
   ```
   /uslegislation congress_bills
   /eulegislation eurlex
   ```

4. **Monitor:**
   - Legislation posts appear every hour
   - Blue embeds with relevant emojis
   - EU uses official EU blue color (RGB: 0, 51, 153)

## Performance

- **Memory**: Same as other news categories (~150MB peak per run)
- **Bandwidth**: Minimal with ETag caching
- **Frequency**: Hourly is appropriate for legislative activity
- **Deduplication**: Last 50 links per source prevents duplicates

## Future Enhancements

- [ ] Add US state-level legislation sources
- [ ] Add UK Parliament RSS feeds
- [ ] Add bill status tracking (introduced, passed, enacted)
- [ ] Add vote results and roll calls
- [ ] Filter by specific topics/tags
- [ ] Add notification for "hot" bills (controversial/popular)
