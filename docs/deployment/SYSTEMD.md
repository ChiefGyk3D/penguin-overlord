# systemd Deployment (install-systemd.sh)

`scripts/install-systemd.sh` installs Penguin Overlord as a set of systemd
units. This page describes what the script actually writes, unit by unit, and
the commands you use to run it afterwards. The script is the source of truth;
if this page and the script disagree, trust the script and open an issue.

## Run it as your normal user, not with sudo

```bash
cd /path/to/penguin-overlord
./scripts/install-systemd.sh
```

Do not prefix the command with `sudo`. The script reads `$USER`, `id -u` and
`id -g` at the top and writes them into every unit (`User=`, `Group=`, and
the `--user UID:GID` flag on the Docker timer containers). It calls `sudo`
itself for the steps that need root: writing to `/etc/systemd/system`,
`systemctl`, and `usermod`. You will be prompted for your password once.

If you run the script under `sudo`, `$USER` is `root`, so the bot and every
timer are installed as root and the containers run as `--user 0:0`. Files
under `data/` then end up root-owned and the non-root deployment breaks. That
is the bug the README refers to as "no more --user 0:0 issues".

## Prompts

The script asks, in order:

1. If `penguin-overlord.service` already exists: stop it, and reinstall with
   the same deployment mode (it detects Python vs Docker from the existing
   unit file).
2. **Deployment mode**: `1` Python (venv at `./venv`) or `2` Docker (image
   `penguin-overlord`, built locally or pulled from GHCR).
3. **News fetching strategy**: `1` Integrated (news loops run inside the bot,
   default) or `2` Optimized (one systemd timer per news category).
4. **Background task timers** (KEV, solar, XKCD, comics): `Y` (default) or `n`.
5. Whether to continue if `.env` is missing.
6. For Docker: reuse the existing image, or rebuild locally / pull from GHCR.
7. Enable and start the news timers (if selected).
8. Enable and start the background timers (if selected).
9. Enable `penguin-overlord.service` on boot, then start or restart it now.
10. Optional "fresh pull": run every selected service once immediately,
    optionally clearing `data/feed_cache_*.json` and `data/*_state.json`
    first.

## Units the script can create

All units are written to `/etc/systemd/system/`. Every service and timer
runs as the user who ran the script.

### Main bot (always)

| Unit | Notes |
|------|-------|
| `penguin-overlord.service` | Python mode: `Type=simple`, `venv/bin/python penguin-overlord/bot.py`, `Restart=always`, hardened with `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths=<project>`. Docker mode: `Type=oneshot` + `RemainAfterExit=yes` wrapping `docker run -d --name penguin-overlord --restart unless-stopped` with json-file log rotation (20m x 5) and `events/` + `data/` mounted. |

### News timers (only when news strategy 2, Optimized, is selected)

One `penguin-news-<category>.service` (oneshot) and one
`penguin-news-<category>.timer` per category. Each service runs
`penguin-overlord/news_runner.py --category <category>` from the
`penguin-overlord/` working directory (Python mode) or
`python3 /app/penguin-overlord/news_runner.py --category <category>` inside a
throwaway `--rm` container (Docker mode). Resource caps per run:
`MemoryMax=256M` (300M in Docker), `CPUQuota=50%`, `TasksMax=50`,
`TimeoutStartSec=120` (180 in Docker). Timers are `Persistent=true` with
`AccuracySec=1min`, so a missed run fires at the next boot.

`news_runner.py` accepts 11 categories. The script writes units for 10 of
them; KEV is covered by the background `penguin-kev` timer instead (see the
next section and "KEV is posted by one timer, not two").

| Category | Units | `OnCalendar` (as written in the script) | Plain English |
|----------|-------|------------------------------------------|---------------|
| `cve` | `penguin-news-cve.{service,timer}` | `*-*-* 00,08,16:00:00` | every 8 h at :00 |
| `cybersecurity` | `penguin-news-cybersecurity.{service,timer}` | `*-*-* 00,03,06,09,12,15,18,21:01:00` | every 3 h at :01 |
| `tech` | `penguin-news-tech.{service,timer}` | `*-*-* 00,04,08,12,16,20:30:00` | every 4 h at :30 |
| `gaming` | `penguin-news-gaming.{service,timer}` | `*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:15:00` | every 2 h at :15 |
| `apple_google` | `penguin-news-apple_google.{service,timer}` | `*-*-* 00,03,06,09,12,15,18,21:45:00` | every 3 h at :45 |
| `us_legislation` | `penguin-news-us_legislation.{service,timer}` | `*-*-* *:05:00` | hourly at :05 |
| `eu_legislation` | `penguin-news-eu_legislation.{service,timer}` | `*-*-* *:10:00` | hourly at :10 |
| `uk_legislation` | `penguin-news-uk_legislation.{service,timer}` | `*-*-* *:15:00` | hourly at :15 |
| `general_news` | `penguin-news-general_news.{service,timer}` | `*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:20:00` | every 2 h at :20 |
| `vendor_alerts` | `penguin-news-vendor_alerts.{service,timer}` | `*-*-* *:25,55:00` | every 30 min at :25 and :55 |
| `kev` | none under `penguin-news-`; see `penguin-kev` below | n/a | n/a |

