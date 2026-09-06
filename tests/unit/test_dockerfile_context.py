# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Dockerfile and .dockerignore have to agree about scripts/.

.dockerignore excludes `scripts/*` wholesale and re-includes named files.
A COPY of a script nobody re-included fails the build with "file not
found", which is how CI found this once: the Dockerfile was edited and
.dockerignore was not. Static check, no daemon needed.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / 'Dockerfile'
DOCKERIGNORE = REPO_ROOT / '.dockerignore'

# COPY [--flags] <src>... <dest>
_COPY = re.compile(r'^\s*COPY\s+(?P<rest>.+)$')


def _copy_sources() -> list:
    """Every build-context source path a COPY instruction reads."""
    sources = []
    for line in DOCKERFILE.read_text(encoding='utf-8').splitlines():
        match = _COPY.match(line)
        if not match:
            continue
        words = match['rest'].split()
        if any(w.startswith('--from=') for w in words):
            continue          # copied from an earlier stage, not the context
        words = [w for w in words if not w.startswith('--')]
        if len(words) < 2:
            continue
        # The last word is the destination inside the image.
        sources.extend(words[:-1])
    return sources


def _dockerignore_lines() -> list:
    return [line.strip() for line in DOCKERIGNORE.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.strip().startswith('#')]


def test_every_copied_script_is_re_included_in_dockerignore():
    ignored = _dockerignore_lines()
    assert 'scripts/*' in ignored, 'the scripts/* exclusion moved; update this test'
    copied = [s for s in _copy_sources() if s.startswith('scripts/')]
    assert copied, 'no scripts are COPYed; did the Dockerfile change shape?'
    for source in copied:
        assert f'!{source}' in ignored, (
            f'Dockerfile COPYs {source} but .dockerignore never re-includes it, '
            f'so the build context will not contain it')


def test_check_config_ships_in_the_image():
    # Operators run it against the real .env with the image's own Python.
    assert 'scripts/check-config.py' in _copy_sources()


@pytest.mark.parametrize('source', sorted(set(_copy_sources())))
def test_every_copy_source_exists(source):
    assert (REPO_ROOT / source).exists(), f'Dockerfile COPYs a missing {source}'
