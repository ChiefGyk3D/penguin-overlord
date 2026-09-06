# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Typed configuration, loaded and validated once at startup.

Before this module every feature read its own `os.getenv` calls, so a typo
in one channel id surfaced hours later as a silent no-post, and a missing
token produced a different error in each of the six entry points. Now
`load_config()` reads the whole environment in one pass, parses each value
into its real type, and raises a single `ConfigError` that lists every
missing or malformed variable together with what was expected.

Design rules:

- Stdlib only (dataclasses), no pydantic: this module is a prerequisite
  for the repo split and the Kubernetes deployment, and it must import
  cleanly in every process, runners included.
- `env` is a parameter. Tests pass a plain dict and never touch the real
  environment or a .env file.
- Anything with a secrets-manager platform (DISCORD_*, NEWS_*, MOD_*,
  WELCOME_*, ...) is resolved through `utils.secrets.get_secret`, exactly
  as the cogs do today, so Doppler/AWS/Vault keep overriding .env.
- Secret values are wrapped in `Secret`, which redacts itself in repr and
  str. Error messages name the variable and the expected shape; they only
  echo the offending value for non-secret variables, and truncated.
- Optional features default OFF. The one required variable is the bot
  token.

The section loaders (`load_logging_config`, `load_metrics_config`,
`load_paths_config`) exist for the few module-level reads that must happen
before `load_config()` can run (logging has to exist to report the
config error; metrics and the runners' DATA_DIR are import-time constants).
They substitute defaults for anything malformed and never raise; the same
malformed value is then reported by `load_config()` at startup.

Adding a variable: give its section dataclass a typed field with a
default, read it in that section's `_load_*` function with the matching
`_Reader` method, document it in docs/reference/CONFIGURATION.md and
.env.example, and add a line to tests/unit/test_config.py.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

NEWS_CATEGORIES = (
    'cybersecurity', 'tech', 'gaming', 'apple_google', 'cve', 'kev',
    'us_legislation', 'eu_legislation', 'uk_legislation', 'general_news',
    'vendor_alerts',
)

# Feature names ai/config.py knows about; each gets AI_<FEATURE>_* overrides.
AI_FEATURES = ('roasting', 'moderation', 'news', 'cve', 'legislation')

# Variables whose prefix is a get_secret() platform. Everything else is
# plain environment. Mirrors the per-cog _env() helpers, which consult the
# secrets manager for exactly these prefixes.
_SECRET_PLATFORMS = ('DISCORD', 'NEWS', 'XKCD', 'COMIC', 'SOLAR', 'MOD',
                     'HELPER', 'WELCOME', 'AI', 'GEMINI')

DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUPS = 5

_SNOWFLAKE_RE = re.compile(r'\d{17,20}')
_TIME_RE = re.compile(r'^(\d{1,2}):(\d{2})$')
_TRUE = ('1', 'true', 'yes', 'on')
_FALSE = ('0', 'false', 'no', 'off')

SecretLookup = Callable[[str, str], Optional[str]]


# ---------------------------------------------------------------------------
# Secret wrapper and error type
# ---------------------------------------------------------------------------

class Secret:
    """A string that will not print itself. Call `.reveal()` to use it."""

    __slots__ = ('_value',)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return 'Secret(***)'

    __str__ = __repr__


class ConfigError(ValueError):
    """Raised by load_config() with every problem found, not just the first."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        count = len(self.problems)
        noun = 'problem' if count == 1 else 'problems'
        lines = [f'{count} configuration {noun}:']
        lines.extend(f'  - {p}' for p in self.problems)
        super().__init__('\n'.join(lines))


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscordConfig:
    bot_token: Secret = field(repr=False, default=Secret(''))
    owner_id: Optional[int] = None


@dataclass(frozen=True)
class LoggingConfig:
    level: int = logging.INFO
    file: Optional[str] = None
    max_bytes: int = DEFAULT_LOG_MAX_BYTES
    backups: int = DEFAULT_LOG_BACKUPS


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path = Path('data')
    database_path: Path = Path('data/penguin_overlord.db')
    xkcd_state_path: Path = Path('data/xkcd_state.json')
    comic_state_path: Path = Path('data/comic_state.json')


@dataclass(frozen=True)
class NewsConfig:
    cybersecurity: Optional[int] = None
    tech: Optional[int] = None
    gaming: Optional[int] = None
    apple_google: Optional[int] = None
    cve: Optional[int] = None
    kev: Optional[int] = None
    us_legislation: Optional[int] = None
    eu_legislation: Optional[int] = None
    uk_legislation: Optional[int] = None
    general_news: Optional[int] = None
    vendor_alerts: Optional[int] = None
    # NEWS_AUTO_POST: in-bot posting loops; off where systemd timers own it.
    auto_post: bool = True

    def channel_id(self, category: str) -> Optional[int]:
        if category not in NEWS_CATEGORIES:
            raise KeyError(f'unknown news category: {category}')
        return getattr(self, category)

    def configured(self) -> int:
        return sum(1 for c in NEWS_CATEGORIES if getattr(self, c) is not None)


@dataclass(frozen=True)
class PostingConfig:
    """The three one-shot posters (xkcd, daily comic, solar report)."""
    xkcd_channel_id: Optional[int] = None
    xkcd_poll_interval_minutes: int = 30
    comic_channel_id: Optional[int] = None
    solar_channel_id: Optional[int] = None


@dataclass(frozen=True)
class MetricsConfig:
    enabled: bool = False
    port: int = 9200


@dataclass(frozen=True)
class AiFeatureConfig:
    """Per-feature AI_<FEATURE>_* overrides; None means inherit the default."""
    enabled: bool = False
    model: Optional[str] = None
    ollama_host: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None
    gemini_fallback: Optional[bool] = None


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    ollama_host: str = 'http://localhost:11434'
    default_model: str = 'llama3.2'
    default_temperature: float = 0.7
    default_max_tokens: int = 256
    default_timeout: float = 30.0
    gemini_api_key: Optional[Secret] = field(repr=False, default=None)
    gemini_fallback: bool = False
    gemini_model: str = 'gemini-2.0-flash'
    max_concurrent_requests: int = 2
    max_pending_requests: int = 20
    min_delay_between_requests: float = 0.5
    max_retries: int = 2
    retry_delay_base: float = 2.0
    reconnect_interval: float = 60.0
    features: Mapping[str, AiFeatureConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class ModerationConfig:
    enabled: bool = False
    dry_run: bool = True
    auto_delete: bool = False
    auto_timeout: bool = False
    min_confidence: float = 0.75
    alert_min_confidence: float = 0.0
    ignored_categories: frozenset[str] = frozenset()
    timeout_minutes: int = 10
    min_message_length: int = 6
    user_cooldown_seconds: float = 20.0
    retention_days: int = 90
    alert_channel_id: Optional[int] = None
    ping_role_id: Optional[int] = None
    channels: frozenset[int] = frozenset()
    ignored_roles: frozenset[int] = frozenset()
    trusted_roles: frozenset[int] = frozenset()
    creator_roles: frozenset[int] = frozenset()
    member_days: int = 30
    veteran_days: int = 365
    reclaimed_tiers: frozenset[str] = frozenset({'veteran', 'trusted', 'creator'})
    profile: tuple[str, ...] = ('general',)
    review_votes: int = 1
    leniency_max_confidence: float = 0.95
    rules_channel_id: Optional[int] = None
    rules_sync_hours: float = 24.0
    # Second-stage model (ai/features/moderation.py).
    second_model: Optional[str] = None
    second_categories: frozenset[str] = frozenset({'hate_speech', 'harassment'})
    second_min_confidence: float = 0.85


@dataclass(frozen=True)
class GreeterConfig:
    enabled: bool = False
    max_mentions: int = 12
    channel_id: Optional[int] = None
    verify_channel_id: Optional[int] = None
    rules_channel_id: Optional[int] = None
    roles_channel_id: Optional[int] = None
    resource_channel_id: Optional[int] = None
    wagon_channel_id: Optional[int] = None
    general_channel_id: Optional[int] = None
    role_id: Optional[int] = None
    timezone: str = 'UTC'
    retract_window_seconds: float = 86400.0
    join_enabled: bool = True
    join_channel_id: Optional[int] = None
    join_message: Optional[str] = None
    join_image: Optional[str] = None
    join_cooldown_seconds: float = 900.0
    join_remind_after_seconds: float = 300.0
    join_daily_at: Optional[tuple[int, int]] = None
    verify_enabled: bool = True
    verify_message: Optional[str] = None
    verify_image: Optional[str] = None
    verify_cooldown_seconds: float = 10800.0
    max_tenure_days: float = 30.0
    verify_daily_at: Optional[tuple[int, int]] = None


@dataclass(frozen=True)
class HelperConfig:
    enabled: bool = False
    channels: frozenset[int] = frozenset()
    tiers: frozenset[str] = frozenset({'new'})
    cooldown_seconds: float = 60.0
    user_cooldown_seconds: float = 1800.0
    min_length: int = 12
    use_llm: bool = True
    resource_channel_id: Optional[int] = None
    rules_channel_id: Optional[int] = None
    message: Optional[str] = None


@dataclass(frozen=True)
class RolePickerConfig:
    enabled: bool = False


@dataclass(frozen=True)
class ProfileScreenConfig:
    enabled: bool = False
    use_llm: bool = True
    hold_greeting: bool = True
    protected_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkidDetectorConfig:
    enabled: bool = True
    fire_chance: float = 0.30
    cooldown_seconds: float = 180.0
    llm: bool = False


@dataclass(frozen=True)
class BanterConfig:
    arch_llm: bool = False


@dataclass(frozen=True)
class EventsConfig:
    enabled: bool = False
    dry_run: bool = True
    channel_id: Optional[int] = None
    review_channel_id: Optional[int] = None
    timezone: str = 'America/New_York'
    post_at: tuple[int, int] = (9, 0)
    reminder_days: tuple[int, ...] = (30, 7, 1)
    digest_enabled: bool = True
    max_pending_per_member: int = 3
    pending_expire_days: int = 30
    discovery_enabled: bool = False


@dataclass(frozen=True)
class Config:
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    posting: PostingConfig = field(default_factory=PostingConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    ai: AiConfig = field(default_factory=AiConfig)
    moderation: ModerationConfig = field(default_factory=ModerationConfig)
    greeter: GreeterConfig = field(default_factory=GreeterConfig)
    helper: HelperConfig = field(default_factory=HelperConfig)
    role_picker: RolePickerConfig = field(default_factory=RolePickerConfig)
    profile_screen: ProfileScreenConfig = field(default_factory=ProfileScreenConfig)
    skid_detector: SkidDetectorConfig = field(default_factory=SkidDetectorConfig)
    banter: BanterConfig = field(default_factory=BanterConfig)
    events: EventsConfig = field(default_factory=EventsConfig)


# ---------------------------------------------------------------------------
# Reader: one place that knows how to turn a raw string into a typed value
# and how to phrase the complaint when it cannot.
# ---------------------------------------------------------------------------

def _platform_for(name: str) -> Optional[str]:
    for platform in _SECRET_PLATFORMS:
        if name.startswith(platform + '_'):
            return platform
    return None


def _is_placeholder(value: str) -> bool:
    # .env.example ships `your_bot_token_here` style values; bot.py has
    # always treated those as unset rather than as garbage.
    return value.lower().startswith('your_')


def _show(value: str, limit: int = 32) -> str:
    """Quote a non-secret value for an error line, truncated so a secret
    pasted into the wrong variable is never echoed whole."""
    if len(value) > limit:
        return repr(value[:limit] + '...')
    return repr(value)


def _split(raw: str, lower: bool) -> list[str]:
    parts = [p.strip() for p in raw.split(',')]
    parts = [p for p in parts if p]
    return [p.lower() for p in parts] if lower else parts


class _Reader:
    def __init__(self, env: Mapping[str, str], secrets: Optional[SecretLookup]):
        self.env = env
        self.secrets = secrets
        self.problems: list[str] = []

    # -- raw access ---------------------------------------------------------

    def raw(self, name: str) -> Optional[str]:
        """The trimmed value, or None when unset, blank, or a placeholder.

        Secrets-manager platforms are consulted first so Doppler/AWS/Vault
        keep overriding .env, matching get_secret()'s own priority.
        """
        value = None
        platform = _platform_for(name)
        if platform and self.secrets is not None:
            value = self.secrets(platform, name[len(platform) + 1:])
        if not value:
            value = self.env.get(name)
        if value is None:
            return None
        value = str(value).strip()
        if not value or _is_placeholder(value):
            return None
        return value

    def fail(self, name: str, expected: str, value: Optional[str] = None) -> None:
        if value is None:
            self.problems.append(f'{name}: {expected}')
        else:
            self.problems.append(f'{name}: {expected}, got {_show(value)}')

    # -- typed parsers ------------------------------------------------------

    def str(self, name: str, default: Optional[str] = None) -> Optional[str]:
        value = self.raw(name)
        return default if value is None else value

    def secret(self, name: str, *, required: bool = False, aliases: tuple[str, ...] = ()) -> Optional[Secret]:
        value = self.raw(name)
        for alias in aliases:
            if value:
                break
            value = self.raw(alias)
        if value:
            return Secret(value)
        if required:
            # Never a value here, by construction: a secret is either
            # present or absent, and this line is the only thing logged.
            self.fail(name, 'required, not set (environment, .env, or a secrets manager; see .env.example)')
        return None

    def bool(self, name: str, default: bool) -> bool:
        value = self.raw(name)
        if value is None:
            return default
        lowered = value.lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        self.fail(name, 'expected true/false (also 1/0, yes/no, on/off)', value)
        return default

    def int(self, name: str, default: int, *, minimum: Optional[int] = None,
            maximum: Optional[int] = None) -> int:
        value = self.raw(name)
        if value is None:
            return default
        try:
            parsed = int(value)
        except ValueError:
            self.fail(name, 'expected an integer', value)
            return default
        if minimum is not None and parsed < minimum:
            self.fail(name, f'expected an integer >= {minimum}', value)
            return default
        if maximum is not None and parsed > maximum:
            self.fail(name, f'expected an integer <= {maximum}', value)
            return default
        return parsed

    def optional_int(self, name: str) -> Optional[int]:
        value = self.raw(name)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            self.fail(name, 'expected an integer', value)
            return None

    def float(self, name: str, default: float) -> float:
        value = self.raw(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            self.fail(name, 'expected a number', value)
            return default

    def optional_float(self, name: str) -> Optional[float]:
        value = self.raw(name)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            self.fail(name, 'expected a number', value)
            return None

    def optional_bool(self, name: str) -> Optional[bool]:
        if self.raw(name) is None:
            return None
        return self.bool(name, False)

    def snowflake(self, name: str) -> Optional[int]:
        """A Discord id: 17 to 20 digits. `<#id>`, `<@id>`, `<@&id>` and
        quoted ids are unwrapped (the runners accepted those)."""
        value = self.raw(name)
        if value is None:
            return None
        parsed = self._snowflake(value)
        if parsed is None:
            self.fail(name, 'expected a Discord id (17 to 20 digits)', value)
        return parsed

    def snowflakes(self, name: str) -> frozenset[int]:
        """Comma or whitespace separated Discord ids."""
        value = self.raw(name)
        if value is None:
            return frozenset()
        ids = set()
        for part in re.split(r'[,\s]+', value):
            if not part:
                continue
            parsed = self._snowflake(part)
            if parsed is None:
                self.fail(name, 'expected comma-separated Discord ids (17 to 20 digits each)', part)
                continue
            ids.add(parsed)
        return frozenset(ids)

    @staticmethod
    def _snowflake(value: str) -> Optional[int]:
        stripped = value.strip().strip('"\'')
        if stripped.startswith('<') and stripped.endswith('>'):
            stripped = stripped[1:-1].lstrip('#@&!')
        return int(stripped) if _SNOWFLAKE_RE.fullmatch(stripped) else None

    def words(self, name: str, default: tuple[str, ...] = (), *, lower: bool = True) -> tuple[str, ...]:
        value = self.raw(name)
        if value is None:
            return default
        return tuple(_split(value, lower))

    def time(self, name: str) -> Optional[tuple[int, int]]:
        value = self.raw(name)
        if value is None:
            return None
        match = _TIME_RE.match(value)
        if match and int(match[1]) <= 23 and int(match[2]) <= 59:
            return (int(match[1]), int(match[2]))
        self.fail(name, 'expected a time of day as HH:MM (24-hour)', value)
        return None

    def timezone(self, name: str, default: str = 'UTC') -> str:
        value = self.raw(name)
        if value is None:
            return default
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except Exception:
            self.fail(name, 'expected an IANA timezone name such as America/New_York', value)
            return default
        return value

    def level(self, name: str, default: int = logging.INFO) -> int:
        value = self.raw(name)
        if value is None:
            return default
        resolved = logging.getLevelName(value.upper())
        if isinstance(resolved, int):
            return resolved
        self.fail(name, 'expected a log level: DEBUG, INFO, WARNING, ERROR or CRITICAL', value)
        return default

    def path(self, name: str, default: Path) -> Path:
        value = self.raw(name)
        return default if value is None else Path(value)


# ---------------------------------------------------------------------------
# Section loaders
# ---------------------------------------------------------------------------

def _load_discord(r: _Reader) -> DiscordConfig:
    return DiscordConfig(
        bot_token=r.secret('DISCORD_BOT_TOKEN', required=True, aliases=('DISCORD_TOKEN',)) or Secret(''),
        owner_id=r.snowflake('DISCORD_OWNER_ID'),
    )


def _load_logging(r: _Reader) -> LoggingConfig:
    return LoggingConfig(
        level=r.level('LOG_LEVEL'),
        file=r.str('LOG_FILE'),
        max_bytes=r.int('LOG_MAX_BYTES', DEFAULT_LOG_MAX_BYTES, minimum=1),
        backups=r.int('LOG_BACKUPS', DEFAULT_LOG_BACKUPS, minimum=0),
    )


def _default_data_dir() -> Path:
    # Same order as utils.state.resolve_data_dir: DATA_DIR, then the Docker
    # volume mount, then ./data relative to the working directory.
    return Path('/app/data') if os.path.exists('/app/data') else Path('data')


def _load_paths(r: _Reader) -> PathsConfig:
    data_dir = r.path('DATA_DIR', _default_data_dir())
    return PathsConfig(
        data_dir=data_dir,
        database_path=r.path('BOT_DATABASE_PATH', data_dir / 'penguin_overlord.db'),
        xkcd_state_path=r.path('XKCD_STATE_PATH', data_dir / 'xkcd_state.json'),
        comic_state_path=r.path('COMIC_STATE_PATH', data_dir / 'comic_state.json'),
    )


def _load_news(r: _Reader) -> NewsConfig:
    channels = {c: r.snowflake(f'NEWS_{c.upper()}_CHANNEL_ID') for c in NEWS_CATEGORIES}
    return NewsConfig(auto_post=r.bool('NEWS_AUTO_POST', True), **channels)


def _load_posting(r: _Reader) -> PostingConfig:
    return PostingConfig(
        xkcd_channel_id=r.snowflake('XKCD_POST_CHANNEL_ID'),
        xkcd_poll_interval_minutes=r.int('XKCD_POLL_INTERVAL_MINUTES', 30, minimum=1),
        comic_channel_id=r.snowflake('COMIC_POST_CHANNEL_ID'),
        solar_channel_id=r.snowflake('SOLAR_POST_CHANNEL_ID'),
    )


def _load_metrics(r: _Reader) -> MetricsConfig:
    return MetricsConfig(
        enabled=r.bool('METRICS_ENABLED', False),
        port=r.int('METRICS_PORT', 9200, minimum=1, maximum=65535),
    )


def _load_ai(r: _Reader) -> AiConfig:
    # Same resolution as ai/config.py: AI_DEFAULT_OLLAMA_HOST or OLLAMA_HOST,
    # scheme-less values get http:// and OLLAMA_PORT (default 11434).
    host = r.str('AI_DEFAULT_OLLAMA_HOST') or r.str('OLLAMA_HOST')
    if host and '://' not in host:
        host = f"http://{host}:{r.str('OLLAMA_PORT', '11434')}"
    features = {}
    for feature in AI_FEATURES:
        prefix = f'AI_{feature.upper()}'
        features[feature] = AiFeatureConfig(
            enabled=r.bool(f'{prefix}_ENABLED', False),
            model=r.str(f'{prefix}_MODEL'),
            ollama_host=r.str(f'{prefix}_OLLAMA_HOST'),
            temperature=r.optional_float(f'{prefix}_TEMPERATURE'),
            max_tokens=r.optional_int(f'{prefix}_MAX_TOKENS'),
            timeout=r.optional_float(f'{prefix}_TIMEOUT'),
            gemini_fallback=r.optional_bool(f'{prefix}_GEMINI_FALLBACK'),
        )
    return AiConfig(
        enabled=r.bool('AI_ENABLED', False),
        ollama_host=host or 'http://localhost:11434',
        default_model=r.str('AI_DEFAULT_MODEL') or r.str('OLLAMA_MODEL') or 'llama3.2',
        default_temperature=r.float('AI_DEFAULT_TEMPERATURE', 0.7),
        default_max_tokens=r.int('AI_DEFAULT_MAX_TOKENS', 256),
        default_timeout=r.float('AI_DEFAULT_TIMEOUT', 30.0),
        gemini_api_key=r.secret('GEMINI_API_KEY'),
        gemini_fallback=r.bool('AI_GEMINI_FALLBACK', False),
        gemini_model=r.str('AI_GEMINI_MODEL', 'gemini-2.0-flash'),
        max_concurrent_requests=r.int('AI_MAX_CONCURRENT_REQUESTS', 2, minimum=1),
        max_pending_requests=r.int('AI_MAX_PENDING_REQUESTS', 20, minimum=0),
        min_delay_between_requests=r.float('AI_MIN_DELAY_BETWEEN_REQUESTS', 0.5),
        max_retries=r.int('AI_MAX_RETRIES', 2, minimum=0),
        retry_delay_base=r.float('AI_RETRY_DELAY_BASE', 2.0),
        reconnect_interval=r.float('AI_RECONNECT_INTERVAL', 60.0),
        features=features,
    )


def _load_moderation(r: _Reader) -> ModerationConfig:
    return ModerationConfig(
        enabled=r.bool('MOD_ENABLED', False),
        dry_run=r.bool('MOD_DRY_RUN', True),
        auto_delete=r.bool('MOD_AUTO_DELETE', False),
        auto_timeout=r.bool('MOD_AUTO_TIMEOUT', False),
        min_confidence=r.float('MOD_MIN_CONFIDENCE', 0.75),
        alert_min_confidence=r.float('MOD_ALERT_MIN_CONFIDENCE', 0.0),
        ignored_categories=frozenset(r.words('MOD_IGNORED_CATEGORIES')),
        timeout_minutes=r.int('MOD_TIMEOUT_MINUTES', 10),
        min_message_length=r.int('MOD_MIN_MESSAGE_LENGTH', 6),
        user_cooldown_seconds=r.float('MOD_USER_COOLDOWN_SECONDS', 20.0),
        retention_days=r.int('MOD_RETENTION_DAYS', 90),
        alert_channel_id=r.snowflake('MOD_ALERT_CHANNEL_ID'),
        ping_role_id=r.snowflake('MOD_PING_ROLE_ID'),
        channels=r.snowflakes('MOD_CHANNELS'),
        ignored_roles=r.snowflakes('MOD_IGNORED_ROLES'),
        trusted_roles=r.snowflakes('MOD_TRUSTED_ROLES'),
        creator_roles=r.snowflakes('MOD_CREATOR_ROLES'),
        member_days=r.int('MOD_MEMBER_DAYS', 30),
        veteran_days=r.int('MOD_VETERAN_DAYS', 365),
        reclaimed_tiers=frozenset(r.words('MOD_RECLAIMED_TIERS', ('veteran', 'trusted', 'creator'))),
        profile=r.words('MOD_PROFILE', ('general',)),
        review_votes=r.int('MOD_REVIEW_VOTES', 1, minimum=1),
        leniency_max_confidence=r.float('MOD_LENIENCY_MAX_CONFIDENCE', 0.95),
        rules_channel_id=r.snowflake('MOD_RULES_CHANNEL_ID'),
        rules_sync_hours=r.float('MOD_RULES_SYNC_HOURS', 24.0),
        second_model=r.str('AI_MODERATION_SECOND_MODEL'),
        second_categories=frozenset(r.words('AI_MODERATION_SECOND_CATEGORIES', ('hate_speech', 'harassment'))),
        second_min_confidence=r.float('AI_MODERATION_SECOND_MIN_CONFIDENCE', 0.85),
    )


def _load_greeter(r: _Reader) -> GreeterConfig:
    return GreeterConfig(
        enabled=r.bool('WELCOME_ENABLED', False),
        max_mentions=r.int('WELCOME_MAX_MENTIONS', 12, minimum=1),
        channel_id=r.snowflake('WELCOME_CHANNEL_ID'),
        verify_channel_id=r.snowflake('WELCOME_VERIFY_CHANNEL_ID'),
        rules_channel_id=r.snowflake('WELCOME_RULES_CHANNEL_ID'),
        roles_channel_id=r.snowflake('WELCOME_ROLES_CHANNEL_ID'),
        resource_channel_id=r.snowflake('WELCOME_RESOURCE_CHANNEL_ID'),
        wagon_channel_id=r.snowflake('WELCOME_WAGON_CHANNEL_ID'),
        general_channel_id=r.snowflake('WELCOME_GENERAL_CHANNEL_ID'),
        role_id=r.snowflake('WELCOME_ROLE_ID'),
        timezone=r.timezone('WELCOME_TIMEZONE'),
        retract_window_seconds=r.float('WELCOME_RETRACT_WINDOW_SECONDS', 86400.0),
        join_enabled=r.bool('WELCOME_JOIN_ENABLED', True),
        join_channel_id=r.snowflake('WELCOME_JOIN_CHANNEL_ID'),
        join_message=r.str('WELCOME_JOIN_MESSAGE'),
        join_image=r.str('WELCOME_JOIN_IMAGE'),
        join_cooldown_seconds=r.float('WELCOME_JOIN_COOLDOWN_SECONDS', 900.0),
        join_remind_after_seconds=r.float('WELCOME_JOIN_REMIND_AFTER_SECONDS', 300.0),
        join_daily_at=r.time('WELCOME_JOIN_DAILY_AT'),
        verify_enabled=r.bool('WELCOME_VERIFY_ENABLED', True),
        verify_message=r.str('WELCOME_VERIFY_MESSAGE'),
        verify_image=r.str('WELCOME_VERIFY_IMAGE'),
        verify_cooldown_seconds=r.float('WELCOME_VERIFY_COOLDOWN_SECONDS', 10800.0),
        max_tenure_days=r.float('WELCOME_MAX_TENURE_DAYS', 30.0),
        verify_daily_at=r.time('WELCOME_VERIFY_DAILY_AT'),
    )


def _load_helper(r: _Reader) -> HelperConfig:
    return HelperConfig(
        enabled=r.bool('HELPER_ENABLED', False),
        channels=r.snowflakes('HELPER_CHANNELS'),
        tiers=frozenset(r.words('HELPER_TIERS', ('new',))),
        cooldown_seconds=r.float('HELPER_COOLDOWN_SECONDS', 60.0),
        user_cooldown_seconds=r.float('HELPER_USER_COOLDOWN_SECONDS', 1800.0),
        min_length=r.int('HELPER_MIN_LENGTH', 12),
        use_llm=r.bool('HELPER_USE_LLM', True),
        resource_channel_id=r.snowflake('HELPER_RESOURCE_CHANNEL_ID'),
        rules_channel_id=r.snowflake('HELPER_RULES_CHANNEL_ID'),
        message=r.str('HELPER_MESSAGE'),
    )


def _load_role_picker(r: _Reader) -> RolePickerConfig:
    return RolePickerConfig(enabled=r.bool('ROLE_PICKER_ENABLED', False))


def _load_profile_screen(r: _Reader) -> ProfileScreenConfig:
    return ProfileScreenConfig(
        enabled=r.bool('PROFILE_SCREEN_ENABLED', False),
        use_llm=r.bool('PROFILE_SCREEN_LLM', True),
        hold_greeting=r.bool('PROFILE_SCREEN_HOLD_GREETING', True),
        protected_names=r.words('PROFILE_SCREEN_PROTECTED_NAMES', lower=False),
    )


def _load_skid_detector(r: _Reader) -> SkidDetectorConfig:
    return SkidDetectorConfig(
        enabled=r.bool('SKID_DETECTOR_ENABLED', True),
        fire_chance=r.float('SKID_FIRE_CHANCE', 0.30),
        cooldown_seconds=r.float('SKID_COOLDOWN_SECONDS', 180.0),
        llm=r.bool('SKID_DETECTOR_LLM', False),
    )


def _load_banter(r: _Reader) -> BanterConfig:
    return BanterConfig(arch_llm=r.bool('ARCH_BANTER_LLM', False))


def _load_events(r: _Reader) -> EventsConfig:
    enabled = r.bool('EVENTS_ENABLED', False)
    channel_id = r.snowflake('EVENTS_CHANNEL_ID')
    if enabled and channel_id is None:
        r.fail('EVENTS_CHANNEL_ID', 'required when EVENTS_ENABLED=true')
    raw_days = r.str('EVENTS_REMINDER_DAYS', '30,7,1')
    days: tuple[int, ...] = (30, 7, 1)
    try:
        parsed = sorted({int(part) for part in _split(raw_days, lower=False)}, reverse=True)
        if not parsed or any(day < 1 for day in parsed):
            raise ValueError
        days = tuple(parsed)
    except ValueError:
        r.fail('EVENTS_REMINDER_DAYS', 'expected comma-separated positive day counts such as 30,7,1', raw_days)
    return EventsConfig(
        enabled=enabled,
        dry_run=r.bool('EVENTS_DRY_RUN', True),
        channel_id=channel_id,
        review_channel_id=r.snowflake('EVENTS_REVIEW_CHANNEL_ID') or r.snowflake('MOD_ALERT_CHANNEL_ID'),
        timezone=r.timezone('EVENTS_TIMEZONE', 'America/New_York'),
        post_at=r.time('EVENTS_POST_AT') or (9, 0),
        reminder_days=days,
        digest_enabled=r.bool('EVENTS_DIGEST_ENABLED', True),
        max_pending_per_member=r.int('EVENTS_MAX_PENDING_PER_MEMBER', 3, minimum=1),
        pending_expire_days=r.int('EVENTS_PENDING_EXPIRE_DAYS', 30, minimum=1),
        discovery_enabled=r.bool('EVENTS_DISCOVERY_ENABLED', False),
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _reader(env: Optional[Mapping[str, str]], secrets: Optional[SecretLookup], *, use_secrets: bool) -> _Reader:
    if env is None:
        env = os.environ
        if secrets is None and use_secrets:
            from utils.secrets import get_secret
            secrets = get_secret
    return _Reader(env, secrets)


def load_config(env: Optional[Mapping[str, str]] = None, *,
                secrets: Optional[SecretLookup] = None) -> Config:
    """Load and validate the whole configuration.

    Args:
        env: the variables to read. None means the real environment
            (call load_dotenv() first if a .env file should count).
        secrets: a `(platform, key) -> value | None` lookup consulted before
            `env` for secrets-manager variables. Defaults to
            `utils.secrets.get_secret` when `env` is None and to no lookup
            at all when an explicit `env` is given, so tests stay hermetic.

    Raises:
        ConfigError: listing every missing or malformed variable at once.
    """
    r = _reader(env, secrets, use_secrets=True)
    config = Config(
        discord=_load_discord(r),
        logging=_load_logging(r),
        paths=_load_paths(r),
        news=_load_news(r),
        posting=_load_posting(r),
        metrics=_load_metrics(r),
        ai=_load_ai(r),
        moderation=_load_moderation(r),
        greeter=_load_greeter(r),
        helper=_load_helper(r),
        role_picker=_load_role_picker(r),
        profile_screen=_load_profile_screen(r),
        skid_detector=_load_skid_detector(r),
        banter=_load_banter(r),
        events=_load_events(r),
    )
    if r.problems:
        raise ConfigError(r.problems)
    return config


def load_logging_config(env: Optional[Mapping[str, str]] = None) -> LoggingConfig:
    """LOG_* only, defaults substituted for anything malformed; never raises.

    Logging has to exist before load_config() can report its problems, so
    this is what configure_logging() falls back to. load_config() reports
    the same bad value afterwards.
    """
    return _load_logging(_reader(env, None, use_secrets=False))


def load_metrics_config(env: Optional[Mapping[str, str]] = None) -> MetricsConfig:
    """METRICS_* only, lenient; for utils/metrics.py's import-time constants."""
    return _load_metrics(_reader(env, None, use_secrets=False))


def load_paths_config(env: Optional[Mapping[str, str]] = None) -> PathsConfig:
    """DATA_DIR and state-file paths only, lenient (it cannot fail today)."""
    return _load_paths(_reader(env, None, use_secrets=False))


def load_events_config(env: Optional[Mapping[str, str]] = None) -> EventsConfig:
    """EVENTS_* only, lenient; for the cog when the bot carries no Config
    (tests, tooling). bot.py's load_config() has already refused to start
    on anything malformed here."""
    return _load_events(_reader(env, None, use_secrets=False))


def load_news_config(env: Optional[Mapping[str, str]] = None) -> NewsConfig:
    """NEWS_* only, lenient; for utils/news_dedupe.py's NEWS_AUTO_POST read."""
    return load_section('news', env)


def load_ai_config(env: Optional[Mapping[str, str]] = None) -> AiConfig:
    """AI_*, OLLAMA_* and GEMINI_API_KEY only, lenient; the fallback for the
    `ai` package when no caller passed a Config in."""
    return load_section('ai', env)


def load_moderation_config(env: Optional[Mapping[str, str]] = None) -> ModerationConfig:
    """MOD_* and AI_MODERATION_SECOND_* only, lenient; the fallback for
    ai/features/moderation.py when no caller passed a Config in."""
    return load_section('moderation', env)


# Every section, with whether its variables have a secrets-manager platform.
# The `use_secrets` flag mirrors what each reader did before the migration,
# so a lenient load resolves exactly the same values a cog's own _env() did.
_LENIENT_SECTIONS: dict[str, tuple[Callable[[_Reader], object], bool]] = {
    'discord': (_load_discord, True),
    'logging': (_load_logging, False),
    'paths': (_load_paths, False),
    'news': (_load_news, True),
    'posting': (_load_posting, True),
    'metrics': (_load_metrics, False),
    'ai': (_load_ai, True),
    'moderation': (_load_moderation, True),
    'greeter': (_load_greeter, True),
    'helper': (_load_helper, True),
    'role_picker': (_load_role_picker, False),
    'profile_screen': (_load_profile_screen, False),
    'skid_detector': (_load_skid_detector, False),
    'banter': (_load_banter, False),
    'events': (_load_events, False),
}


def load_section(name: str, env: Optional[Mapping[str, str]] = None):
    """One `Config` section, loaded leniently: defaults are substituted for
    anything malformed and nothing is raised.

    Raises:
        KeyError: for a name that is not a `Config` field.
    """
    if name not in _LENIENT_SECTIONS:
        raise KeyError(f'unknown config section: {name}')
    loader, use_secrets = _LENIENT_SECTIONS[name]
    return loader(_reader(env, None, use_secrets=use_secrets))


def section_config(bot, name: str, *, env: Optional[Mapping[str, str]] = None):
    """The named section from `bot.config`, or a lenient environment load.

    This is how a cog reads its settings. In the bot the config was loaded
    and validated once at startup, so `bot.config` is there and nothing is
    re-parsed. Tests and tooling build cogs with a bare fake bot; those
    fall back to `load_section`, which never raises.

    The isinstance check is deliberate: a `MagicMock` bot answers every
    attribute, and a mock section would hand the cog mock channel ids
    instead of falling back.
    """
    config = getattr(bot, 'config', None)
    if isinstance(config, Config):
        return getattr(config, name)
    return load_section(name, env)


def describe_config(config: Config) -> str:
    """One-line summary for the startup banner and --check-config.

    Counts and on/off flags only: never a value, never an id.
    """
    def flag(value: bool) -> str:
        return 'on' if value else 'off'

    posters = [name for name, channel in (
        ('xkcd', config.posting.xkcd_channel_id),
        ('comic', config.posting.comic_channel_id),
        ('solar', config.posting.solar_channel_id),
    ) if channel is not None]
    parts = [
        f"owner={'set' if config.discord.owner_id else 'unset'}",
        f'log={logging.getLevelName(config.logging.level)}',
        f'news={config.news.configured()}/{len(NEWS_CATEGORIES)} channels (auto_post {flag(config.news.auto_post)})',
        f"posters={','.join(posters) or 'none'}",
        f'metrics={flag(config.metrics.enabled)}',
        f'ai={flag(config.ai.enabled)}',
        f'moderation={flag(config.moderation.enabled)}',
        f'greeter={flag(config.greeter.enabled)}',
        f'helper={flag(config.helper.enabled)}',
        f'role_picker={flag(config.role_picker.enabled)}',
        f'profile_screen={flag(config.profile_screen.enabled)}',
        f'skid_detector={flag(config.skid_detector.enabled)}',
        f'events={flag(config.events.enabled)}',
    ]
    return ' '.join(parts)
