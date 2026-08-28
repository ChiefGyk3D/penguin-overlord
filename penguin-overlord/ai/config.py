# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI configuration, resolved from environment / secrets manager.

Layering (highest wins):
    AI_<FEATURE>_<KEY>   per-feature override (e.g. AI_ROASTING_MODEL)
    AI_DEFAULT_<KEY>     global default      (e.g. AI_DEFAULT_MODEL)
    built-in default

Every feature is disabled unless BOTH AI_ENABLED=true and
AI_<FEATURE>_ENABLED=true. get_feature_config() returns a fresh dataclass
per call — never a shared mutable object.
"""

import os
from dataclasses import dataclass

from utils.secrets import get_secret

KNOWN_FEATURES = ('roasting', 'moderation', 'news', 'cve', 'legislation')

# Features whose inputs are other people's messages: content must never be
# sent to a remote provider, whatever the fallback flags say.
LOCAL_ONLY_FEATURES = frozenset({'moderation'})


def _env(name: str, default: str = None) -> str:
    """Env lookup that also consults the secrets manager for AI_* keys."""
    value = os.getenv(name)
    if value is None and name.startswith('AI_'):
        value = get_secret('AI', name[3:])
    return value if value is not None else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def ai_enabled() -> bool:
    """Master switch. Defaults OFF: enabling AI is a deliberate operator act."""
    return _env_bool('AI_ENABLED', False)


def default_ollama_host() -> str:
    host = _env('AI_DEFAULT_OLLAMA_HOST') or _env('OLLAMA_HOST')
    if host:
        if '://' not in host:
            port = _env('OLLAMA_PORT', '11434')
            host = f"http://{host}:{port}"
        return host
    return 'http://localhost:11434'


def gemini_api_key() -> str:
    return _env('GEMINI_API_KEY') or get_secret('GEMINI', 'API_KEY')


@dataclass
class FeatureConfig:
    feature: str
    enabled: bool
    model: str
    host: str
    temperature: float
    max_tokens: int
    timeout: float
    gemini_fallback: bool


def get_feature_config(feature: str) -> FeatureConfig:
    """Resolve the effective config for one feature. Always a fresh object."""
    prefix = f'AI_{feature.upper()}'

    gemini_fallback = _env_bool(f'{prefix}_GEMINI_FALLBACK',
                                _env_bool('AI_GEMINI_FALLBACK', False))
    if feature in LOCAL_ONLY_FEATURES:
        # Moderation scans other people's messages: local inference only.
        gemini_fallback = False

    return FeatureConfig(
        feature=feature,
        enabled=ai_enabled() and _env_bool(f'{prefix}_ENABLED', False),
        model=_env(f'{prefix}_MODEL') or _env('AI_DEFAULT_MODEL') or _env('OLLAMA_MODEL') or 'llama3.2',
        host=_env(f'{prefix}_OLLAMA_HOST') or default_ollama_host(),
        temperature=_env_float(f'{prefix}_TEMPERATURE', _env_float('AI_DEFAULT_TEMPERATURE', 0.7)),
        max_tokens=_env_int(f'{prefix}_MAX_TOKENS', _env_int('AI_DEFAULT_MAX_TOKENS', 256)),
        timeout=_env_float(f'{prefix}_TIMEOUT', _env_float('AI_DEFAULT_TIMEOUT', 30.0)),
        gemini_fallback=gemini_fallback,
    )


@dataclass
class RuntimeConfig:
    max_concurrent: int
    max_pending: int
    min_delay: float
    max_retries: int
    retry_delay_base: float
    reconnect_interval: float
    gemini_model: str


def get_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        max_concurrent=_env_int('AI_MAX_CONCURRENT_REQUESTS', 2),
        max_pending=_env_int('AI_MAX_PENDING_REQUESTS', 20),
        min_delay=_env_float('AI_MIN_DELAY_BETWEEN_REQUESTS', 0.5),
        max_retries=_env_int('AI_MAX_RETRIES', 2),
        retry_delay_base=_env_float('AI_RETRY_DELAY_BASE', 2.0),
        reconnect_interval=_env_float('AI_RECONNECT_INTERVAL', 60.0),
        gemini_model=_env('AI_GEMINI_MODEL', 'gemini-2.0-flash'),
    )
