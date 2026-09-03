# News System Optimization Guide
**Efficient, Low-Resource News Aggregation for Penguin Overlord Bot**

> **Deploying?** Use `scripts/install-systemd.sh` (run as your own user,
> not with sudo) and choose news strategy 2, "Optimized". It writes one
> service and timer per category with the schedules below. Unit names and
> operating commands are in
> [docs/deployment/SYSTEMD.md](../deployment/SYSTEMD.md). This page explains
> why the runner exists and how it saves bandwidth; it is not a set of unit
> files to copy.

The standalone runner is `penguin-overlord/news_runner.py`. It is invoked
from the `penguin-overlord/` directory (that is the unit's
`WorkingDirectory`), one category per run:

```bash
cd /path/to/penguin-overlord/penguin-overlord
../venv/bin/python news_runner.py --category cybersecurity
# or, as the installer writes it, with absolute paths:
/path/to/penguin-overlord/venv/bin/python /path/to/penguin-overlord/penguin-overlord/news_runner.py --category cybersecurity
```

Categories (11): `cybersecurity`, `tech`, `gaming`, `apple_google`, `cve`,
`kev`, `us_legislation`, `eu_legislation`, `uk_legislation`, `general_news`,
`vendor_alerts`. Together they cover 220+ feeds.

## 📊 Performance Improvements

### Before Optimization
- ❌ 11 long-running tasks in Discord bot (24/7)
- ❌ Re-fetching full feeds every cycle (~5MB each)
- ❌ No duplicate detection across restarts
- ❌ Fixed intervals causing traffic spikes
- ❌ Memory: ~500MB constant usage

### After Optimization
- ✅ Scheduled systemd timers (run & exit)
- ✅ ETag/Last-Modified caching (~99% bandwidth reduction)
- ✅ GUID tracking prevents duplicates
- ✅ Staggered intervals distribute load
- ✅ Memory: ~50-150MB peak, 0MB idle

## 🎯 Optimization Strategy

### 1. Staggered Scheduling
Prevents traffic spikes and distributes system load:

| Category         | Interval   | Offset     | Example Times                | Timer unit |
|------------------|------------|------------|------------------------------|------------|
| CVE              | 8 hours    | :00        | 00:00, 08:00, 16:00          | `penguin-news-cve.timer` |
| Cybersecurity    | 3 hours    | :01        | 00:01, 03:01, 06:01...       | `penguin-news-cybersecurity.timer` |
| Tech             | 4 hours    | :30        | 00:30, 04:30, 08:30...       | `penguin-news-tech.timer` |
| Gaming           | 2 hours    | :15        | 00:15, 02:15, 04:15...       | `penguin-news-gaming.timer` |
| Apple/Google     | 3 hours    | :45        | 00:45, 03:45, 06:45...       | `penguin-news-apple_google.timer` |
| US Legislation   | 1 hour     | :05        | 00:05, 01:05, 02:05...       | `penguin-news-us_legislation.timer` |
| EU Legislation   | 1 hour     | :10        | 00:10, 01:10, 02:10...       | `penguin-news-eu_legislation.timer` |
| UK Legislation   | 1 hour     | :15        | 00:15, 01:15, 02:15...       | `penguin-news-uk_legislation.timer` |
| General News     | 2 hours    | :20        | 00:20, 02:20, 04:20...       | `penguin-news-general_news.timer` |
| Vendor Alerts    | 30 minutes | :25, :55   | 00:25, 00:55, 01:25...       | `penguin-news-vendor_alerts.timer` |
| KEV              | 4 hours    | :00        | 00:00, 04:00, 08:00...       | `penguin-kev.timer` (background runner `kev_runner.py`, not `news_runner.py`) |

These are the `OnCalendar` values `install-systemd.sh` writes. KEV is the one
category the installer schedules through the dedicated `kev_runner.py`
instead of `news_runner.py --category kev`; run one or the other, not both
(see SYSTEMD.md).

