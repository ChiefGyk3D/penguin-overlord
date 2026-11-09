# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Security event log: schema, validated writer, JSONL sink, SQLite store.

The design is docs/features/SECURITY_EVENT_LOG.md. This module is the
collection half and has no Discord imports, so it is unit-testable and the
runners can use it. The gateway listeners (#283) and `/whois` (#284) build
on `SecurityLog.emit()` and `SecurityEventStore`.

What it guarantees, and what the tests prove:

- One envelope, one registry of fields. `build_event` accepts only the
  fields named in `FIELDS`, with their types; an unknown field, kind or
  action is an error, so a typo is a test failure and not a new bucket.
- Nothing a member controls can break a JSONL line or forge a field. Names
  lose every control character; free text keeps only newline and tab (JSON
  escapes both); lone surrogates, U+2028/2029/0085 and bidi overrides are
  replaced. Sizes are capped per field and per line.
- Secrets never enter an event: secret-shaped values are replaced by
  `[REDACTED]` (the event itself is kept: a silent sensor is worse than
  none) and the field is named in `event.redacted`.
- Privacy rules (content mode, excluded channels, links as domains) are
  applied before any sink sees the event.
- A failing sink never blocks the other sink or the caller.
- SQL is parameterised; there is no string-built SQL anywhere here.
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import gzip
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import shutil
import stat
import threading
import time
import unicodedata
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import unquote, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------

NAME_MAX = 128            # single-line names, nicknames, commands
CONTENT_MAX = 4000        # one message body (Discord's own ceiling)
TEXT_MAX = 512            # `reason`
URL_MAX = 2048
JSON_STR_MAX = 1024       # a string inside `changes` / `args`
JSON_KEY_MAX = 64
MAX_LIST = 100
MAX_JSON_KEYS = 50
MAX_JSON_DEPTH = 4
MAX_JSON_NODES = 500
MAX_EVENT_BYTES = 131072  # one serialized line
MAX_QUERY_LIMIT = 1000

REDACTED = '[REDACTED]'

# ---------------------------------------------------------------------------
# Closed lists: kind -> actions
# ---------------------------------------------------------------------------

_AUDIT_SUBJECTS = ('role', 'channel', 'overwrite', 'webhook', 'integration', 'invite', 'emoji', 'sticker',
                   'automod_rule', 'thread', 'scheduled_event', 'stage_instance', 'soundboard_sound')
_STRUCTURE_SUBJECTS = ('channel', 'thread', 'role', 'emoji', 'sticker', 'webhook', 'invite', 'scheduled_event')


def _crud(subjects) -> frozenset:
    return frozenset(f'{s}_{verb}' for s in subjects for verb in ('create', 'update', 'delete'))


KINDS: dict[str, frozenset] = {
    'audit': _crud(_AUDIT_SUBJECTS) | frozenset({
        'ban', 'unban', 'kick', 'timeout', 'member_update', 'member_role_update', 'member_move',
        'member_disconnect', 'bot_add', 'bot_remove', 'guild_update', 'message_pin', 'message_unpin',
        'message_delete', 'message_bulk_delete', 'prune'}),
    'member': frozenset({'join', 'leave', 'update', 'ban', 'unban'}),
    'message': frozenset({'create', 'edit', 'delete', 'bulk_delete', 'reaction_add', 'reaction_remove'}),
    'voice': frozenset({'join', 'leave', 'move', 'mute', 'unmute', 'deafen', 'undeafen',
                        'stream_start', 'stream_stop', 'camera_start', 'camera_stop'}),
    'structure': _crud(_STRUCTURE_SUBJECTS),
    'automod': frozenset({'triggered', 'message_blocked', 'member_timeout'}),
    'interaction': frozenset({'command', 'prefix_command', 'context_menu', 'button', 'select'}),
    'decision': frozenset({'moderation_scan', 'alert', 'adjudication', 'vote', 'enforcement', 'profile_hold',
                           'greeter_batch', 'role_picker_change', 'ticket_opened', 'ticket_claimed',
                           'ticket_closed', 'ticket_blocked', 'events_review'}),
    'lifecycle': frozenset({'start', 'cog_load', 'cog_unload', 'gateway_connect', 'gateway_disconnect',
                            'gateway_resume', 'http_429', 'error', 'shutdown'}),
}

REACTION_ACTIONS = frozenset({'reaction_add', 'reaction_remove'})

TRUST_TIERS = ('new', 'member', 'veteran', 'trusted', 'creator')   # utils/trust.TIERS (a test keeps them equal)
ACTOR_TYPES = ('member', 'bot', 'system', 'integration')
VIA = ('gateway', 'audit_log', 'bot')
OUTCOMES = ('ok', 'denied', 'error', 'cooldown')

CONTENT_FIELDS = ('content', 'content.before', 'content.after')

# ---------------------------------------------------------------------------
# Field registry: name -> (type, parameter)
# ---------------------------------------------------------------------------

FIELDS: dict[str, tuple] = {
    '@timestamp': ('ts', None),
    'via': ('enum', VIA),
    # who and where (snowflakes are strings: they exceed 2^53)
    'guild.id': ('id', None), 'channel.id': ('id', None), 'message.id': ('id', None),
    'user.id': ('id', None), 'actor.id': ('id', None), 'target.id': ('id', None),
    'channel.before': ('id', None), 'channel.after': ('id', None),
    'channel.name': ('name', NAME_MAX), 'user.name': ('name', NAME_MAX),
    'actor.name': ('name', NAME_MAX), 'target.name': ('name', NAME_MAX),
    'target.type': ('name', 64),
    'user.trust_tier': ('enum', TRUST_TIERS), 'actor.type': ('enum', ACTOR_TYPES),
    # audit
    'reason': ('text', TEXT_MAX), 'changes': ('json', None),
    # membership
    'account.created_at': ('ts', None), 'account.age_days': ('int', 200_000),
    'account.flags': ('int', 2 ** 53), 'invite.code': ('name', 64), 'invite.inviter': ('id', None),
    'member.pending': ('bool', None), 'roles.added': ('idlist', None), 'roles.removed': ('idlist', None),
    'nick.before': ('name', NAME_MAX), 'nick.after': ('name', NAME_MAX), 'timeout.until': ('ts', None),
    # messages
    'content': ('text', CONTENT_MAX), 'content.before': ('text', CONTENT_MAX),
    'content.after': ('text', CONTENT_MAX), 'content_available': ('bool', None),
    'length': ('int', 10 ** 9), 'attachments': ('attachments', None), 'links': ('links', None),
    'mentions.count': ('int', 10 ** 6), 'mentions.everyone': ('bool', None),
    'reply_to': ('id', None), 'is_thread': ('bool', None),
    # automod (action is namespaced: bare `action` would collide with event.action)
    'rule': ('name', NAME_MAX), 'matched_keyword': ('name', NAME_MAX), 'automod.action': ('name', 64),
    # interactions
    'command': ('name', 64), 'args': ('json', None), 'outcome': ('enum', OUTCOMES),
    'latency_ms': ('num', 10 ** 9), 'error_id': ('name', 64),
    # decisions
    'infraction_id': ('id', None), 'ticket_id': ('id', None), 'category': ('name', 64),
    'confidence': ('num', 1), 'decision.action': ('name', 64),
}

# Written by the writer, never by the caller.
META_FIELDS = ('event.sanitized', 'event.truncated', 'event.redacted')
ENVELOPE = ('@timestamp', 'event.kind', 'event.action', 'event.id', 'schema')

# ---------------------------------------------------------------------------
# Errors and small helpers
# ---------------------------------------------------------------------------


class SecurityEventError(ValueError):
    """The event (or a sink input) breaks the schema. Messages never echo raw values."""


def _safe(value: Any, limit: int = 40) -> str:
    """A printable, bounded description of a hostile value for error text."""
    text = ascii(value) if isinstance(value, str) else type(value).__name__
    text = re.sub(r'[^\x20-\x7e]', '?', text)
    return text[:limit]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_TS_RE = re.compile(r'^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d{1,6}))?Z$')
_ID_RE = re.compile(r'^[0-9]{1,19}$')
_EVENT_ID_RE = re.compile(r'^[0-7][0-9A-HJKMNP-TV-Z]{25}$')
_CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
_MIN_TS = datetime(2015, 1, 1, tzinfo=timezone.utc)


def fmt_ts(moment: datetime) -> str:
    """Fixed-width UTC, millisecond precision: sorts lexicographically."""
    moment = moment.astimezone(timezone.utc)
    return f'{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z'


def parse_ts(value: Any, *, name: str = 'timestamp') -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SecurityEventError(f'{name}: naive datetime')
        return fmt_ts(value)
    if isinstance(value, str):
        m = _TS_RE.fullmatch(value)
        if m:
            try:
                parsed = datetime(*(int(g) for g in m.groups()[:6]), tzinfo=timezone.utc)
            except ValueError:
                raise SecurityEventError(f'{name}: not a real date') from None
            micro = int((m.group(7) or '0').ljust(6, '0'))
            return fmt_ts(parsed.replace(microsecond=micro))
    raise SecurityEventError(f'{name}: expected an aware datetime or ISO-8601 UTC string, got {_safe(value)}')


def new_event_id(moment: datetime) -> str:
    """ULID: 48-bit millisecond clock then 80 random bits, Crockford base32."""
    millis = int(moment.timestamp() * 1000) & ((1 << 48) - 1)
    number = (millis << 80) | secrets.randbits(80)
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[number & 31])
        number >>= 5
    return ''.join(reversed(out))


