# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
AI Configuration - Per-feature model and endpoint routing.

Supports FrankenLLM-style multi-server setups where different AI servers
handle different workloads. Each feature can be assigned:
    - A specific Ollama server (endpoint)
    - A specific model
    - A Gemini fallback model
    - Custom generation parameters

Example setup:
    Server 1 (GPU workstation): Runs Qwen3 for news analysis
    Server 2 (inference server): Runs Llama Guard for moderation
    Server 3 (cloud GPU): Runs Gemma3 for roasting

Environment Variables:
    # Global defaults
    AI_ENABLED=true
    AI_DEFAULT_PROVIDER=ollama
    AI_DEFAULT_OLLAMA_HOST=http://localhost:11434
    AI_DEFAULT_MODEL=gemma3:4b

    # Per-feature overrides (feature = roasting|news|cve|moderation)
    AI_ROASTING_PROVIDER=gemini
    AI_ROASTING_MODEL=gemini-2.0-flash
    AI_ROASTING_OLLAMA_HOST=http://gpu-server-1:11434

    AI_NEWS_PROVIDER=ollama
    AI_NEWS_MODEL=qwen3:14b
    AI_NEWS_OLLAMA_HOST=http://gpu-server-2:11434

    AI_MODERATION_PROVIDER=ollama
    AI_MODERATION_MODEL=llama-guard3:8b
    AI_MODERATION_OLLAMA_HOST=http://gpu-server-3:11434

    AI_CVE_PROVIDER=ollama
    AI_CVE_MODEL=qwen3:14b
    AI_CVE_OLLAMA_HOST=http://gpu-server-2:11434

    # Gemini fallback (used when Ollama is unavailable)
    GEMINI_API_KEY=your_key_here
    AI_GEMINI_MODEL=gemini-2.0-flash

    # Thinking model support (Qwen3)
    AI_ENABLE_THINKING_MODE=false
    AI_THINKING_TOKEN_MULTIPLIER=4.0

    # Queue and retry settings
    AI_MAX_CONCURRENT_REQUESTS=4
    AI_MIN_DELAY_BETWEEN_REQUESTS=1.0
    AI_MAX_RETRIES=3
    AI_RETRY_DELAY_BASE=2

    # Reconnection
    AI_ENABLE_AUTO_RECONNECT=true
    AI_RECONNECT_INTERVAL=60
    AI_MAX_RECONNECT_ATTEMPTS=0
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Any

logger = logging.getLogger(__name__)


# Feature names used throughout the system
FEATURE_ROASTING = 'roasting'
FEATURE_NEWS = 'news'
FEATURE_CVE = 'cve'
FEATURE_MODERATION = 'moderation'
FEATURE_LEGISLATION = 'legislation'

ALL_FEATURES = [FEATURE_ROASTING, FEATURE_NEWS, FEATURE_CVE, FEATURE_MODERATION, FEATURE_LEGISLATION]


@dataclass
class ModelConfig:
    """Configuration for a specific model's generation parameters."""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 150
    context_window: int = 8192
    # Thinking model support
    enable_thinking: bool = False
    thinking_token_multiplier: float = 4.0


@dataclass
class FeatureConfig:
    """Configuration for a specific feature's AI routing."""
    provider: str = 'ollama'          # 'ollama' or 'gemini'
    model: str = 'gemma3:4b'          # Model name
    ollama_host: str = 'http://localhost:11434'  # Ollama server URL
    gemini_model: str = 'gemini-2.0-flash'  # Gemini fallback model
    gemini_fallback_enabled: bool = True  # Allow Gemini fallback
    model_config: ModelConfig = field(default_factory=ModelConfig)
    timeout: int = 30                 # Request timeout in seconds
    enabled: bool = True              # Whether this feature is enabled