**Benefit**: Network activity spread across the hour instead of bunched together.

### 2. HTTP ETag Caching
Implements RFC 7232 conditional requests:

```http
# First request - full download
GET /feed.xml HTTP/1.1
Host: example.com
→ 200 OK
   ETag: "abc123"
   Content-Length: 524288

# Subsequent requests - conditional
GET /feed.xml HTTP/1.1
Host: example.com
If-None-Match: "abc123"
→ 304 Not Modified
   Content-Length: 0
```

**Benefit**: 
- Unchanged feeds return 304 (no body)
- Saves ~5MB → ~500 bytes per feed
- ~99% bandwidth reduction
- Faster response times

### 3. GUID Deduplication
Tracks last 50 GUIDs per feed:

```python
# Before: Link-based tracking (unreliable)
if link != last_posted_link:
    post(item)

# After: GUID-based tracking (reliable)
if guid not in last_50_guids:
    post(item)
```

**Benefit**:
- Survives bot restarts
- Handles feed re-ordering
- Prevents duplicate posts

### 4. Concurrency Control
Semaphore-based rate limiting:

```python
# Limit concurrent requests per category
semaphore = asyncio.Semaphore(5)  # Max 5 at once

async with semaphore:
    response = await session.get(url)
```

**Benefit**:
- Prevents overwhelming remote servers
- Reduces memory spikes
- Better error handling

### 5. Systemd Timers (vs. Long-Running)
Replace continuous loops with scheduled runs:

```systemd
# Run every 3 hours at :01
OnCalendar=*-*-* 00,03,06,09,12,15,18,21:01:00
Type=oneshot  # Exits after completion
```

**Benefit**:
- Zero memory when idle
- Automatic crash recovery (systemd restarts)
- Better resource isolation
- Easier to monitor

## 🚀 Deployment Options

### Option A: Systemd Timers (Recommended)
**Best for**: Production, 24/7 operation, low resource systems

```bash
# Deploy all timers: run the installer as your user (it sudo's internally)
# and pick news strategy 2 (Optimized). Do not hand-write unit files.
./scripts/install-systemd.sh

# Tell the bot to stop running its own news loops
echo 'NEWS_AUTO_POST=false' >> .env && sudo systemctl restart penguin-overlord

# Check status
systemctl list-timers 'penguin-news-*'

# View logs
journalctl -u penguin-news-cybersecurity -f
```

Full unit list, schedules, enable/disable and uninstall commands:
[docs/deployment/SYSTEMD.md](../deployment/SYSTEMD.md).

**Pros**:
- Lowest resource usage
- Automatic restarts on failure
- Centralized logging
- Production-grade reliability

**Cons**:
- Needs sudo for the unit files (the installer prompts for it)
- Linux-only

### Option B: Cron Jobs
**Best for**: Simple setups, shared hosting

```bash
# Add to crontab
crontab -e

# Adjust the two paths: the repo checkout and its venv.
# The runner lives in penguin-overlord/ and is run from that directory.
PENGUIN=/path/to/penguin-overlord
PY=$PENGUIN/venv/bin/python

# CVE - Every 8 hours at :00
0 */8 * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category cve

# Cybersecurity - Every 3 hours at :01
1 */3 * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category cybersecurity

# Tech - Every 4 hours at :30
30 */4 * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category tech

# Gaming - Every 2 hours at :15
15 */2 * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category gaming

# Apple/Google - Every 3 hours at :45
45 */3 * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category apple_google

# US / EU / UK legislation - hourly at :05, :10, :15
5 * * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category us_legislation
10 * * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category eu_legislation
15 * * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category uk_legislation

# General news - Every 2 hours at :20
20 */2 * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category general_news

# Vendor alerts - Every 30 minutes at :25 and :55
25,55 * * * * cd $PENGUIN/penguin-overlord && $PY news_runner.py --category vendor_alerts

# KEV - Every 4 hours at :00 (dedicated runner, same directory)
0 */4 * * * cd $PENGUIN/penguin-overlord && $PY kev_runner.py
```