# ---------------------------------------------------------------------------
# Sanitising and redaction
# ---------------------------------------------------------------------------

_SURROGATES = re.compile('[\ud800-\udfff]')
# C0, DEL, C1, line/paragraph separators, bidi embeddings and overrides.
_CTRL_NAME = re.compile('[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e]')
_CTRL_TEXT = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e]')
_JSON_LINE_BREAKERS = re.compile('[\x7f-\x9f\u2028\u2029]')

_SECRET_PATTERNS = [re.compile(p) for p in (
    r'[MNO][A-Za-z0-9_-]{23,27}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}',           # Discord bot token
    r'(?i)(?<![a-z0-9-])(?:https?://)?(?:[a-z0-9-]+\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[A-Za-z0-9_-]+',  # webhook URL
    r'gh[pousr]_[A-Za-z0-9]{36,}',                                                  # GitHub tokens
    r'github_pat_[A-Za-z0-9_]{22,}',
    r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b',                                               # AWS key id
    r'xox[abprs]-[A-Za-z0-9-]{10,}',                                                # Slack
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)',   # whole block, even truncated
    r'eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}',             # JWT
    r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}',
    r'\bdp\.(?:st|pt|ct|sa|scim|audit)\.[A-Za-z0-9._-]{20,}',                     # Doppler
    r'\bsk-[A-Za-z0-9_-]{32,}',                                                     # OpenAI style
    r'\bAIza[0-9A-Za-z_-]{35}\b',                                                   # Google API key
)]
_SECRET_KEY_WORDS = ('token', 'secret', 'password', 'passwd', 'apikey', 'authorization', 'cookie', 'credential',
                     'privatekey', 'webhookurl')

# Common Cyrillic and Greek lookalikes -> Latin (after NFKC), so a spoofed key or token still matches.
_CONFUSABLE_PAIRS = (
    '0430a 0435e 043eo 0440p 0441c 0445x 0443y 0456i 0455s 0458j 043ak 0442t 043dh 043cm 0432b 0501d 051bq 051dw '
    '0410A 0412B 0415E 041aK 041cM 041dH 041eO 0420P 0421C 0422T 0425X 0423Y 0405S 0406I 0408J '
    '03b1a 03b5e 0391A 0392B 0395E 0396Z 0397H 0399I 039aK 039cM 039dN 039fO 03a1P 03a4T 03a5Y 03a7X '
    '03bfo 03bdv 03c1p 03c5u 03c4t 03b9i 03bak').split()
_CONFUSABLES = {ord(chr(int(item[:4], 16))): item[4] for item in _CONFUSABLE_PAIRS}
_INVISIBLE = re.compile('[\u00ad\u200b-\u200f\u2060-\u2064\ufeff\u202a-\u202e\u2066-\u2069]')


def _fold(text: str) -> str:
    """NFKC, invisible characters removed, common lookalike letters mapped to Latin."""
    return _INVISIBLE.sub('', unicodedata.normalize('NFKC', text)).translate(_CONFUSABLES)


def _secret_key(key: str) -> bool:
    squashed = re.sub(r'[\W_]+', '', _fold(key).lower())
    return squashed == 'key' or any(word in squashed for word in _SECRET_KEY_WORDS)


class _Notes:
    """Which fields the writer changed, so no change is silent."""

    def __init__(self):
        self.sanitized: set = set()
        self.truncated: set = set()
        self.redacted: set = set()


def _clean_str(value: str, max_len: int, *, multiline: bool, notes: _Notes, name: str) -> str:
    text = value[:max_len * 4]
    over = len(value) > len(text)
    original = text
    if multiline:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _SURROGATES.sub('\ufffd', text)
    text = (_CTRL_TEXT if multiline else _CTRL_NAME).sub('\ufffd', text)
    if text != original:
        notes.sanitized.add(name)
    for pattern in _SECRET_PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        if n:
            notes.redacted.add(name)
    folded = _fold(text)
    if folded != text and any(p.search(folded) for p in _SECRET_PATTERNS):
        text = REDACTED    # a spoofed spelling of a secret: its span cannot be mapped back, drop the value
        notes.redacted.add(name)
    text, changed = _redact_secret_urls(text)
    if changed:
        notes.redacted.add(name)
    if over or len(text) > max_len:
        text = text[:max_len]
        notes.truncated.add(name)
    return text


