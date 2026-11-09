# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Security event log (docs/features/SECURITY_EVENT_LOG.md): the schema, the
validated writer, the rotated JSONL sink, the SQLite table, retention and
the privacy rules. Hermetic: temp dirs, an injected clock, no Discord."""

import asyncio
import gzip
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from utils import database
from utils import security_log as sl
from utils.config import Secret

UTC = timezone.utc
T0 = datetime(2026, 9, 28, 14, 3, 11, 482000, tzinfo=UTC)
ON = sl.SecLogSettings(enabled=True)


# Secret-shaped fixtures are assembled at run time from fragments so that no committed
# file contains a complete token-shaped literal (push protection and scanners).
def fake_discord_token():
    return 'M' + 'T' * 24 + '.' + 'G' + 'a' * 5 + '.' + 'x' * 10 + 'Y' * 10 + 'z' * 10


def fake_github_token():
    return 'gh' + 'p_' + 'aB3d' * 9


def fake_github_pat():
    return 'github' + '_pat_' + 'A' * 40


def fake_aws_key():
    return 'AK' + 'IA' + 'Q' * 16


def fake_slack_token():
    return 'xo' + 'xb-' + '1' * 12 + '-' + '2' * 12 + '-' + 'a' * 24


def fake_private_key_header():
    return '-' * 5 + 'BEGIN RSA PRIV' + 'ATE KEY' + '-' * 5


def fake_jwt():
    return 'ey' + 'J' + 'h' * 12 + '.' + 'ey' + 'J' + 'z' * 12 + '.' + 'q' * 20


def fake_bearer():
    return 'Authorization: Bear' + 'er ' + 'k' * 36


def fake_doppler():
    return 'dp' + '.st.' + 'prd.' + 'a' * 40


def fake_openai():
    return 's' + 'k-' + 'Z' * 40


def fake_google_key():
    return 'AI' + 'za' + 'B' * 35


_HOOK_PIECES = ('AbCd', '_ef-', 'GH12', '34')
HOOK_TAIL = ''.join(_HOOK_PIECES)


def hook_url(host='discord.com', *, scheme='https://', prefix='/api', hooks='web' + 'hooks', tail=HOOK_TAIL):
    return f'{scheme}{host}{prefix}/{hooks}/123456789/{tail}'


@pytest.fixture(autouse=True)
def _private_umask():
    """Directories the tests create must not be group-writable (the sink refuses those)."""
    old = os.umask(0o022)
    yield
    os.umask(old)


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def build(kind='message', action='delete', settings=None, **fields):
    base = {'guild.id': '123', 'user.id': '1011', 'channel.id': '20'}
    base.update(fields)
    return sl.build_event(kind, action, base, settings=settings, clock=Clock())


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def test_envelope_is_filled_and_ecs_shaped():
    ev = build(**{'channel.id': 456, 'content': 'hi', 'length': 2})
    assert ev['@timestamp'] == '2026-09-28T14:03:11.482Z'
    assert ev['event.kind'] == 'message' and ev['event.action'] == 'delete'
    assert ev['schema'] == sl.SCHEMA_VERSION == 1
    assert len(ev['event.id']) == 26
    assert ev['channel.id'] == '456'  # snowflakes are strings


def test_event_ids_are_unique_and_time_ordered():
    clock = Clock()
    a = sl.build_event('lifecycle', 'start', {}, clock=clock)
    clock.now += timedelta(milliseconds=5)
    b = sl.build_event('lifecycle', 'start', {}, clock=clock)
    assert a['event.id'] < b['event.id']
    ids = {sl.build_event('lifecycle', 'start', {}, clock=clock)['event.id'] for _ in range(500)}
    assert len(ids) == 500


@pytest.mark.parametrize('kind,action', [
    ('presence', 'update'), ('typing', 'start'), ('message', 'frobnicate'),
    ('Message', 'delete'), ('message', ''), ('', 'delete'), ('member', 'delete'),
])
def test_unknown_kind_or_action_is_rejected(kind, action):
    with pytest.raises(sl.SecurityEventError):
        sl.build_event(kind, action, {}, clock=Clock())


def test_trust_tiers_match_the_trust_module():
    from utils import trust
    assert sl.TRUST_TIERS == trust.TIERS


def test_every_documented_kind_is_closed_and_nonempty():
    assert set(sl.KINDS) == {'audit', 'member', 'message', 'voice', 'structure',
                             'automod', 'interaction', 'decision', 'lifecycle'}
    assert all(sl.KINDS[k] for k in sl.KINDS)


def test_unknown_field_is_rejected():
    with pytest.raises(sl.SecurityEventError, match='unknown field'):
        build(**{'presence.status': 'online'})


def test_envelope_fields_cannot_be_supplied_by_the_caller():
    for name in ('event.kind', 'event.action', 'schema'):
        with pytest.raises(sl.SecurityEventError):
            build(**{name: 'x'})


@pytest.mark.parametrize('bad', ['abc', '', '-1', '1' * 20, 2 ** 63, -5, 1.5, True, None, ['1'], '12 34', '１２３', '123\n', '\n123'])
def test_snowflake_fields_reject_non_ids(bad):
    with pytest.raises(sl.SecurityEventError):
        build(**{'channel.id': bad})


@pytest.mark.parametrize('field,bad', [
    ('length', -1), ('length', 'x'), ('length', True), ('length', 2 ** 40),
    ('content_available', 'yes'), ('mentions.everyone', 1),
    ('user.trust_tier', 'god'), ('actor.type', 'alien'), ('via', 'telepathy'),
    ('confidence', 1.5), ('confidence', float('nan')), ('latency_ms', float('inf')),
    ('roles.added', 'not-a-list'), ('roles.added', ['x']),
    ('attachments', [{'name': 'a', 'size': 1, 'type': 't', 'bytes': 'AAAA'}]),
    ('attachments', ['a']), ('links', [1]), ('changes', ['x']), ('changes', {'k': object()}),
])
def test_typed_fields_reject_wrong_types_and_values(field, bad):
    with pytest.raises(sl.SecurityEventError):
        build(**{field: bad})


def test_timestamp_field_accepts_aware_datetime_and_iso_only():
    ev = build('member', 'update', **{'timeout.until': datetime(2026, 9, 29, 1, 2, 3, tzinfo=timezone(timedelta(hours=-4)))})
    assert ev['timeout.until'] == '2026-09-29T05:02:03.000Z'
    for bad in (datetime(2026, 9, 29), '2026-09-29', 'yesterday', 12):
        with pytest.raises(sl.SecurityEventError):
            build('member', 'update', **{'timeout.until': bad})


def test_error_messages_do_not_echo_raw_hostile_values():
    with pytest.raises(sl.SecurityEventError) as exc:
        build(**{'channel.id': 'x\n{"forged":1}\x1b[31m' + 'A' * 500})
    text = str(exc.value)
    assert '\n' not in text and '\x1b' not in text and len(text) < 200


def test_oversized_event_is_rejected():
    # Every field is within its own cap; together they blow the per-line cap.
    args = {f'k{i}': {'before': '\U0001F600' * sl.JSON_STR_MAX, 'after': 'x'} for i in range(sl.MAX_JSON_KEYS)}
    with pytest.raises(sl.SecurityEventError, match='too large'):
        sl.serialize(sl.build_event('interaction', 'command', {'channel.id': '9', 'args': args}, clock=Clock()))


def test_serialized_line_cap_is_enforced():
    huge = sl.MAX_EVENT_BYTES
    event = {'@timestamp': 'x', 'blob': 'a' * huge}
    with pytest.raises(sl.SecurityEventError, match='too large'):
        sl.serialize(event)


def test_timestamp_override_must_be_sane():
    ok = build(**{'@timestamp': '2026-09-27T01:02:03.5Z'})
    assert ok['@timestamp'] == '2026-09-27T01:02:03.500Z'
    for bad in ('2999-01-01T00:00:00Z', '1999-01-01T00:00:00Z', '2026-02-30T00:00:00Z', '2026-09-27T01:02:03Z\n'):
        with pytest.raises(sl.SecurityEventError):
            build(**{'@timestamp': bad})


def test_validate_event_refuses_non_canonical_hand_built_events():
    good = build(**{'user.name': 'someone'})
    assert sl.validate_event(good) == good
    for mutate in (lambda e: e.update({'user.name': 'a\nb'}), lambda e: e.update({'length': 'many'}),
                   lambda e: e.update({'event.id': 'not-a-ulid'}), lambda e: e.update({'schema': 2}),
                   lambda e: e.update({'event.redacted': ['nonsense']}), lambda e: e.update({'surprise': 1})):
        bad = dict(good)
        mutate(bad)
        with pytest.raises(sl.SecurityEventError):
            sl.validate_event(bad)


def test_serialize_escapes_line_separators_even_on_hand_built_input():
    line = sl.serialize({'a': 'x\u2028y\u2029z\x85w\x7fv'})
    assert not any(ch in line for ch in ('\u2028', '\u2029', '\x85', '\x7f'))
    assert json.loads(line) == {'a': 'x\u2028y\u2029z\x85w\x7fv'}
    with pytest.raises(sl.SecurityEventError):
        sl.serialize({'a': 'lone\ud800surrogate'})


# --------------------------------------------------------------------------
# Injection: every string field
# --------------------------------------------------------------------------

HOSTILE = [
    'line1\nline2', 'a\r\nb', 'a\rb', 'a\x00b', 'a\x1b[2Jb', 'a\x7fb', 'a\x85b',
    'a\u2028b', 'a\u2029b', 'a\u202eb', 'x"}\n{"event.kind":"audit","forged":true}',
    'a\ud800b',  # lone surrogate: would crash a UTF-8 encode
]
STRING_FIELDS = [
    'channel.name', 'user.name', 'actor.name', 'target.name', 'reason',
    'nick.before', 'nick.after', 'invite.code', 'rule', 'matched_keyword',
    'command', 'error_id', 'category', 'content', 'content.before', 'content.after',
]


def _kind_for(field):
    if field.startswith('content'):
        return 'message', 'edit'
    return {'nick.before': ('member', 'update'), 'nick.after': ('member', 'update'),
            'invite.code': ('member', 'join'), 'rule': ('automod', 'triggered'),
            'matched_keyword': ('automod', 'triggered'),
            'command': ('interaction', 'command'), 'error_id': ('interaction', 'command'),
            'category': ('decision', 'moderation_scan'),
            }.get(field, ('audit', 'ban'))


@pytest.mark.parametrize('field', STRING_FIELDS)
@pytest.mark.parametrize('hostile', HOSTILE)
def test_hostile_strings_cannot_break_out_of_a_jsonl_line(field, hostile):
    kind, action = _kind_for(field)
    settings = sl.SecLogSettings(content_mode='create')
    ev = sl.build_event(kind, action, {field: hostile, 'channel.id': '9'}, settings=settings, clock=Clock())
    line = sl.serialize(ev)
    assert '\n' not in line and '\r' not in line
    assert not any(ch in line for ch in ('\u2028', '\u2029', '\x85', '\x00', '\x1b', '\x7f'))
    raw = line.encode('utf-8')  # must not raise
    back = json.loads(raw.decode('utf-8'))
    assert list(back).count('forged') == 0 and 'forged' not in back
    assert back['event.kind'] == kind  # the forged kind did not replace ours


def test_names_lose_every_control_char_content_keeps_only_newline_and_tab():
    ev = build(**{'user.name': 'a\nb\tc\u202ed', 'content': 'a\nb\tc\rd\x00e\u202ef'})
    assert ev['user.name'] == 'a\ufffdb\ufffdc\ufffdd'
    assert ev['content'] == 'a\nb\tc\nd\ufffde\ufffdf'
    assert 'user.name' in ev['event.sanitized'] and 'content' in ev['event.sanitized']


def test_clean_values_are_not_marked_sanitized():
    ev = build(**{'user.name': 'someone', 'content': 'plain text, émoji 😀'})
    assert 'event.sanitized' not in ev


def test_hostile_keys_and_values_inside_json_objects_are_sanitized():
    ev = interaction(args={'perm\nissions': {'before': 'a\nb', 'after': ['x\x00y']}})
    line = sl.serialize(ev)
    assert '\n' not in line and '\x00' not in line
    assert list(ev['args']) == ['perm\ufffdissions']


def test_colliding_sanitized_keys_are_rejected():
    with pytest.raises(sl.SecurityEventError):
        interaction(args={'a\nb': {'after': 1}, 'a\rb': {'after': 2}})


def test_free_text_is_truncated_not_rejected_and_says_so():
    ev = build(**{'content': 'x' * (sl.CONTENT_MAX + 50), 'user.name': 'n' * 500})
    assert len(ev['content']) == sl.CONTENT_MAX
    assert len(ev['user.name']) == sl.NAME_MAX
    assert {'content', 'user.name'} <= set(ev['event.truncated'])


def test_list_and_object_size_caps():
    with pytest.raises(sl.SecurityEventError):
        build(links=['example.com'] * (sl.MAX_LIST + 1))
    with pytest.raises(sl.SecurityEventError):
        build('audit', 'role_update', changes={f'k{i}': {'after': 1} for i in range(sl.MAX_JSON_KEYS + 1)})
    deep = {'after': 1}
    for _ in range(sl.MAX_JSON_DEPTH + 2):
        deep = {'after': deep}
    with pytest.raises(sl.SecurityEventError):
        build('audit', 'role_update', changes={'k': deep})


def test_big_integers_become_strings_so_readers_do_not_round_them():
    big = 2 ** 60 + 1
    ev = build('audit', 'role_update', changes={'permissions': {'before': 0, 'after': big}})
    assert ev['changes']['permissions']['after'] == str(big)
    assert ev['changes']['permissions']['before'] == 0


def test_serialize_is_valid_utf8_json_with_sorted_stable_output():
    ev = build(**{'user.name': 'Zoë 😀', 'content': '日本語'})
    line = sl.serialize(ev)
    assert json.loads(line) == ev
    assert line == sl.serialize(json.loads(line))


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------

def test_content_modes():
    def with_mode(mode, action):
        s = sl.SecLogSettings(content_mode=mode)
        return sl.build_event('message', action, {'user.id': '1', 'channel.id': '9', 'content': 'secret text'},
                              settings=s, clock=Clock())
    assert 'content' not in with_mode('none', 'delete')
    assert 'content' not in with_mode('none', 'create')
    assert with_mode('edits_and_deletes', 'delete')['content'] == 'secret text'
    assert 'content' not in with_mode('edits_and_deletes', 'create')
    assert with_mode('create', 'create')['content'] == 'secret text'


def test_stripped_content_is_declared_not_silent():
    s = sl.SecLogSettings(content_mode='none')
    ev = sl.build_event('message', 'delete', {'channel.id': '9', 'content': 'x', 'content_available': True}, settings=s, clock=Clock())
    assert 'content' not in ev and ev['content_available'] is False
    assert 'content' in ev['event.redacted']


def test_content_edit_before_after_follow_the_same_mode():
    s = sl.SecLogSettings(content_mode='none')
    ev = sl.build_event('message', 'edit', {'channel.id': '9', 'content.before': 'a', 'content.after': 'b'}, settings=s, clock=Clock())
    assert 'content.before' not in ev and 'content.after' not in ev
    assert set(ev['event.redacted']) == {'content.before', 'content.after'}


def test_content_is_dropped_for_excluded_channels_and_later_exclusions():
    s = sl.SecLogSettings(content_exclude_channels=frozenset({'456'}))
    ev = sl.build_event('message', 'delete', {'channel.id': '456', 'content': 'x'}, settings=s, clock=Clock())
    assert 'content' not in ev
    other = sl.build_event('message', 'delete', {'channel.id': '457', 'content': 'x'}, settings=s, clock=Clock())
    assert other['content'] == 'x'


def test_content_is_only_legal_on_message_events():
    with pytest.raises(sl.SecurityEventError):
        sl.build_event('member', 'update', {'content': 'x'}, clock=Clock())


def test_links_are_domains_on_create_and_edit_full_urls_on_delete():
    s = sl.SecLogSettings(content_mode='create')
    urls = ['https://User:pw@Evil.Example.com:8443/path?token=abc#x', 'http://example.org/a']
    create = sl.build_event('message', 'create', {'links': urls}, settings=s, clock=Clock())
    assert create['links'] == ['evil.example.com', 'example.org']
    edit = sl.build_event('message', 'edit', {'links': urls}, settings=s, clock=Clock())
    assert edit['links'] == ['evil.example.com', 'example.org']
    delete = sl.build_event('message', 'delete', {'channel.id': '9', 'links': ['http://example.org/a?x=1']}, settings=s, clock=Clock())
    assert delete['links'] == ['http://example.org/a?x=1']


def test_delete_urls_never_keep_userinfo():
    ev = build(links=['https://user:hunter2@example.org/x'])
    assert 'hunter2' not in json.dumps(ev) and 'user:' not in json.dumps(ev)


def test_unparseable_link_on_create_is_dropped_not_stored_raw():
    s = sl.SecLogSettings(content_mode='create')
    ev = sl.build_event('message', 'create', {'links': ['http://[::1', 'not a url']}, settings=s, clock=Clock())
    assert ev['links'] == []


def test_reactions_are_off_unless_enabled():
    assert sl.build_event('message', 'reaction_add', {}, clock=Clock(), settings=sl.SecLogSettings()) is None
    on = sl.build_event('message', 'reaction_add', {}, clock=Clock(), settings=sl.SecLogSettings(reactions=True))
    assert on['event.action'] == 'reaction_add'


@pytest.mark.parametrize('make', [
    fake_discord_token, fake_github_token, fake_github_pat, fake_aws_key, fake_slack_token,
    fake_private_key_header, fake_jwt, fake_bearer, fake_doppler, fake_openai, fake_google_key,
    lambda: hook_url(),
], ids=lambda f: getattr(f, '__name__', 'webhook'))
def test_secret_shaped_values_are_redacted_everywhere_but_the_event_is_kept(make):
    secret = make()
    s = sl.SecLogSettings(content_mode='create')
    ev = sl.build_event('message', 'create', {'channel.id': '9', 'content': f'my key is {secret} ok', 'user.name': secret},
                        settings=s, clock=Clock())
    dumped = sl.serialize(ev)
    assert secret not in dumped
    assert sl.REDACTED in ev['content'] and ev['content'].startswith('my key is')
    assert {'content', 'user.name'} <= set(ev['event.redacted'])


def test_interaction_args_are_redacted_by_key_and_by_secret_type():
    ev = sl.build_event('interaction', 'command', {
        'command': 'setup',
        'channel.id': '9',
        'args': {'api_key': 'plain', 'Password': 'p', 'nested': {'client_secret': 'z', 'ok': 'fine'},
                 'wrapped': Secret('top'), 'note': 'hello'},
    }, clock=Clock())
    args = ev['args']
    assert args['api_key'] == sl.REDACTED and args['Password'] == sl.REDACTED
    assert args['nested'] == {'client_secret': sl.REDACTED, 'ok': 'fine'}
    assert args['wrapped'] == sl.REDACTED and args['note'] == 'hello'
    assert 'top' not in sl.serialize(ev)
    assert 'args' in ev['event.redacted']


def test_secret_objects_are_never_stored_by_repr_in_any_field():
    ev = build('audit', 'role_update', changes={'token': {'after': Secret('abc')}})
    assert 'abc' not in sl.serialize(ev)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def test_settings_defaults_match_the_design_doc():
    s = sl.SecLogSettings()
    assert (s.enabled, s.content_mode, s.content_days, s.meta_days, s.audit_days, s.file_days, s.reactions) == \
        (False, 'edits_and_deletes', 90, 365, 0, 90, False)


@pytest.mark.parametrize('kw', [
    {'content_mode': 'everything'}, {'content_days': 0}, {'meta_days': 0}, {'meta_days': -1},
    {'audit_days': -1}, {'file_days': 0}, {'content_days': True}, {'content_days': '90'},
    {'content_exclude_channels': frozenset({'abc'})},
    {'file_days': 91}, {'content_days': 30, 'file_days': 60, 'content_mode': 'create'},
])
def test_settings_reject_bad_values(kw):
    with pytest.raises(ValueError):
        sl.SecLogSettings(**kw)


def test_settings_allow_long_files_only_when_no_content_is_logged():
    assert sl.SecLogSettings(content_mode='none', file_days=400).file_days == 400
    assert sl.SecLogSettings(file_days=90).file_days == 90
    with pytest.raises(ValueError, match='file_days'):
        sl.SecLogSettings(content_mode='create', file_days=400)


# -- review fixes: fail-closed content, links under the same rule, URL rebuild, webhook pattern ----------

def msg(action='delete', settings=None, **fields):
    return sl.build_event('message', action, fields, settings=settings, clock=Clock())


@pytest.mark.parametrize('action', ['create', 'edit', 'delete'])
def test_content_without_a_channel_id_is_dropped_not_kept(action):
    s = sl.SecLogSettings(content_mode='create')
    ev = msg(action, s, **{'content': 'x', 'content.before': 'a', 'content.after': 'b'})
    assert not any(k in ev for k in sl.CONTENT_FIELDS)
    assert set(ev['event.redacted']) == set(sl.CONTENT_FIELDS)
    assert ev['content_available'] is False


@pytest.mark.parametrize('settings,channel', [
    (sl.SecLogSettings(content_mode='none'), '9'),
    (sl.SecLogSettings(content_exclude_channels=frozenset({'9'})), '9'),
    (sl.SecLogSettings(), None),
])
def test_links_follow_the_content_decision(settings, channel):
    fields = {'links': ['https://example.org/private/path?token=1', 'http://Other.example.net/x']}
    if channel:
        fields['channel.id'] = channel
    ev = msg('delete', settings, **fields)
    assert ev['links'] == ['example.org', 'other.example.net']
    assert 'links' in ev['event.redacted']


def test_links_keep_full_urls_when_content_is_kept():
    ev = msg('delete', None, **{'channel.id': '9', 'links': ['https://example.org/a?b=1']})
    assert ev['links'] == ['https://example.org/a?b=1'] and 'event.redacted' not in ev


async def test_full_url_rows_count_as_content_and_retention_and_forget_strip_them(store):
    full = {'channel.id': '20', 'links': ['https://example.org/secret/path?x=1']}
    await store.insert(ev_at(T0 - timedelta(days=95), **full, **{'message.id': '1'}))
    await store.insert(ev_at(T0, **full, **{'message.id': '2'}))
    await store.insert(ev_at(T0, **{'links': ['example.org'], 'message.id': '3'}))   # domains only: not content
    rows = {r['message_id']: r for r in await store.by_user(10)}
    assert (rows[1]['has_content'], rows[2]['has_content'], rows[3]['has_content']) == (1, 1, 0)
    assert await store.count_content_rows() == 2
    await store.apply_retention(sl.SecLogSettings(), now=T0)
    rows = {r['message_id']: r for r in await store.by_user(10)}
    assert 'links' not in rows[1]['data'] and rows[1]['has_content'] == 0
    assert rows[2]['data']['links'] == full['links']
    assert await store.forget_user_content(10) == 1
    rows = {r['message_id']: r for r in await store.by_user(10)}
    assert 'links' not in rows[2]['data'] and rows[3]['data']['links'] == ['example.org']


async def test_retention_keeps_domain_links_on_create_rows_that_carry_content(store):
    s = sl.SecLogSettings(content_mode='create')
    ev = sl.build_event('message', 'create', {'user.id': '10', 'channel.id': '20', 'content': 'hi',
                                              'links': ['https://example.org/x']}, settings=s,
                        clock=Clock(T0 - timedelta(days=95)))
    await store.insert(ev)
    await store.apply_retention(sl.SecLogSettings(), now=T0)
    data = (await store.by_user(10))[0]['data']
    assert 'content' not in data and data['links'] == ['example.org']


@pytest.mark.parametrize('url,expected', [
    ('https://user:p@ss@example.org/x', 'https://example.org/x'),           # @ inside the password
    ('https://user@example.org:8443/a?b=1#frag', 'https://example.org:8443/a?b=1'),
    ('HTTP://Example.ORG/Path', 'http://example.org/Path'),
    ('http://[2001:db8::1]:8080/x', 'http://[2001:db8::1]:8080/x'),
    ('http://[::1]/', 'http://[::1]/'),
])
def test_delete_urls_are_rebuilt_without_credentials(url, expected):
    assert msg('delete', None, **{'channel.id': '9', 'links': [url]})['links'] == [expected]


@pytest.mark.parametrize('url', [
    'https://evil.com\\@good.com/x', 'https://exa mple.org/', 'https://example.org/a b', 'https://example.org/\tx',
    'http://[::1', 'http://[nothex]/', 'https://example.org:99999/', 'https://example.org:abc/',
    'ftp://example.org/x', 'javascript:alert(1)', 'https://', 'https:///path', 'not a url',
    'https://example.org/' + 'a' * sl.URL_MAX, '',
])
def test_unparseable_or_hostile_links_are_dropped(url):
    for action in ('delete', 'create'):
        assert msg(action, sl.SecLogSettings(content_mode='create'), **{'channel.id': '9', 'links': [url]})['links'] == []


def test_secret_inside_a_url_is_redacted_and_the_url_kept():
    ev = msg('delete', None, **{'channel.id': '9', 'links': ['https://example.org/x?k=' + fake_github_token()]})
    assert ev['links'] == ['https://example.org/x?k=[REDACTED]'] and 'links' in ev['event.redacted']


TOKEN = HOOK_TAIL


@pytest.mark.parametrize('url', [
    hook_url('discord.com:443'),
    hook_url('discord.com.'),
    hook_url('DiScOrD.CoM', prefix='/Api', hooks='Web' + 'Hooks'),
    hook_url('user:pw@discord.com'),
    hook_url(hooks='%77ebhooks'),
    hook_url(prefix='/%61pi'),
    hook_url(hooks='%2577ebhooks'),
    hook_url(prefix='//api/', hooks='/web' + 'hooks'),
    hook_url('ptb.discord.com:8443', prefix='/api/v9'),
    hook_url('canary.discordapp.com.', tail=HOOK_TAIL + '/github'),
    hook_url('discordapp.com', tail=HOOK_TAIL + '?wait=true'),
])
def test_webhook_urls_in_parser_differential_forms_never_survive_in_links(url):
    for action in ('delete', 'create'):
        s = sl.SecLogSettings(content_mode='create')
        ev = msg(action, s, **{'channel.id': '9', 'links': [url, 'https://example.org/ok']})
        assert TOKEN not in sl.serialize(ev)
        assert ev['links'] in (['https://example.org/ok'], ['example.org'])
        assert 'links' in ev['event.redacted']


def test_ordinary_discord_urls_are_not_mistaken_for_webhooks():
    ev = msg('delete', None, **{'channel.id': '9',
                                 'links': ['https://discord.com/channels/1/2/3', 'https://discord.com/api/users/1']})
    assert len(ev['links']) == 2 and 'event.redacted' not in ev


def test_domain_reduction_never_carries_userinfo_or_ipv6():
    s = sl.SecLogSettings(content_mode='create')
    ev = msg('create', s, **{'channel.id': '9', 'links': ['https://u:p@ss@Example.org/x', 'http://[::1]/']})
    assert ev['links'] == ['example.org']


def test_validate_event_refuses_a_link_with_credentials():
    good = msg('delete', None, **{'channel.id': '9', 'links': ['https://example.org/x']})
    assert sl.validate_event(good) == good
    bad = dict(good, links=['https://user:pw@example.org/x'])
    with pytest.raises(sl.SecurityEventError):
        sl.validate_event(bad)


@pytest.mark.parametrize('text', [
    hook_url(),
    hook_url().upper(),
    hook_url(scheme=''),
    hook_url('discordapp.com', prefix='/api/v10'),
    hook_url('ptb.discord.com'),
    hook_url('canary.discordapp.com'),
    hook_url('DiscordApp.com', hooks='Web' + 'hooks', scheme=''),
])
def test_webhook_urls_are_redacted_in_any_case_with_or_without_scheme(text):
    ev = msg('delete', None, **{'channel.id': '9', 'content': f'look {text} here'})
    assert HOOK_TAIL.lower() not in sl.serialize(ev).lower() and sl.REDACTED in ev['content']


# --------------------------------------------------------------------------
# JSONL sink: write, rotation boundaries, concurrency, retention
# --------------------------------------------------------------------------

def line_for(n):
    return sl.serialize(sl.build_event('lifecycle', 'start', {'error_id': f'e{n}'}, clock=Clock()))


def test_sink_appends_one_line_per_event_in_a_dated_file(tmp_path):
    sink = sl.JsonlSink(tmp_path / 'sec', clock=Clock())
    for n in range(3):
        sink.write(line_for(n))
    path = tmp_path / 'sec' / 'events-2026-09-28.jsonl'
    rows = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
    assert [r['error_id'] for r in rows] == ['e0', 'e1', 'e2']
    assert oct(path.stat().st_mode & 0o777) == oct(0o640)


def test_sink_refuses_a_line_with_a_newline_in_it(tmp_path):
    sink = sl.JsonlSink(tmp_path, clock=Clock())
    for bad in ('{"a":1}\n{"b":2}', '{"a":1}\r', 'a\u2028b'):
        with pytest.raises(sl.SecurityEventError):
            sink.write(bad)
    assert list(tmp_path.iterdir()) == []


def test_rotation_at_the_midnight_boundary(tmp_path):
    clock = Clock(datetime(2026, 9, 28, 23, 59, 59, 999999, tzinfo=UTC))
    sink = sl.JsonlSink(tmp_path, clock=clock)
    sink.write(line_for(1))
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith('.seclog')) == ['events-2026-09-28.jsonl']
    clock.now = datetime(2026, 9, 29, 0, 0, 0, 0, tzinfo=UTC)
    sink.write(line_for(2))
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith('.seclog')) == ['events-2026-09-28.jsonl.gz', 'events-2026-09-29.jsonl']
    old = gzip.open(tmp_path / 'events-2026-09-28.jsonl.gz', 'rt', encoding='utf-8').read().splitlines()
    assert [json.loads(x)['error_id'] for x in old] == ['e1']
    assert json.loads((tmp_path / 'events-2026-09-29.jsonl').read_text().strip())['error_id'] == 'e2'


def test_today_is_never_compressed(tmp_path):
    clock = Clock(datetime(2026, 9, 28, 23, 59, 59, tzinfo=UTC))
    sink = sl.JsonlSink(tmp_path, clock=clock)
    sink.write(line_for(1))
    assert sink.rotate() == []
    assert (tmp_path / 'events-2026-09-28.jsonl').exists()


def test_rotation_catches_up_days_missed_while_the_bot_was_down(tmp_path):
    (tmp_path / 'events-2026-09-01.jsonl').write_text(line_for(1) + '\n', encoding='utf-8')
    (tmp_path / 'events-2026-09-02.jsonl').write_text(line_for(2) + '\n', encoding='utf-8')
    sink = sl.JsonlSink(tmp_path, clock=Clock())
    sink.write(line_for(3))
    names = sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith('.seclog'))
    assert names == ['events-2026-09-01.jsonl.gz', 'events-2026-09-02.jsonl.gz', 'events-2026-09-28.jsonl']


def test_rotation_appends_to_an_existing_gz_without_losing_either_half(tmp_path):
    with gzip.open(tmp_path / 'events-2026-09-01.jsonl.gz', 'wt', encoding='utf-8') as f:
        f.write(line_for(1) + '\n')
    (tmp_path / 'events-2026-09-01.jsonl').write_text(line_for(2) + '\n', encoding='utf-8')
    sl.JsonlSink(tmp_path, clock=Clock()).rotate()
    text = gzip.open(tmp_path / 'events-2026-09-01.jsonl.gz', 'rt', encoding='utf-8').read().splitlines()
    assert [json.loads(x)['error_id'] for x in text] == ['e1', 'e2']
    assert not (tmp_path / 'events-2026-09-01.jsonl').exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_rotation_ignores_unrelated_files_and_symlinks(tmp_path):
    outside = tmp_path / 'outside.txt'
    outside.write_text('keep me')
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'notes.txt').write_text('x')
    (d / 'events-2026-13-45.jsonl').write_text('x')
    (d / 'events-2026-09-01.jsonl').symlink_to(outside)
    assert sl.JsonlSink(d, clock=Clock()).rotate() == []
    assert outside.read_text() == 'keep me' and (d / 'events-2026-09-01.jsonl').is_symlink()


def test_sink_will_not_follow_a_symlink_planted_at_todays_file(tmp_path):
    outside = tmp_path / 'victim.txt'
    outside.write_text('original')
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'events-2026-09-28.jsonl').symlink_to(outside)
    sink = sl.JsonlSink(d, clock=Clock())
    with pytest.raises(OSError):
        sink.write(line_for(1))
    assert outside.read_text() == 'original'


def test_concurrent_writers_never_interleave_lines(tmp_path):
    sink = sl.JsonlSink(tmp_path, clock=Clock())
    threads_n, per = 8, 150
    pad = 'p' * 3000  # large enough that interleaving would be visible
    errors = []

    def worker(t):
        try:
            for i in range(per):
                ev = sl.build_event('lifecycle', 'start', {'error_id': f't{t}-{i}', 'reason': pad}, clock=Clock())
                sink.write(sl.serialize(ev))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    rows = [json.loads(x) for x in (tmp_path / 'events-2026-09-28.jsonl').read_text().splitlines()]
    assert len(rows) == threads_n * per
    assert len({r['error_id'] for r in rows}) == threads_n * per


def test_concurrent_writers_across_a_rotation_lose_nothing(tmp_path):
    clock = Clock(datetime(2026, 9, 28, 23, 59, 59, tzinfo=UTC))
    sink = sl.JsonlSink(tmp_path, clock=clock)
    stop = threading.Event()

    def flip():
        stop.wait(0.01)
        clock.now = datetime(2026, 9, 29, 0, 0, 1, tzinfo=UTC)

    flipper = threading.Thread(target=flip)
    flipper.start()
    threads = [threading.Thread(target=lambda t=t: [sink.write(line_for(f'{t}-{i}')) for i in range(120)])
               for t in range(6)]
    for t in threads:
        t.start()
    stop.set()
    for t in threads:
        t.join()
    flipper.join()
    seen = []
    for p in sorted(tmp_path.iterdir()):
        opener = gzip.open if p.suffix == '.gz' else open
        with opener(p, 'rt', encoding='utf-8') as f:
            seen += [json.loads(x)['error_id'] for x in f.read().splitlines()]
    assert len(seen) == 6 * 120 == len(set(seen))


def test_file_retention_uses_the_filename_date_not_mtime(tmp_path):
    clock = Clock()
    names = {
        'events-2025-08-23.jsonl.gz': True,    # 401 days before 2026-09-28: gone
        'events-2025-08-24.jsonl.gz': False,   # exactly 400 days: kept
        'events-2026-09-28.jsonl': False,
        'events-2020-01-01.jsonl': True,       # an uncompressed straggler is pruned too
        'readme.txt': False,
    }
    for name in names:
        p = tmp_path / name
        p.write_bytes(b'x')
        os.utime(p, (T0.timestamp(), T0.timestamp()))  # fresh mtime must not save an old file
    removed = sl.JsonlSink(tmp_path, clock=clock).prune(file_days=400)
    assert sorted(removed) == sorted(n for n, gone in names.items() if gone)
    assert {p.name for p in tmp_path.iterdir() if not p.name.startswith('.seclog')} == {n for n, gone in names.items() if not gone}


def test_file_retention_never_deletes_symlink_targets(tmp_path):
    target = tmp_path / 'precious'
    target.write_text('x')
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'events-2020-01-01.jsonl.gz').symlink_to(target)
    assert sl.JsonlSink(d, clock=Clock()).prune(file_days=400) == []
    assert target.exists()


# --------------------------------------------------------------------------
# SQLite table, migration, queries, retention
# --------------------------------------------------------------------------

@pytest.fixture
async def store(tmp_data_dir):
    database.reset_database()
    db = await database.get_database()
    yield sl.SecurityEventStore(db)
    await db.close()
    database.reset_database()


def ev_at(ts, kind='message', action='delete', **fields):
    clock = Clock(ts)
    base = {'guild.id': '1', 'user.id': '10', 'channel.id': '20', 'message.id': '30'}
    base.update(fields)
    return sl.build_event(kind, action, base, clock=clock)


async def test_schema_is_v4_with_security_events_table_and_indexes(store):
    conn = store.db.conn
    cur = await conn.execute('SELECT version FROM schema_version')
    assert (await cur.fetchone())['version'] == 4
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    assert 'security_events' in {r['name'] for r in await cur.fetchall()}
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='security_events'")
    idx = {r['name'] for r in await cur.fetchall()}
    assert {'idx_secev_user', 'idx_secev_actor', 'idx_secev_channel', 'idx_secev_kind'} <= idx
    cur = await conn.execute('PRAGMA table_info(security_events)')
    cols = {r['name'] for r in await cur.fetchall()}
    assert {'id', 'event_id', 'ts', 'kind', 'action', 'guild_id', 'channel_id', 'user_id', 'actor_id',
            'message_id', 'has_content', 'data'} <= cols


async def test_migration_from_v3_adds_the_table_and_keeps_data(tmp_data_dir):
    path = str(tmp_data_dir / 'old.db')
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (3);
        CREATE TABLE ai_key_usage (key_id TEXT NOT NULL, day TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0, cooldown_until TEXT, disabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (key_id, day));
        INSERT INTO ai_key_usage (key_id, day, requests) VALUES ('k', '2026-01-01', 7);
    """)
    raw.commit()
    raw.close()
    db = database.ModerationDatabase(path)
    await db.connect()
    try:
        cur = await db.conn.execute('SELECT version FROM schema_version')
        assert (await cur.fetchone())['version'] == 4
        cur = await db.conn.execute('SELECT requests FROM ai_key_usage')
        assert (await cur.fetchone())['requests'] == 7
        await sl.SecurityEventStore(db).insert(ev_at(T0))
    finally:
        await db.close()


