# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One logging configuration for every entry point.

The bot and the five one-shot runners each used to call `basicConfig`
themselves, at different levels (news_runner defaulted to DEBUG), and
`bot.run()` additionally installed discord.py's own root handler on top —
so every `discord.*` record was emitted twice. This module replaces all of
that with a single `configure_logging()` call.

Rotation is handled in two places, deliberately:

- **Container (normal deployment):** the Docker json-file driver rotates,
  configured on the `docker run` in the systemd unit and in
  docker-compose.yml. Logs stay in `docker logs` / journald where the rest
  of the host's logs are.
- **Bare metal or when you want a file:** set `LOG_FILE` and a
  `RotatingFileHandler` takes over the same rotation job in-process.

Never both by accident: a file handler is added only when `LOG_FILE` is
set, and stdout logging always stays on so `docker logs` is never empty.
"""

import logging
import logging.handlers
import os
from pathlib import Path

# Third-party loggers that are useful at WARNING and pure noise at INFO.
# httpx logs a line per request: with two model calls per scanned message
# that buried the bot's own records in the moderation logs.
_NOISY = {
    'httpx': logging.WARNING,
    'httpcore': logging.WARNING,
    'urllib3': logging.WARNING,
    'aiohttp.access': logging.WARNING,
    'asyncio': logging.WARNING,
    'discord.http': logging.WARNING,
    'discord.state': logging.WARNING,
    'websockets': logging.WARNING,
}

_FORMAT = '%(asctime)s %(levelname)-8s %(name)s: %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'

# Marks the handlers this module owns, so repeat calls replace their own
# work instead of stacking duplicates on top of it.
_OWNED = '_penguin_logging'

DEFAULT_MAX_BYTES = 10 * 1024 * 1024   # 10 MB per file
DEFAULT_BACKUPS = 5                    # ~60 MB ceiling with the default size


def _level(name: str, default: int = logging.INFO) -> int:
    raw = (os.getenv(name) or '').strip().upper()
    if not raw:
        return default
    resolved = logging.getLevelName(raw)
    return resolved if isinstance(resolved, int) else default


def configure_logging(component: str = 'penguin', *, level: int = None) -> logging.Logger:
    """Install stdout logging (plus a rotating file when LOG_FILE is set).

    Env:
        LOG_LEVEL     root level, default INFO (DEBUG/INFO/WARNING/...)
        LOG_FILE      path to also write to; enables in-process rotation
        LOG_MAX_BYTES rotate at this size, default 10 MB
        LOG_BACKUPS   keep this many rotated files, default 5

    Returns the component's logger. Safe to call more than once.
    """
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _OWNED, False)]:
        root.removeHandler(handler)
        handler.close()

    root.setLevel(level if level is not None else _level('LOG_LEVEL'))
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    setattr(stream, _OWNED, True)
    root.addHandler(stream)

    log_file = (os.getenv('LOG_FILE') or '').strip()
    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=int(os.getenv('LOG_MAX_BYTES') or DEFAULT_MAX_BYTES),
                backupCount=int(os.getenv('LOG_BACKUPS') or DEFAULT_BACKUPS),
                encoding='utf-8',
            )
            file_handler.setFormatter(formatter)
            setattr(file_handler, _OWNED, True)
            root.addHandler(file_handler)
        except OSError as e:
            # An unwritable LOG_FILE must never stop the bot from starting;
            # stdout logging is already in place to carry the complaint.
            root.warning('LOG_FILE %s is not writable (%s) — stdout only', log_file, e)

    for name, noisy_level in _NOISY.items():
        logging.getLogger(name).setLevel(noisy_level)

    return logging.getLogger(component)


def describe_logging() -> str:
    """One-line summary for the startup banner."""
    root = logging.getLogger()
    sinks = ['stdout']
    for handler in root.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            sinks.append(f'{handler.baseFilename} '
                         f'(rotate {handler.maxBytes // (1024 * 1024)}MB x{handler.backupCount})')
    return f"level={logging.getLevelName(root.level)} sinks={', '.join(sinks)}"
