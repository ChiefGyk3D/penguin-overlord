# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI configuration: the layering rules over a typed `AiConfig`.

Layering (highest wins):
    AI_<FEATURE>_<KEY>   per-feature override (e.g. AI_ROASTING_MODEL)
    AI_DEFAULT_<KEY>     global default      (e.g. AI_DEFAULT_MODEL)
    built-in default

utils/config.py owns the parsing: it reads every AI_*, OLLAMA_* and
GEMINI_API_KEY once and hands back an `AiConfig` whose `features` mapping
carries the per-feature overrides. This module resolves the layering and
enforces the privacy rule, and no longer reads the environment itself.

Every entry point takes the settings as an argument. Cogs pass
`self.bot.config.ai`; anything built without a Config (tests, tooling,
one-off scripts) omits it and gets `load_ai_config()`, a lenient read of
the same variables.

Every feature is disabled unless BOTH AI_ENABLED=true and
AI_<FEATURE>_ENABLED=true. get_feature_config() returns a fresh dataclass
per call, never a shared mutable object.
"""

from dataclasses import dataclass
from typing import Optional

from utils.config import AiConfig, AiFeatureConfig, load_ai_config

KNOWN_FEATURES = ('roasting', 'moderation', 'news', 'cve', 'legislation')

# Features whose inputs are other people's messages: content must never be
# sent to a remote provider, whatever the fallback flags say.
LOCAL_ONLY_FEATURES = frozenset({'moderation'})

_NO_OVERRIDES = AiFeatureConfig()


def _settings(ai: Optional[AiConfig]) -> AiConfig:
    """The settings to use: the ones passed in, or a lenient environment read."""
    return ai if ai is not None else load_ai_config()


def ai_enabled(ai: Optional[AiConfig] = None) -> bool:
    """Master switch. Defaults OFF: enabling AI is a deliberate operator act."""
    return _settings(ai).enabled


def default_ollama_host(ai: Optional[AiConfig] = None) -> str:
    return _settings(ai).ollama_host


def gemini_api_key(ai: Optional[AiConfig] = None) -> Optional[str]:
    """The raw Gemini key, or None. The only place it leaves `Secret`."""
    key = _settings(ai).gemini_api_key
    return key.reveal() if key else None


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


def get_feature_config(feature: str, ai: Optional[AiConfig] = None) -> FeatureConfig:
    """Resolve the effective config for one feature. Always a fresh object."""
    settings = _settings(ai)
    override = settings.features.get(feature, _NO_OVERRIDES)

    gemini_fallback = override.gemini_fallback
    if gemini_fallback is None:
        gemini_fallback = settings.gemini_fallback
    if feature in LOCAL_ONLY_FEATURES:
        # Moderation scans other people's messages: local inference only.
        gemini_fallback = False

    def inherited(value, default):
        return default if value is None else value

    return FeatureConfig(
        feature=feature,
        enabled=settings.enabled and override.enabled,
        model=override.model or settings.default_model,
        host=override.ollama_host or settings.ollama_host,
        temperature=inherited(override.temperature, settings.default_temperature),
        max_tokens=inherited(override.max_tokens, settings.default_max_tokens),
        timeout=inherited(override.timeout, settings.default_timeout),
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


def get_runtime_config(ai: Optional[AiConfig] = None) -> RuntimeConfig:
    settings = _settings(ai)
    return RuntimeConfig(
        max_concurrent=settings.max_concurrent_requests,
        max_pending=settings.max_pending_requests,
        min_delay=settings.min_delay_between_requests,
        max_retries=settings.max_retries,
        retry_delay_base=settings.retry_delay_base,
        reconnect_interval=settings.reconnect_interval,
        gemini_model=settings.gemini_model,
    )
