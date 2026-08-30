# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for utils/logging_setup.py.

Logging is shared by six entry points, so the failure modes worth pinning
are the ones that are invisible until you read a week of logs: duplicated
records, a level that silently ignores the environment, and a file handler
that grows without bound.
"""

import logging
import logging.handlers

import pytest

from utils.logging_setup import configure_logging, describe_logging


@pytest.fixture(autouse=True)
def restore_root_logging():
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved[0]:
        root.addHandler(handler)
    root.setLevel(saved[1])


def _owned(root):
    return [h for h in root.handlers if getattr(h, '_penguin_logging', False)]


def test_configures_stdout_at_info_by_default(monkeypatch):
    monkeypatch.delenv('LOG_LEVEL', raising=False)
    monkeypatch.delenv('LOG_FILE', raising=False)
    logger = configure_logging('bot')

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert len(_owned(root)) == 1
    assert logger.name == 'bot'


def test_repeat_calls_do_not_duplicate_handlers(monkeypatch):
    monkeypatch.delenv('LOG_FILE', raising=False)
    configure_logging('bot')
    configure_logging('bot')
    configure_logging('news_runner')
    # Every record would otherwise be emitted once per call — which is the
    # bug that made discord.py's own handler double the bot's output.
    assert len(_owned(logging.getLogger())) == 1


def test_level_comes_from_environment(monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'debug')
    configure_logging('bot')
    assert logging.getLogger().level == logging.DEBUG


def test_nonsense_level_falls_back_to_info(monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'chatty')
    configure_logging('bot')
    assert logging.getLogger().level == logging.INFO


def test_explicit_level_beats_environment(monkeypatch):
    monkeypatch.setenv('LOG_LEVEL', 'WARNING')
    configure_logging('news_runner', level=logging.DEBUG)
    assert logging.getLogger().level == logging.DEBUG


def test_noisy_third_party_loggers_are_quieted(monkeypatch):
    monkeypatch.delenv('LOG_FILE', raising=False)
    configure_logging('bot')
    # httpx logs a line per request; two model calls per scanned message
    # buried the moderation records underneath them.
    assert logging.getLogger('httpx').level == logging.WARNING
    assert logging.getLogger('discord.http').level == logging.WARNING


def test_log_file_gets_a_rotating_handler(monkeypatch, tmp_path):
    target = tmp_path / 'logs' / 'bot.log'
    monkeypatch.setenv('LOG_FILE', str(target))
    monkeypatch.setenv('LOG_MAX_BYTES', '2048')
    monkeypatch.setenv('LOG_BACKUPS', '3')
    configure_logging('bot')

    handlers = [h for h in _owned(logging.getLogger())
                if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 2048
    assert handlers[0].backupCount == 3
    assert target.parent.exists()
    # stdout logging survives alongside it, so `docker logs` is never empty
    assert len(_owned(logging.getLogger())) == 2


def test_rotation_actually_caps_the_file(monkeypatch, tmp_path):
    target = tmp_path / 'bot.log'
    monkeypatch.setenv('LOG_FILE', str(target))
    monkeypatch.setenv('LOG_MAX_BYTES', '1024')
    monkeypatch.setenv('LOG_BACKUPS', '2')
    logger = configure_logging('bot')

    for i in range(200):
        logger.info('a padded line to force rotation %03d %s', i, 'x' * 60)

    rotated = sorted(p.name for p in tmp_path.iterdir())
    assert rotated == ['bot.log', 'bot.log.1', 'bot.log.2']
    for path in tmp_path.iterdir():
        assert path.stat().st_size < 4096, path


def test_unwritable_log_file_does_not_stop_startup(monkeypatch, tmp_path):
    blocker = tmp_path / 'not-a-dir'
    blocker.write_text('')
    monkeypatch.setenv('LOG_FILE', str(blocker / 'bot.log'))
    logger = configure_logging('bot')

    assert logger.name == 'bot'
    assert len(_owned(logging.getLogger())) == 1  # stdout only, still running


def test_describe_logging_names_the_sinks(monkeypatch, tmp_path):
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'bot.log'))
    monkeypatch.setenv('LOG_MAX_BYTES', str(5 * 1024 * 1024))
    monkeypatch.setenv('LOG_BACKUPS', '4')
    configure_logging('bot')

    summary = describe_logging()
    assert 'level=INFO' in summary
    assert 'stdout' in summary
    assert 'rotate 5MB x4' in summary