async def test_newer_schema_is_still_refused(tmp_data_dir):
    path = str(tmp_data_dir / 'future.db')
    raw = sqlite3.connect(path)
    raw.executescript('CREATE TABLE schema_version (version INTEGER NOT NULL); INSERT INTO schema_version VALUES (99);')
    raw.commit()
    raw.close()
    db = database.ModerationDatabase(path)
    with pytest.raises(RuntimeError, match='newer'):
        await db.connect()
    assert db.conn is None  # the refused open did not leave a connection (and its thread) behind


async def test_insert_roundtrips_the_full_event(store):
    ev = ev_at(T0, **{'actor.id': '99', 'content': 'gone', 'content_available': True})
    row_id = await store.insert(ev)
    rows = await store.by_user(10)
    assert [r['id'] for r in rows] == [row_id]
    r = rows[0]
    assert r['data'] == ev and r['kind'] == 'message' and r['action'] == 'delete'
    assert (r['guild_id'], r['channel_id'], r['user_id'], r['actor_id'], r['message_id']) == (1, 20, 10, 99, 30)
    assert r['ts'] == '2026-09-28T14:03:11.482Z' and r['has_content'] == 1


async def test_event_id_is_unique(store):
    ev = ev_at(T0)
    await store.insert(ev)
    with pytest.raises(sqlite3.IntegrityError):
        await store.insert(ev)


