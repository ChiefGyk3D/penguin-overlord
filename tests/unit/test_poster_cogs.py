# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The three one-shot posters (xkcd, daily comic, solar) take their channel
ids, poll interval and state-file paths from the typed config on the bot.

Every case sets NEWS_AUTO_POST=false so no background loop starts: these
are construction tests, not scheduling tests.
"""

from pathlib import Path

import pytest

from tests.conftest import bot_with_config

CHANNEL = 123456789012345678
OTHER_CHANNEL = 234567890123456789


@pytest.fixture(autouse=True)
def no_autopost(monkeypatch):
    """utils.news_dedupe.autopost_enabled() gates the background loops and
    reads the environment, not the bot. Keep the loops out of these tests."""
    monkeypatch.setenv('NEWS_AUTO_POST', 'false')


def _bot(tmp_path, **env):
    return bot_with_config(NEWS_AUTO_POST='false', DATA_DIR=str(tmp_path), **env)


# -- xkcd_poster -------------------------------------------------------------

def test_xkcd_poster_reads_channel_and_interval_from_config(tmp_path):
    from cogs.xkcd_poster import XKCDPoster
    cog = XKCDPoster(_bot(tmp_path, XKCD_POST_CHANNEL_ID=str(CHANNEL),
                          XKCD_POLL_INTERVAL_MINUTES='7'))
    assert cog.state['channel_id'] == CHANNEL
    assert cog.poll_minutes == 7
    assert cog.state_file == tmp_path / 'xkcd_state.json'


def test_xkcd_poster_honours_an_explicit_state_path(tmp_path):
    from cogs.xkcd_poster import XKCDPoster
    elsewhere = tmp_path / 'nested' / 'x.json'
    cog = XKCDPoster(_bot(tmp_path, XKCD_STATE_PATH=str(elsewhere)))
    assert cog.state_file == elsewhere
    assert cog.state['channel_id'] is None


# -- comics ------------------------------------------------------------------

def test_comics_reads_channel_and_state_path_from_config(tmp_path):
    from cogs.comics import Comics
    cog = Comics(_bot(tmp_path, COMIC_POST_CHANNEL_ID=str(OTHER_CHANNEL)))
    assert cog.state['channel_id'] == OTHER_CHANNEL
    assert cog.state_file == tmp_path / 'comic_state.json'


def test_comics_honours_an_explicit_state_path(tmp_path):
    from cogs.comics import Comics
    elsewhere = tmp_path / 'nested' / 'c.json'
    cog = Comics(_bot(tmp_path, COMIC_STATE_PATH=str(elsewhere)))
    assert cog.state_file == Path(elsewhere)


# -- radiohead (solar report) ------------------------------------------------

def test_solar_poster_reads_channel_from_config(tmp_path):
    from cogs.radiohead import Radiohead
    cog = Radiohead(_bot(tmp_path, SOLAR_POST_CHANNEL_ID=str(CHANNEL)))
    assert cog.state['channel_id'] == CHANNEL


def test_solar_poster_without_a_channel_stays_unset(tmp_path):
    from cogs.radiohead import Radiohead
    cog = Radiohead(_bot(tmp_path))
    assert cog.state['channel_id'] is None
