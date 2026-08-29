#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Container healthcheck.

With METRICS_ENABLED=true this checks the bot's own /metrics endpoint and
requires the Discord gateway to be connected (penguin_bot_connected 1).
Without metrics there is nothing meaningful to probe from outside the
process, so it degrades to a liveness no-op (the previous behavior).
"""

import os
import sys
import urllib.request


def main() -> int:
    if os.getenv('METRICS_ENABLED', 'false').strip().lower() not in ('1', 'true', 'yes', 'on'):
        return 0

    port = os.getenv('METRICS_PORT', '9200')
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics', timeout=5) as response:
            body = response.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'unhealthy: metrics endpoint unreachable ({e})', file=sys.stderr)
        return 1

    for line in body.splitlines():
        if line.startswith('penguin_bot_connected '):
            value = line.split()[-1]
            if value in ('1', '1.0'):
                return 0
            print('unhealthy: bot not connected to the Discord gateway', file=sys.stderr)
            return 1

    print('unhealthy: penguin_bot_connected metric missing', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