async def test_insert_revalidates_so_a_hand_built_dict_cannot_bypass_the_schema(store):
    ev = ev_at(T0)
    ev['event.kind'] = 'presence'
    with pytest.raises(sl.SecurityEventError):
        await store.insert(ev)
    ev = ev_at(T0)
    ev['user.id'] = "1'; DROP TABLE security_events;--"
    with pytest.raises(sl.SecurityEventError):
        await store.insert(ev)


async def test_sql_injection_strings_are_stored_as_data_and_queries_survive(store):
    nasty = "x'); DROP TABLE security_events;--"
    await store.insert(ev_at(T0, **{'user.name': nasty, 'reason': nasty}))
    rows = await store.by_user(10)
    assert rows[0]['data']['user.name'] == nasty
    cur = await store.db.conn.execute('SELECT COUNT(*) AS n FROM security_events')
    assert (await cur.fetchone())['n'] == 1


async def test_query_inputs_are_typed_so_injection_cannot_reach_sql(store):
    for bad in ("1 OR 1=1", "1; DROP TABLE security_events", 1.5, None, True):
        with pytest.raises((TypeError, ValueError)):
            await store.by_user(bad)
    with pytest.raises((TypeError, ValueError)):
        await store.by_kind('message', "delete' OR '1'='1")
    with pytest.raises(ValueError):
        await store.by_user(10, since="2026'; DROP TABLE x;--")


