#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Configuration pre-flight.

Loads the environment exactly the way bot.py does (.env, then the secrets
manager on top) and validates it with utils.config. Prints OK plus a
values-free summary, or the full list of missing and malformed variables.
Exit code 0 when the bot would start, 1 when it would refuse.

Meant for a container init step or a deploy hook:

    python scripts/check-config.py
    docker compose run --rm penguin-overlord python scripts/check-config.py

Never prints a value: secrets are redacted by type, and the summary is
counts and on/off flags only.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'penguin-overlord'))

from dotenv import load_dotenv  # noqa: E402

from utils.config import ConfigError, describe_config, load_config  # noqa: E402


def main() -> int:
    load_dotenv()
    try:
        config = load_config()
    except ConfigError as e:
        print(f'FAIL: {e}', file=sys.stderr)
        return 1
    print(f'OK: {describe_config(config)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
