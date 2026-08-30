# Logging and log rotation

Every entry point — the bot and the five one-shot runners — configures
logging through `utils/logging_setup.py`. Nothing else calls
`basicConfig`, and `bot.run()` is passed `log_handler=None` so discord.py
does not install a second root handler of its own.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root level. `DEBUG` for feed parsing and model prompts. An unrecognised value falls back to `INFO` rather than failing to start. |
| `LOG_FILE` | unset | Also write to this path, with in-process rotation. Leave unset in Docker — the daemon rotates instead. |
| `LOG_MAX_BYTES` | `10485760` (10 MB) | Rotate the file at this size. |
| `LOG_BACKUPS` | `5` | Rotated files to keep, so ~60 MB at the defaults. |

Stdout logging is always on, whatever else is configured, so
`docker logs` and `journalctl` are never empty.

Third-party loggers are pinned to WARNING: `httpx`, `httpcore`,
`urllib3`, `aiohttp.access`, `asyncio`, `discord.http`, `discord.state`,
`websockets`. `httpx` alone logged a line per model call — two per scanned
message — which buried the moderation records it sat between.

## Rotation

Rotation lives in one of two places, depending on how you run the bot.

**Docker (the normal deployment).** The json-file driver rotates, set
explicitly on the container so it does not depend on the host's
`daemon.json`:

```
--log-driver json-file --log-opt max-size=20m --log-opt max-file=5
```

That is in `scripts/install-systemd.sh` and `docker-compose.yml`, and caps
the bot at ~100 MB. A host-wide default is still worth setting, since it
covers every other container too:

```json
/etc/docker/daemon.json
{ "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "3" } }
```

An existing deployment picks up the new flags at the next
`systemctl restart penguin-overlord` **after** the unit file is updated —
re-run `scripts/install-systemd.sh`, or edit the `ExecStart` line and
`systemctl daemon-reload`.

**Bare metal.** No Docker driver, so set `LOG_FILE` and the in-process
`RotatingFileHandler` does the same job:

```env
LOG_FILE=/var/log/penguin-overlord/bot.log
LOG_MAX_BYTES=20971520
LOG_BACKUPS=5
```

The one-shot news and comic timers run attached under systemd, so their
output lands in journald and is bounded by `SystemMaxUse` in
`/etc/systemd/journald.conf` (10% of the filesystem by default). If those
timers dominate your journal, `journalctl --disk-usage` will show it.

## Reading the logs

```bash
docker logs -f penguin-overlord                    # live
docker logs --since 2h penguin-overlord            # recent
journalctl -u penguin-overlord --since today       # systemd's view

# moderation review clicks: arrival, then resolution with latency
docker logs --since 24h penguin-overlord | grep -E 'Review button|Review .* resolved'
```

A missing `Review button ... clicked` line for a click a moderator says
they made means the interaction never reached the bot — a delivery
problem, not a handler problem. That distinction is why the line exists.