async def test_queries_by_user_actor_channel_kind_with_paging_and_window(store):
    for i in range(5):
        await store.insert(ev_at(T0 + timedelta(minutes=i), **{'actor.id': '99', 'message.id': str(100 + i)}))
    await store.insert(ev_at(T0, 'member', 'join', **{'user.id': '11', 'channel.id': '21'}))
    assert [r['message_id'] for r in await store.by_user(10, limit=3)] == [104, 103, 102]  # newest first
    assert [r['message_id'] for r in await store.by_user(10, limit=3, offset=3)] == [101, 100]
    assert len(await store.by_actor(99)) == 5
    assert len(await store.by_channel(21)) == 1
    assert len(await store.by_kind('message', 'delete')) == 5
    assert len(await store.by_kind('member')) == 1
    since = (T0 + timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    assert len(await store.by_user(10, since=since)) == 3
    assert len(await store.by_user(10, guild_id=2)) == 0
    assert len(await store.by_user(10, limit=10 ** 9)) == 5  # clamped, not an error or an unbounded scan


async def test_query_limit_is_clamped_to_the_cap(store, monkeypatch):
    monkeypatch.setattr(sl, 'MAX_QUERY_LIMIT', 3)
    for i in range(5):
        await store.insert(ev_at(T0 + timedelta(seconds=i), **{'message.id': str(i + 1)}))
    assert len(await store.by_user(10, limit=10 ** 9)) == 3
    assert len(await store.by_user(10, limit=0)) == 1


async def test_deleted_message_count_for_whois(store):
    now = T0
    await store.insert(ev_at(now - timedelta(days=3)))
    await store.insert(ev_at(now - timedelta(days=40)))
    await store.insert(ev_at(now - timedelta(days=1), action='edit'))
    assert await store.count_deleted_messages(10, days=30, now=now) == 1


async def test_concurrent_inserts_do_not_lose_or_duplicate_rows(store):
    events = [ev_at(T0, **{'message.id': str(i)}) for i in range(200)]
    await asyncio.gather(*(store.insert(e) for e in events))
    cur = await store.db.conn.execute('SELECT COUNT(*) AS n, COUNT(DISTINCT event_id) AS d FROM security_events')
    row = await cur.fetchone()
    assert (row['n'], row['d']) == (200, 200)


async def test_retention_three_clocks(store):
    now = T0
    old = lambda days: now - timedelta(days=days)  # noqa: E731
    await store.insert(ev_at(old(100), **{'content': 'old text', 'message.id': '1'}))          # content aged
    await store.insert(ev_at(old(10), **{'content': 'fresh text', 'message.id': '2'}))         # content kept
    await store.insert(ev_at(old(400), **{'message.id': '3'}))                                  # meta aged: deleted
    await store.insert(ev_at(old(300), **{'message.id': '4'}))                                  # meta kept
    await store.insert(ev_at(old(2000), 'audit', 'ban', **{'actor.id': '5'}))                   # audit forever
    result = await store.apply_retention(sl.SecLogSettings(), now=now)
    assert result == {'content_stripped': 1, 'deleted': 1}
    rows = {r['message_id']: r for r in await store.by_kind('message', limit=100)}
    assert set(rows) == {1, 2, 4}
    assert 'content' not in rows[1]['data'] and rows[1]['has_content'] == 0
    assert rows[1]['kind'] == 'message' and rows[1]['user_id'] == 10  # metadata stays
    assert rows[2]['data']['content'] == 'fresh text' and rows[2]['has_content'] == 1
    assert len(await store.by_kind('audit')) == 1


async def test_retention_content_strip_removes_before_and_after_too(store):
    await store.insert(ev_at(T0 - timedelta(days=95), 'message', 'edit',
                             **{'content.before': 'a', 'content.after': 'b'}))
    await store.apply_retention(sl.SecLogSettings(), now=T0)
    data = (await store.by_user(10))[0]['data']
    assert not any(k.startswith('content') and k != 'content_available' for k in data)


async def test_audit_clock_can_be_enabled(store):
    await store.insert(ev_at(T0 - timedelta(days=800), 'audit', 'ban'))
    await store.insert(ev_at(T0 - timedelta(days=10), 'audit', 'ban'))
    result = await store.apply_retention(sl.SecLogSettings(audit_days=365), now=T0)
    assert result['deleted'] == 1 and len(await store.by_kind('audit')) == 1


async def test_retention_is_idempotent_and_handles_many_rows_in_batches(store):
    for i in range(30):
        await store.insert(ev_at(T0 - timedelta(days=500), **{'message.id': str(i)}))
    first = await store.apply_retention(sl.SecLogSettings(), now=T0, batch=7)
    second = await store.apply_retention(sl.SecLogSettings(), now=T0, batch=7)
    assert first['deleted'] == 30 and second == {'content_stripped': 0, 'deleted': 0}


async def test_forget_user_content_keeps_metadata_and_other_members(store):
    await store.insert(ev_at(T0, **{'content': 'mine', 'message.id': '1'}))
    await store.insert(ev_at(T0, **{'user.id': '11', 'content': 'theirs', 'message.id': '2'}))
    n = await store.forget_user_content(10)
    assert n == 1
    mine = (await store.by_user(10))[0]
    assert 'content' not in mine['data'] and mine['has_content'] == 0 and mine['action'] == 'delete'
    assert (await store.by_user(11))[0]['data']['content'] == 'theirs'


async def test_content_row_gauge(store):
    await store.insert(ev_at(T0, **{'content': 'x'}))
    await store.insert(ev_at(T0, **{'message.id': '9'}))
    assert await store.count_content_rows() == 1


# --------------------------------------------------------------------------
# Emitter: sinks fail independently, nothing leaks, nothing blocks
# --------------------------------------------------------------------------

async def test_emit_writes_file_and_sqlite_with_the_same_event(store, tmp_path):
    sink = sl.JsonlSink(tmp_path / 'sec', clock=Clock())
    log = sl.SecurityLog(settings=ON, jsonl=sink, store=store, clock=Clock())
    ev = await log.emit('message', 'delete', **{'guild.id': '1', 'user.id': '10', 'channel.id': '20', 'content': 'hello'})
    file_rows = [json.loads(x) for x in (tmp_path / 'sec' / 'events-2026-09-28.jsonl').read_text().splitlines()]
    assert file_rows == [ev] == [(await store.by_user(10))[0]['data']]
    assert log.stats['events'] == 1 and log.stats['sink_errors'] == {}


async def test_a_failing_sink_never_blocks_the_other_or_raises(store, tmp_path):
    class Boom(sl.JsonlSink):
        def write(self, line, cancelled=None):
            raise OSError('disk full')

    log = sl.SecurityLog(settings=ON, jsonl=Boom(tmp_path, clock=Clock()), store=store, clock=Clock())
    ev = await log.emit('lifecycle', 'start')
    assert ev is not None and len(await store.by_kind('lifecycle')) == 1
    assert log.stats['sink_errors'] == {'file': 1}

    class BadStore:
        async def insert(self, ev):
            raise sqlite3.OperationalError('locked')

    sink = sl.JsonlSink(tmp_path / 's2', clock=Clock())
    log2 = sl.SecurityLog(settings=ON, jsonl=sink, store=BadStore(), clock=Clock())
    assert await log2.emit('lifecycle', 'start') is not None
    assert log2.stats['sink_errors'] == {'sqlite': 1}
    assert len((tmp_path / 's2' / 'events-2026-09-28.jsonl').read_text().splitlines()) == 1


async def test_emit_rejects_bad_events_without_raising_and_counts_them(store, tmp_path):
    log = sl.SecurityLog(settings=ON, store=store, clock=Clock())
    assert await log.emit('presence', 'update') is None
    assert await log.emit('message', 'delete', **{'user.id': 'nope'}) is None
    assert log.stats['rejected'] == 2 and log.stats['events'] == 0
    assert await store.by_kind('message') == []


async def test_emit_filtered_reactions_are_counted_not_rejected(store):
    log = sl.SecurityLog(settings=ON, store=store, clock=Clock())
    assert await log.emit('message', 'reaction_add') is None
    assert log.stats['filtered'] == 1 and log.stats['rejected'] == 0


async def test_disabled_log_writes_nothing(store, tmp_path):
    sec = tmp_path / 'sec'
    log = sl.SecurityLog(settings=sl.SecLogSettings(enabled=False), jsonl=sl.JsonlSink(sec, clock=Clock()),
                         store=store, clock=Clock())
    assert await log.emit('lifecycle', 'start') is None
    assert not sec.exists() and await store.by_kind('lifecycle') == []


async def test_concurrent_emits_through_both_sinks(store, tmp_path):
    sec = tmp_path / 'sec'
    sink = sl.JsonlSink(sec, clock=Clock())
    log = sl.SecurityLog(settings=ON, jsonl=sink, store=store, clock=Clock())
    await asyncio.gather(*(log.emit('message', 'delete', **{'user.id': '10', 'message.id': str(i)}) for i in range(100)))
    lines = (sec / 'events-2026-09-28.jsonl').read_text().splitlines()
    assert len(lines) == 100 and len(await store.by_user(10, limit=500)) == 100


async def test_run_retention_covers_files_and_sqlite(store, tmp_path):
    sec = tmp_path / 'sec'
    sec.mkdir()
    sink = sl.JsonlSink(sec, clock=Clock())
    (sec / 'events-2020-01-01.jsonl.gz').write_bytes(b'x')
    (sec / 'events-2026-09-01.jsonl').write_text(line_for(1) + '\n', encoding='utf-8')
    await store.insert(ev_at(T0 - timedelta(days=500)))
    log = sl.SecurityLog(settings=ON, jsonl=sink, store=store, clock=Clock())
    result = await log.run_retention()
    assert result == {'content_stripped': 0, 'deleted': 1, 'files_removed': 1, 'files_compressed': 1}
    assert sorted(p.name for p in sec.iterdir() if not p.name.startswith('.seclog')) == ['events-2026-09-01.jsonl.gz']


async def test_content_exclusion_added_at_runtime(store):
    log = sl.SecurityLog(settings=ON, store=store, clock=Clock())
    log.add_content_exclusion(555)
    ev = await log.emit('message', 'delete', **{'channel.id': '555', 'user.id': '10', 'content': 'ticket text'})
    assert 'content' not in ev and (await store.by_user(10))[0]['has_content'] == 0
    with pytest.raises(sl.SecurityEventError):
        log.add_content_exclusion('abc')


# --------------------------------------------------------------------------
# Review round: free-form args/changes, key folding, symlinked temp, inter-process lock,
# FIFO, sink timeouts, rollback, version-before-DDL, private-key blocks, URL-like text
# --------------------------------------------------------------------------

import multiprocessing  # noqa: E402
import time  # noqa: E402
import stat  # noqa: E402


def interaction(settings=None, **fields):
    base = {'command': 'report', 'channel.id': '9'}
    base.update(fields)
    return sl.build_event('interaction', 'command', base, settings=settings, clock=Clock())


def test_args_and_changes_are_refused_where_they_do_not_belong():
    for kind, action, field in (('message', 'delete', 'args'), ('message', 'edit', 'changes'),
                                ('member', 'update', 'changes'), ('audit', 'message_delete', 'changes'),
                                ('audit', 'ban', 'args'), ('interaction', 'command', 'changes')):
        with pytest.raises(sl.SecurityEventError, match='not allowed'):
            sl.build_event(kind, action, {field: {'a': 1}}, clock=Clock())
    # and where they do: interaction args, audit/structure changes
    interaction(args={'a': 1})
    sl.build_event('audit', 'role_update', {'changes': {'a': {'after': 1}}}, clock=Clock())
    sl.build_event('structure', 'role_update', {'changes': {'a': {'after': 1}}}, clock=Clock())


def test_validate_event_enforces_the_same_field_rules():
    good = interaction(args={'a': 1})
    bad = dict(good)
    bad['event.kind'], bad['event.action'] = 'message', 'delete'
    with pytest.raises(sl.SecurityEventError):
        sl.validate_event(bad)


@pytest.mark.parametrize('settings,fields', [
    (sl.SecLogSettings(content_mode='none'), {}),
    (sl.SecLogSettings(content_exclude_channels=frozenset({'9'})), {}),
    (sl.SecLogSettings(), {'channel.id': None}),
])
def test_args_follow_the_content_decision(settings, fields):
    base = {'command': 'report', 'args': {'text': 'private words'}}
    if fields.get('channel.id', '9'):
        base['channel.id'] = '9'
    ev = sl.build_event('interaction', 'command', base, settings=settings, clock=Clock())
    assert 'args' not in ev and 'args' in ev['event.redacted']


async def test_args_rows_count_as_content_and_retention_and_forget_strip_them(store):
    for i, age in enumerate((95, 1)):
        ev = sl.build_event('interaction', 'command', {'user.id': '10', 'channel.id': '9', 'command': 'report',
                                                       'args': {'text': 'private words'}},
                            clock=Clock(T0 - timedelta(days=age)))
        await store.insert(ev)
    assert await store.count_content_rows() == 2
    await store.apply_retention(sl.SecLogSettings(), now=T0)
    rows = {r['ts']: r for r in await store.by_user(10)}
    old, new = sorted(rows.values(), key=lambda r: r['ts'])
    assert 'args' not in old['data'] and old['has_content'] == 0 and old['data']['command'] == 'report'
    assert new['data']['args'] == {'text': 'private words'}
    assert await store.forget_user_content(10) == 1
    assert 'args' not in (await store.by_user(10))[0]['data']


def audit_changes(changes):
    return sl.build_event('audit', 'channel_update', {'changes': changes}, clock=Clock())


def test_changes_keep_structural_values_and_redact_free_text():
    ev = audit_changes({'permissions': {'before': '1024', 'after': 8}, 'name': {'before': 'general', 'after': 'ops-room'},
                        'role_ids': {'after': ['123', '456']}, 'nsfw': {'after': True}, 'colour': {'after': None},
                        'topic': {'before': 'a free text topic', 'after': 'Mod Chat'}})
    c = ev['changes']
    assert c['permissions'] == {'before': '1024', 'after': 8} and c['name'] == {'before': 'general', 'after': 'ops-room'}
    assert c['role_ids'] == {'after': ['123', '456']} and c['nsfw'] == {'after': True} and c['colour'] == {'after': None}
    assert c['topic'] == {'before': sl.REDACTED, 'after': sl.REDACTED} and 'changes' in ev['event.redacted']


@pytest.mark.parametrize('text', [
    'see https://user:pw@Example.org/a?x=1 now', 'example.com/path', '//host.example/x', 'https://x.example/z',
    'user@host.example', 'host.example:8080', 'x' * 65, 'two words', 'line\nbreak', 'ｅxample.com/ｐath',
    'discord.com./api/web' + 'hooks/1/' + HOOK_TAIL,
])
def test_changes_never_carry_urls_or_free_text_in_values(text):
    ev = audit_changes({'k': {'before': text, 'after': [text, 'ok']}})
    dumped = json.dumps(ev)
    assert ev['changes']['k']['before'] == sl.REDACTED and ev['changes']['k']['after'] == [sl.REDACTED, 'ok']
    assert 'example' not in dumped and 'user:pw' not in dumped and HOOK_TAIL not in dumped


@pytest.mark.parametrize('key', ['example.com/path', '//host.example/x', 'two words', '1abc', 'x' * 65, 'tоken', ''])
def test_changes_drop_keys_that_are_not_identifiers(key):
    ev = audit_changes({key: {'after': 'leak-me'}, 'name': {'after': 'kept'}})
    assert list(ev['changes']) == ['name'] and 'leak-me' not in json.dumps(ev) and 'changes' in ev['event.redacted']


def test_changes_are_metadata_but_args_are_content_for_has_content():
    assert not sl._holds_content(audit_changes({'name': {'after': 'x'}}))


@pytest.mark.parametrize('key', [
    'token', 'tоken',                       # Cyrillic o
    'ｔｏｋｅｎ',       # fullwidth
    't\u200boken', 'API key', 'api‐key', 'Pаssword',   # zero-width, space, hyphen, Cyrillic a
    'ѕecret', 'ΑPI_KEY', 'sεcret', 'tοken', 'сookie', 'secrеt', 'Αuthorization', 'kеy',                    # Cyrillic s, Greek capital alpha
])
def test_secret_key_names_are_matched_after_unicode_folding(key):
    for ev in (interaction(args={key: 'hunter2'}),
               sl.build_event('audit', 'role_update', {'changes': {key: {'after': 'hunter2'}}}, clock=Clock())):
        assert 'hunter2' not in json.dumps(ev)


def test_ordinary_keys_survive_folding():
    ev = interaction(args={'author': 'x', 'monkey': 'y', 'user': 'z'})
    assert ev['args'] == {'author': 'x', 'monkey': 'y', 'user': 'z'}


def test_confusable_spellings_of_secret_values_are_redacted():
    tok = fake_github_token().replace('p', 'р', 1)           # Cyrillic er
    wide = ''.join(chr(ord(c) + 0xFEE0) if c.isascii() and c.isalnum() else c for c in fake_github_token())
    for text in (tok, wide):
        ev = msg('delete', None, **{'channel.id': '9', 'content': f'x {text} y'})
        assert ev['content'] == sl.REDACTED or sl.REDACTED in ev['content']
        assert text not in sl.serialize(ev)


def test_private_key_block_is_redacted_whole_even_without_an_end_line():
    body = '\n'.join(['Zm9vYmFyYmF6' * 5] * 3)
    head = fake_private_key_header()
    end = head.replace('BEGIN', 'END')
    for text in (f'before\n{head}\n{body}\n{end}\nafter', f'before\n{head}\n{body}'):
        ev = msg('delete', None, **{'channel.id': '9', 'content': text})
        assert 'Zm9vYmFy' not in sl.serialize(ev) and ev['content'].startswith('before')
    name = sl.build_event('lifecycle', 'start', {'error_id': f'{head}\n{body}'}, clock=Clock())
    assert 'Zm9vYmFy' not in sl.serialize(name)


@pytest.mark.parametrize('url', [
    hook_url('user:pw@discord.com'), hook_url('discord.com:443'), hook_url('discord.com.'),
    hook_url(prefix='//api/', hooks='/web' + 'hooks'), hook_url(hooks='%77ebhooks'),
    hook_url(prefix='/%61pi'), hook_url('discord%2Ecom'), hook_url('PTB.DiScOrD.com:8443', scheme=''),
    hook_url('canary.discordapp.com.', scheme=''),
])
def test_webhook_url_forms_in_free_text_are_redacted(url):
    for text in (f'look {url} here', f'({url}).', f'<{url}>', f'x\n{url}'):
        ev = msg('delete', None, **{'channel.id': '9', 'content': text, 'user.name': f'n {url}'[:100]})
        assert HOOK_TAIL not in sl.serialize(ev)
        assert {'content'} <= set(ev['event.redacted'])


def test_ordinary_discord_text_is_not_redacted():
    text = 'join https://discord.com/channels/1/2/3 or read discord.com/api/users and the webhooks docs'
    ev = msg('delete', None, **{'channel.id': '9', 'content': text})
    assert ev['content'] == text and 'event.redacted' not in ev


# -- JSONL sink hardening ----------------------------------------------------------------------------

def test_planted_tmp_symlink_is_never_followed_by_compression(tmp_path):
    victim = tmp_path / 'victim.txt'
    victim.write_text('original')
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'events-2026-09-01.jsonl').write_text(line_for(1) + '\n', encoding='utf-8')
    with gzip.open(d / 'events-2026-09-01.jsonl.gz', 'wt', encoding='utf-8') as f:
        f.write(line_for(0) + '\n')
    (d / 'events-2026-09-01.jsonl.gz.tmp').symlink_to(victim)
    assert sl.JsonlSink(d, clock=Clock()).rotate() == ['events-2026-09-01.jsonl']
    assert victim.read_text() == 'original'
    text = gzip.open(d / 'events-2026-09-01.jsonl.gz', 'rt', encoding='utf-8').read().splitlines()
    assert [json.loads(x)['error_id'] for x in text] == ['e0', 'e1']
    assert not list(d.glob('*.tmp'))