Cron does not load `.env`; export the variables in the crontab or source the
file in a wrapper. Set `NEWS_AUTO_POST=false` for the bot here too.

**Pros**:
- No root required (user crontab)
- Universal (works everywhere)
- Simple setup

**Cons**:
- Less robust error handling
- Manual log management
- No automatic restarts

### Option C: Discord Bot Tasks (Original)
**Best for**: Development, testing, single-purpose bot

Keep the existing `@tasks.loop()` decorators in cogs.

**Pros**:
- Integrated with bot
- Immediate feedback
- Easy debugging

**Cons**:
- Higher memory usage (24/7)
- All news stops if bot crashes
- No load distribution

## 📈 Performance Metrics

### Bandwidth Usage

Rough sizing with 220+ sources across 11 categories. Feeds vary a lot in
size (the cybersecurity category alone is over 100 of them), so treat these
as order-of-magnitude figures, not a measurement.

#### Without Optimization (full re-download every run):
```
220 sources × ~1MB avg           = ~220MB if every feed were fetched once
Runs per day, all categories     = 3 + 8 + 6 + 12 + 8 + 24 + 24 + 24 + 12 + 48 = 169
Weighted by category size        = several GB/day, tens to hundreds of GB/month
```

#### With ETag / Last-Modified Caching:
```
Unchanged feed                   = ~500 bytes (304 Not Modified, no body)
Changed feed                     = full download, but only the ones that changed
Typical day                      = tens to low hundreds of MB
```

**Savings**: roughly 99% of transfer once the cache is warm, because most
feeds do not change between polls and answer with a 304.

### Memory Usage

| Mode              | Idle | Peak During Run |
|-------------------|------|-----------------|
| Long-running bot  | 500M | 600M            |
| Systemd timers    | 0M   | 150M            |
| Cron jobs         | 0M   | 150M            |

**Savings**: 500MB constant → 0MB idle

### CPU Usage

| Mode              | Idle | During Run |
|-------------------|------|------------|
| Long-running bot  | 2-5% | 10-20%     |
| Systemd timers    | 0%   | 10-20%     |

**Runtime**: 10-30 seconds per category run

## 🔧 Configuration

### Cache Settings
Edit `data/news_config.json`:

```json
{
  "cybersecurity": {
    "use_etag_cache": true,        // Enable ETag caching
    "concurrency_limit": 5,         // Max concurrent requests
    "interval_hours": 3,            // How often to run
    "minute_offset": 1              // Start at :01
  }
}
```

### Concurrency Limits
Adjust based on server capacity:

```python
# Conservative (slow server)
concurrency_limit = 3

# Balanced (normal)
concurrency_limit = 5

# Aggressive (powerful server)
concurrency_limit = 10
```

### Cache Persistence
One cache file per category, `feed_cache_<category>.json`, holding ETags,
Last-Modified values and the recent GUIDs:

- `feed_cache_cybersecurity.json`, `feed_cache_tech.json`,
  `feed_cache_gaming.json`, `feed_cache_apple_google.json`,
  `feed_cache_cve.json`
- `feed_cache_us_legislation.json`, `feed_cache_eu_legislation.json`,
  `feed_cache_uk_legislation.json`
- `feed_cache_general_news.json`, `feed_cache_vendor_alerts.json`
- `feed_cache_kev.json` only if you run `news_runner.py --category kev`;
  the installer uses `kev_runner.py`, which keeps `data/kev_state.json`
  (relative to its working directory) instead.

Location: `news_runner.py` writes its caches under `/app/data`, the volume
the Docker image and the installer's `docker run` mount from the project's
`data/` directory. In Python (venv) mode that path must exist and be
writable by the service user, or the run fails before fetching anything.

**Automatic cleanup**: Keeps last 50 GUIDs per feed

