# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared JSON state persistence for cogs and runners.

Guarantees the two properties the hand-rolled per-cog savers lacked:

- **Atomic writes**: state is written to a temp file in the same directory
  and swapped in with os.replace, so a crash or SIGKILL mid-write can never
  leave a truncated file behind (a truncated state file used to silently
  reset dedup state and mass re-post every feed).
- **Corrupt files are preserved, not swallowed**: an unreadable state file
  is renamed to <name>.corrupt-<timestamp> and logged loudly before the
  default is returned, so the evidence survives and the operator notices.

Also centralizes data-directory resolution (previously three divergent
schemes across cogs and runners):
    1. DATA_DIR env var, if set
    2. /app/data when it exists (the Docker volume mount)
    3. ./data relative to the current working directory
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_data_dir() -> Path:
    """Resolve the data directory using the env var > Docker volume > CWD order.

    DATA_DIR is parsed in exactly one place, utils/config.py, so the cogs,
    the runners and this helper cannot drift apart on it.
    """
    from utils.config import load_paths_config
    return load_paths_config().data_dir


def state_path(filename: str) -> Path:
    """Full path for a state file name inside the resolved data directory."""
    name = Path(filename).name  # never allow directory traversal via config
    return resolve_data_dir() / name


def load_json_state(path, default=None):
    """Load JSON state from *path*.

    Returns *default* (or {}) when the file is missing. When the file exists
    but cannot be parsed, it is preserved as <path>.corrupt-<timestamp> and
    the default is returned — the previous behavior of silently resetting
    state hid corruption and caused mass re-posts.
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        quarantine = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            os.replace(path, quarantine)
            logger.error(
                f"State file {path} is corrupt ({e}); preserved as {quarantine} "
                f"and falling back to defaults"
            )
        except OSError:
            logger.error(f"State file {path} is corrupt ({e}) and could not be quarantined")
        return default


def save_json_state(path, data) -> bool:
    """Atomically write *data* as JSON to *path*.

    Writes to a temp file in the same directory, fsyncs, then os.replace()s
    it over the target, so readers always see either the old or the new
    complete file. Returns True on success.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix='.tmp'
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return True
    except OSError as e:
        logger.error(f"Failed to save state to {path}: {e}")
        return False