_CANDIDATE = re.compile(r'[^\s<>"\'`|]+')


def _redact_secret_urls(text: str) -> tuple:
    """Find URL-like substrings that point at a Discord webhook however they are spelled
    (userinfo, port, trailing dot, case, percent-encoding, repeated slashes, no scheme),
    rebuild them with _canonical_link and redact the original substring."""
    if text.isascii() and '%' not in text and 'discord' not in text.lower():
        return text, False   # nothing that could fold or decode into the word
    if 'webhook' not in _fold(unquote(unquote(text))).lower():
        return text, False   # a webhook URL must also spell 'webhooks' once decoded and folded

    out, last, changed = [], 0, False
    for m in _CANDIDATE.finditer(text):
        raw = m.group()
        for variant in (raw.lstrip('([{').rstrip(').,;:!?]}'), raw.lstrip('([{')):
            if not variant:
                continue
            if variant.isascii() and '%' not in variant and 'discord' not in variant.lower():
                continue
            decoded = _fold(unquote(unquote(variant)))
            if 'discord' not in decoded.lower():
                continue
            canon = _canonical_link(decoded if '://' in decoded else 'https://' + decoded)
            secret = _link_is_secret(canon) if canon else bool(
                re.search(r'(?i)discord(?:app)?\.com', decoded) and re.search(r'(?i)webhooks', decoded))
            if secret:
                start = m.start() + raw.find(variant)
                out.append(text[last:start])
                out.append(REDACTED)
                last = start + len(variant)
                changed = True
                break
    out.append(text[last:])
    return ''.join(out), changed


# ---------------------------------------------------------------------------
# Field normalisers
# ---------------------------------------------------------------------------

def _id(value: Any, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SecurityEventError(f'{name}: expected a snowflake, got {_safe(value)}')
    text = str(value)
    if not _ID_RE.fullmatch(text) or int(text) >= 2 ** 63:
        raise SecurityEventError(f'{name}: not a snowflake: {_safe(value)}')
    return text


def _int(value: Any, name: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= ceiling:
        raise SecurityEventError(f'{name}: expected an integer 0..{ceiling}, got {_safe(value)}')
    return value


def _num(value: Any, name: str, ceiling: float):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SecurityEventError(f'{name}: expected a number, got {_safe(value)}')
    if not math.isfinite(value) or not 0 <= value <= ceiling:
        raise SecurityEventError(f'{name}: out of range 0..{ceiling}')
    return value


def _json_value(value: Any, name: str, notes: _Notes, depth: int, budget: list, *, key: str = ''):
    budget[0] -= 1
    if budget[0] < 0:
        raise SecurityEventError(f'{name}: too many values')
    if value.__class__.__name__ == 'Secret':
        notes.redacted.add(name)
        return REDACTED
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > 2 ** 53 else value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SecurityEventError(f'{name}: non-finite number')
        return value
    if isinstance(value, str):
        text = _clean_str(value, JSON_STR_MAX, multiline=True, notes=notes, name=name)
        if name == 'changes' and not _SHORT_TOKEN.fullmatch(text):
            notes.redacted.add(name)     # free text (names with spaces, topics, URLs) is not structural
            return REDACTED
        return text
    if depth >= MAX_JSON_DEPTH:
        raise SecurityEventError(f'{name}: nested too deeply')
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_LIST:
            raise SecurityEventError(f'{name}: list longer than {MAX_LIST}')
        return [_json_value(v, name, notes, depth + 1, budget) for v in value]
    if isinstance(value, Mapping):
        if len(value) > MAX_JSON_KEYS:
            raise SecurityEventError(f'{name}: more than {MAX_JSON_KEYS} keys')
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise SecurityEventError(f'{name}: non-string key')
            clean_key = _clean_str(k, JSON_KEY_MAX, multiline=False, notes=notes, name=name)
            if name == 'changes' and (len(k) > JSON_KEY_MAX or not _CHANGE_KEY.fullmatch(clean_key)):
                notes.redacted.add(name)  # keys are Discord's fixed identifiers; anything else is user text
                continue
            if clean_key in out:
                raise SecurityEventError(f'{name}: keys collide after sanitising')
            if _secret_key(clean_key):
                notes.redacted.add(name)
                out[clean_key] = REDACTED
            else:
                out[clean_key] = _json_value(v, name, notes, depth + 1, budget)
        return out
    raise SecurityEventError(f'{name}: unsupported value type {_safe(value)}')


# `changes` is metadata that outlives the content clock (the audit mirror is kept forever), so it
# is structural only: identifier keys, and values that are typed scalars or short tokens (ids,
# permission bitfields, enum names, short slugs). Anything else is replaced, never stored.
_CHANGE_KEY = re.compile(r'[A-Za-z][A-Za-z0-9_.]{0,63}')
_SHORT_TOKEN = re.compile(r'[\w.#+-]{1,64}')


def _normalise(name: str, value: Any, notes: _Notes):
    kind, param = FIELDS[name]
    if kind == 'id':
        return _id(value, name)
    if kind == 'name':
        if not isinstance(value, str):
            raise SecurityEventError(f'{name}: expected a string, got {_safe(value)}')
        return _clean_str(value, param, multiline=False, notes=notes, name=name)
    if kind == 'text':
        if not isinstance(value, str):
            raise SecurityEventError(f'{name}: expected a string, got {_safe(value)}')
        return _clean_str(value, param, multiline=True, notes=notes, name=name)
    if kind == 'enum':
        if not isinstance(value, str) or value not in param:
            raise SecurityEventError(f'{name}: not one of {list(param)}')
        return value
    if kind == 'int':
        return _int(value, name, param)
    if kind == 'num':
        return _num(value, name, param)
    if kind == 'bool':
        if not isinstance(value, bool):
            raise SecurityEventError(f'{name}: expected true or false, got {_safe(value)}')
        return value
    if kind == 'ts':
        return parse_ts(value, name=name)
    if kind == 'idlist':
        if not isinstance(value, (list, tuple)) or len(value) > MAX_LIST:
            raise SecurityEventError(f'{name}: expected a list of at most {MAX_LIST} ids')
        return [_id(v, name) for v in value]
    if kind == 'links':
        if not isinstance(value, (list, tuple)) or len(value) > MAX_LIST:
            raise SecurityEventError(f'{name}: expected a list of at most {MAX_LIST} strings')
        out = []
        for v in value:
            if not isinstance(v, str):
                raise SecurityEventError(f'{name}: expected strings, got {_safe(v)}')
            link = None if len(v) > URL_MAX else _canonical_link(
                _clean_str(v, URL_MAX, multiline=False, notes=notes, name=name))
            if link is not None and _link_is_secret(link):
                # Redaction ran on the raw text; the rebuilt URL can differ (port, trailing
                # dot, case, userinfo, percent-encoding), so it is checked again, fail closed.
                notes.redacted.add(name)
                link = None
            if link is None:
                notes.sanitized.add(name)   # dropped: unparseable, hostile or over-long
            elif link not in out:
                out.append(link)
        return out
    if kind == 'attachments':
        if not isinstance(value, (list, tuple)) or len(value) > MAX_LIST:
            raise SecurityEventError(f'{name}: expected a list of at most {MAX_LIST} objects')
        out = []
        for item in value:
            if not isinstance(item, Mapping) or set(item) - {'name', 'size', 'type'}:
                raise SecurityEventError(f'{name}: each attachment is {{name, size, type}} and nothing else')
            entry = {}
            if 'name' in item:
                entry['name'] = _normalise_str(item['name'], 255, name, notes)
            if 'size' in item:
                entry['size'] = _int(item['size'], name, 2 ** 40)
            if 'type' in item:
                entry['type'] = _normalise_str(item['type'], 100, name, notes)
            out.append(entry)
        return out
    if kind == 'json':
        if not isinstance(value, Mapping):
            raise SecurityEventError(f'{name}: expected an object, got {_safe(value)}')
        return _json_value(value, name, notes, 0, [MAX_JSON_NODES])
    raise AssertionError(kind)  # pragma: no cover


def _normalise_str(value: Any, limit: int, name: str, notes: _Notes) -> str:
    if not isinstance(value, str):
        raise SecurityEventError(f'{name}: expected a string, got {_safe(value)}')
    return _clean_str(value, limit, multiline=False, notes=notes, name=name)


_HOST_RE = re.compile(r'[\w.-]{1,253}')


def _canonical_link(text: str) -> Optional[str]:
    """A bare lowercase hostname, or http(s)://host[:port]/path?query rebuilt from
    its parsed parts (no credentials, no fragment). None when it cannot be
    trusted: whitespace, backslashes, replaced control characters, an unparseable authority, any other scheme."""
    if not text or '\\' in text or '\ufffd' in text or any(c.isspace() for c in text):
        return None
    if '://' not in text:
        host = text.lower()
        return host if _HOST_RE.fullmatch(host) else None
    try:
        parts = urlsplit(text)
        port = parts.port
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ('http', 'https') or not host:
        return None
    if '[' in parts.netloc or ':' in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
        if '%' in host:
            return None
        netloc = f'[{host}]'
    elif _HOST_RE.fullmatch(host):
        netloc = host
    else:
        return None
    if port is not None:
        netloc += f':{port}'
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ''))