def _writer_proc(directory, day, start, n, barrier, hold):
    class Slow(sl.JsonlSink):
        def _before_write(self):        # widens the window between opening the day file and writing to it
            import time
            time.sleep(hold)

    clock = Clock(datetime(2026, 9, day, 12, tzinfo=UTC))
    sink = Slow(directory, clock=clock)
    barrier.wait(10)
    if start == 'rotate':
        import time
        time.sleep(0.15)
        sink.rotate()
    else:
        for i in range(n):
            sink.write(line_for(f'w{i}'))
            hold = 0


def test_two_processes_cannot_lose_events_across_a_rotation(tmp_path):
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'events-2026-09-27.jsonl').write_text(line_for('seed') + '\n', encoding='utf-8')
    ctx = multiprocessing.get_context('fork')
    barrier = ctx.Barrier(2)
    rotator = ctx.Process(target=_writer_proc, args=(str(d), 28, 'rotate', 0, barrier, 0))
    writer = ctx.Process(target=_writer_proc, args=(str(d), 27, 'write', 20, barrier, 0.5))
    rotator.start()
    writer.start()
    rotator.join(30)
    writer.join(30)
    assert rotator.exitcode == 0 and writer.exitcode == 0
    sl.JsonlSink(d, clock=Clock(datetime(2026, 9, 29, tzinfo=UTC))).rotate()
    seen = []
    for p in sorted(d.iterdir()):
        if p.suffix == '.gz':
            seen += [json.loads(x)['error_id'] for x in gzip.open(p, 'rt', encoding='utf-8').read().splitlines()]
    assert sorted(seen) == sorted(['e' + 'seed'] + [f'ew{i}' for i in range(20)])


