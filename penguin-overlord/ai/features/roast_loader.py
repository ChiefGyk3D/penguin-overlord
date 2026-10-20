# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Loader and validator for the roast data files (roast_data/<distro>.json).

The wording of the roasts (prompt text, angles, formats, exemplars, banned
phrases, fallback jokes) lives in data, not in Python, so it can be replaced
without a code change. See docs/features/ROAST_DATA.md for the schema.

Two sources feed this loader and both are treated as untrusted input:
the files shipped in the package and an optional operator override
directory. Every malformed input raises `RoastDataError` (never a raw
OSError, UnicodeDecodeError, RecursionError or KeyError). Limits: a file
size cap read before parsing, duplicate keys rejected, NaN/Infinity
rejected, string types and lengths checked, list sizes capped, and the
override file is opened without following symlinks and must be a regular
file (so a FIFO cannot hang the bot).

House style: no em dash in any text that can reach a user. Loaded text is
stripped of it the same way the skid detector strips model output. The one
exemption is `system_prompt`, which is instruction text the model reads and
which names the rule itself.
"""

import json
import logging
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SHIPPED_DIR = Path(__file__).resolve().parent / 'roast_data'
DISTROS = ('arch', 'nix')

MAX_FILE_BYTES = 256 * 1024
MAX_PROMPT_CHARS = 8000
MAX_INSTRUCTION_CHARS = 1000
MAX_ENTRY_CHARS = 400
MAX_ANGLES = 64
MAX_EXEMPLARS = 32
MAX_BANNED = 64
MAX_FALLBACK = 500
MAX_HOUSE = 50
MAX_FORMATS = 16
MIN_LENGTH_LIMIT, MAX_LENGTH_LIMIT = 20, 1000
DEFAULT_MAX_LENGTH = 120

PLACEHOLDERS = ('{angles}', '{exemplars}', '{format}', '{avoid}')
EM_DASH = '—'

_LINE_BAD = re.compile(r'[\x00-\x1f\x7f]')
_BLOCK_BAD = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')
_PLACEHOLDER_RE = re.compile('|'.join(re.escape(p) for p in PLACEHOLDERS))

_TOP_KEYS = {
    'schema_version', 'system_prompt', 'user_prompt_tail', 'max_length', 'avoid_header',
    'exemplar_header', 'angles', 'formats', 'exemplars', 'banned_phrases',
    'fallback_jokes', 'house_jokes',
}
_REQUIRED = ('schema_version', 'system_prompt', 'user_prompt_tail', 'angles', 'formats', 'fallback_jokes')


class RoastDataError(ValueError):
    """A roast data file is missing, malformed, or over a limit."""


@dataclass(frozen=True)
class RoastFormat:
    name: str
    instruction: str
    max_length: Optional[int] = None


@dataclass(frozen=True)
class HouseJokes:
    chance: float
    jokes: tuple


@dataclass(frozen=True)
class RoastData:
    system_prompt: str
    user_prompt_tail: str
    max_length: int
    avoid_header: str
    exemplar_header: str
    angles: tuple
    formats: tuple
    exemplars: tuple
    banned_phrases: tuple
    fallback_jokes: tuple
    house_jokes: Optional[HouseJokes]


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------

def _no_dupes(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise RoastDataError(f'duplicate key {key[:60]!r}')
        seen[key] = value
    return seen


def _reject_constant(name):
    raise ValueError(f'constant {name} is not allowed')


def strip_em_dash(text: str) -> str:
    """Same replacement the skid detector applies to model output."""
    return text.replace(' ' + EM_DASH + ' ', ': ').replace(EM_DASH, ',')


def parse_roast_data(raw: bytes, source: str = 'roast data') -> RoastData:
    """Validate raw JSON bytes into a RoastData, or raise RoastDataError."""
    try:
        return _parse(raw)
    except RoastDataError as exc:
        raise RoastDataError(f'{source}: {exc}') from None


def _parse(raw: bytes) -> RoastData:
    if len(raw) > MAX_FILE_BYTES:
        raise RoastDataError(f'file too large (limit {MAX_FILE_BYTES} bytes)')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise RoastDataError('not valid UTF-8') from None
    try:
        doc = json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_reject_constant)
    except RoastDataError:
        raise
    except RecursionError:
        raise RoastDataError('not valid JSON: nested too deeply') from None
    except ValueError as exc:
        raise RoastDataError(f'not valid JSON ({str(exc)[:120]})') from None

    if not isinstance(doc, dict):
        raise RoastDataError('top level must be an object')
    unknown = sorted(set(doc) - _TOP_KEYS)
    if unknown:
        raise RoastDataError(f'unknown key {unknown[0][:60]!r}')
    for key in _REQUIRED:
        if key not in doc:
            raise RoastDataError(f'missing required key {key!r}')

    version = doc['schema_version']
    if isinstance(version, bool) or version != SCHEMA_VERSION or not isinstance(version, int):
        raise RoastDataError(f'schema_version must be the integer {SCHEMA_VERSION}')

    system_prompt = _prompt_text(doc['system_prompt'], 'system_prompt', MAX_PROMPT_CHARS)
    for placeholder in PLACEHOLDERS:
        if system_prompt.count(placeholder) != 1:
            raise RoastDataError(f'system_prompt: placeholder {placeholder} must appear exactly once')

    return RoastData(
        system_prompt=system_prompt,
        user_prompt_tail=_line(doc['user_prompt_tail'], 'user_prompt_tail'),
        max_length=_length(doc.get('max_length', DEFAULT_MAX_LENGTH), 'max_length'),
        avoid_header=_line(doc.get('avoid_header', ''), 'avoid_header', allow_blank=True),
        exemplar_header=_line(doc.get('exemplar_header', ''), 'exemplar_header', allow_blank=True),
        angles=_lines(doc['angles'], 'angles', MAX_ANGLES, required=True),
        formats=_formats(doc['formats']),
        exemplars=_lines(doc.get('exemplars', []), 'exemplars', MAX_EXEMPLARS),
        banned_phrases=_lines(doc.get('banned_phrases', []), 'banned_phrases', MAX_BANNED),
        fallback_jokes=_lines(doc['fallback_jokes'], 'fallback_jokes', MAX_FALLBACK, required=True),
        house_jokes=_house(doc.get('house_jokes')),
    )


def _string(value, where: str) -> str:
    if not isinstance(value, str):
        raise RoastDataError(f'{where}: must be a string')
    return value


def _prompt_text(value, where: str, cap: int) -> str:
    """Multi-line instruction text. Em dashes are allowed here (see module doc)."""
    text = _string(value, where)
    if not text.strip():
        raise RoastDataError(f'{where}: must not be blank')
    if len(text) > cap:
        raise RoastDataError(f'{where}: too long (limit {cap} characters)')
    if _BLOCK_BAD.search(text):
        raise RoastDataError(f'{where}: contains control characters')
    return text


def _line(value, where: str, allow_blank: bool = False) -> str:
    text = strip_em_dash(_string(value, where)).strip()
    if not text and not allow_blank:
        raise RoastDataError(f'{where}: must not be blank')
    if len(text) > MAX_ENTRY_CHARS:
        raise RoastDataError(f'{where}: too long (limit {MAX_ENTRY_CHARS} characters)')
    if _LINE_BAD.search(text):
        raise RoastDataError(f'{where}: must be one line with no control characters')
    return text


def _lines(value, where: str, cap: int, required: bool = False) -> tuple:
    if not isinstance(value, list):
        raise RoastDataError(f'{where}: must be a list')
    if len(value) > cap:
        raise RoastDataError(f'{where}: too many entries (limit {cap})')
    if required and not value:
        raise RoastDataError(f'{where}: must not be empty')
    out = [_line(item, f'{where}[{i}]') for i, item in enumerate(value)]
    if len(set(out)) != len(out):
        raise RoastDataError(f'{where}: duplicate entry')
    return tuple(out)


def _length(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoastDataError(f'{where}: must be an integer')
    if not MIN_LENGTH_LIMIT <= value <= MAX_LENGTH_LIMIT:
        raise RoastDataError(f'{where}: must be between {MIN_LENGTH_LIMIT} and {MAX_LENGTH_LIMIT}')
    return value


def _formats(value) -> tuple:
    if not isinstance(value, list):
        raise RoastDataError('formats: must be a list')
    if len(value) > MAX_FORMATS:
        raise RoastDataError(f'formats: too many entries (limit {MAX_FORMATS})')
    if not value:
        raise RoastDataError('formats: must not be empty')
    out = []
    for i, item in enumerate(value):
        where = f'formats[{i}]'
        if not isinstance(item, dict):
            raise RoastDataError(f'{where}: must be an object')
        extra = sorted(set(item) - {'name', 'instruction', 'max_length'})
        if extra:
            raise RoastDataError(f'{where}: unknown key {extra[0][:60]!r}')
        for key in ('name', 'instruction'):
            if key not in item:
                raise RoastDataError(f'{where}: missing key {key!r}')
        instruction = strip_em_dash(_string(item['instruction'], f'{where}.instruction')).strip()
        if len(instruction) > MAX_INSTRUCTION_CHARS:
            raise RoastDataError(f'{where}.instruction: too long (limit {MAX_INSTRUCTION_CHARS} characters)')
        if _BLOCK_BAD.search(instruction):
            raise RoastDataError(f'{where}.instruction: contains control characters')
        limit = _length(item['max_length'], f'{where}.max_length') if 'max_length' in item else None
        out.append(RoastFormat(_line(item['name'], f'{where}.name'), instruction, limit))
    if len({f.name for f in out}) != len(out):
        raise RoastDataError('formats: duplicate format name')
    return tuple(out)


def _house(value) -> Optional[HouseJokes]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RoastDataError('house_jokes: must be an object')
    extra = sorted(set(value) - {'chance', 'jokes'})
    if extra:
        raise RoastDataError(f'house_jokes: unknown key {extra[0][:60]!r}')
    for key in ('chance', 'jokes'):
        if key not in value:
            raise RoastDataError(f'house_jokes: missing key {key!r}')
    chance = value['chance']
    if isinstance(chance, bool) or not isinstance(chance, (int, float)) \
            or not math.isfinite(chance) or not 0 <= chance <= 1:
        raise RoastDataError('house_jokes.chance: must be a number from 0 to 1')
    jokes = _lines(value['jokes'], 'house_jokes.jokes', MAX_HOUSE, required=True)
    return HouseJokes(float(chance), jokes)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _bullets(items, prefix: str) -> str:
    return '\n'.join(f'{prefix}{item}' for item in items)


def render_system_prompt(data: RoastData, angles, fmt: RoastFormat, avoid, exemplars) -> str:
    """Fill the system prompt template.

    Single pass, so text inserted for one placeholder is never expanded as
    another. A placeholder that renders empty takes its whole line with it.
    """
    blocks = {
        '{angles}': _bullets(angles, '  * '),
        '{format}': fmt.instruction,
        '{exemplars}': (data.exemplar_header + '\n' if data.exemplar_header else '')
        + _bullets(exemplars, '- ') if exemplars else '',
        '{avoid}': (data.avoid_header + '\n' if data.avoid_header else '')
        + _bullets(avoid, '- ') if avoid else '',
    }
    out = []
    for line in data.system_prompt.split('\n'):
        if line.strip() in blocks and not blocks[line.strip()]:
            continue
        out.append(_PLACEHOLDER_RE.sub(lambda m: blocks[m.group(0)], line))
    text = '\n'.join(out)
    return re.sub(r'\n{3,}', '\n\n', text)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class _NoFile(Exception):
    """The file does not exist in the directory (not an error for an override)."""


def _read_capped(directory, filename: str) -> bytes:
    """Read <directory>/<filename> safely: no symlink, regular file, size cap."""
    try:
        dir_fd = os.open(os.fspath(directory), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    except OSError:
        raise RoastDataError('directory not found or not readable') from None
    try:
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
        except FileNotFoundError:
            raise _NoFile from None
        except OSError:
            raise RoastDataError(f'cannot open {filename} (symlinks are refused)') from None
    finally:
        os.close(dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RoastDataError(f'{filename} is not a regular file')
        chunks, total = [], 0
        while total <= MAX_FILE_BYTES:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b''.join(chunks)
    except OSError:
        raise RoastDataError(f'cannot read {filename}') from None
    finally:
        os.close(fd)


def _load_from(directory, distro: str) -> RoastData:
    filename = f'{distro}.json'
    return parse_roast_data(_read_capped(directory, filename), source=filename)


def load_roast_data(distro: str, override_dir: Optional[str] = None) -> RoastData:
    """Roast data for *distro*.

    A valid `<override_dir>/<distro>.json` replaces the shipped file
    wholesale. An invalid one is logged (a warning that names the file and
    the problem, never its contents) and the shipped file is used instead.
    A shipped file that fails validation raises RoastDataError: that is a
    packaging bug, not an operator mistake.
    """
    if distro not in DISTROS:
        raise RoastDataError(f'unknown distro {str(distro)[:40]!r}')
    if override_dir:
        try:
            data = _load_from(override_dir, distro)
            logger.info('Using operator roast data for %s from the override directory', distro)
            return data
        except _NoFile:
            pass
        except RoastDataError as exc:
            logger.warning('Ignoring operator roast data for %s, using the shipped file: %s',
                           distro, str(exc)[:300])
    try:
        return _load_from(SHIPPED_DIR, distro)
    except _NoFile:
        raise RoastDataError(f'shipped {distro}.json is missing') from None
