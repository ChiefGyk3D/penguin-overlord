# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
AI Manager - Central orchestrator for all AI features in Penguin Overlord.

Routes requests to the correct provider (Ollama/Gemini), model, and server
based on per-feature configuration. Manages the request queue to prevent
overloading servers when multiple features fire simultaneously.

Architecture:
    AIManager
    ├── OllamaProvider (per unique host) - Pooled connections to Ollama servers
    ├── GeminiProvider (shared) - Gemini API fallback
    ├── RequestQueue - Async concurrency control
    └── Feature modules
        ├── ArchRoaster - Arch Linux roasting
        ├── NewsAnalyzer - Article summarization
        ├── CVEAnalyzer - Vulnerability analysis
        └── ModerationAnalyzer - Content moderation (stub)
"""

import logging
from typing import Optional, Dict

from .config import (
    AIConfig, FeatureConfig, load_ai_config,
)
from .ollama_provider import OllamaProvider
from .gemini_provider import GeminiProvider
from .queue import RequestQueue
from .guardrails import Guardrails, GuardrailConfig, GuardrailResult, FEATURE_GUARDRAIL_DEFAULTS
from .features import ArchRoaster, NewsAnalyzer, CVEAnalyzer, ModerationAnalyzer, LegislationAnalyzer

logger = logging.getLogger(__name__)


class AIManager:
    """
    Central AI manager that routes feature requests to the correct providers.

    Supports:
    - Multiple Ollama servers (one provider per unique host)
    - Per-feature model and endpoint routing
    - Gemini fallback when Ollama is unavailable
    - Async request queuing to prevent server overload
    - Thinking model support (Qwen3, DeepSeek-R1)
    - Automatic reconnection for Ollama servers
    - Multi-layer guardrails (content filtering, hallucination detection,
      quality scoring, deduplication, Discord validation)

    Usage:
        manager = AIManager()
        manager.initialize()

        # Use feature modules directly
        roast = await manager.roaster.roast("I use Arch btw", "username")
        summary = await manager.news.summarize("Title", "Content...")
        analysis = await manager.cve.analyze("CVE-2024-12345", "Description...")
        mod_result = await manager.moderation.analyze("message text")
        bill = await manager.legislation.summarize("HR 1234", "Description...")

        # Or use the generic generate method for custom prompts
        result = await manager.generate(
            feature='news',
            prompt="Summarize this...",
            system_prompt="You are a news analyst..."
        )
    """

    def __init__(self, config: Optional[AIConfig] = None):
        """
        Initialize the AI Manager.

        Args:
            config: Optional pre-loaded config. If None, loads from env vars.
        """
        self.config = config or load_ai_config()
        self.enabled = self.config.enabled

        # Provider pools
        self._ollama_providers: Dict[str, OllamaProvider] = {}
        self._gemini_provider: Optional[GeminiProvider] = None
        self._queue: Optional[RequestQueue] = None

        # Guardrails engine
        self._guardrails = Guardrails()
        self._guardrail_configs: Dict[str, GuardrailConfig] = {}

        # Feature modules (initialized after providers connect)
        self._roaster: Optional[ArchRoaster] = None
        self._news: Optional[NewsAnalyzer] = None
        self._cve: Optional[CVEAnalyzer] = None
        self._moderation: Optional[ModerationAnalyzer] = None
        self._legislation: Optional[LegislationAnalyzer] = None

        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize all providers and feature modules.

        Connects to Ollama servers, authenticates Gemini, and sets up
        the request queue. Should be called once at bot startup.

        Returns:
            True if at least one provider is available
        """
        if not self.enabled:
            logger.info("AI system is disabled via configuration")
            return False

        # Set up the request queue
        self._queue = RequestQueue(
            max_concurrent=self.config.max_concurrent_requests,
            min_delay=self.config.min_delay_between_requests,
        )

        # Connect to unique Ollama hosts
        any_ollama_connected = False
        for feature_name, feature_config in self.config.features.items():
            if feature_config.provider == 'ollama' and feature_config.enabled:
                host = feature_config.ollama_host
                if host not in self._ollama_providers:
                    provider = OllamaProvider(
                        host=host,
                        enable_auto_reconnect=self.config.enable_auto_reconnect,
                        reconnect_interval=self.config.reconnect_interval,
                        max_reconnect_attempts=self.config.max_reconnect_attempts,
                        max_retries=self.config.max_retries,
                        retry_delay_base=self.config.retry_delay_base,
                    )
                    if provider.connect():
                        any_ollama_connected = True
                    self._ollama_providers[host] = provider
                    logger.info(
                        f"Ollama provider for {host}: "
                        f"{'connected' if provider.connected else 'unavailable'}"
                    )

        # Set up Gemini fallback
        if self.config.gemini_api_key:
            self._gemini_provider = GeminiProvider(
                api_key=self.config.gemini_api_key,
                max_retries=self.config.max_retries,
                retry_delay_base=self.config.retry_delay_base,
            )
            logger.info(
                f"Gemini fallback: {'available' if self._gemini_provider.is_available else 'unavailable'}"
            )

        # Initialize feature modules (they use self.generate as their generation function)
        self._roaster = ArchRoaster(self.generate)
        self._news = NewsAnalyzer(self.generate)
        self._cve = CVEAnalyzer(self.generate)
        self._moderation = ModerationAnalyzer(self.generate)
        self._legislation = LegislationAnalyzer(self.generate)

        # Load guardrail configs per feature (using defaults, can be overridden via env)
        for feature_name in self.config.features:
            self._guardrail_configs[feature_name] = FEATURE_GUARDRAIL_DEFAULTS.get(
                feature_name, GuardrailConfig()
            )

        self._initialized = True
        any_available = any_ollama_connected or (
            self._gemini_provider and self._gemini_provider.is_available
        )

        if any_available:
            logger.info(
                f"✓ AI Manager initialized: "
                f"{len(self._ollama_providers)} Ollama server(s), "
                f"Gemini {'available' if self._gemini_provider and self._gemini_provider.is_available else 'unavailable'}"
            )
        else:
            logger.warning("⚠ AI Manager initialized but no providers available")

        return any_available

    async def generate(
        self,
        feature: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        skip_guardrails: bool = False,
        **kwargs,
    ) -> Optional[str]:
        """
        Generate text for a specific feature with guardrail protection.

        Routes to the correct provider/model based on feature configuration.
        Falls back to Gemini if the primary Ollama provider is unavailable.
        Applies input sanitization before generation and output guardrails after.

        Args:
            feature: Feature name (roasting, news, cve, moderation, legislation)
            prompt: User prompt
            system_prompt: Optional system context
            temperature: Override temperature (uses feature default if None)
            max_tokens: Override max tokens (uses feature default if None)
            timeout: Override timeout (uses feature default if None)
            skip_guardrails: Bypass output guardrails (for internal/structured outputs)
            **kwargs: Additional generation parameters

        Returns:
            Generated text or None if all providers fail or guardrails block
        """
        if not self.enabled or not self._initialized:
            return None

        # Get feature config
        feature_config = self.config.features.get(feature)
        if not feature_config or not feature_config.enabled:
            logger.debug(f"Feature '{feature}' is disabled or unconfigured")
            return None

        # Apply defaults from feature config
        mc = feature_config.model_config
        temperature = temperature if temperature is not None else mc.temperature
        max_tokens = max_tokens if max_tokens is not None else mc.max_tokens
        timeout = timeout if timeout is not None else feature_config.timeout

        # Input sanitization via guardrails
        guardrail_config = self._guardrail_configs.get(feature, GuardrailConfig())
        if guardrail_config.enable_input_sanitization:
            prompt = self._guardrails.sanitize_input(prompt, guardrail_config.max_input_length)

        # Route through the request queue
        result = await self._queue.submit(
            self._generate_with_fallback,
            feature=feature,
            feature_config=feature_config,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )

        if result is None:
            return None

        # Apply output guardrails
        if not skip_guardrails:
            guardrail_result = self._guardrails.apply(
                text=result,
                config=guardrail_config,
                feature=feature,
                original_prompt=prompt,
            )

            if guardrail_result.blocked:
                logger.warning(
                    f"Guardrails blocked output for '{feature}': "
                    f"{guardrail_result.issues}"
                )
                return None

            if not guardrail_result.passed and guardrail_config.enable_strict_retry:
                # Retry once with strict-mode prompt prefix
                logger.warning(
                    f"Guardrails flagged {len(guardrail_result.issues)} issue(s) "
                    f"for '{feature}': {guardrail_result.issues} — retrying strict"
                )
                strict_prefix = self._guardrails.get_strict_prompt_prefix()
                strict_prompt = strict_prefix + prompt

                retry_result = await self._queue.submit(
                    self._generate_with_fallback,
                    feature=feature,
                    feature_config=feature_config,
                    prompt=strict_prompt,
                    system_prompt=system_prompt,
                    temperature=max(0.1, temperature - 0.2),  # Lower temp for retry
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **kwargs,
                )

                if retry_result:
                    retry_guardrail = self._guardrails.apply(
                        text=retry_result,
                        config=guardrail_config,
                        feature=feature,
                        original_prompt=prompt,
                    )
                    if retry_guardrail.passed or not retry_guardrail.blocked:
                        logger.info(
                            f"Strict retry improved output for '{feature}' "
                            f"(issues: {len(retry_guardrail.issues)})"
                        )
                        return retry_guardrail.text

                # Strict retry failed or didn't improve — use original cleaned text
                # if it wasn't blocked (just had warnings)
                if not guardrail_result.blocked:
                    logger.info(
                        f"Using original output for '{feature}' despite "
                        f"{len(guardrail_result.issues)} guardrail issue(s)"
                    )
                    return guardrail_result.text
                return None

            if guardrail_result.was_modified:
                logger.debug(
                    f"Guardrails cleaned output for '{feature}': "
                    f"{guardrail_result.issues}"
                )

            return guardrail_result.text

        return result

    async def _generate_with_fallback(
        self,
        feature: str,
        feature_config: FeatureConfig,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
        timeout: int = 30,
        **kwargs,
    ) -> Optional[str]:
        """
        Generate text with provider fallback logic.

        Tries the primary provider first. If it fails and Gemini fallback
        is enabled, tries Gemini as a backup.
        """
        mc = feature_config.model_config
        result = None

        # Try primary provider
        if feature_config.provider == 'ollama':
            provider = self._ollama_providers.get(feature_config.ollama_host)
            if provider:
                result = await provider.generate(
                    model=feature_config.model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=mc.top_p,
                    top_k=mc.top_k,
                    context_window=mc.context_window,
                    enable_thinking=mc.enable_thinking,
                    thinking_token_multiplier=mc.thinking_token_multiplier,
                    timeout=timeout,
                )
            else:
                logger.warning(
                    f"No Ollama provider for {feature_config.ollama_host} "
                    f"(feature: {feature})"
                )

        elif feature_config.provider == 'gemini':
            if self._gemini_provider and self._gemini_provider.is_available:
                result = await self._gemini_provider.generate(
                    model=feature_config.gemini_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=mc.top_p,
                    timeout=timeout,
                )

        # Fallback to Gemini if primary failed
        if result is None and feature_config.gemini_fallback_enabled:
            if (self._gemini_provider and self._gemini_provider.is_available
                    and feature_config.provider != 'gemini'):
                logger.info(
                    f"Primary provider failed for '{feature}', "
                    f"falling back to Gemini ({feature_config.gemini_model})"
                )
                result = await self._gemini_provider.generate(
                    model=feature_config.gemini_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=mc.top_p,
                    timeout=timeout,
                )

        if result is None:
            logger.warning(f"All providers failed for feature '{feature}'")

        return result

    # ── Feature module accessors ─────────────────────────────────────────

    @property
    def roaster(self) -> Optional[ArchRoaster]:
        """Access the Arch Roaster feature."""
        return self._roaster

    @property
    def news(self) -> Optional[NewsAnalyzer]:
        """Access the News Analyzer feature."""
        return self._news

    @property
    def cve(self) -> Optional[CVEAnalyzer]:
        """Access the CVE Analyzer feature."""
        return self._cve

    @property
    def moderation(self) -> Optional[ModerationAnalyzer]:
        """Access the Moderation Analyzer feature."""
        return self._moderation

    @property
    def legislation(self) -> Optional[LegislationAnalyzer]:
        """Access the Legislation Analyzer feature."""
        return self._legislation

    @property
    def guardrails(self) -> Guardrails:
        """Access the guardrails engine for manual use."""
        return self._guardrails

    @property
    def queue_stats(self) -> dict:
        """Get request queue statistics."""
        if self._queue:
            return self._queue.stats
        return {}

    @property
    def provider_status(self) -> dict:
        """Get status of all providers."""
        status = {}
        for host, provider in self._ollama_providers.items():
            status[f'ollama:{host}'] = {
                'connected': provider.connected,
                'models': provider.available_models[:5],  # First 5
            }
        if self._gemini_provider:
            status['gemini'] = {
                'connected': self._gemini_provider.connected,
            }
        return status

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific feature is enabled and has a working provider."""
        if not self.enabled or not self._initialized:
            return False
        fc = self.config.features.get(feature)
        if not fc or not fc.enabled:
            return False

        # Check if the assigned provider is available
        if fc.provider == 'ollama':
            provider = self._ollama_providers.get(fc.ollama_host)
            if provider and provider.is_available:
                return True
        elif fc.provider == 'gemini':
            if self._gemini_provider and self._gemini_provider.is_available:
                return True

        # Gemini fallback counts
        if fc.gemini_fallback_enabled and self._gemini_provider and self._gemini_provider.is_available:
            return True

        return False


# ── Global singleton ──────────────────────────────────────────────────────

_ai_manager: Optional[AIManager] = None


def get_ai_manager() -> AIManager:
    """
    Get or create the global AIManager singleton.

    The manager is created and initialized on first call.
    Subsequent calls return the same instance.

    Returns:
        Initialized AIManager instance
    """
    global _ai_manager
    if _ai_manager is None:
        _ai_manager = AIManager()
        _ai_manager.initialize()
    return _ai_manager