# Well-known model configurations for optimal defaults
KNOWN_MODEL_CONFIGS: Dict[str, ModelConfig] = {
    # Gemma models
    'gemma2:2b':  ModelConfig(temperature=0.7, max_tokens=150, context_window=8192),
    'gemma2:9b':  ModelConfig(temperature=0.7, max_tokens=200, context_window=8192),
    'gemma3:4b':  ModelConfig(temperature=0.7, max_tokens=200, context_window=8192),
    'gemma3:12b': ModelConfig(temperature=0.7, max_tokens=250, context_window=8192),
    'gemma3:27b': ModelConfig(temperature=0.7, max_tokens=300, context_window=8192),

    # Llama models
    'llama3.2:1b':  ModelConfig(temperature=0.7, max_tokens=120, context_window=128000),
    'llama3.2:3b':  ModelConfig(temperature=0.7, max_tokens=150, context_window=128000),
    'llama3.1:8b':  ModelConfig(temperature=0.7, max_tokens=200, context_window=128000),
    'llama3.1:70b': ModelConfig(temperature=0.7, max_tokens=300, context_window=128000),
    'llama3.3:70b': ModelConfig(temperature=0.7, max_tokens=300, context_window=128000),

    # Llama Guard (moderation)
    # ┌────────────────────────────────────────────────────────────────────┐
    # │  Model                 │ VRAM    │ Speed   │ Notes               │
    # ├────────────────────────────────────────────────────────────────────┤
    # │  llama-guard3:1b       │ ~1.5 GB │ Fast    │ CPU viable, good    │
    # │  llama-guard3:8b-q4_0  │ ~4.5 GB │ Medium  │ Best for 3070 8GB   │
    # │  llama-guard3:8b-q5_1  │ ~6.0 GB │ Medium  │ 3070 tight fit      │
    # │  llama-guard3:8b       │ ~8.0 GB │ Slower  │ Needs ≥10 GB VRAM   │
    # └────────────────────────────────────────────────────────────────────┘
    # For RTX 3070 (8 GB): use q4_0 quantization — ``ollama pull llama-guard3:8b-q4_0``
    # For ≤6 GB VRAM: use the 1B model — ``ollama pull llama-guard3:1b``
    'llama-guard3:1b': ModelConfig(temperature=0.1, max_tokens=50, context_window=8192),
    'llama-guard3:8b': ModelConfig(temperature=0.1, max_tokens=50, context_window=8192),
    'llama-guard3:8b-q4_0': ModelConfig(temperature=0.1, max_tokens=50, context_window=4096),
    'llama-guard3:8b-q5_1': ModelConfig(temperature=0.1, max_tokens=50, context_window=4096),

    # Qwen models (thinking-capable)
    'qwen2.5:3b':  ModelConfig(temperature=0.7, max_tokens=150, context_window=32768),
    'qwen2.5:7b':  ModelConfig(temperature=0.7, max_tokens=200, context_window=128000),
    'qwen2.5:14b': ModelConfig(temperature=0.7, max_tokens=250, context_window=128000),
    'qwen2.5:32b': ModelConfig(temperature=0.7, max_tokens=300, context_window=128000),
    'qwen3:1.7b':  ModelConfig(temperature=0.7, max_tokens=150, context_window=40960,
                               enable_thinking=True, thinking_token_multiplier=4.0),
    'qwen3:4b':    ModelConfig(temperature=0.7, max_tokens=200, context_window=40960,
                               enable_thinking=True, thinking_token_multiplier=4.0),
    'qwen3:8b':    ModelConfig(temperature=0.7, max_tokens=200, context_window=40960,
                               enable_thinking=True, thinking_token_multiplier=4.0),
    'qwen3:14b':   ModelConfig(temperature=0.7, max_tokens=250, context_window=40960,
                               enable_thinking=True, thinking_token_multiplier=4.0),
    'qwen3:32b':   ModelConfig(temperature=0.7, max_tokens=300, context_window=40960,
                               enable_thinking=True, thinking_token_multiplier=4.0),

    # Phi models (Microsoft)
    'phi3:mini':    ModelConfig(temperature=0.7, max_tokens=120, context_window=128000),
    'phi3:medium':  ModelConfig(temperature=0.7, max_tokens=180, context_window=128000),
    'phi4:latest':  ModelConfig(temperature=0.7, max_tokens=200, context_window=16384),

    # Mistral models
    'mistral:7b':    ModelConfig(temperature=0.7, max_tokens=200, context_window=32000),
    'mixtral:8x7b':  ModelConfig(temperature=0.7, max_tokens=250, context_window=32000),

    # DeepSeek models (thinking-capable)
    'deepseek-r1:7b':  ModelConfig(temperature=0.7, max_tokens=200, context_window=65536,
                                   enable_thinking=True, thinking_token_multiplier=4.0),
    'deepseek-r1:14b': ModelConfig(temperature=0.7, max_tokens=250, context_window=65536,
                                   enable_thinking=True, thinking_token_multiplier=4.0),
    'deepseek-r1:32b': ModelConfig(temperature=0.7, max_tokens=300, context_window=65536,
                                   enable_thinking=True, thinking_token_multiplier=4.0),
}


def _get_env(key: str, default: str = '') -> str:
    """Get environment variable with consistent handling."""
    return os.getenv(key, default).strip()