## 📊 Monitoring

### Check Timer Status
```bash
# List all timers and next run times
systemctl list-timers penguin-news-*

# Detailed status
systemctl status penguin-news-cybersecurity.timer
```

### View Real-Time Logs
```bash
# Follow specific category
journalctl -u penguin-news-cybersecurity -f

# All news categories
journalctl -u 'penguin-news-*' -f --since today

# Show only errors
journalctl -u 'penguin-news-*' -p err
```

### Performance Statistics
```bash
# Run count per timer
systemctl show penguin-news-cybersecurity.timer | grep NAccepted

# Last run time
systemctl show penguin-news-cybersecurity.service | grep ExecMainExitTimestamp

# Resource usage
systemctl status penguin-news-cybersecurity.service | grep Memory
```

### Cache Efficiency
Check cache hit rate:

```bash
# View cache file
cat data/feed_cache_cybersecurity.json | jq

# Count cached feeds
jq '.etags | length' data/feed_cache_cybersecurity.json
```

## 🔍 Troubleshooting

### Timer Not Running
```bash
# Check if enabled
systemctl is-enabled penguin-news-cybersecurity.timer

# Enable it
sudo systemctl enable penguin-news-cybersecurity.timer

# Start it
sudo systemctl start penguin-news-cybersecurity.timer
```

### Service Failing
```bash
# Check logs
journalctl -u penguin-news-cybersecurity -n 50

# Test manually, as the user the units run as (the one who ran the installer)
cd /path/to/penguin-overlord/penguin-overlord
../venv/bin/python news_runner.py --category cybersecurity --verbose

# Or let systemd run it exactly as the timer would
sudo systemctl start penguin-news-cybersecurity.service

# Check permissions on the state directory
ls -la /path/to/penguin-overlord/data/
```

### High Memory Usage
```bash
# Check current usage
systemctl status penguin-news-*.service | grep Memory

# Set lower limits in service files
sudo vim /etc/systemd/system/penguin-news-cybersecurity.service
# Change: MemoryMax=128M

# Reload
sudo systemctl daemon-reload
```

### Cache Not Working
```bash
# Verify cache file exists and is writable
ls -la data/feed_cache_*.json

# Check file contents
jq . data/feed_cache_cybersecurity.json

# Test with verbose logging (from the penguin-overlord/ directory)
cd penguin-overlord && ../venv/bin/python news_runner.py --category cybersecurity --verbose
```

## 🎯 Best Practices

1. **Start with systemd timers** - Most efficient for 24/7 operation
2. **Monitor for first week** - Watch logs to catch issues early
3. **Adjust intervals as needed** - Not all feeds update frequently
4. **Keep cache files** - Don't delete, they prevent duplicates
5. **Enable log rotation** - Prevent disk space issues
6. **Set resource limits** - Protect system from runaway processes

## 📚 Additional Resources

- **Deployment and unit reference**: [docs/deployment/SYSTEMD.md](../deployment/SYSTEMD.md)
- **Installer** (writes every unit): `scripts/install-systemd.sh`
- **Standalone runner**: `penguin-overlord/news_runner.py`
- **KEV runner**: `penguin-overlord/kev_runner.py`
- **Fetcher library**: `penguin-overlord/utils/news_fetcher.py`
- **Cross-feed dedupe**: `penguin-overlord/utils/news_dedupe.py` (also home of the `NEWS_AUTO_POST` gate)
- **Historical**: `docs/archive/NEWS_OPTIMIZATION.conf`, the original hand-written unit examples. Paths in it are wrong for the current tree; kept for history only.

## 🔮 Future Enhancements

- **SQLite Database**: Replace JSON files for better performance
- **Webhook Support**: Push notifications instead of polling
- **Feed Health Monitoring**: Alert on broken feeds
- **Intelligent Scheduling**: Adjust frequency based on update patterns
- **Redis Caching**: Distributed caching for multiple bots