def test_a_planted_fifo_cannot_wedge_the_sink(tmp_path):
    d = tmp_path / 'sec'
    d.mkdir()
    os.mkfifo(d / 'events-2026-09-28.jsonl')
    sink = sl.JsonlSink(d, clock=Clock())
    result = []

    def attempt():
        try:
            sink.write(line_for(1))
        except OSError as exc:
            result.append(exc)

    t = threading.Thread(target=attempt, daemon=True)
    t.start()
    t.join(3)
    assert not t.is_alive() and result, 'write blocked on a FIFO or did not refuse it'


def test_a_planted_fifo_lock_file_cannot_wedge_the_sink(tmp_path):
    d = tmp_path / 'sec'
    d.mkdir()
    os.mkfifo(d / sl.LOCK_NAME)
    sink = sl.JsonlSink(d, clock=Clock())
    t = threading.Thread(target=lambda: pytest.raises(OSError, sink.write, line_for(1)), daemon=True)
    t.start()
    t.join(3)
    assert not t.is_alive()


def test_sink_refuses_files_not_owned_by_the_bot_user(tmp_path, monkeypatch):
    sink = sl.JsonlSink(tmp_path, clock=Clock())
    sink.write(line_for(1))
    monkeypatch.setattr(os, 'geteuid', lambda: os.stat(tmp_path).st_uid + 12345)
    with pytest.raises(OSError, match='not owned'):
        sink.write(line_for(2))