def _get_secret(section: str, key: str, default: str = '') -> str:
    """
    Get a secret value using the project's secrets pipeline.

    Priority: Doppler -> AWS -> Vault -> Environment -> .env -> default.
    Falls back to plain env var if secrets.py is not available.
    """
    try:
        from utils.secrets import get_secret
        value = get_secret(section, key)
        return value if value else default
    except ImportError:
        pass
    try:
        from penguin_overlord.utils.secrets import get_secret
        value = get_secret(section, key)
        return value if value else default
    except ImportError:
        pass
    # Fallback to plain env var
    env_key = f"{section}_{key}".upper()
    return os.getenv(env_key, os.getenv(key.upper(), default)).strip()


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean."""
    val = _get_env(key, str(default))
    return val.lower() in ('true', '1', 'yes')


def _get_env_float(key: str, default: float = 0.0) -> float:
    """Get environment variable as float."""
    try:
        return float(_get_env(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_env_int(key: str, default: int = 0) -> int:
    """Get environment variable as int."""
    try:
        return int(_get_env(key, str(default)))
    except (ValueError, TypeError):
        return default


def _normalize_ollama_host(host: str, port: str = '') -> str:
    """Normalize Ollama host URL, ensuring scheme and port are present."""
    if not host:
        host = 'http://localhost'
    if not host.startswith(('http://', 'https://')):
        host = f'http://{host}'
    # Only append port if not already in the URL
    host_part = host.split('://', 1)[-1]
    if ':' not in host_part and port:
        host = f'{host}:{port}'
    elif ':' not in host_part:
        host = f'{host}:11434'
    return host


def get_model_config(model_name: str) -> ModelConfig:
    """
    Get configuration for a model, falling back to family defaults.

    Tries exact match first, then prefix match, then returns defaults.
    """
    # Exact match
    if model_name in KNOWN_MODEL_CONFIGS:
        return KNOWN_MODEL_CONFIGS[model_name]

    # Prefix match (e.g., "qwen3:14b-q8_0" matches "qwen3:14b")
    for known, config in KNOWN_MODEL_CONFIGS.items():
        if model_name.startswith(known.split(':')[0]):
            logger.debug(f"Using config from {known} for model {model_name}")
            return config

    # Check for thinking models by name pattern
    is_thinking = any(t in model_name.lower() for t in ['qwen3', 'deepseek-r1'])
    return ModelConfig(
        enable_thinking=is_thinking,
        thinking_token_multiplier=4.0 if is_thinking else 1.0
    )


def _load_feature_config(feature: str, defaults: Dict[str, Any]) -> FeatureConfig:
    """
    Load configuration for a specific feature from environment variables.

    Feature-specific env vars override global defaults.
    Pattern: AI_{FEATURE}_{KEY} overrides AI_DEFAULT_{KEY}
    """
    prefix = f'AI_{feature.upper()}'

    # Determine provider
    provider = _get_env(f'{prefix}_PROVIDER', defaults.get('provider', 'ollama'))

    # Determine model
    model = _get_env(f'{prefix}_MODEL', defaults.get('model', 'gemma3:4b'))

    # Determine Ollama host
    host = _get_env(f'{prefix}_OLLAMA_HOST', '')
    if not host:
        # Try legacy OLLAMA_HOST + OLLAMA_PORT format for backward compat
        host = defaults.get('ollama_host', 'http://localhost:11434')
    host = _normalize_ollama_host(host)

    # Determine Gemini fallback
    gemini_model = _get_env(f'{prefix}_GEMINI_MODEL', defaults.get('gemini_model', 'gemini-2.0-flash'))
    gemini_fallback = _get_env_bool(f'{prefix}_GEMINI_FALLBACK',
                                     defaults.get('gemini_fallback', True))

    # Timeout
    timeout = _get_env_int(f'{prefix}_TIMEOUT', defaults.get('timeout', 30))

    # Feature enabled
    enabled = _get_env_bool(f'{prefix}_ENABLED', defaults.get('enabled', True))

    # Build model config with overrides
    base_config = get_model_config(model)

    # Allow per-feature temperature/token overrides
    temp = _get_env_float(f'{prefix}_TEMPERATURE', 0)
    if temp > 0:
        base_config.temperature = temp
    max_tok = _get_env_int(f'{prefix}_MAX_TOKENS', 0)
    if max_tok > 0:
        base_config.max_tokens = max_tok

    # Global thinking mode override
    global_thinking = _get_env_bool('AI_ENABLE_THINKING_MODE', False)
    if global_thinking:
        base_config.enable_thinking = True
    thinking_mult = _get_env_float('AI_THINKING_TOKEN_MULTIPLIER', 0)
    if thinking_mult > 0:
        base_config.thinking_token_multiplier = thinking_mult

    return FeatureConfig(
        provider=provider,
        model=model,
        ollama_host=host,
        gemini_model=gemini_model,
        gemini_fallback_enabled=gemini_fallback,
        model_config=base_config,
        timeout=timeout,
        enabled=enabled,
    )


@dataclass
class AIConfig:
    """Complete AI configuration for all features."""
    enabled: bool = True
    features: Dict[str, FeatureConfig] = field(default_factory=dict)

    # Queue settings
    max_concurrent_requests: int = 4
    min_delay_between_requests: float = 1.0

    # Retry settings
    max_retries: int = 3
    retry_delay_base: int = 2

    # Reconnection settings
    enable_auto_reconnect: bool = True
    reconnect_interval: int = 60
    max_reconnect_attempts: int = 0  # 0 = unlimited

    # Gemini API key
    gemini_api_key: str = ''


def load_ai_config() -> AIConfig:
    """
    Load the complete AI configuration from environment variables.

    Supports backward-compatible OLLAMA_* env vars as well as
    the new AI_* prefix system for per-feature routing.
    """
    # Global enabled flag
    enabled = _get_env_bool('AI_ENABLED', _get_env_bool('OLLAMA_ENABLED', True))

    # Build global defaults from legacy + new env vars
    legacy_host = _get_env('OLLAMA_HOST', 'http://localhost')
    legacy_port = _get_env('OLLAMA_PORT', '11434')
    legacy_model = _get_env('OLLAMA_MODEL', 'gemma3:4b')

    defaults = {
        'provider': _get_env('AI_DEFAULT_PROVIDER', 'ollama'),
        'model': _get_env('AI_DEFAULT_MODEL', legacy_model),
        'ollama_host': _normalize_ollama_host(
            _get_env('AI_DEFAULT_OLLAMA_HOST', legacy_host),
            legacy_port
        ),
        'gemini_model': _get_env('AI_GEMINI_MODEL', 'gemini-2.0-flash'),
        'gemini_fallback': _get_env_bool('AI_GEMINI_FALLBACK', True),
        'timeout': _get_env_int('AI_DEFAULT_TIMEOUT', 30),
        'enabled': True,
    }

    # Load per-feature configs
    features = {}
    for feature in ALL_FEATURES:
        features[feature] = _load_feature_config(feature, defaults)

    # Queue settings
    max_concurrent = _get_env_int('AI_MAX_CONCURRENT_REQUESTS', 4)
    min_delay = _get_env_float('AI_MIN_DELAY_BETWEEN_REQUESTS', 1.0)

    # Retry settings
    max_retries = _get_env_int('AI_MAX_RETRIES', 3)
    retry_delay_base = _get_env_int('AI_RETRY_DELAY_BASE', 2)

    # Reconnection
    auto_reconnect = _get_env_bool('AI_ENABLE_AUTO_RECONNECT', True)
    reconnect_interval = _get_env_int('AI_RECONNECT_INTERVAL', 60)
    max_reconnect_attempts = _get_env_int('AI_MAX_RECONNECT_ATTEMPTS', 0)

    # Gemini API key - use secrets pipeline (Doppler/AWS/Vault/.env)
    gemini_key = _get_secret('AI', 'GEMINI_API_KEY', default='')
    if not gemini_key:
        gemini_key = _get_secret('GEMINI', 'API_KEY', default='')
    if not gemini_key:
        gemini_key = _get_env('GEMINI_API_KEY', '')

    config = AIConfig(
        enabled=enabled,
        features=features,
        max_concurrent_requests=max_concurrent,
        min_delay_between_requests=min_delay,
        max_retries=max_retries,
        retry_delay_base=retry_delay_base,
        enable_auto_reconnect=auto_reconnect,
        reconnect_interval=reconnect_interval,
        max_reconnect_attempts=max_reconnect_attempts,
        gemini_api_key=gemini_key,
    )

    logger.info(f"AI Config loaded: enabled={enabled}, features={list(features.keys())}")
    for feat, fc in features.items():
        logger.info(
            f"  {feat}: provider={fc.provider}, model={fc.model}, "
            f"host={fc.ollama_host}, gemini_fallback={fc.gemini_fallback_enabled}"
        )

    return config