Offsets are staggered on purpose so the 220+ feeds across the 11 categories
are never all fetched in the same minute.

### Background task timers (only when you answer Y to background timers)

Same shape as the news units: `penguin-<task>.service` (oneshot) plus
`penguin-<task>.timer`, running the matching runner script from
`penguin-overlord/`. Resource caps: `MemoryMax=256M` (300M in Docker),
`CPUQuota=50%`, `TasksMax=50`, `TimeoutStartSec=60` (90 in Docker).

| Task | Units | Runner | `OnCalendar` (as written in the script) | Plain English |
|------|-------|--------|------------------------------------------|---------------|
| KEV | `penguin-kev.{service,timer}` | `kev_runner.py` | `*-*-* 00,04,08,12,16,20:00:00` | every 4 h at :00 |
| Solar / propagation | `penguin-solar.{service,timer}` | `solar_runner.py` | `*-*-* *:00,30:00` | every 30 min |
| XKCD | `penguin-xkcd.{service,timer}` | `xkcd_runner.py` | `*-*-* *:00,30:00` | every 30 min |
| Comics | `penguin-comics.{service,timer}` | `comics_runner.py` | `*-*-* 10:00:00` | daily at 10:00 (host timezone) |

Note: the summary the script prints at the end says "Solar: every 6 hours" and
"KEV: every 4 hours at :30". Those lines are stale; the `OnCalendar` values
above are what is actually written. `systemctl list-timers 'penguin-*'` shows
the truth on your box.

### Unit count

| Selection | Units |
|-----------|-------|
| Main bot only (news integrated, no background timers) | 1 |
| Main bot + background timers | 1 + 8 = 9 |
| Main bot + news timers | 1 + 20 = 21 |
| Everything (news timers + background timers) | 1 + 20 + 8 = **29** |

## Turn off the in-bot loops when timers own posting

Selecting timers does not stop the bot's own `@tasks.loop` posters; the
script does not edit `.env`. Every news cog, the KEV cog, the XKCD poster and
the comics cog check `NEWS_AUTO_POST` at load. Add this to `.env` whenever
you deploy either set of timers, then restart the bot:

```bash
NEWS_AUTO_POST=false
```

Without it the same category is posted twice, once by the bot and once by
the timer, each with its own dedupe state. The in-bot solar poster is
different: it starts only if it was enabled through the bot's solar commands,
so leave that disabled when `penguin-solar.timer` is active.

## KEV is posted by one timer, not two

`news_runner.py --category kev` and `kev_runner.py` both post CISA KEV
entries, to the same channel (`NEWS_KEV_CHANNEL_ID`), from separate state
files. The installer only ever writes `penguin-kev.{service,timer}`; it never
creates `penguin-news-kev.*` (the `enable` loop mentions that name, but the
`systemctl enable` for it is a no-op because the unit does not exist).
`penguin-kev` is therefore the primary and the one to keep.