_WEBHOOK_PATH = re.compile(r'api(?:/v\d+)?/webhooks/\d+/[^/]+')


def _link_is_secret(link: str) -> bool:
    """A canonical link that carries a secret: a Discord webhook by parsed host and
    path, or any secret pattern in the link or its percent-decoded forms."""
    decoded = [link, unquote(link), unquote(unquote(link))]
    if any(p.search(text) for text in decoded for p in _SECRET_PATTERNS):
        return True
    if '://' not in link:
        return False
    parts = urlsplit(link)
    host = (parts.hostname or '').rstrip('.')
    if host == 'discord.com' or host == 'discordapp.com' or host.endswith(('.discord.com', '.discordapp.com')):
        segments = '/'.join(seg for seg in unquote(unquote(parts.path)).split('/') if seg)
        return bool(_WEBHOOK_PATH.match(segments))
    return False


def _domain(link: str) -> Optional[str]:
    """Hostname of a canonical link; IPv6 literals are dropped, not reduced."""
    if '://' not in link:
        return link
    host = urlsplit(link).hostname
    return None if not host or ':' in host else host


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

CONTENT_MODES = ('none', 'edits_and_deletes', 'create')


@dataclass(frozen=True)
class SecLogSettings:
    """Mirrors the SECLOG_* block of the design doc. Wiring these from the
    environment belongs to utils/config.py and arrives with the listeners."""

    enabled: bool = False
    content_mode: str = 'edits_and_deletes'
    content_exclude_channels: frozenset = frozenset()
    reactions: bool = False
    content_days: int = 90
    meta_days: int = 365
    audit_days: int = 0        # 0 = keep the audit mirror forever
    file_days: int = 90        # design doc says 400; see the content-clock check in __post_init__

    def __post_init__(self):
        for name in ('enabled', 'reactions'):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f'{name} must be a bool')
        if self.content_mode not in CONTENT_MODES:
            raise ValueError(f'content_mode must be one of {CONTENT_MODES}')
        for name, minimum in (('content_days', 1), ('meta_days', 1), ('audit_days', 0), ('file_days', 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f'{name} must be an integer >= {minimum}')
        if self.content_mode != 'none' and self.file_days > self.content_days:
            raise ValueError(
                f'file_days ({self.file_days}) must not exceed content_days ({self.content_days}) while '
                f'content_mode is {self.content_mode!r}: the JSONL files hold message content, so they '
                'would outlive the content clock')
        try:
            ids = frozenset(_id(c, 'content_exclude_channels') for c in self.content_exclude_channels)
        except SecurityEventError as exc:
            raise ValueError(str(exc)) from None
        object.__setattr__(self, 'content_exclude_channels', ids)


# ---------------------------------------------------------------------------
# Building and validating events
# ---------------------------------------------------------------------------

def _check_kind(kind: Any, action: Any):
    if not isinstance(kind, str) or kind not in KINDS:
        raise SecurityEventError(f'unknown event kind {_safe(kind)}')
    if not isinstance(action, str) or action not in KINDS[kind]:
        raise SecurityEventError(f'unknown action {_safe(action)} for kind {kind}')


FIELD_SCOPE = {
    'args': lambda kind, action: kind == 'interaction',
    'changes': lambda kind, action: kind in ('audit', 'structure') and not action.startswith('message_'),
}


def _check_scope(kind: str, action: str, names) -> None:
    """Free-form objects are only legal where the design needs them: they are the one place
    content or URLs could ride along unclassified."""
    for name in names:
        rule = FIELD_SCOPE.get(name)
        if rule is not None and not rule(kind, action):
            raise SecurityEventError(f'{name} is not allowed on {kind}.{action}')


def _normalise_fields(fields: Mapping, notes: _Notes) -> dict:
    clean = {}
    for name, value in fields.items():
        if not isinstance(name, str) or name not in FIELDS:
            raise SecurityEventError(f'unknown field {_safe(name)}')
        clean[name] = _normalise(name, value, notes)
    return clean


def _apply_privacy(kind: str, action: str, clean: dict, settings: SecLogSettings, notes: _Notes) -> None:
    present = [f for f in CONTENT_FIELDS if f in clean]
    if present and kind != 'message':
        raise SecurityEventError('content fields are only legal on message events')
    # Deny by default: content (and the full URLs of a deleted message) are kept
    # only when the mode allows it AND the event names a channel that is not excluded.
    channel = clean.get('channel.id')
    allowed = settings.content_mode != 'none' and channel is not None \
        and channel not in settings.content_exclude_channels
    if present:
        keep = allowed and action in ('create', 'edit', 'delete') \
            and not (action == 'create' and settings.content_mode != 'create')
        if not keep:
            for f in present:
                del clean[f]
                notes.redacted.add(f)
            clean['content_available'] = False
    if 'args' in clean and not allowed:
        del clean['args']
        notes.redacted.add('args')
    if 'links' in clean:
        full = kind == 'message' and action == 'delete' and allowed
        if not full:
            domains = []
            for link in clean['links']:
                d = _domain(link)
                if d and d not in domains:
                    domains.append(d)
            if domains != clean['links']:
                (notes.redacted if kind == 'message' and action == 'delete' else notes.sanitized).add('links')
            clean['links'] = domains


def build_event(kind: str, action: str, fields: Optional[Mapping] = None, *,
                settings: Optional[SecLogSettings] = None,
                clock: Callable[[], datetime] = _utcnow) -> Optional[dict]:
    """Validate, sanitise and apply the privacy rules; return the event dict.

    Returns None for an event the settings filter out (reactions while
    SECLOG_REACTIONS is off). Raises SecurityEventError for anything that
    breaks the schema."""
    settings = settings or SecLogSettings()
    _check_kind(kind, action)
    if action in REACTION_ACTIONS and not settings.reactions:
        return None
    notes = _Notes()
    _check_scope(kind, action, [n for n in (fields or {}) if isinstance(n, str)])
    clean = _normalise_fields(fields or {}, notes)
    _apply_privacy(kind, action, clean, settings, notes)
    now = clock()
    if now.tzinfo is None:
        raise SecurityEventError('clock must return an aware datetime')
    stamp = clean.pop('@timestamp', None) or fmt_ts(now)
    _check_timestamp_window(stamp, now)
    event = dict(clean)
    event.update({'@timestamp': stamp, 'event.kind': kind, 'event.action': action,
                  'event.id': new_event_id(now), 'schema': SCHEMA_VERSION})
    for key, items in (('event.sanitized', notes.sanitized), ('event.truncated', notes.truncated),
                       ('event.redacted', notes.redacted)):
        if items:
            event[key] = sorted(items)
    return event


def _check_timestamp_window(stamp: str, now: datetime) -> None:
    moment = datetime.fromisoformat(stamp[:-1] + '+00:00')
    if moment < _MIN_TS or moment > now + timedelta(days=1):
        raise SecurityEventError('@timestamp outside the accepted window')


def validate_event(event: Mapping, *, now: Optional[datetime] = None) -> dict:
    """Re-check an already built event (what a sink is handed). The event must
    be canonical: validating it must not change a byte of it."""
    if not isinstance(event, Mapping):
        raise SecurityEventError('event must be a mapping')
    kind, action = event.get('event.kind'), event.get('event.action')
    _check_kind(kind, action)
    if event.get('schema') != SCHEMA_VERSION or isinstance(event.get('schema'), bool):
        raise SecurityEventError('unsupported schema version')
    event_id = event.get('event.id')
    if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
        raise SecurityEventError('malformed event.id')
    for meta in META_FIELDS:
        if meta in event:
            value = event[meta]
            if not isinstance(value, list) or not all(isinstance(v, str) and v in FIELDS for v in value):
                raise SecurityEventError(f'{meta} must be a list of field names')
    stamp = event.get('@timestamp')
    parse_ts(stamp, name='@timestamp')
    _check_timestamp_window(stamp, now or _utcnow())
    body = {k: v for k, v in event.items() if k not in ENVELOPE and k not in META_FIELDS}
    notes = _Notes()
    _check_scope(kind, action, list(body))
    clean = _normalise_fields(body, notes)
    if clean != body or '@timestamp' in body:
        raise SecurityEventError('event is not canonical')
    if kind != 'message' and any(f in clean for f in CONTENT_FIELDS):
        raise SecurityEventError('content fields are only legal on message events')
    return dict(event)


def serialize(event: Mapping) -> str:
    """One JSON object, one line, valid UTF-8, no raw line separator of any kind."""
    try:
        text = json.dumps(event, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        text = _JSON_LINE_BREAKERS.sub(lambda m: f'\\u{ord(m.group()):04x}', text)
        size = len(text.encode('utf-8'))
    except (TypeError, ValueError) as exc:
        raise SecurityEventError(f'event cannot be serialised: {type(exc).__name__}') from None
    if size > MAX_EVENT_BYTES:
        raise SecurityEventError(f'event too large ({size} bytes, cap {MAX_EVENT_BYTES})')
    return text


# ---------------------------------------------------------------------------
# JSONL sink: events-YYYY-MM-DD.jsonl, gzipped once the day has ended
# ---------------------------------------------------------------------------

_FILE_RE = re.compile(r'^events-(\d{4})-(\d\d)-(\d\d)\.jsonl(\.gz)?$')
_LINE_BREAKS = re.compile('[\n\r\x85\u2028\u2029]')


def _file_date(name: str) -> Optional[date]:
    m = _FILE_RE.match(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


LOCK_NAME = '.seclog.lock'
COMPRESS_LOCK_NAME = '.seclog.compress.lock'
LOCK_TIMEOUT = 60.0
_PART_RE = re.compile(r'^(events-\d{4}-\d\d-\d\d\.jsonl)\.[0-9a-f]{8}\.part$')


def _open_regular(name: str, flags: int, mode: int, dir_fd: int) -> int:
    """Open `name` inside the log directory without following a symlink or blocking on a
    FIFO, and refuse anything that is not a regular file owned by the bot user."""
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, mode, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, 'security log path is not a regular file')
        if info.st_uid != os.geteuid():
            raise OSError(errno.EPERM, 'security log file is not owned by the bot user')
    except BaseException:
        os.close(fd)
        raise
    return fd


class JsonlSink:
    """Daily files plus inter-process locking.

    - Appends hold a short `flock` on `.seclog.lock`. Finished days are only RENAMED to
      `*.part` under that lock; gzip runs afterwards under a separate lock
      (`.seclog.compress.lock`), so a long compression never blocks writers.
    - Everything is opened relative to a directory fd with O_NOFOLLOW (and O_NONBLOCK for
      files): a symlink or FIFO is refused, never followed or waited on. The directory must be
      owned by the bot user and not group/world writable; lock and log files must be regular
      files owned by the bot user. After taking a flock the lock inode is re-checked against
      the path and the lock retaken if it was replaced.
    - `write()` takes a cancel flag: a call that timed out upstream sees it under the lock and
      writes nothing.
    """

    def __init__(self, directory, *, clock: Callable[[], datetime] = _utcnow,
                 lock_timeout: Optional[float] = None):
        self.directory = Path(directory)
        self._clock = clock
        self._lock = threading.Lock()
        self._current_day: Optional[date] = None
        self.lock_timeout = LOCK_TIMEOUT if lock_timeout is None else lock_timeout

    def _today(self) -> date:
        return self._clock().astimezone(timezone.utc).date()

    # test seams (no-ops)
    def _after_read(self) -> None:
        """Runs after a day has been read for compression, before its part file is removed."""

    def _before_write(self) -> None:
        """Runs after the day file is open, before the record is written."""

    def _after_flock(self, attempt: int) -> None:
        """Runs after a flock is taken, before the lock inode is verified."""

    def _open_dir(self, *, missing_ok: bool) -> Optional[int]:
        try:
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid():
                raise OSError(errno.EPERM, 'security log directory is not owned by the bot user')
            if info.st_mode & 0o022:
                raise OSError(errno.EPERM, 'security log directory is group or world writable')
        except BaseException:
            os.close(fd)
            raise
        return fd

    @contextmanager
    def _held(self, *, create: bool, lock_name: str = LOCK_NAME, timeout: Optional[float] = None):
        """Directory fd with the inter-process lock held. Only a read-only caller (create=False)
        may be handed None for a missing directory; a writer fails closed."""
        if create:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o750)
        dir_fd = self._open_dir(missing_ok=not create)
        if dir_fd is None:
            yield None
            return
        try:
            deadline = time.monotonic() + (self.lock_timeout if timeout is None else timeout)
            attempt = 0
            while True:
                lock_fd = _open_regular(lock_name, os.O_RDWR | os.O_CREAT, 0o600, dir_fd)
                try:
                    while True:
                        try:
                            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() > deadline:
                                raise OSError(errno.ETIMEDOUT, 'timed out waiting for the security log lock') from None
                            time.sleep(0.005)
                    self._after_flock(attempt)
                    held = self._same_inode(lock_fd, lock_name, dir_fd)
                except BaseException:
                    os.close(lock_fd)
                    raise
                if held:
                    break
                os.close(lock_fd)                       # replaced while we waited: take the new one
                attempt += 1
                if time.monotonic() > deadline:
                    raise OSError(errno.ETIMEDOUT, 'timed out waiting for the security log lock')
            try:
                yield dir_fd
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
        finally:
            os.close(dir_fd)

    @staticmethod
    def _same_inode(lock_fd: int, lock_name: str, dir_fd: int) -> bool:
        try:
            on_path = os.stat(lock_name, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        held = os.fstat(lock_fd)
        return (held.st_ino, held.st_dev) == (on_path.st_ino, on_path.st_dev)

    def write(self, line: str, cancelled: Optional[threading.Event] = None) -> None:
        if not isinstance(line, str) or _LINE_BREAKS.search(line):
            raise SecurityEventError('a JSONL record must be one line')
        data = (line + '\n').encode('utf-8')
        if len(data) > MAX_EVENT_BYTES + 1:
            raise SecurityEventError('event too large')
        rotated = False
        with self._lock:
            if cancelled is not None and cancelled.is_set():
                return
            with self._held(create=True) as dir_fd:
                if cancelled is not None and cancelled.is_set():
                    return
                today = self._today()
                if today != self._current_day:
                    try:
                        self._rename_finished(today, dir_fd)
                        rotated = True
                    except Exception:
                        logger.exception('security log rotation failed; continuing to write')
                    self._current_day = today
                fd = _open_regular(f'events-{today.isoformat()}.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                                   0o640, dir_fd)
                try:
                    self._before_write()
                    view = memoryview(data)
                    while view:
                        view = view[os.write(fd, view):]
                finally:
                    os.close(fd)
        if rotated:
            try:
                self._compress_pending(wait=False)   # outside the append lock; never queues behind another
            except OSError as exc:
                if exc.errno != errno.ETIMEDOUT:     # busy: whoever holds it, or the nightly job, finishes it
                    logger.exception('security log compression failed; it will be retried')
            except Exception:
                logger.exception('security log compression failed; it will be retried')

    def rotate(self) -> list:
        """Gzip every finished day. Returns the day files it compressed."""
        with self._lock, self._held(create=False) as dir_fd:
            if dir_fd is None:
                return []
            self._rename_finished(self._today(), dir_fd)
        return self._compress_pending()

    @staticmethod
    def _entries(dir_fd: int):
        with os.scandir(dir_fd) as it:
            return sorted(
                ((e.name, d) for e in it
                 if (d := _file_date(e.name)) is not None
                 and not e.is_symlink() and e.is_file(follow_symlinks=False)),
                key=lambda t: t[0])

    @staticmethod
    def _parts(dir_fd: int) -> list:
        with os.scandir(dir_fd) as it:
            found = []
            for e in it:
                m = _PART_RE.match(e.name)
                if m and _file_date(m.group(1)) is not None and not e.is_symlink() \
                        and e.is_file(follow_symlinks=False):
                    found.append((e.name, m.group(1)))
            return sorted(found)

    def _rename_finished(self, today: date, dir_fd: int) -> None:
        """Under the append lock: move finished days out of the writers' way."""
        for name, day in self._entries(dir_fd):
            if name.endswith('.gz') or day >= today:
                continue
            os.rename(name, f'{name}.{secrets.token_hex(4)}.part', src_dir_fd=dir_fd, dst_dir_fd=dir_fd)

    def _compress_pending(self, wait: bool = True) -> list:
        """Gzip every `*.part` (also leftovers of a crash), under the compression lock only."""
        with self._held(create=False, lock_name=COMPRESS_LOCK_NAME, timeout=None if wait else 0) as dir_fd:
            if dir_fd is None:
                return []
            done = set()
            for part, original in self._parts(dir_fd):
                try:
                    self._compress(dir_fd, part, original)
                except FileNotFoundError:
                    continue                    # another process got there first
                done.add(original)
            return sorted(done)

    def _compress(self, dir_fd: int, src: str, name: str) -> None:
        dst, tmp = name + '.gz', name + '.gz.tmp'
        try:
            os.unlink(tmp, dir_fd=dir_fd)          # a stale or planted temp; unlink never follows a symlink
        except FileNotFoundError:
            pass
        tmp_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640,
                         dir_fd=dir_fd)
        try:
            with os.fdopen(tmp_fd, 'ab') as raw:
                try:
                    existing = _open_regular(dst, os.O_RDONLY, 0, dir_fd)
                except FileNotFoundError:
                    existing = None
                if existing is not None:
                    with os.fdopen(existing, 'rb') as old:
                        shutil.copyfileobj(old, raw)
                with os.fdopen(_open_regular(src, os.O_RDONLY, 0, dir_fd), 'rb') as source:
                    with gzip.GzipFile(fileobj=raw, mode='wb') as gz:
                        shutil.copyfileobj(source, gz)
                raw.flush()
                os.fsync(raw.fileno())
            self._after_read()
            os.replace(tmp, dst, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.unlink(src, dir_fd=dir_fd)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            raise

    def prune(self, file_days: int) -> list:
        """Delete files whose NAME date is more than file_days old (never mtime)."""
        with self._lock, self._held(create=False) as dir_fd:
            if dir_fd is None:
                return []
            cutoff = self._today() - timedelta(days=file_days)
            removed = []
            for name, day in self._entries(dir_fd):
                if day < cutoff:
                    os.unlink(name, dir_fd=dir_fd)
                    removed.append(name)
            return sorted(removed)


# ---------------------------------------------------------------------------
# SQLite store (table lives in utils/database.py, schema v4)
# ---------------------------------------------------------------------------

def _query_id(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be an int')
    if not 0 <= value < 2 ** 63:
        raise ValueError(f'{name} out of range')
    return value


def _query_ts(value: Any, name: str) -> Optional[str]:
    if value is None:
        return None
    try:
        return parse_ts(value, name=name)
    except SecurityEventError as exc:
        raise ValueError(str(exc)) from None


def _page(limit: Any, offset: Any) -> tuple:
    for name, v in (('limit', limit), ('offset', offset)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f'{name} must be an int')
    return max(1, min(limit, MAX_QUERY_LIMIT)), max(0, offset)


_CONTENT_PATHS = ('$."content"', '$."content.before"', '$."content.after"', '$."args"')
_LINKS_PATH = '$."links"'
# A deleted message's links are full URLs, so they go with the content; on other
# rows links are domains and stay.
_STRIP_PARAMS = (*_CONTENT_PATHS, _LINKS_PATH, *_CONTENT_PATHS)

_SELECT = ('SELECT id, event_id, ts, kind, action, guild_id, channel_id, user_id, actor_id, message_id, '
           'has_content, data FROM security_events ')


def _holds_content(event: Mapping) -> bool:
    """Message text, or the full URLs of a deleted message (domains are metadata)."""
    return any(f in event for f in CONTENT_FIELDS) or 'args' in event or (
        event.get('event.kind') == 'message' and event.get('event.action') == 'delete'
        and any('://' in link for link in event.get('links', ())))


def _row(row) -> dict:
    out = dict(row)
    out['data'] = json.loads(out['data'])
    return out


class SecurityEventStore:
    """Writes and reads `security_events` over the shared ModerationDatabase
    connection, serialised by its lock like every other store."""

    def __init__(self, db):
        self.db = db

    @property
    def _conn(self):
        return self.db.conn

    async def insert(self, event: Mapping) -> int:
        event = validate_event(event)
        line = serialize(event)

        def num(key):
            v = event.get(key)
            return int(v) if v is not None else None

        async with self.db.lock:
            try:
                cursor = await self._conn.execute(
                    """INSERT INTO security_events
                       (event_id, ts, kind, action, guild_id, channel_id, user_id, actor_id, message_id,
                        has_content, data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event['event.id'], event['@timestamp'], event['event.kind'], event['event.action'],
                     num('guild.id'), num('channel.id'), num('user.id'), num('actor.id'), num('message.id'),
                     1 if _holds_content(event) else 0, line))
                await self._conn.commit()
            except BaseException:
                await self._conn.rollback()
                raise
            return cursor.lastrowid

    # -- reads (static SQL; every filter is a bound parameter) -------------

    @staticmethod
    def _filters(guild_id, since, until, limit, offset) -> tuple:
        lim, off = _page(limit, offset)
        s, u = _query_ts(since, 'since'), _query_ts(until, 'until')
        g = None if guild_id is None else _query_id(guild_id, 'guild_id')
        return g, g, s, s, u, u, lim, off

    async def _run(self, sql: str, params: tuple) -> list:
        cursor = await self._conn.execute(sql, params)
        return [_row(r) for r in await cursor.fetchall()]

    async def by_user(self, user_id: int, *, guild_id: Optional[int] = None, since=None, until=None,
                      limit: int = 50, offset: int = 0) -> list:
        return await self._run(
            _SELECT + """WHERE user_id = ? AND (? IS NULL OR guild_id = ?)
                         AND (? IS NULL OR ts >= ?) AND (? IS NULL OR ts <= ?)
                         ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?""",
            (_query_id(user_id, 'user_id'), *self._filters(guild_id, since, until, limit, offset)))

    async def by_actor(self, actor_id: int, *, guild_id: Optional[int] = None, since=None, until=None,
                       limit: int = 50, offset: int = 0) -> list:
        return await self._run(
            _SELECT + """WHERE actor_id = ? AND (? IS NULL OR guild_id = ?)
                         AND (? IS NULL OR ts >= ?) AND (? IS NULL OR ts <= ?)
                         ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?""",
            (_query_id(actor_id, 'actor_id'), *self._filters(guild_id, since, until, limit, offset)))

    async def by_channel(self, channel_id: int, *, guild_id: Optional[int] = None, since=None, until=None,
                         limit: int = 50, offset: int = 0) -> list:
        return await self._run(
            _SELECT + """WHERE channel_id = ? AND (? IS NULL OR guild_id = ?)
                         AND (? IS NULL OR ts >= ?) AND (? IS NULL OR ts <= ?)
                         ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?""",
            (_query_id(channel_id, 'channel_id'), *self._filters(guild_id, since, until, limit, offset)))

    async def by_kind(self, kind: str, action: Optional[str] = None, *, guild_id: Optional[int] = None,
                      since=None, until=None, limit: int = 50, offset: int = 0) -> list:
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError('unknown kind')
        if action is not None and (not isinstance(action, str) or action not in KINDS[kind]):
            raise ValueError('unknown action')
        return await self._run(
            _SELECT + """WHERE kind = ? AND (? IS NULL OR action = ?) AND (? IS NULL OR guild_id = ?)
                         AND (? IS NULL OR ts >= ?) AND (? IS NULL OR ts <= ?)
                         ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?""",
            (kind, action, action, *self._filters(guild_id, since, until, limit, offset)))

    async def count_deleted_messages(self, user_id: int, *, days: int = 30,
                                     now: Optional[datetime] = None) -> int:
        """Messages by this member that were deleted in the last `days` (the /whois figure)."""
        since = fmt_ts((now or _utcnow()) - timedelta(days=days))
        cursor = await self._conn.execute(
            """SELECT COUNT(*) AS n FROM security_events
               WHERE user_id = ? AND kind = 'message' AND action = 'delete' AND ts >= ?""",
            (_query_id(user_id, 'user_id'), since))
        return (await cursor.fetchone())['n']

    async def count_content_rows(self) -> int:
        """Rows the content clock will eventually strip (the penguin_seclog_content_rows gauge)."""
        cursor = await self._conn.execute('SELECT COUNT(*) AS n FROM security_events WHERE has_content = 1')
        return (await cursor.fetchone())['n']

    # -- retention and erasure ----------------------------------------------

    @asynccontextmanager
    async def _txn(self):
        """Lock, run, commit; on any failure (including cancellation) roll back so a later
        insert's commit cannot publish half of a failed job."""
        async with self.db.lock:
            try:
                yield self._conn
                await self._conn.commit()
            except BaseException:
                await self._conn.rollback()
                raise

    async def apply_retention(self, settings: SecLogSettings, *, now: Optional[datetime] = None,
                              batch: int = 5000) -> dict:
        """The nightly job: drop aged metadata, then strip aged content.

        Metadata clock: every kind but `audit`. Audit clock: only when
        audit_days > 0. Content clock: removes the content keys and leaves the
        row. Batched so a big backlog never holds the shared lock for long."""
        now = now or _utcnow()
        meta_cut = fmt_ts(now - timedelta(days=settings.meta_days))
        content_cut = fmt_ts(now - timedelta(days=settings.content_days))
        audit_cut = fmt_ts(now - timedelta(days=settings.audit_days)) if settings.audit_days else None
        deleted = stripped = 0
        while True:
            async with self._txn() as conn:
                cursor = await conn.execute(
                    """DELETE FROM security_events WHERE id IN
                       (SELECT id FROM security_events WHERE kind <> 'audit' AND ts < ? ORDER BY id LIMIT ?)""",
                    (meta_cut, batch))
                n = cursor.rowcount
                if audit_cut is not None:
                    cursor = await conn.execute(
                        """DELETE FROM security_events WHERE id IN
                           (SELECT id FROM security_events WHERE kind = 'audit' AND ts < ? ORDER BY id LIMIT ?)""",
                        (audit_cut, batch))
                    n += cursor.rowcount
            deleted += n
            if n == 0:
                break
        while True:
            async with self._txn() as conn:
                cursor = await conn.execute(
                    """UPDATE security_events SET data = CASE WHEN kind = 'message' AND action = 'delete'
                           THEN json_remove(data, ?, ?, ?, ?, ?) ELSE json_remove(data, ?, ?, ?, ?) END,
                           has_content = 0
                       WHERE id IN (SELECT id FROM security_events
                                    WHERE has_content = 1 AND ts < ? ORDER BY id LIMIT ?)""",
                    (*_STRIP_PARAMS, content_cut, batch))
                n = cursor.rowcount
            stripped += n
            if n == 0:
                break
        return {'content_stripped': stripped, 'deleted': deleted}

    async def forget_user_content(self, user_id: int) -> int:
        """`/seclog forget`: strip content for one member; metadata stays."""
        uid = _query_id(user_id, 'user_id')
        async with self._txn() as conn:
            cursor = await conn.execute(
                """UPDATE security_events SET data = CASE WHEN kind = 'message' AND action = 'delete'
                       THEN json_remove(data, ?, ?, ?, ?, ?) ELSE json_remove(data, ?, ?, ?, ?) END,
                       has_content = 0
                   WHERE user_id = ? AND has_content = 1""",
                (*_STRIP_PARAMS, uid))
            return cursor.rowcount


# ---------------------------------------------------------------------------
# The emitter
# ---------------------------------------------------------------------------

class SecurityLog:
    """`await log.emit(kind, action, **fields)`; never raises, never blocks the
    caller on a failed sink. Field names with dots go in via `**{'user.id': ...}`."""

    def __init__(self, settings: Optional[SecLogSettings] = None, *, jsonl: Optional[JsonlSink] = None,
                 store: Optional[SecurityEventStore] = None, clock: Callable[[], datetime] = _utcnow,
                 sink_timeout: float = 5.0):
        self.settings = settings or SecLogSettings()
        self.jsonl = jsonl
        self.store = store
        self._clock = clock
        self.sink_timeout = sink_timeout
        self.stats: dict = {'events': 0, 'rejected': 0, 'filtered': 0, 'sink_errors': {}}

    def add_content_exclusion(self, channel_id) -> None:
        """Ticket threads and other channels whose content must never be logged."""
        self.settings = replace(self.settings, content_exclude_channels=self.settings.content_exclude_channels
                                | {_id(channel_id, 'channel_id')})

    def _sink_error(self, sink: str, exc: BaseException) -> None:
        self.stats['sink_errors'][sink] = self.stats['sink_errors'].get(sink, 0) + 1
        logger.error('security log %s sink failed: %s', sink, type(exc).__name__)

    async def _guard(self, sink: str, awaitable, cancel: Optional[threading.Event] = None) -> None:
        """Run one sink with a bound on its time; a wedged sink costs one counted error. On a
        timeout the cancel flag is raised so an abandoned worker thread writes nothing later."""
        try:
            await asyncio.wait_for(awaitable, self.sink_timeout)
        except asyncio.TimeoutError as exc:
            if cancel is not None:
                cancel.set()
            self._sink_error(sink, exc)
        except Exception as exc:
            self._sink_error(sink, exc)

    async def emit(self, kind: str, action: str, /, **fields) -> Optional[dict]:
        if not self.settings.enabled:
            return None
        try:
            event = build_event(kind, action, fields, settings=self.settings, clock=self._clock)
            if event is None:
                self.stats['filtered'] += 1
                return None
            line = serialize(event)
        except Exception as exc:
            self.stats['rejected'] += 1
            logger.warning('security event rejected: %s', _safe(str(exc), 160))
            return None
        self.stats['events'] += 1
        jobs = []
        if self.jsonl is not None:
            cancel = threading.Event()
            jobs.append(self._guard('file', asyncio.to_thread(self.jsonl.write, line, cancel), cancel))
        if self.store is not None:
            jobs.append(self._guard('sqlite', self.store.insert(event)))
        await asyncio.gather(*jobs)
        return event

    async def run_retention(self) -> dict:
        """The nightly job: gzip finished days, prune old files, enforce the three clocks."""
        out = {'content_stripped': 0, 'deleted': 0, 'files_removed': 0, 'files_compressed': 0}
        if self.jsonl is not None:
            try:
                out['files_compressed'] = len(await asyncio.to_thread(self.jsonl.rotate))
                out['files_removed'] = len(await asyncio.to_thread(self.jsonl.prune, self.settings.file_days))
            except Exception as exc:
                self._sink_error('file', exc)
        if self.store is not None:
            try:
                out.update(await self.store.apply_retention(self.settings, now=self._clock()))
            except Exception as exc:
                self._sink_error('sqlite', exc)
        return out
