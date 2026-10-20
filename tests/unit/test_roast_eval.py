# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""scripts/eval-roasts: metric maths and the run loop, with a fake generator.
Never touches a real manager."""

import importlib.util
import json
import random
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'eval-roasts' / 'eval_roasts.py'
EM_DASH = '—'


@pytest.fixture(scope='module')
def ev():
    spec = importlib.util.spec_from_file_location('eval_roasts', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rec(ev, distro, text, angles=(), fmt='one-liner'):
    return ev.Record(distro=distro, text=text, angles=list(angles), format=fmt, attempts=1, reasons=[])


def test_distinct_ratio(ev):
    records = [rec(ev, 'arch', 'Same line 🔥'), rec(ev, 'arch', 'same   line!! 🔥'),
               rec(ev, 'arch', 'other words entirely 🔥')]
    m = ev.compute_metrics(records)['arch']
    assert m['generated'] == 3 and m['distinct'] == 2
    assert m['distinct_ratio'] == pytest.approx(2 / 3)


def test_mean_pairwise_jaccard(ev):
    records = [rec(ev, 'arch', 'a b c 🔥'), rec(ev, 'arch', 'a b c 🔥'), rec(ev, 'arch', 'x y z 🔥')]
    m = ev.compute_metrics(records)['arch']
    # pairs: (1,2)=1.0 (1,3)=0 (2,3)=0
    assert m['mean_pairwise_jaccard'] == pytest.approx(1 / 3)


def test_single_roast_has_zero_pairwise(ev):
    m = ev.compute_metrics([rec(ev, 'nix', 'only one 🔥')])['nix']
    assert m['mean_pairwise_jaccard'] == 0.0 and m['distinct_ratio'] == 1.0


def test_top_repeated_trigrams(ev):
    records = [rec(ev, 'arch', 'btw i use arch 🔥'), rec(ev, 'arch', 'btw i use nix 🔥'),
               rec(ev, 'arch', 'something unrelated happens here 🔥')]
    top = ev.compute_metrics(records)['arch']['top_3grams']
    assert top[0] == ['btw i use', 2]
    assert all(count >= 2 for _, count in top)


def test_angle_and_format_usage(ev):
    records = [rec(ev, 'arch', 'one 🔥', ['A', 'B'], 'one-liner'),
               rec(ev, 'arch', 'two 🔥', ['A', 'C'], 'two-parter')]
    m = ev.compute_metrics(records)['arch']
    assert m['angle_usage'] == {'A': 2, 'B': 1, 'C': 1}
    assert m['format_usage'] == {'one-liner': 1, 'two-parter': 1}


def test_violations(ev):
    records = [rec(ev, 'arch', f'dash {EM_DASH} here 🔥'), rec(ev, 'arch', 'no emoji'),
               rec(ev, 'arch', 'two 🔥 emoji 🌱'), rec(ev, 'arch', 'perfect 🔥')]
    m = ev.compute_metrics(records)['arch']
    assert m['em_dash_violations'] == 1
    assert m['emoji_violations'] == 2
    assert m['emoji_histogram'] == {'0': 1, '1': 2, '2': 1}


def test_failures_are_counted_not_averaged_in(ev):
    records = [rec(ev, 'arch', 'fine words 🔥'), ev.Record('arch', None, [], 'one-liner', 2, ['duplicate', 'duplicate'])]
    m = ev.compute_metrics(records)['arch']
    assert m['requested'] == 2 and m['generated'] == 1 and m['failed'] == 1
    assert m['retries'] == 1 and m['rejections'] == {'duplicate': 2}


def test_empty_distro_does_not_divide_by_zero(ev):
    m = ev.compute_metrics([ev.Record('arch', None, [], 'one-liner', 1, [])])['arch']
    assert m['generated'] == 0 and m['distinct_ratio'] == 0.0


async def test_run_eval_uses_the_injected_generator(ev):
    seen = []

    async def fake_generate(distro, message, username):
        seen.append((distro, message))
        n = len(seen)
        return ev.Record(distro, f'roast number {n} unique{n} 🔥', ['A'], 'one-liner', 1, [])

    records = await ev.run_eval(fake_generate, distros=['arch', 'nix'], n=3, messages=['hello there'])
    assert len(records) == 6 and len(seen) == 6
    assert {d for d, _ in seen} == {'arch', 'nix'}


def test_write_report_json(ev, tmp_path):
    records = [rec(ev, 'arch', 'hello world friend 🔥', ['A'])]
    out = tmp_path / 'sub' / 'report.json'
    ev.write_report(out, records, meta={'n': 1})
    doc = json.loads(out.read_text())
    assert doc['meta'] == {'n': 1}
    assert doc['metrics']['arch']['generated'] == 1
    assert doc['roasts'][0]['text'] == 'hello world friend 🔥'


def test_cli_refuses_to_run_without_the_live_flag(ev, tmp_path, capsys):
    code = ev.main(['--out', str(tmp_path / 'r.json')])
    assert code == 2
    assert 'live' in capsys.readouterr().err.lower()
    assert not (tmp_path / 'r.json').exists()


def test_cli_requires_an_out_path(ev):
    with pytest.raises(SystemExit):
        ev.main(['--live'])


async def test_make_generator_drives_the_real_roaster_with_a_fake_manager(ev):
    """The glue between the roaster and the eval loop, hermetic."""
    from ai.features.arch_roaster import RoastSettings

    class Manager:
        def __init__(self):
            self.n = 0

        async def generate(self, **kw):
            self.n += 1
            return f'distinct reply {self.n} token{self.n} 🔥'

    gen = ev.make_generator(Manager(), settings=RoastSettings(), rng=random.Random(3), data_dir=None)
    records = await ev.run_eval(gen, distros=['arch', 'nix'], n=4, messages=['i use arch btw'])
    assert len(records) == 8
    assert all(r.text and r.angles for r in records)
    metrics = ev.compute_metrics(records)
    assert metrics['arch']['generated'] == 4 and metrics['nix']['generated'] == 4