If a `penguin-news-kev.timer` exists on your host (left over from an older
install, or hand-written from the runner's usage text), remove one side:

```bash
# Keep penguin-kev, drop the news-runner copy
sudo systemctl disable --now penguin-news-kev.timer
sudo rm -f /etc/systemd/system/penguin-news-kev.timer /etc/systemd/system/penguin-news-kev.service
sudo systemctl daemon-reload
```

## Channel configuration

News channels are set from Discord and persisted in `data/news_config.json`,
or by environment variable, which the runners also read:

```
/news set_channel cybersecurity #security-news
/news set_channel tech #tech-news
/news set_channel gaming #gaming-news
/news set_channel cve #security-alerts
/news set_channel vendor_alerts #vendor-alerts
```

Equivalent `.env` keys are `NEWS_<CATEGORY>_CHANNEL_ID` (uppercase category,
for example `NEWS_APPLE_GOOGLE_CHANNEL_ID`, `NEWS_KEV_CHANNEL_ID`). The
background runners use `SOLAR_POST_CHANNEL_ID`, `XKCD_POST_CHANNEL_ID` and
`COMIC_POST_CHANNEL_ID`. All of them resolve through `utils/secrets.py`, so
Doppler values win over `.env`.

## Operating the units

### Main bot

```bash
sudo systemctl start penguin-overlord
sudo systemctl stop penguin-overlord
sudo systemctl restart penguin-overlord
sudo systemctl status penguin-overlord
sudo journalctl -u penguin-overlord -f
```

### Timers: status and schedules

```bash
# Every penguin timer, next and last run
sudo systemctl list-timers 'penguin-*'

# Only the news timers, or only one category
sudo systemctl list-timers 'penguin-news-*'
sudo systemctl status penguin-news-cybersecurity.timer

# Background timers
sudo systemctl status penguin-kev.timer penguin-solar.timer penguin-xkcd.timer penguin-comics.timer
```

### Logs

Each unit has its own `SyslogIdentifier` matching its name.

```bash
sudo journalctl -u penguin-news-tech -f
sudo journalctl -u penguin-kev -n 50
sudo journalctl -u penguin-solar --since today
sudo journalctl -f -u 'penguin-*'          # everything at once
sudo journalctl -u 'penguin-news-*' -p err  # news errors only
```

### Run a job now

Start the `.service`, not the `.timer`:

```bash
sudo systemctl start penguin-news-cve.service
sudo systemctl start penguin-kev.service
sudo systemctl start penguin-comics.service
```

### Enable or disable a single schedule

```bash
sudo systemctl disable --now penguin-news-gaming.timer
sudo systemctl enable --now penguin-news-gaming.timer
```

### Enable or disable a whole group

```bash
for c in cve cybersecurity tech gaming apple_google us_legislation eu_legislation uk_legislation general_news vendor_alerts; do
  sudo systemctl disable --now penguin-news-$c.timer
done

for t in kev solar xkcd comics; do
  sudo systemctl disable --now penguin-$t.timer
done
```

### Change a schedule

Edit the `OnCalendar=` line, or use a drop-in so a reinstall does not
overwrite it:

```bash
sudo systemctl edit penguin-news-cve.timer
# [Timer]
# OnCalendar=
# OnCalendar=*-*-* 00,06,12,18:00:00
sudo systemctl daemon-reload
sudo systemctl restart penguin-news-cve.timer
```

Verify with `systemd-analyze calendar '*-*-* 00,06,12,18:00:00'`.

## Reinstalling and upgrading

Run the installer again as your user. It detects the existing
`penguin-overlord.service`, offers to stop the bot, and offers to keep the
same deployment mode. In Docker mode a rebuild removes every `penguin-*`
container and the local and GHCR-tagged images first, then builds with
`--no-cache` or pulls `ghcr.io/chiefgyk3d/penguin-overlord:latest` (GHCR
only carries `main`; build locally for other branches). Timer units are
rewritten each time, so drop-ins (`systemctl edit`) are the safe place for
local schedule changes.

## Uninstall

The uninstaller is the one script that does run as root:

```bash
sudo ./scripts/uninstall-systemd.sh
```

It stops and disables `penguin-overlord.service`, every
`penguin-news-<category>.{service,timer}` (including a stray
`penguin-news-kev`), and every `penguin-{kev,solar,xkcd,comics}.{service,timer}`,
removes the unit files, and in Docker mode removes the `penguin-*`
containers and offers to remove the image. It leaves the project directory,
`venv/` and `data/` in place.

## Resource notes

- Integrated news mode keeps one process resident (roughly 350 to 500 MB
  with all news loops active) and polls 220+ feeds from inside the bot.
- Optimized mode keeps only the bot resident; each timer run is a short-lived
  process capped at 256 MB (300 MB in Docker) that fetches one category with
  ETag / Last-Modified conditional requests and exits. Idle cost is zero.
- Background timers survive bot restarts and crashes, which is why the
  script recommends them; a post that would have been missed while the bot
  was down fires at the next timer tick (`Persistent=true`).

## Related

- `docs/deployment/PRODUCTION.md`: Docker, compose, CI, secrets and logging.
- `docs/reference/NEWS_OPTIMIZATION.md`: why the news runner exists and how
  its caching works.
- `scripts/deploy-news-timers.sh`: an older, news-only deployer that hardcodes
  a `penguin` system user and covers six categories. Prefer the installer.