def test_sink_files_are_regular_and_private(tmp_path):
    sl.JsonlSink(tmp_path, clock=Clock()).write(line_for(1))
    assert stat.S_ISREG((tmp_path / sl.LOCK_NAME).stat().st_mode)
    assert (tmp_path / sl.LOCK_NAME).stat().st_mode & 0o077 == 0


async def test_a_wedged_file_sink_cannot_stall_sqlite_or_the_caller(store, tmp_path):
    class Wedged(sl.JsonlSink):
        def write(self, line, cancelled=None):
            import time
            time.sleep(1.0)

    log = sl.SecurityLog(settings=ON, jsonl=Wedged(tmp_path / 'sec', clock=Clock()), store=store, clock=Clock(),
                         sink_timeout=0.1)
    started = asyncio.get_running_loop().time()
    ev = await log.emit('lifecycle', 'start')
    assert asyncio.get_running_loop().time() - started < 0.8
    assert ev is not None and len(await store.by_kind('lifecycle')) == 1
    assert log.stats['sink_errors'] == {'file': 1}


async def test_a_wedged_sqlite_sink_cannot_stall_the_file_or_the_caller(tmp_path):
    class Wedged:
        async def insert(self, event):
            await asyncio.sleep(5)

    sink = sl.JsonlSink(tmp_path / 'sec', clock=Clock())
    log = sl.SecurityLog(settings=ON, jsonl=sink, store=Wedged(), clock=Clock(), sink_timeout=0.1)
    started = asyncio.get_running_loop().time()
    assert await log.emit('lifecycle', 'start') is not None
    assert asyncio.get_running_loop().time() - started < 1.5
    assert log.stats['sink_errors'] == {'sqlite': 1}
    assert len((tmp_path / 'sec' / 'events-2026-09-28.jsonl').read_text().splitlines()) == 1


# -- SQLite hardening --------------------------------------------------------------------------------

async def test_failed_retention_rolls_back_and_a_later_insert_does_not_commit_half_of_it(store):
    await store.insert(ev_at(T0 - timedelta(days=500), **{'message.id': '1'}))               # meta aged
    await store.insert(ev_at(T0 - timedelta(days=900), 'audit', 'ban'))                      # audit aged
    await store.db.conn.execute(
        """CREATE TRIGGER no_audit_delete BEFORE DELETE ON security_events WHEN old.kind = 'audit'
           BEGIN SELECT RAISE(ABORT, 'nope'); END""")
    await store.db.conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        await store.apply_retention(sl.SecLogSettings(audit_days=365), now=T0)
    await store.insert(ev_at(T0, **{'message.id': '2'}))       # would commit a leftover transaction
    assert {r['message_id'] for r in await store.by_kind('message', limit=10)} == {1, 2}


async def test_failed_forget_rolls_back_and_the_store_keeps_working(store):
    await store.insert(ev_at(T0, **{'content': 'mine', 'message.id': '1'}))
    await store.db.conn.execute(
        "CREATE TRIGGER no_update BEFORE UPDATE ON security_events BEGIN SELECT RAISE(ABORT, 'nope'); END")
    await store.db.conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        await store.forget_user_content(10)
    await store.db.conn.execute('DROP TRIGGER no_update')
    await store.db.conn.commit()
    assert await store.forget_user_content(10) == 1


