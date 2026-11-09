# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Narrowed exception handling must still swallow ordinary errors but let
cancellation and interpreter exits (BaseException) propagate."""

import asyncio
import types

import pytest

from cogs.admin import HelpPaginatorView
from cogs.arch_banter import ArchBanter
from cogs.help_categorized import HelpView
from cogs.techquote import PaginatorView
from utils.state import save_json_state


def _message(exc):
    async def edit(**kw):
        raise exc
    return types.SimpleNamespace(edit=edit)


def _make_view(kind):
    if kind == 'admin':
        return HelpPaginatorView([object()])
    if kind == 'help':
        return HelpView()
    return PaginatorView([object()])


@pytest.mark.parametrize('kind', ['admin', 'help', 'techquote'])
async def test_on_timeout_swallows_ordinary_errors(kind):
    view = _make_view(kind)
    view.message = _message(RuntimeError('message deleted'))
    await view.on_timeout()          # must not raise


@pytest.mark.parametrize('kind', ['admin', 'help', 'techquote'])
async def test_on_timeout_lets_cancellation_through(kind):
    view = _make_view(kind)
    view.message = _message(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await view.on_timeout()


def _leaderboard_cog(monkeypatch, tmp_path, fetch_user):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ARCH_BANTER_LLM', 'false')
    cog = ArchBanter(bot=types.SimpleNamespace(fetch_user=fetch_user))
    cog.stats['users'] = {'5': {'username': 'fallbackname', 'roast_count': 3}}
    return cog


async def _run_leaderboard(cog):
    sent = []

    async def send(**kw):
        sent.append(kw['embed'])
    ctx = types.SimpleNamespace(send=send)
    await ArchBanter.arch_leaderboard.callback(cog, ctx)
    return sent


async def test_leaderboard_falls_back_to_username_on_lookup_error(monkeypatch, tmp_path):
    async def fetch_user(_):
        raise RuntimeError('unknown user')
    sent = await _run_leaderboard(_leaderboard_cog(monkeypatch, tmp_path, fetch_user))
    assert 'fallbackname' in sent[0].fields[0].value


async def test_leaderboard_lets_cancellation_through(monkeypatch, tmp_path):
    async def fetch_user(_):
        raise asyncio.CancelledError()
    cog = _leaderboard_cog(monkeypatch, tmp_path, fetch_user)
    with pytest.raises(asyncio.CancelledError):
        await _run_leaderboard(cog)


def test_save_cleans_temp_file_and_reraises_on_interrupt(monkeypatch, tmp_path):
    target = tmp_path / 'state.json'

    def boom(*a, **kw):
        raise KeyboardInterrupt()
    monkeypatch.setattr('utils.state.os.replace', boom)
    with pytest.raises(KeyboardInterrupt):
        save_json_state(target, {'v': 1})
    assert list(tmp_path.iterdir()) == []
