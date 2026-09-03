# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for utils/config.py.

Every test passes an explicit `env` mapping, so nothing here reads the real
environment or a .env file. The properties worth pinning: a good env loads
into typed values with the documented defaults, a bad env produces ONE
error that names every problem, and a secret never leaks into an error
message or a repr.
"""

import logging
from pathlib import Path

import pytest

from utils.config import (
    NEWS_CATEGORIES,
    Config,
    ConfigError,
    Secret,
    describe_config,
    load_config,
    load_logging_config,
    load_metrics_config,
    load_paths_config,
)

TOKEN = 'MTIzNDU2Nzg5.fake-token-value.not-real-but-secret'
SNOWFLAKE = '123456789012345678'
OTHER_SNOWFLAKE = '234567890123456789'

MINIMAL = {'DISCORD_BOT_TOKEN': TOKEN}


def _load(**overrides) -> Config:
    env = dict(MINIMAL)
    env.update(overrides)
    return load_config(env)


def _problems(**overrides) -> str:
    env = dict(MINIMAL)
    env.update(overrides)
    with pytest.raises(ConfigError) as excinfo:
        load_config(env)
    return str(excinfo.value)


# ---------------------------------------------------------------------------
# Happy path and defaults
# ---------------------------------------------------------------------------

def test_minimal_env_loads_with_features_off():
    config = _load()

    assert config.discord.bot_token.reveal() == TOKEN
    assert config.discord.owner_id is None
    assert config.logging.level == logging.INFO
    assert config.logging.file is None
    assert config.metrics.enabled is False
    assert config.metrics.port == 9200
    assert config.ai.enabled is False
    assert config.moderation.enabled is False
    assert config.moderation.dry_run is True
    assert config.greeter.enabled is False
    assert config.helper.enabled is False
    assert config.role_picker.enabled is False
    assert config.profile_screen.enabled is False
    # The skid detector is the one feature that ships on by default.
    assert config.skid_detector.enabled is True
    assert all(config.news.channel_id(c) is None for c in NEWS_CATEGORIES)
    assert config.news.auto_post is True


def test_full_env_round_trips_every_parser():
    config = _load(
        DISCORD_OWNER_ID=SNOWFLAKE,
        LOG_LEVEL='debug',
        LOG_FILE='/var/log/penguin/bot.log',
        LOG_MAX_BYTES='2048',
        LOG_BACKUPS='3',
        DATA_DIR='/srv/penguin',
        METRICS_ENABLED='yes',
        METRICS_PORT='9300',
        NEWS_TECH_CHANNEL_ID=SNOWFLAKE,
        NEWS_KEV_CHANNEL_ID=OTHER_SNOWFLAKE,
        NEWS_AUTO_POST='false',
        XKCD_POST_CHANNEL_ID=SNOWFLAKE,
        XKCD_POLL_INTERVAL_MINUTES='15',
        AI_ENABLED='1',
        OLLAMA_HOST='ollama.lan',
        OLLAMA_PORT='11500',
        AI_DEFAULT_TEMPERATURE='0.4',
        AI_ROASTING_ENABLED='true',
        AI_ROASTING_MODEL='gemma4:12b',
        MOD_ENABLED='true',
        MOD_CHANNELS=f'{SNOWFLAKE}, {OTHER_SNOWFLAKE}',
        MOD_IGNORED_CATEGORIES='Spam, violence',
        MOD_MIN_CONFIDENCE='0.6',
        MOD_TIMEOUT_MINUTES='15',
        MOD_PROFILE='cybersecurity,hobbyist',
        WELCOME_ENABLED='on',
        WELCOME_VERIFY_DAILY_AT='9:30',
        WELCOME_TIMEZONE='America/New_York',
        HELPER_TIERS='new,member',
        PROFILE_SCREEN_PROTECTED_NAMES='chiefgyk3d, penguin overlord',
        SKID_FIRE_CHANCE='0.5',
    )

    assert config.discord.owner_id == int(SNOWFLAKE)
    assert config.logging.level == logging.DEBUG
    assert config.logging.file == '/var/log/penguin/bot.log'
    assert config.logging.max_bytes == 2048
    assert config.logging.backups == 3
    assert config.paths.data_dir == Path('/srv/penguin')
    assert config.paths.database_path == Path('/srv/penguin/penguin_overlord.db')
    assert config.metrics.enabled is True
    assert config.metrics.port == 9300
    assert config.news.tech == int(SNOWFLAKE)
    assert config.news.channel_id('kev') == int(OTHER_SNOWFLAKE)
    assert config.news.auto_post is False
    assert config.posting.xkcd_channel_id == int(SNOWFLAKE)
    assert config.posting.xkcd_poll_interval_minutes == 15
    assert config.ai.enabled is True
    assert config.ai.ollama_host == 'http://ollama.lan:11500'
    assert config.ai.default_temperature == 0.4
    assert config.ai.features['roasting'].enabled is True
    assert config.ai.features['roasting'].model == 'gemma4:12b'
    assert config.ai.features['news'].enabled is False
    assert config.moderation.enabled is True
    assert config.moderation.channels == frozenset({int(SNOWFLAKE), int(OTHER_SNOWFLAKE)})
    assert config.moderation.ignored_categories == frozenset({'spam', 'violence'})
    assert config.moderation.min_confidence == 0.6
    assert config.moderation.timeout_minutes == 15
    assert config.moderation.profile == ('cybersecurity', 'hobbyist')
    assert config.greeter.enabled is True
    assert config.greeter.verify_daily_at == (9, 30)
    assert config.greeter.timezone == 'America/New_York'
    assert config.helper.tiers == frozenset({'new', 'member'})
    assert config.profile_screen.protected_names == ('chiefgyk3d', 'penguin overlord')
    assert config.skid_detector.fire_chance == 0.5


def test_config_is_frozen():
    config = _load()
    with pytest.raises(AttributeError):
        config.metrics = None  # type: ignore[misc]
    with pytest.raises(AttributeError):
        config.metrics.port = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Individual parsers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw', ['true', 'True', ' TRUE ', '1', 'yes', 'on'])
def test_bool_truthy_spellings(raw):
    assert _load(METRICS_ENABLED=raw).metrics.enabled is True


@pytest.mark.parametrize('raw', ['false', '0', 'no', 'off', ''])
def test_bool_falsy_spellings(raw):
    assert _load(METRICS_ENABLED=raw).metrics.enabled is False


def test_bool_rejects_nonsense():
    message = _problems(METRICS_ENABLED='maybe')
    assert 'METRICS_ENABLED' in message
    assert 'true/false' in message


def test_int_rejects_non_numeric():
    message = _problems(METRICS_PORT='nine thousand')
    assert 'METRICS_PORT' in message
    assert 'integer' in message


def test_int_accepts_surrounding_whitespace():
    assert _load(METRICS_PORT=' 9201 ').metrics.port == 9201


def test_float_rejects_non_numeric():
    message = _problems(MOD_MIN_CONFIDENCE='high')
    assert 'MOD_MIN_CONFIDENCE' in message
    assert 'number' in message


def test_comma_list_strips_blanks_and_lowercases():
    config = _load(MOD_RECLAIMED_TIERS=' Veteran,, trusted ,')
    assert config.moderation.reclaimed_tiers == frozenset({'veteran', 'trusted'})


def test_empty_string_means_unset():
    # .env files routinely carry `VAR=` for every optional key; that must
    # read as "not configured", never as a malformed value.
    config = _load(NEWS_TECH_CHANNEL_ID='', MOD_ALERT_CHANNEL_ID='', LOG_MAX_BYTES='')
    assert config.news.tech is None
    assert config.moderation.alert_channel_id is None
    assert config.logging.max_bytes == 10 * 1024 * 1024


def test_example_placeholder_means_unset():
    # bot.py has always ignored the `your_..._here` values from .env.example
    # for the owner id; the loader keeps that so a half-filled example file
    # reports "not set" rather than "malformed".
    config = _load(DISCORD_OWNER_ID='your_discord_user_id_here')
    assert config.discord.owner_id is None


def test_time_parses_hh_mm():
    config = _load(WELCOME_JOIN_DAILY_AT='23:05')
    assert config.greeter.join_daily_at == (23, 5)


@pytest.mark.parametrize('raw', ['24:00', '9:60', 'noon', '9', '09:5'])
def test_time_rejects_out_of_range_and_wrong_shape(raw):
    message = _problems(WELCOME_JOIN_DAILY_AT=raw)
    assert 'WELCOME_JOIN_DAILY_AT' in message
    assert 'HH:MM' in message


def test_timezone_must_be_iana():
    message = _problems(WELCOME_TIMEZONE='Eastern')
    assert 'WELCOME_TIMEZONE' in message
    assert 'IANA' in message


def test_log_level_must_be_a_known_name():
    message = _problems(LOG_LEVEL='chatty')
    assert 'LOG_LEVEL' in message
    assert 'DEBUG' in message


def test_discord_token_alias_is_accepted():
    # The runners historically fell back to DISCORD_TOKEN.
    config = load_config({'DISCORD_TOKEN': TOKEN})
    assert config.discord.bot_token.reveal() == TOKEN


def test_ollama_host_with_scheme_is_kept_verbatim():
    config = _load(AI_DEFAULT_OLLAMA_HOST='https://ollama.example:8443')
    assert config.ai.ollama_host == 'https://ollama.example:8443'


def test_ollama_host_defaults_to_localhost():
    assert _load().ai.ollama_host == 'http://localhost:11434'


# ---------------------------------------------------------------------------
# Snowflakes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw', ['12345678901234567', '123456789012345678', '12345678901234567890'])
def test_snowflake_accepts_17_to_20_digits(raw):
    assert _load(NEWS_CVE_CHANNEL_ID=raw).news.cve == int(raw)


def test_snowflake_accepts_channel_mention_wrapper():
    # The xkcd/comic runners tolerated `<#id>` and quoted ids; keep that.
    assert _load(XKCD_POST_CHANNEL_ID=f'<#{SNOWFLAKE}>').posting.xkcd_channel_id == int(SNOWFLAKE)
    assert _load(COMIC_POST_CHANNEL_ID=f'"{SNOWFLAKE}"').posting.comic_channel_id == int(SNOWFLAKE)


@pytest.mark.parametrize('raw', ['1234', '1234567890123456', '123456789012345678901', 'general', '12345678901234567x'])
def test_snowflake_rejects_wrong_shapes(raw):
    message = _problems(NEWS_GAMING_CHANNEL_ID=raw)
    assert 'NEWS_GAMING_CHANNEL_ID' in message
    assert '17 to 20 digits' in message


def test_snowflake_list_rejects_one_bad_entry():
    message = _problems(MOD_TRUSTED_ROLES=f'{SNOWFLAKE},nope')
    assert 'MOD_TRUSTED_ROLES' in message
    assert 'nope' in message


def test_owner_id_is_a_snowflake():
    message = _problems(DISCORD_OWNER_ID='42')
    assert 'DISCORD_OWNER_ID' in message


# ---------------------------------------------------------------------------
# Aggregated errors
# ---------------------------------------------------------------------------

def test_missing_token_is_the_one_required_variable():
    with pytest.raises(ConfigError) as excinfo:
        load_config({})
    message = str(excinfo.value)
    assert 'DISCORD_BOT_TOKEN' in message
    assert 'required' in message
    assert excinfo.value.problems == [excinfo.value.problems[0]]  # exactly one


def test_every_problem_is_reported_in_one_error():
    with pytest.raises(ConfigError) as excinfo:
        load_config({
            'DISCORD_OWNER_ID': 'me',
            'METRICS_PORT': 'x',
            'NEWS_TECH_CHANNEL_ID': '12',
            'WELCOME_JOIN_DAILY_AT': '25:00',
            'LOG_BACKUPS': 'many',
        })
    error = excinfo.value
    names = [p.split(':', 1)[0] for p in error.problems]
    # The missing token plus the five malformed values, each exactly once.
    assert sorted(names) == sorted([
        'DISCORD_BOT_TOKEN', 'DISCORD_OWNER_ID', 'METRICS_PORT',
        'NEWS_TECH_CHANNEL_ID', 'WELCOME_JOIN_DAILY_AT', 'LOG_BACKUPS',
    ])
    message = str(error)
    assert message.startswith('6 configuration problem')
    for name in names:
        assert message.count(name) == 1


def test_problem_lines_include_the_offending_value_for_non_secrets():
    message = _problems(NEWS_TECH_CHANNEL_ID='general')
    assert "'general'" in message


# ---------------------------------------------------------------------------
# Secrets never leak
# ---------------------------------------------------------------------------

def test_secret_repr_and_str_are_redacted():
    secret = Secret(TOKEN)
    assert TOKEN not in repr(secret)
    assert TOKEN not in str(secret)
    assert TOKEN not in f'{secret}'
    assert secret.reveal() == TOKEN


def test_secret_does_not_appear_in_config_repr():
    config = _load(GEMINI_API_KEY='AIza-fake-gemini-key')
    text = repr(config)
    assert TOKEN not in text
    assert 'AIza-fake-gemini-key' not in text
    assert config.ai.gemini_api_key.reveal() == 'AIza-fake-gemini-key'


def test_secret_does_not_appear_in_error_text():
    # A token that is set but every other secret-shaped value malformed:
    # the error must name the variables and never echo any secret.
    with pytest.raises(ConfigError) as excinfo:
        load_config({'DISCORD_BOT_TOKEN': TOKEN, 'METRICS_PORT': TOKEN + '-as-port'})
    assert TOKEN not in str(excinfo.value)
    assert TOKEN not in repr(excinfo.value)


def test_secret_does_not_appear_in_describe():
    text = describe_config(_load(GEMINI_API_KEY='AIza-fake-gemini-key', NEWS_TECH_CHANNEL_ID=SNOWFLAKE))
    assert TOKEN not in text
    assert 'AIza-fake-gemini-key' not in text
    assert SNOWFLAKE not in text  # ids are not secret, but the summary is counts only
    assert 'news' in text


# ---------------------------------------------------------------------------
# Secrets manager integration
# ---------------------------------------------------------------------------

def test_secret_lookup_wins_over_env_and_is_asked_per_platform():
    asked = []

    def fake_secrets(platform, key):
        asked.append((platform, key))
        if (platform, key) == ('DISCORD', 'BOT_TOKEN'):
            return 'from-doppler'
        if (platform, key) == ('NEWS', 'TECH_CHANNEL_ID'):
            return SNOWFLAKE
        return None

    config = load_config({'DISCORD_BOT_TOKEN': 'from-env', 'NEWS_TECH_CHANNEL_ID': ''}, secrets=fake_secrets)
    assert config.discord.bot_token.reveal() == 'from-doppler'
    assert config.news.tech == int(SNOWFLAKE)
    assert ('DISCORD', 'BOT_TOKEN') in asked
    assert ('MOD', 'ALERT_CHANNEL_ID') in asked
    # Plain settings (logging, metrics, paths) never hit the secrets manager.
    assert not any(platform in ('LOG', 'METRICS', 'DATA') for platform, _ in asked)


def test_env_mapping_never_consults_secrets_by_default(monkeypatch):
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'real-env-must-not-be-read')
    with pytest.raises(ConfigError):
        load_config({})


# ---------------------------------------------------------------------------
# Lenient section loaders for the pre-config bootstrap
# ---------------------------------------------------------------------------

def test_logging_section_substitutes_defaults_instead_of_raising():
    settings = load_logging_config({'LOG_LEVEL': 'chatty', 'LOG_MAX_BYTES': 'lots', 'LOG_FILE': '/tmp/x.log'})
    assert settings.level == logging.INFO
    assert settings.max_bytes == 10 * 1024 * 1024
    assert settings.file == '/tmp/x.log'


def test_metrics_section_substitutes_defaults_instead_of_raising():
    settings = load_metrics_config({'METRICS_ENABLED': 'true', 'METRICS_PORT': 'nope'})
    assert settings.enabled is True
    assert settings.port == 9200


def test_paths_section_prefers_data_dir_env(tmp_path):
    settings = load_paths_config({'DATA_DIR': str(tmp_path)})
    assert settings.data_dir == tmp_path
    assert settings.xkcd_state_path == tmp_path / 'xkcd_state.json'
    assert settings.comic_state_path == tmp_path / 'comic_state.json'


def test_state_path_overrides_are_honoured(tmp_path):
    settings = load_paths_config({'DATA_DIR': str(tmp_path), 'XKCD_STATE_PATH': '/elsewhere/x.json'})
    assert settings.xkcd_state_path == Path('/elsewhere/x.json')


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_events_defaults_are_off_and_dry():
    events = _load().events
    assert events.enabled is False and events.dry_run is True
    assert events.channel_id is None and events.review_channel_id is None
    assert events.timezone == 'America/New_York' and events.post_at == (9, 0)
    assert events.reminder_days == (30, 7, 1) and events.digest_enabled is True
    assert events.max_pending_per_member == 3 and events.pending_expire_days == 30


def test_events_enabled_requires_a_channel():
    text = _problems(EVENTS_ENABLED='true')
    assert 'EVENTS_CHANNEL_ID' in text


def test_events_review_channel_falls_back_to_mod_alert_channel():
    events = _load(EVENTS_ENABLED='true', EVENTS_CHANNEL_ID=SNOWFLAKE,
                   MOD_ALERT_CHANNEL_ID=OTHER_SNOWFLAKE).events
    assert events.review_channel_id == int(OTHER_SNOWFLAKE)


def test_events_reminder_days_parse_and_sort_descending():
    events = _load(EVENTS_REMINDER_DAYS='1, 14,7').events
    assert events.reminder_days == (14, 7, 1)
    assert 'EVENTS_REMINDER_DAYS' in _problems(EVENTS_REMINDER_DAYS='soon')
    assert 'EVENTS_REMINDER_DAYS' in _problems(EVENTS_REMINDER_DAYS='0,7')


def test_events_post_at_and_timezone_validate():
    events = _load(EVENTS_POST_AT='18:30', EVENTS_TIMEZONE='Europe/Berlin').events
    assert events.post_at == (18, 30) and events.timezone == 'Europe/Berlin'
    assert 'EVENTS_POST_AT' in _problems(EVENTS_POST_AT='6pm')
    assert 'EVENTS_TIMEZONE' in _problems(EVENTS_TIMEZONE='Mars/Olympus')


def test_describe_config_mentions_events():
    from utils.config import describe_config
    assert 'events=off' in describe_config(_load())