async def test_a_newer_database_is_refused_before_any_ddl_runs(tmp_data_dir):
    path = str(tmp_data_dir / 'future2.db')
    raw = sqlite3.connect(path)
    raw.executescript('CREATE TABLE schema_version (version INTEGER NOT NULL); INSERT INTO schema_version VALUES (99);')
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match='newer'):
        await database.ModerationDatabase(path).connect()
    raw = sqlite3.connect(path)
    tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    raw.close()
    assert tables == {'schema_version'}


# -- final round ---------------------------------------------------------------------------------------

async def test_a_timed_out_file_write_never_mutates_the_sink_afterwards(tmp_path):
    sink = sl.JsonlSink(tmp_path / 'sec', clock=Clock())
    log = sl.SecurityLog(settings=ON, jsonl=sink, clock=Clock(), sink_timeout=0.1)
    sink._lock.acquire()                 # another thread holds the sink: the call queues behind it
    try:
        assert await log.emit('lifecycle', 'start') is not None
        assert log.stats['sink_errors'] == {'file': 1}
    finally:
        sink._lock.release()
    await asyncio.sleep(0.3)             # the queued thread now runs; it must see it was abandoned
    assert not (tmp_path / 'sec').exists() or not list((tmp_path / 'sec').glob('events-*'))
    ev = await log.emit('lifecycle', 'start')    # and a later call is the only line, in order
    lines = (tmp_path / 'sec' / 'events-2026-09-28.jsonl').read_text().splitlines()
    assert [json.loads(x)['event.id'] for x in lines] == [ev['event.id']]


async def test_a_timed_out_sqlite_insert_never_lands_afterwards(store):
    log = sl.SecurityLog(settings=ON, store=store, clock=Clock(), sink_timeout=0.1)
    await store.db.lock.acquire()
    try:
        assert await log.emit('lifecycle', 'start') is not None
        assert log.stats['sink_errors'] == {'sqlite': 1}
    finally:
        store.db.lock.release()
    await asyncio.sleep(0.2)
    assert await store.by_kind('lifecycle') == []


def test_write_fails_closed_when_the_directory_cannot_be_opened(tmp_path, monkeypatch):
    sink = sl.JsonlSink(tmp_path / 'sec', clock=Clock())
    real_open = os.open

    def flaky(path, flags, *a, **kw):
        if flags & os.O_DIRECTORY:
            raise FileNotFoundError(2, 'vanished')
        return real_open(path, flags, *a, **kw)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, 'open', flaky)
    with pytest.raises(OSError):
        sink.write(line_for(1))
    monkeypatch.undo()
    assert not list(tmp_path.glob('**/events-*')) and not list(tmp_path.glob('**/.seclog*'))


def test_read_only_paths_may_see_a_missing_directory(tmp_path):
    sink = sl.JsonlSink(tmp_path / 'absent', clock=Clock())
    assert sink.rotate() == [] and sink.prune(10) == []


def test_compression_happens_outside_the_append_lock(tmp_path):
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'events-2026-09-01.jsonl').write_text(line_for(1) + '\n', encoding='utf-8')
    observed = []

    class Probe(sl.JsonlSink):
        def _after_read(self):
            # while a day is being compressed another writer must be able to take the append lock
            other = sl.JsonlSink(d, clock=Clock())
            other.write(line_for('during'))
            observed.append(True)

    Probe(d, clock=Clock()).rotate()
    assert observed
    today = (d / 'events-2026-09-28.jsonl').read_text().splitlines()
    assert [json.loads(x)['error_id'] for x in today] == ['eduring']


def test_the_lock_timeout_is_configurable_and_long_by_default(tmp_path):
    assert sl.LOCK_TIMEOUT >= 60
    sink = sl.JsonlSink(tmp_path, clock=Clock(), lock_timeout=0.2)
    holder = sl.JsonlSink(tmp_path, clock=Clock())
    with holder._held(create=True):
        started = time.monotonic()
        with pytest.raises(OSError, match='timed out'):
            sink.write(line_for(1))
    assert time.monotonic() - started < 3


def test_a_symlinked_log_directory_is_refused(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    (tmp_path / 'link').symlink_to(real)
    with pytest.raises(OSError):
        sl.JsonlSink(tmp_path / 'link', clock=Clock()).write(line_for(1))
    assert list(real.iterdir()) == []


@pytest.mark.parametrize('mode', [0o777, 0o770, 0o757])
def test_a_group_or_world_writable_log_directory_is_refused(tmp_path, mode):
    d = tmp_path / 'sec'
    d.mkdir()
    d.chmod(mode)
    with pytest.raises(OSError, match='writable'):
        sl.JsonlSink(d, clock=Clock()).write(line_for(1))
    assert list(d.iterdir()) == []


def test_a_foreign_owned_log_directory_is_refused(tmp_path, monkeypatch):
    d = tmp_path / 'sec'
    d.mkdir()
    monkeypatch.setattr(os, 'geteuid', lambda: d.stat().st_uid + 4242)
    with pytest.raises(OSError, match='directory is not owned'):
        sl.JsonlSink(d, clock=Clock()).write(line_for(1))


def test_a_replaced_lock_file_is_detected_and_the_lock_retaken(tmp_path):
    attempts = []

    class Swap(sl.JsonlSink):
        def _after_flock(self, attempt):
            attempts.append(attempt)
            if attempt == 0:                           # an attacker (or tmp cleaner) swaps the lock inode
                (tmp_path / sl.LOCK_NAME).unlink()
                (tmp_path / sl.LOCK_NAME).write_text('')

    sink = Swap(tmp_path, clock=Clock())
    sink.write(line_for(1))
    assert attempts[:2] == [0, 1]
    assert len((tmp_path / 'events-2026-09-28.jsonl').read_text().splitlines()) == 1


def test_greek_and_cyrillic_lookalikes_are_folded_but_ordinary_words_are_not():
    for key in ('s\u03b5cret', 'tok\u03b5n', 'k\u03b5y', 'c\u043eokie', 'passw\u043erd',
                '\u0430pi_key', 'cr\u0435dential', 'auth\u043erization', 'private_k\u0435y'):
        ev = interaction(args={key: 'hunter2'})
        assert 'hunter2' not in json.dumps(ev), key
    ev = interaction(args={'author': 'a', 'monkey': 'b', 'keyboard': 'c'})
    assert ev['args'] == {'author': 'a', 'monkey': 'b', 'keyboard': 'c'}


@pytest.mark.parametrize('spelling', [
    lambda t: t.replace('discord', 'd\u0456sc\u043erd'),                    # Cyrillic i and o
    lambda t: t.replace('discord', '\uff44\uff49\uff53\uff43\uff4f\uff52\uff44'),   # fullwidth
    lambda t: t.replace('discord', '%64%69scord'),                          # percent-encoded
    lambda t: t.replace('discord', 'dis\u200bcord'),                         # zero-width
    lambda t: t.replace('discord', 'DISCORD'),
])
def test_obfuscated_discord_never_skips_the_url_scan(spelling):
    text = f'see {spelling(hook_url(scheme=""))} now'
    redacted, changed = sl._redact_secret_urls(text)
    assert changed and HOOK_TAIL not in redacted


def test_the_url_scan_stays_fast_on_a_megabyte_and_on_adversarial_input():
    big = ('lorem ipsum dolor %41 sit \u00e9met ' * 40000)[:10 ** 6]
    started = time.monotonic()
    sl._redact_secret_urls(big)
    sl._redact_secret_urls('a' * 10 ** 6)
    sl._redact_secret_urls(' '.join(['discord'] * 100000))
    assert time.monotonic() - started < 5
    # the production path caps a field first, so the worst realistic input is small
    started = time.monotonic()
    sl.build_event('message', 'delete', {'channel.id': '9', 'content': 'discord webhooks %41 ' * 20000}, clock=Clock())
    assert time.monotonic() - started < 5


@pytest.mark.parametrize('payload', ['a' * 200000, ' ' * 200000, '-----BEGIN ' * 20000, 'ey' + 'J' * 200000,
                                     'bearer ' + ' ' * 200000, 'gh' + 'p_' * 50000, '[' * 200000,
                                     '-----BEGIN ' + 'A ' * 100000])
def test_secret_patterns_do_not_backtrack_catastrophically(payload):
    for pattern in sl._SECRET_PATTERNS:
        started = time.monotonic()
        pattern.sub(sl.REDACTED, payload)
        assert time.monotonic() - started < 2


def test_leftover_part_files_from_a_crash_are_compressed_on_the_next_rotation(tmp_path):
    d = tmp_path / 'sec'
    d.mkdir()
    (d / 'events-2026-09-01.jsonl.deadbeef.part').write_text(line_for(1) + '\n', encoding='utf-8')
    (d / 'events-2026-09-01.jsonl.nothex!!.part').write_text('ignored', encoding='utf-8')
    assert sl.JsonlSink(d, clock=Clock()).rotate() == ['events-2026-09-01.jsonl']
    text = gzip.open(d / 'events-2026-09-01.jsonl.gz', 'rt', encoding='utf-8').read().splitlines()
    assert [json.loads(x)['error_id'] for x in text] == ['e1']
    assert (d / 'events-2026-09-01.jsonl.nothex!!.part').exists()


def test_a_call_abandoned_while_waiting_for_the_file_lock_writes_nothing(tmp_path):
    d = tmp_path / 'sec'
    sink = sl.JsonlSink(d, clock=Clock())
    holder = sl.JsonlSink(d, clock=Clock())
    cancel = threading.Event()
    with holder._held(create=True):
        t = threading.Thread(target=sink.write, args=(line_for(1), cancel))
        t.start()
        time.sleep(0.2)                    # the writer is now waiting on the flock
        cancel.set()
    t.join(5)
    assert not t.is_alive() and not list(d.glob('events-*'))
