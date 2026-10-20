# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Roast data files: schema validation, size caps, duplicate keys, the
operator override directory, and the shipped files themselves.

Every validation rule has its own test, so deleting a rule turns one red.
"""

import copy
import json
import logging
import os

import pytest

from ai.features import roast_loader as roast_data
from ai.features.roast_loader import (
    MAX_FILE_BYTES, RoastDataError, load_roast_data, parse_roast_data,
    render_system_prompt,
)

EM_DASH = '—'

GOOD = {
    'schema_version': 1,
    'system_prompt': 'You roast {distro}.\n{angles}\n{exemplars}\n{format}\n{avoid}\nOne roast only.',
    'user_prompt_tail': 'Roast for {distro_name}, under {max_length} characters.',
    'max_length': 120,
    'avoid_header': 'Recent:',
    'exemplar_header': 'Style:',
    'angles': ['angle one', 'angle two', 'angle three'],
    'formats': [{'name': 'one-liner', 'instruction': ''},
                {'name': 'two-parter', 'instruction': 'Two short sentences.', 'max_length': 200}],
    'exemplars': ['sample a'],
    'banned_phrases': ['banned thing'],
    'fallback_jokes': ['joke one', 'joke two'],
    'house_jokes': {'chance': 0.1, 'jokes': ['house one']},
}


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False).encode('utf-8')


def good(**changes):
    doc = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is KeyError:
            doc.pop(key)
        else:
            doc[key] = value
    return doc


def bad(match, **changes):
    with pytest.raises(RoastDataError, match=match):
        parse_roast_data(dumps(good(**changes)))


# -- the good path ---------------------------------------------------------

def test_good_document_parses():
    data = parse_roast_data(dumps(GOOD))
    assert data.angles == ('angle one', 'angle two', 'angle three')
    assert [f.name for f in data.formats] == ['one-liner', 'two-parter']
    assert data.formats[0].max_length is None and data.formats[1].max_length == 200
    assert data.house_jokes.chance == 0.1 and data.house_jokes.jokes == ('house one',)
    assert data.fallback_jokes == ('joke one', 'joke two')


def test_optional_keys_default():
    doc = good()
    for key in ('exemplars', 'banned_phrases', 'house_jokes', 'max_length',
                'avoid_header', 'exemplar_header'):
        doc.pop(key)
    data = parse_roast_data(dumps(doc))
    assert data.exemplars == () and data.banned_phrases == ()
    assert data.house_jokes is None and data.max_length == 120


# -- hostile input ---------------------------------------------------------

def test_oversize_bytes_rejected():
    blob = b' ' * (MAX_FILE_BYTES + 1)
    with pytest.raises(RoastDataError, match='too large'):
        parse_roast_data(blob)


def test_invalid_utf8_rejected():
    with pytest.raises(RoastDataError, match='UTF-8'):
        parse_roast_data(b'\xff\xfe{}')


def test_invalid_json_rejected():
    with pytest.raises(RoastDataError, match='not valid JSON'):
        parse_roast_data(b'{"schema_version": 1,')


def test_deep_nesting_is_our_error_not_recursion_error():
    with pytest.raises(RoastDataError):
        parse_roast_data(b'[' * 100_000)


def test_nan_and_infinity_rejected():
    raw = dumps(good()).replace(b'"chance": 0.1', b'"chance": NaN')
    with pytest.raises(RoastDataError, match='not valid JSON'):
        parse_roast_data(raw)


def test_duplicate_top_level_key_rejected():
    raw = b'{"schema_version": 1, "schema_version": 1}'
    with pytest.raises(RoastDataError, match='duplicate key'):
        parse_roast_data(raw)


def test_duplicate_nested_key_rejected():
    text = dumps(good()).decode().replace(
        '{"name": "one-liner", "instruction": ""}',
        '{"name": "one-liner", "name": "other", "instruction": ""}')
    with pytest.raises(RoastDataError, match='duplicate key'):
        parse_roast_data(text.encode())


def test_top_level_must_be_object():
    with pytest.raises(RoastDataError, match='object'):
        parse_roast_data(b'["a"]')


# -- schema ----------------------------------------------------------------

def test_schema_version_must_be_1():
    bad('schema_version', schema_version=2)
    bad('schema_version', schema_version='1')
    bad('schema_version', schema_version=True)
    bad('schema_version', schema_version=KeyError)


def test_unknown_key_rejected():
    bad('unknown key', surprise='x')


@pytest.mark.parametrize('key', ['system_prompt', 'user_prompt_tail', 'angles', 'formats', 'fallback_jokes'])
def test_required_keys(key):
    bad(key, **{key: KeyError})


@pytest.mark.parametrize('key', ['system_prompt', 'user_prompt_tail', 'avoid_header', 'exemplar_header'])
def test_string_fields_must_be_strings(key):
    bad(key, **{key: 5})


@pytest.mark.parametrize('key', ['angles', 'exemplars', 'banned_phrases', 'fallback_jokes'])
def test_string_lists_reject_non_strings_and_non_lists(key):
    bad(f'{key}: must be a list', **{key: 'just a string'})
    bad('must be a string', **{key: ['ok', 7]})


def test_system_prompt_cannot_be_blank():
    bad('system_prompt: must not be blank', system_prompt='   \n ')


@pytest.mark.parametrize('key', ['angles', 'fallback_jokes'])
def test_required_lists_cannot_be_empty(key):
    bad(key, **{key: []})


@pytest.mark.parametrize('key', ['angles', 'exemplars', 'banned_phrases', 'fallback_jokes'])
def test_list_entries_cannot_be_blank(key):
    bad(key, **{key: ['fine', '   ']})


@pytest.mark.parametrize('key', ['angles', 'exemplars', 'banned_phrases', 'fallback_jokes'])
def test_list_entries_are_single_line(key):
    bad(key, **{key: ['two\nlines']})


@pytest.mark.parametrize('key', ['angles', 'exemplars', 'banned_phrases', 'fallback_jokes'])
def test_list_entries_reject_control_characters(key):
    bad(key, **{key: ['bell\x07']})


def test_system_prompt_rejects_control_characters_but_allows_newlines():
    bad('control', system_prompt=GOOD['system_prompt'] + '\x00')
    parse_roast_data(dumps(good(system_prompt=GOOD['system_prompt'] + '\n\ttail')))


def test_string_size_caps():
    bad('too long', angles=['x' * (roast_data.MAX_ENTRY_CHARS + 1)])
    bad('too long', system_prompt='{angles}{format}{avoid}{exemplars}' + 'x' * roast_data.MAX_PROMPT_CHARS)
    bad('too long', user_prompt_tail='x' * (roast_data.MAX_ENTRY_CHARS + 1))


def test_list_size_caps():
    bad('too many', angles=[f'a{i}' for i in range(roast_data.MAX_ANGLES + 1)])
    bad('too many', exemplars=[f'e{i}' for i in range(roast_data.MAX_EXEMPLARS + 1)])
    bad('too many', banned_phrases=[f'b{i}' for i in range(roast_data.MAX_BANNED + 1)])
    bad('too many', fallback_jokes=[f'j{i}' for i in range(roast_data.MAX_FALLBACK + 1)])
    bad('too many', formats=[{'name': f'f{i}', 'instruction': ''} for i in range(roast_data.MAX_FORMATS + 1)])


def test_duplicate_angles_and_jokes_rejected():
    bad('duplicate entry', angles=['same', 'same'])
    bad('duplicate entry', fallback_jokes=['same', 'same'])


@pytest.mark.parametrize('placeholder', ['{angles}', '{format}', '{avoid}', '{exemplars}'])
def test_system_prompt_needs_each_placeholder_exactly_once(placeholder):
    prompt = GOOD['system_prompt']
    bad(re_escape(placeholder), system_prompt=prompt.replace(placeholder, ''))
    bad(re_escape(placeholder), system_prompt=prompt + placeholder)


def re_escape(text):
    import re
    return re.escape(text)


def test_max_length_bounds():
    bad('max_length', max_length=5)
    bad('max_length', max_length=5000)
    bad('max_length', max_length=True)
    bad('max_length', max_length=100.5)


def test_formats_validation():
    bad('formats: must not be empty', formats=[])
    bad('formats: must be a list', formats='one-liner')
    bad('must be an object', formats=['one-liner'])
    bad('instruction: too long', formats=[{'name': 'x', 'instruction': 'i' * (roast_data.MAX_INSTRUCTION_CHARS + 1)}])
    bad('instruction: contains control', formats=[{'name': 'x', 'instruction': 'bell\x07'}])
    bad('name', formats=[{'instruction': ''}])
    bad('instruction', formats=[{'name': 'x'}])
    bad('instruction', formats=[{'name': 'x', 'instruction': 3}])
    bad('name', formats=[{'name': ' ', 'instruction': ''}])
    bad('duplicate format', formats=[{'name': 'x', 'instruction': ''}, {'name': 'x', 'instruction': ''}])
    bad('unknown key', formats=[{'name': 'x', 'instruction': '', 'extra': 1}])
    bad('max_length', formats=[{'name': 'x', 'instruction': '', 'max_length': 'long'}])
    bad('max_length', formats=[{'name': 'x', 'instruction': '', 'max_length': 5}])
    bad('max_length', formats=[{'name': 'x', 'instruction': '', 'max_length': True}])


def test_house_jokes_validation():
    bad('house_jokes: must be an object', house_jokes=['a'])
    bad('chance', house_jokes={'chance': 1.5, 'jokes': ['a']})
    bad('chance', house_jokes={'chance': -0.1, 'jokes': ['a']})
    bad('chance', house_jokes={'chance': True, 'jokes': ['a']})
    bad('chance', house_jokes={'chance': 'x', 'jokes': ['a']})
    bad('jokes', house_jokes={'chance': 0.1, 'jokes': []})
    bad('unknown key', house_jokes={'chance': 0.1, 'jokes': ['a'], 'x': 1})
    bad('house_jokes', house_jokes={'jokes': ['a']})


# -- house style: em dash ---------------------------------------------------

def test_em_dash_is_stripped_from_text_that_can_reach_users():
    doc = good(
        angles=[f'angle {EM_DASH} one', 'plain'],
        fallback_jokes=[f'oops {EM_DASH} bad', f'tight{EM_DASH}dash'],
        exemplars=[f'ex {EM_DASH} ample'],
        formats=[{'name': 'x', 'instruction': f'do {EM_DASH} this'}],
        house_jokes={'chance': 0.1, 'jokes': [f'h {EM_DASH} j']},
    )
    data = parse_roast_data(dumps(doc))
    assert data.angles[0] == 'angle: one'
    assert data.fallback_jokes == ('oops: bad', 'tight,dash')
    assert data.exemplars == ('ex: ample',)
    assert data.formats[0].instruction == 'do: this'
    assert data.house_jokes.jokes == ('h: j',)
    everything = ' '.join(data.angles + data.fallback_jokes + data.exemplars)
    assert EM_DASH not in everything


def test_system_prompt_may_name_the_em_dash_rule():
    prompt = GOOD['system_prompt'] + f' NEVER use an em dash ({EM_DASH}).'
    data = parse_roast_data(dumps(good(system_prompt=prompt)))
    assert EM_DASH in data.system_prompt


# -- rendering -------------------------------------------------------------

def test_render_substitutes_and_drops_empty_placeholder_lines():
    data = parse_roast_data(dumps(good(exemplars=[])))
    out = render_system_prompt(data, angles=['a1', 'a2'], fmt=data.formats[0], avoid=[], exemplars=[])
    assert out == 'You roast {distro}.\n  * a1\n  * a2\nOne roast only.'


def test_render_injects_format_avoid_and_exemplars():
    data = parse_roast_data(dumps(GOOD))
    out = render_system_prompt(data, angles=['a1'], fmt=data.formats[1],
                               avoid=['old roast'], exemplars=['sample a'])
    assert 'Two short sentences.' in out
    assert 'Recent:\n- old roast' in out
    assert 'Style:\n- sample a' in out


def test_render_does_not_reexpand_placeholders_inside_inserted_text():
    data = parse_roast_data(dumps(GOOD))
    out = render_system_prompt(data, angles=['sneaky {avoid} {format}'], fmt=data.formats[1],
                               avoid=['x'], exemplars=[])
    assert '  * sneaky {avoid} {format}' in out


# -- shipped files ---------------------------------------------------------

@pytest.mark.parametrize('distro', ['arch', 'nix'])
def test_shipped_files_validate(distro):
    data = load_roast_data(distro)
    assert len(data.angles) >= 5 and len(data.fallback_jokes) >= 5
    assert [f.name for f in data.formats] == ['one-liner']
    assert '{angles}' in data.system_prompt


def test_shipped_house_jokes_stay_in_the_arch_file():
    arch, nix = load_roast_data('arch'), load_roast_data('nix')
    assert len(arch.house_jokes.jokes) == 3 and 0 < arch.house_jokes.chance <= 0.2
    assert nix.house_jokes is None


def test_shipped_files_are_verbatim_moves():
    # counts of the pre-refactor inline lists (149 Arch, 16 Nix, 10 and 11 angles)
    arch, nix = load_roast_data('arch'), load_roast_data('nix')
    assert (len(arch.fallback_jokes), len(nix.fallback_jokes)) == (149, 16)
    assert (len(arch.angles), len(nix.angles)) == (10, 11)
    assert 'no-shower' in arch.system_prompt and 'no-shower' not in nix.system_prompt


def test_shipped_files_ship_in_the_package_dir():
    assert (roast_data.SHIPPED_DIR / 'arch.json').is_file()
    assert (roast_data.SHIPPED_DIR / 'nix.json').is_file()


def test_unknown_distro_rejected():
    with pytest.raises(RoastDataError, match='distro'):
        load_roast_data('../etc/passwd')


# -- override directory ----------------------------------------------------

def write(path, doc):
    path.write_bytes(doc if isinstance(doc, bytes) else dumps(doc))


def test_valid_override_replaces_the_shipped_file_wholesale(tmp_path):
    write(tmp_path / 'nix.json', good())
    data = load_roast_data('nix', str(tmp_path))
    assert data.fallback_jokes == ('joke one', 'joke two')
    assert data.house_jokes.jokes == ('house one',)       # from the override, not merged
    # arch has no override file: the shipped one is used silently
    assert len(load_roast_data('arch', str(tmp_path)).fallback_jokes) == 149


def test_invalid_override_falls_back_with_a_warning(tmp_path, caplog):
    write(tmp_path / 'nix.json', good(angles=[]))
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        data = load_roast_data('nix', str(tmp_path))
    assert len(data.fallback_jokes) == 16
    assert any('nix.json' in r.message and r.levelno == logging.WARNING for r in caplog.records)


def test_garbage_override_falls_back(tmp_path, caplog):
    write(tmp_path / 'arch.json', b'\xff\xff not json')
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        assert len(load_roast_data('arch', str(tmp_path)).fallback_jokes) == 149
    assert caplog.records


def test_oversize_override_falls_back_without_reading_it_all(tmp_path, caplog):
    write(tmp_path / 'arch.json', b' ' * (MAX_FILE_BYTES + 10))
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        assert len(load_roast_data('arch', str(tmp_path)).fallback_jokes) == 149
    assert 'too large' in caplog.text


def test_symlinked_override_is_refused(tmp_path, caplog):
    real = tmp_path / 'real.json'
    write(real, good())
    link_dir = tmp_path / 'ov'
    link_dir.mkdir()
    os.symlink(real, link_dir / 'nix.json')
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        data = load_roast_data('nix', str(link_dir))
    assert len(data.fallback_jokes) == 16
    assert caplog.records


def test_fifo_override_does_not_hang(tmp_path, caplog):
    os.mkfifo(tmp_path / 'nix.json')
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        data = load_roast_data('nix', str(tmp_path))
    assert len(data.fallback_jokes) == 16
    assert 'not a regular file' in caplog.text


def test_directory_in_place_of_file_falls_back(tmp_path, caplog):
    (tmp_path / 'nix.json').mkdir()
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        assert len(load_roast_data('nix', str(tmp_path)).fallback_jokes) == 16
    assert 'not a regular file' in caplog.text


def test_missing_override_dir_falls_back_with_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        data = load_roast_data('nix', str(tmp_path / 'nope'))
    assert len(data.fallback_jokes) == 16
    assert caplog.records


def test_override_warning_does_not_echo_file_contents(tmp_path, caplog):
    secret = 'SUPERSECRETVALUE'
    write(tmp_path / 'nix.json', good(angles=[secret, secret]))
    with caplog.at_level(logging.WARNING, logger='ai.features.roast_loader'):
        load_roast_data('nix', str(tmp_path))
    assert secret not in caplog.text


def test_shipped_file_that_is_invalid_raises(monkeypatch, tmp_path):
    write(tmp_path / 'arch.json', good(angles=[]))
    monkeypatch.setattr(roast_data, 'SHIPPED_DIR', tmp_path)
    with pytest.raises(RoastDataError):
        load_roast_data('arch')


@pytest.mark.parametrize('distro', ['arch', 'nix'])
def test_shipped_files_carry_no_em_dash_outside_the_system_prompt(distro):
    raw = json.loads((roast_data.SHIPPED_DIR / f'{distro}.json').read_text(encoding='utf-8'))
    raw.pop('system_prompt')
    assert EM_DASH not in json.dumps(raw, ensure_ascii=False)
